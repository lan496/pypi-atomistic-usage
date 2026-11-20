"""Collect PyPI download counts and write docs/data.js for docs/index.html.

All download counts come from ClickPy (https://clickpy.clickhouse.com), ClickHouse's
public copy of the PyPI download logs and metadata, queried through its read-only
demo user. The queries follow the materialized views of the ClickPy project
(https://github.com/ClickHouse/clickpy, Apache-2.0).

The package set is the curated SEEDS plus the most-downloaded packages that
depend on them, found by walking declared dependencies recursively.

For each package the page gets
- daily downloads over the last DAILY_DAYS days and monthly downloads over the
  whole history, each split into all (mirrors excluded), Linux, and macOS + Windows;
- the share of the last AUTOMATION_DAYS days' downloads that came from CI runs
  and from bulk rebuilds of one pinned environment;
- the GitHub owner (for the avatar) and the date of the first release, from PyPI.

The demo user may run 60 queries and 600 s of execution time per hour; a run
uses about 20 queries and 5 minutes. A refused run succeeds after the hour turns.
"""

import gzip
import http.client
import json
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# Category order fixes each category's colour in the dashboard (--c1 to --c8);
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
        # best-of-atomistic-machine-learning: visualization
        "zndraw",
        "atomvision",
        "crystal-toolkit",
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
        # best-of-atomistic-machine-learning: ml-iap and uip
        "python-ace",
        "megnet",
        "sgdml",
        "pyNNsMD",
        "torchani",
        "ccs_fit",
        "kliff",
        "pyxtal_ff",
        "uf3",
        "MEGNetSparse",
        "calorine",
        "apax",
        "mlipx",
        "autoplex",
        "graph-pes",
        "metatrain",
        "matcalc",
        "janus-core",
        "aiida-mlip",
        "m3gnet",
        "pet-mad",
    ],
    "Simulation engines and MD": [
        "openmm",
        "MDAnalysis",
        # Python-installable engines tracked by atomistic.software
        "pyscf",
        "gpaw",
        "lammps",
        "BoltzTraP2",
        "torchmd",
        "xtb",
        # best-of-atomistic-machine-learning: md
        "jax-md",
        "mlcolvar",
    ],
    # The three categories below hold the rest of
    # best-of-atomistic-machine-learning (JuDFTteam), grouped from its categories.
    "Representations and general ML tools": [
        # rep-eng
        "cmlkit",
        "amp-atomistics",
        "CBFV",
        "dscribe",
        "catlearn",
        "benchml",
        "skipatom",
        "glasspy",
        "pysipfenn",
        "chemml",
        "ElementEmbeddings",
        "pdyna",
        # rep-learn
        "schnetpack",
        "crabnet",
        "e3nn",
        "e3nn-jax",
        "dgl",
        "dgllife",
        "kgcnn",
        "escnn",
        "atom2vec",
        "dive-into-graphs",
        "faenet",
        "xtal2png",
        # general-tool
        "skmatter",
        "maml",
        "automatminer",
        "matminer",
        "jarvis-tools",
        "xenonpy",
        "qml",
        "deepchem",
        "rdkit",
        "mlatom",
        "molfeat",
        "atomai",
        # data-structures
        "metatensor",
        "dpdata",
        "mp-pyrho",
        # math
        "sphericart",
        "gpax",
        "kfac-jax",
        "cuequivariance",
        "openequivariance",
        # xai and unsupervised
        "exmol",
        "dadapy",
        "mat_discover",
        "pumml",
    ],
    "Datasets and benchmarks": [
        "matbench",
        "matbench-discovery",
        "ffonons",
        "garden-ai",
        "ml-peg",
        "mpcontribs-client",
        "atom3d",
        "optimade",
        "load-atoms",
        "obelix-data",
        "matpes",
        "mpds_client",
        "openqdc",
    ],
    "Generative, active-learning and other ML": [
        # active-learning
        "flare_pp",
        "dpgen",
        "ipsuite",
        "Bgolearn",
        # materials-discovery
        "aalto-boss",
        "agox",
        "smact",
        "care-crn",
        # generative
        "molecule-generation",
        "synspace",
        "gt4sd",
        "moftransformer",
        "simgen",
        "slices",
        # language-models
        "paper-qa",
        "nlcc",
        "gptchem",
        "chemcrow",
        "chemdataextractor",
        "chemnlp",
        "chatmof",
        "atomgpt",
        "chembench",
        # ml-dft, ml-esm, ml-wft
        "ciderpress",
        "dptb",
        "deeperwin",
        "deepqmc",
    ],
}
# General-purpose seeds whose dependents are mostly outside atomistic simulation;
# the dependents walk does not start from them.
NO_WALK = {
    "rdkit",
    "dgl",
    "deepchem",
    "e3nn",
    "e3nn-jax",
    "escnn",
    "kfac-jax",
    "paper-qa",
    "cuequivariance",
}
# Categories of dependents by what they do, keyed by normalized name; a dependent
# missing here inherits the category of the package it was found through, which
# is often wrong (sumo plots band structures but is found through phonopy).
# Review new dependents after each refresh and add them here.
DEPENDENT_CATEGORIES = {
    **dict.fromkeys(
        [
            "structuregraph-helpers", "pymatgen-core", "irrep", "irreptables",
            "spgrep", "matid", "molify", "robocrys",
        ],
        "Structure and symmetry",
    ),
    **dict.fromkeys(["euphonic", "symfc"], "Phonons"),
    **dict.fromkeys(
        [
            # analysis, plotting and property post-processing
            "sumo", "easyunfold", "amset", "tb2j", "dara-xrd", "xraylarch", "larixite",
            "pymatgen-analysis-alloys", "pymatgen-analysis-defects",
            "pymatgen-analysis-diffusion",
            # defects and calculation set-up
            "doped", "pydefect", "shakenbreak", "vise", "pymatgen-io-validation",
            # workflow managers
            "quacc", "ai2-kit",
            # MDAnalysis plugins
            "mdahole2", "pathsimanalysis", "prolif", "sqq",
        ],
        "Workflows and post-processing",
    ),
    **dict.fromkeys(["aenet-gpr", "neptrainkit"], "Machine-learning potentials"),
    **dict.fromkeys(
        ["abtem", "sella", "matscipy", "icet", "clease", "kups", "asi4py", "carcara"],
        "Simulation engines and MD",
    ),
    **dict.fromkeys(["element-coder", "quests"], "Representations and general ML tools"),
    **dict.fromkeys(
        ["mp-api", "emmet-core", "emmet-api", "emmet-builders", "aflow", "ase-db-backends", "molid"],
        "Datasets and benchmarks",
    ),
    **dict.fromkeys(
        ["chemeleon-dng", "porran", "pormake", "reaction-network"],
        "Generative, active-learning and other ML",
    ),
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
N_DEPENDENTS = 60
# A level far beyond the few thousand dependents the walk finds means a
# general-purpose seed, whose dependents would not fit one query; add it to
# NO_WALK. The query returns at most one row more than this.
MAX_FRONTIER = 5000
DAILY_DAYS = 180
AUTOMATION_DAYS = 28
# Downloads of one version on one day from one identical environment (installer,
# Python, OS, glibc, country) that count as a bulk rebuild of a pinned
# environment rather than many users. The share flagged barely moves between
# 1,000 and 10,000.
BULK_MIN = 3000
# Raw download rows per automation query, so that each stays well under the
# demo user's 60 s limit per query.
AUTOMATION_BATCH_ROWS = 4_000_000
# Installers that copy PyPI wholesale; pypistats excludes the same ones.
MIRRORS = ["bandersnatch", "z3c.pypimirror", "Artifactory", "devpi", "Nexus"]
PYPI = "https://pypi.org/pypi/{key}/json"
# The demo user stops reading after 10^9 rows and by default returns what it has
# read as if complete; read_overflow_mode=throw makes such a query fail instead.
CLICKPY = "https://sql-clickhouse.clickhouse.com/?user=demo&read_overflow_mode=throw"
OUTPUT = Path(__file__).parent / "docs" / "data.js"
PYPI_INTERVAL_S = 0.3
ATTEMPTS = 4


def main() -> None:
    seeds = seed_packages()
    dependents = find_dependents(seeds)
    print(f"{len(dependents)} packages depend on the {len(seeds)} seeds")
    kept = dict(seeds)
    for key in rank_by_downloads(list(dependents))[:N_DEPENDENTS]:
        kept[key] = dependents[key]
    write_data(kept)


def seed_packages() -> dict[str, dict]:
    seeds = {}
    for category, names in SEEDS.items():
        for name in names:
            key = normalize(name)
            if key in seeds:
                raise ValueError(f"{name} is listed twice in SEEDS")
            seeds[key] = {"name": name, "category": category, "via": None}
    for key, category in DEPENDENT_CATEGORIES.items():
        if key != normalize(key) or category not in SEEDS:
            raise ValueError(f"DEPENDENT_CATEGORIES: bad entry {key!r}: {category!r}")
    return seeds


def write_data(packages: dict[str, dict]) -> None:
    keys = sorted(packages)
    # PyPI first: a failure there then costs none of the ClickPy quota
    metas = {}
    for key in keys:
        metas[key] = fetch_pypi(key)
        time.sleep(PYPI_INTERVAL_S)
    last = date.fromisoformat(clickpy("SELECT max(date) AS d FROM pypi.pypi_downloads_per_day")[0]["d"])
    first = last - timedelta(days=DAILY_DAYS - 1)
    dates = [first + timedelta(days=i) for i in range(DAILY_DAYS)]
    daily = fetch_series(keys, "date", first, last)
    monthly = fetch_series(keys, "toStartOfMonth(date)", date(2000, 1, 1), last)
    months = month_range(min(m for series in monthly.values() for m in series), last)
    pypi_monthly = fetch_pypi_total(months, last)
    automation = fetch_automation(keys, daily, last)

    rows = []
    for key in keys:
        info = packages[key]
        meta = metas[key]
        rows.append({
            "name": info["name"],
            "category": info["category"],
            "via": info["via"],
            "owner": GITHUB_OWNERS.get(key) or meta["owner"],
            "since": meta["since"],
            "daily": {
                os: [daily[key].get(d.isoformat(), {}).get(os, 0) for d in dates]
                for os in ("all", "linux", "desktop")
            },
            # downloads per day within each month; the last month may be partial
            "monthly": {
                os: [
                    round(monthly[key].get(m, {}).get(os, 0) / days_counted(m, last), 1)
                    for m in months
                ]
                for os in ("all", "linux", "desktop")
            },
            **automation.get(key, {"ci": None, "bulk": None}),
        })
        print(f"{info['name']}: owner {rows[-1]['owner']}, first release {meta['since']}")

    payload = {
        "fetched": date.today().isoformat(),
        "dates": [d.isoformat() for d in dates],
        "months": [m[:7] for m in months],
        "automation_days": AUTOMATION_DAYS,
        "bulk_min": BULK_MIN,
        "categories": list(SEEDS),
        "pypi_monthly": pypi_monthly,
        "packages": rows,
    }
    OUTPUT.write_text(f"window.PYPI_DATA = {json.dumps(payload, separators=(',', ':'))};\n")
    print(f"wrote {OUTPUT}: {len(rows)} packages, {dates[0]} to {dates[-1]}, {months[0][:7]} on")


def fetch_series(keys: list[str], period: str, first: date, last: date) -> dict[str, dict]:
    """{key: {period start: {all, linux, desktop}}} summed over each period.

    "all" excludes mirror installers; the per-system view cannot, so mirrors
    (which report no system) stay out of Linux and macOS + Windows by themselves.
    """
    where = f"project IN {sql_tuple(keys)} AND date BETWEEN '{first}' AND '{last}'"
    series = {key: {} for key in keys}
    # One row per project, since the demo user gets at most 10,000 result rows.
    for row in clickpy(f"""
        SELECT project, groupArray((p, 'all', n)) AS points FROM (
            SELECT project, toString({period}) AS p, sum(count) AS n
            FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type
            WHERE {where} AND installer NOT IN {sql_tuple(MIRRORS)}
            GROUP BY project, p
        ) GROUP BY project
        UNION ALL
        SELECT project, groupArray((p, os, n)) AS points FROM (
            SELECT project, toString({period}) AS p,
                   multiIf(system = 'Linux', 'linux', 'desktop') AS os, sum(count) AS n
            FROM pypi.pypi_downloads_per_day_by_version_by_system
            WHERE {where} AND system IN ('Linux', 'Darwin', 'Windows')
            GROUP BY project, p, os
        ) GROUP BY project
    """):
        for p, os, n in row["points"]:
            series[row["project"]].setdefault(p, {})[os] = int(n)
    return series


def fetch_pypi_total(months: list[str], last: date) -> list[float]:
    """Downloads per day of all of PyPI within each month, as a baseline.

    Only the per-month view is small enough to sum over every project within the
    demo user's read limit; it includes mirrors (about 0.3% of PyPI downloads in
    a month sampled) and has no split by system.
    """
    rows = clickpy(f"""
        SELECT toString(month) AS m, sum(count) AS n FROM pypi.pypi_downloads_per_month
        WHERE month BETWEEN '{months[0]}' AND '{last}' GROUP BY m
    """)
    totals = {row["m"]: int(row["n"]) for row in rows}
    return [round(totals.get(m, 0) / days_counted(m, last), 1) for m in months]


def fetch_automation(keys: list[str], daily: dict[str, dict], last: date) -> dict[str, dict]:
    """Shares of CI and bulk-rebuild downloads over the last AUTOMATION_DAYS days.

    These need the raw download rows, which cost a query per few million
    downloads, so packages are batched by their recent download count.
    """
    first = last - timedelta(days=AUTOMATION_DAYS - 1)
    recent = {
        key: sum(v.get("all", 0) for d, v in daily[key].items() if d >= first.isoformat())
        for key in keys
    }
    batches, batch, rows = [], [], 0
    for key in sorted(keys, key=recent.get):
        if batch and rows + recent[key] > AUTOMATION_BATCH_ROWS:
            batches.append(batch)
            batch, rows = [], 0
        batch.append(key)
        rows += recent[key]
    batches.append(batch)

    shares = {}
    for i, batch in enumerate(batches, 1):
        print(f"automation batch {i}/{len(batches)}: {len(batch)} packages")
        # A cell is one day of one version's downloads from one identical environment.
        for row in clickpy(f"""
            SELECT project, sum(cell) AS n,
                   sumIf(cell, flag = 'true') AS n_ci,
                   sumIf(cell, flag != 'true' AND cell >= {BULK_MIN}) AS n_bulk
            FROM (
                SELECT project, ci AS flag, count() AS cell FROM pypi.pypi
                WHERE project IN {sql_tuple(batch)}
                  AND date BETWEEN '{first}' AND '{last}'
                  AND installer NOT IN {sql_tuple(MIRRORS)}
                  AND filename NOT LIKE '%.metadata'
                GROUP BY project, date, installer, python_minor, system,
                         country_code, flag, libc.version, version
            )
            GROUP BY project
        """):
            n = int(row["n"])
            shares[row["project"]] = {
                "ci": round(int(row["n_ci"]) / n, 3),
                "bulk": round(int(row["n_bulk"]) / n, 3),
            }
    return shares


def fetch_pypi(key: str) -> dict:
    """GitHub owner of the repository, if any, and the date of the first upload."""
    try:
        meta = json.loads(http_get(PYPI.format(key=key)))
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        return {"owner": None, "since": None}
    info = meta["info"]
    uploads = [f["upload_time"] for files in meta["releases"].values() for f in files]
    urls = list((info["project_urls"] or {}).values()) + [info["home_page"] or ""]
    owner = None
    for url in urls:
        match = re.search(r"github\.com/([A-Za-z0-9-]+)/[A-Za-z0-9_.-]+", url)
        if match and match.group(1).lower() != "sponsors":
            owner = match.group(1)
            break
    return {"owner": owner, "since": min(uploads)[:10] if uploads else None}


def find_dependents(seeds: dict[str, dict]) -> dict[str, dict]:
    """Walk dependents breadth-first; each takes its category from
    DEPENDENT_CATEGORIES, or else inherits the category of its parent."""
    known = dict(seeds)
    found = {}
    frontier = sorted(key for key in seeds if key not in NO_WALK)
    depth = 0
    while frontier:
        depth += 1
        rows = clickpy(dependents_sql(frontier))
        if len(rows) > MAX_FRONTIER:
            raise RuntimeError(
                f"more than {MAX_FRONTIER} dependents at depth {depth}: a seed is "
                "too general for the walk; add it to NO_WALK"
            )
        level = {}
        for row in rows:
            key = row["key"]
            if key in known:
                continue
            parent = known[min(row["parents"])]
            level[key] = {
                "name": row["name"],
                "category": DEPENDENT_CATEGORIES.get(key, parent["category"]),
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
        WHERE project IN {sql_tuple(keys)} AND date > today() - {DAILY_DAYS}
        GROUP BY project ORDER BY sum(count) DESC LIMIT {N_DEPENDENTS}
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
        LIMIT {MAX_FRONTIER + 1}
    """


def clickpy(sql: str) -> list[dict]:
    body = http_get(CLICKPY, data=f"{sql} FORMAT JSONEachRow".encode())
    rows = [json.loads(line) for line in body.splitlines() if line]
    # an error after the first rows arrives as a last row in place of data
    if rows and "exception" in rows[-1]:
        raise RuntimeError(f"ClickPy query failed: {rows[-1]['exception']}")
    return rows


def http_get(url: str, data: bytes | None = None) -> bytes:
    request = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "pypi-atomistic-usage", "Accept-Encoding": "gzip"},
    )
    # Both PyPI and the shared ClickPy endpoint refuse requests now and then.
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body
        except urllib.error.HTTPError as error:
            detail = error.read()
            if error.headers.get("Content-Encoding") == "gzip":
                detail = gzip.decompress(detail)
            detail = detail[:300].decode(errors="replace")
            print(f"{url} failed ({error.code}): {detail}")
            # a query over the read limit fails the same way every time
            if error.code == 404 or "TOO_MANY_ROWS" in detail or attempt == ATTEMPTS - 1:
                raise
            time.sleep(10 * 2**attempt)
        except (urllib.error.URLError, http.client.IncompleteRead) as error:
            # dropped connections, which a quick retry usually gets past
            print(f"{url} failed: {error!r}")
            if attempt == ATTEMPTS - 1:
                raise
            time.sleep(2)
    raise AssertionError("unreachable")


def month_range(first: str, last: date) -> list[str]:
    months = []
    m = date.fromisoformat(first)
    while m <= last:
        months.append(m.isoformat())
        m = (m + timedelta(days=32)).replace(day=1)
    return months


def days_counted(month: str, last: date) -> int:
    """Days of the month covered by the data."""
    start = date.fromisoformat(month)
    end = min((start + timedelta(days=32)).replace(day=1) - timedelta(days=1), last)
    return (end - start).days + 1


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
