# PyPI download counts of atomistic-simulation packages

How much are atomistic-simulation Python packages used, judged by the daily
download counts on pypistats.org? `fetch_stats.py` starts from a curated list
of 38 packages in five categories (`SEEDS`) and pulls each one's 180-day daily
series by operating system (mirrors excluded) from pypistats into
`docs/data.js`. `docs/index.html` reads it and shows a 7-day-mean line chart
with each line named at its end, a bar chart race, and a ranked table with the
GitHub avatar of each repository owner, filterable by period, platform,
package set and category. pypistats cannot tell CI downloads apart, so the
platform filter is the stand-in: "macOS + Windows" drops nearly all automated
installs, at the cost of dropping real Linux use too. `python3 fetch_stats.py`
also adds the most-downloaded packages that depend on the curated ones, up to
100 in total, found by walking declared dependencies recursively in ClickPy's
copy of the PyPI metadata; that endpoint has an hourly read quota, so a refused
run succeeds after the hour turns. The page is deployed to GitHub Pages by
`.github/workflows/pages.yml` on every push that touches `docs/`, and also
opens straight from disk. The committed snapshot of 2026-11-19 (2026-05-22 to
2026-11-18) holds 100 packages: the curated list and 62 of its 1589
dependents. Within the curated list, its 180-day totals are led by ase
(11.8M), spglib (10.8M), seekpath (6.1M), pyxtal (5.8M), moyopy (5.2M) and
pymatgen (5.0M), and the largest machine-learning-potential packages are
nvalchemi-toolkit-ops (1.7M), nequix (0.98M) and mace-torch (0.65M). On macOS
and Windows alone the order is ase, spglib, pymatgen, MDAnalysis, phonopy, and
the multi-day bursts seen on Linux are absent.
