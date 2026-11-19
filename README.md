# PyPI download counts of atomistic-simulation packages

How much are atomistic-simulation Python packages used, judged by the daily
download counts on pypistats.org? `fetch_stats.py` starts from a curated list
of 27 packages in five categories (`SEEDS`), adds the most-downloaded packages
that depend on them (found by walking declared dependencies recursively in
ClickPy's copy of the PyPI metadata) up to 100 packages, and pulls each one's
180-day daily series (mirrors excluded) from pypistats into `docs/data.js`.
`docs/index.html` reads it and shows a 7-day-mean line chart and a ranked
table, filterable by period, package set and category, with the GitHub avatar
of each repository owner. The page is deployed to GitHub Pages by
`.github/workflows/pages.yml` on every push that touches `docs/`, and also
opens straight from disk. Rerun `python3 fetch_stats.py` to refresh the data;
the ClickPy endpoint has an hourly read quota, so a refused run succeeds after
the hour turns. In the snapshot of 2026-11-19 (2026-05-22 to 2026-11-18) the
180-day totals of the curated list are led by ase (11.8M), spglib (10.8M),
seekpath (6.1M), moyopy (5.2M) and pymatgen (5.0M); the largest
machine-learning-potential packages are nvalchemi-toolkit-ops (1.7M) and
mace-torch (0.65M). Counts include CI and other automated installs, and
several packages show multi-day bursts of that kind, so they measure installs
rather than users.
