"""Fetch daily PyPI download counts from pypistats.org and write data.js for dashboard.html.

pypistats keeps 180 days of daily counts. Mirror downloads are excluded.
"""

import json
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# Category order fixes each category's colour in the dashboard (8 at most);
# append categories, do not reorder them.
PACKAGES = {
    "構造と対称性": ["pymatgen", "ase", "spglib", "moyopy", "seekpath"],
    "フォノン": ["phonopy", "phono3py", "hiphive"],
    "ワークフローと後処理": ["aiida-core", "atomate2", "lobsterpy"],
    "機械学習ポテンシャル": [
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
    ],
    "分子動力学": ["openmm", "MDAnalysis"],
}
API = "https://pypistats.org/api/packages/{name}/overall?mirrors=false"
OUTPUT = Path(__file__).parent / "data.js"
REQUEST_INTERVAL_S = 2.0


def main() -> None:
    category_of = {
        name: category for category, names in PACKAGES.items() for name in names
    }
    daily = {}
    for name in category_of:
        daily[name] = fetch_daily(name)
        print(f"{name}: {len(daily[name])} days, {sum(daily[name].values())} downloads")
        time.sleep(REQUEST_INTERVAL_S)

    first = min(min(counts) for counts in daily.values())
    last = max(max(counts) for counts in daily.values())
    dates = [
        (first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)
    ]
    payload = {
        "fetched": date.today().isoformat(),
        "dates": dates,
        "categories": list(PACKAGES),
        "packages": [
            {
                "name": name,
                "category": category_of[name],
                # pypistats omits days without downloads
                "downloads": [
                    daily[name].get(date.fromisoformat(d), 0) for d in dates
                ],
            }
            for name in category_of
        ],
    }
    OUTPUT.write_text(
        f"window.PYPI_DATA = {json.dumps(payload, ensure_ascii=False)};\n"
    )
    print(f"wrote {OUTPUT} ({dates[0]} to {dates[-1]})")


def fetch_daily(name: str) -> dict[date, int]:
    request = urllib.request.Request(
        API.format(name=name.lower()), headers={"User-Agent": "pypi-stats-dashboard"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        rows = json.load(response)["data"]
    return {date.fromisoformat(row["date"]): row["downloads"] for row in rows}


if __name__ == "__main__":
    main()
