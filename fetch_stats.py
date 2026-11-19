"""Collect daily PyPI download counts and write docs/data.js for docs/index.html.

Download counts come from pypistats.org, which keeps 180 days of daily counts
without mirror downloads. Its per-operating-system series is used, so that
Linux (where CI and other automated installs run) can be told from macOS and
Windows.

The package set is the curated SEEDS plus the most-downloaded packages that
depend on them. The dependents are found by walking declared dependencies
recursively in ClickPy (https://clickpy.clickhouse.com), ClickHouse's public
copy of the PyPI metadata.
"""

import json
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# Category order fixes each category's colour in the dashboard (8 at most);
# append categories, do not reorder them.
SEEDS = {
    "Structure and symmetry": [
        "pymatgen",
        "ase",
        "spglib",
        "moyopy",
        "seekpath",
        "pyxtal",
    ],
    "Phonons": ["phonopy", "phono3py", "hiphive"],
    "Workflows and post-processing": [
        "aiida-core",
        "atomate2",
        "lobsterpy",
        "pymatviz",
        "pyiron",
    ],
    "Machine-learning potentials": [
        "mace-torch",
        "chgnet",
        "mattersim",
        "sevenn",
        "deepmd-kit",
        "quippy-ase",
        "upet",
        "matgl",
        "nequip",
        "torch-dftd",
        "torch-sim-atomistic",
        "nvalchemi-toolkit-ops",
        "matbench-discovery",
        # further potentials on the Matbench Discovery leaderboard
        "fairchem-core",
        "orb-models",
        "alignn",
        "tensorpotential",
        "nequip-allegro",
        "nequix",
        "matris",
        "tace",
        "eqnorm",
    ],
    "Molecular dynamics": ["openmm", "MDAnalysis"],
}
# GitHub owners of packages whose PyPI metadata links no GitHub repository.
# ase and hiphive are hosted on GitLab and get no avatar.
GITHUB_OWNERS = {
    "moyopy": "spglib",
    "quippy-ase": "libAtoms",
    "matgl": "materialsvirtuallab",
    "torch-dftd": "pfnet-research",
    "nvalchemi-toolkit-ops": "NVIDIA",
    "openmm": "openmm",
}
N_PACKAGES = 100
RANKING_DAYS = 180
PYPISTATS = "https://pypistats.org/api/packages/{key}/system"
PYPI = "https://pypi.org/pypi/{key}/json"
CLICKPY = "https://sql-clickhouse.clickhouse.com/?user=demo"
OUTPUT = Path(__file__).parent / "docs" / "data.js"
REQUEST_INTERVAL_S = 2.0
ATTEMPTS = 4


def main() -> None:
    seeds = seed_packages()
    dependents = find_dependents(seeds)
    print(f"{len(dependents)} packages depend on the {len(seeds)} seeds")
    ranked = rank_by_downloads(list(dependents))
    kept = dict(seeds)
    for key in ranked[: N_PACKAGES - len(seeds)]:
        kept[key] = dependents[key]
    write_data(kept)


def seed_packages() -> dict[str, dict]:
    return {
        normalize(name): {"name": name, "category": category, "via": None}
        for category, names in SEEDS.items()
        for name in names
    }


def write_data(packages: dict[str, dict]) -> None:
    daily = {}
    owners = {}
    for key, info in packages.items():
        daily[key] = fetch_daily(key)
        owners[key] = GITHUB_OWNERS.get(key) or fetch_github_owner(key)
        total = sum(sum(day.values()) for day in daily[key].values())
        print(f"{info['name']}: {total} downloads, owner {owners[key]}")
        time.sleep(REQUEST_INTERVAL_S)

    first = min(min(days) for days in daily.values())
    last = max(max(days) for days in daily.values())
    dates = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    payload = {
        "fetched": date.today().isoformat(),
        "dates": [d.isoformat() for d in dates],
        "categories": list(SEEDS),
        "packages": [
            {
                "name": info["name"],
                "category": info["category"],
                "via": info["via"],
                "owner": owners[key],
                # pypistats omits days without downloads
                "all": [sum(daily[key].get(d, {}).values()) for d in dates],
                "linux": [daily[key].get(d, {}).get("Linux", 0) for d in dates],
                "desktop": [
                    daily[key].get(d, {}).get("Darwin", 0)
                    + daily[key].get(d, {}).get("Windows", 0)
                    for d in dates
                ],
            }
            for key, info in packages.items()
        ],
    }
    OUTPUT.write_text(f"window.PYPI_DATA = {json.dumps(payload)};\n")
    print(f"wrote {OUTPUT}: {len(packages)} packages, {dates[0]} to {dates[-1]}")


def fetch_daily(key: str) -> dict[date, dict[str, int]]:
    """Downloads per day by operating system (Linux, Darwin, Windows, other, null)."""
    daily = {}
    for row in json.loads(http_get(PYPISTATS.format(key=key)))["data"]:
        day = daily.setdefault(date.fromisoformat(row["date"]), {})
        day[row["category"]] = row["downloads"]
    return daily


def fetch_github_owner(key: str) -> str | None:
    """GitHub organisation or user that hosts the package's repository, if any."""
    info = json.loads(http_get(PYPI.format(key=key)))["info"]
    urls = list((info["project_urls"] or {}).values()) + [info["home_page"] or ""]
    for url in urls:
        match = re.search(r"github\.com/([A-Za-z0-9-]+)/[A-Za-z0-9_.-]+", url)
        if match and match.group(1).lower() != "sponsors":
            return match.group(1)
    return None


def find_dependents(seeds: dict[str, dict]) -> dict[str, dict]:
    """Walk dependents breadth-first; each inherits the category of its parent."""
    known = dict(seeds)
    found = {}
    frontier = sorted(seeds)
    depth = 0
    while frontier:
        depth += 1
        level = {}
        for row in clickpy(dependents_sql(frontier)):
            key = row["key"]
            if key in known:
                continue
            parent = known[min(row["parents"])]
            level[key] = {
                "name": row["name"],
                "category": parent["category"],
                "via": parent["name"],
            }
        print(f"depth {depth}: {len(level)} new dependents")
        known.update(level)
        found.update(level)
        frontier = sorted(level)
    return found


def rank_by_downloads(keys: list[str]) -> list[str]:
    rows = clickpy(
        f"""
        SELECT project FROM pypi.pypi_downloads_per_day
        WHERE project IN {sql_tuple(keys)} AND date > today() - {RANKING_DAYS}
        GROUP BY project ORDER BY sum(count) DESC LIMIT {N_PACKAGES}
        """
    )
    return [row["project"] for row in rows]


def dependents_sql(frontier: list[str]) -> str:
    """Packages whose latest release requires a frontier package outside any extra."""
    dep_name = norm_sql("extract(d, '^[A-Za-z0-9._-]+')")
    return f"""
        SELECT {norm_sql("name")} AS key, name,
               arrayFilter(d -> d IN {sql_tuple(frontier)}, deps) AS parents
        FROM (
            SELECT name,
                   arrayDistinct(arrayMap(d -> {dep_name}, arrayFilter(
                       d -> NOT match(d, 'extra\\\\s*=='),
                       arrayFlatten(groupArray(requires_dist))))) AS deps
            FROM pypi.projects
            WHERE (name, version) IN (
                SELECT name, argMax(version, upload_time) FROM pypi.projects
                WHERE name IN (
                    SELECT DISTINCT name FROM pypi.projects
                    WHERE arrayExists(d -> {dep_name} IN {sql_tuple(frontier)}, requires_dist)
                )
                GROUP BY name
            )
            GROUP BY name
        )
        WHERE length(parents) > 0
    """


def clickpy(sql: str) -> list[dict]:
    body = http_get(CLICKPY, data=f"{sql} FORMAT JSONEachRow".encode())
    return [json.loads(line) for line in body.splitlines() if line]


def http_get(url: str, data: bytes | None = None) -> bytes:
    request = urllib.request.Request(
        url, data=data, headers={"User-Agent": "pypi-stats-dashboard"}
    )
    # Both pypistats and the shared ClickPy endpoint refuse requests now and then.
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            detail = error.read()[:300].decode(errors="replace")
            print(f"{url} failed ({error.code}): {detail}")
            if error.code == 404 or attempt == ATTEMPTS - 1:
                raise
            time.sleep(10 * 2**attempt)
    raise AssertionError("unreachable")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def norm_sql(expr: str) -> str:
    return f"lower(replaceRegexpAll({expr}, '[-_.]+', '-'))"


def sql_tuple(values: list[str]) -> str:
    """A literal set for IN, which ClickHouse hashes."""
    for value in values:
        if "'" in value or "\\" in value:
            raise ValueError(f"unsafe SQL literal: {value!r}")
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


if __name__ == "__main__":
    main()
