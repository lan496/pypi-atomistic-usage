# PyPI download counts of atomistic-simulation packages

How much are atomistic-simulation Python packages used, judged by the daily
download counts on pypistats.org? `fetch_stats.py` pulls the 180-day daily
series (mirrors excluded) for 25 packages in five categories and writes
`docs/data.js`; `docs/index.html` reads it and shows a 7-day-mean line chart
and a ranked table, filterable by period and category. The page is deployed to
GitHub Pages by `.github/workflows/pages.yml` on every push that touches
`docs/`, and also opens straight from disk. Rerun `python3 fetch_stats.py` to
refresh the data, and edit `PACKAGES` there to change the package set. In the snapshot of 2026-11-19
(2026-05-22 to 2026-11-18) the 180-day totals are led by ase (11.8M), spglib
(10.8M), seekpath (6.1M), moyopy (5.2M) and pymatgen (5.0M); the largest
machine-learning-potential packages are nvalchemi-toolkit-ops (1.7M) and
mace-torch (0.65M). Counts include CI and other automated installs, and
several packages show multi-day bursts of that kind, so they measure installs
rather than users.
