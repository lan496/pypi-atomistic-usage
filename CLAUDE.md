# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A static dashboard of PyPI download counts for atomistic-simulation and
atomistic-ML packages, published on GitHub Pages. Two pieces, joined only by
`docs/data.js`:

- `fetch_stats.py` (stdlib only, no dependencies, no venv) queries the network
  and writes `docs/data.js` as `window.PYPI_DATA = {...};`.
- `docs/index.html` is the dashboard (inline JS, no build step, no libraries)
  that loads `data.js` via `<script>` and renders everything as hand-built SVG.
  `docs/about.html` holds the methods and licence text. Both share
  `docs/style.css` and open straight from disk.

There are no tests, linters, or build. `.github/workflows/pages.yml` refreshes
the data on the 2nd of every month, commits it, and deploys `docs/` to Pages.

## Commands

- Regenerate data: `python3 fetch_stats.py` (about 5 minutes; needs network
  access to `sql-clickhouse.clickhouse.com` and `pypi.org`).
- View: open `docs/index.html` in a browser.

## Data pipeline (`fetch_stats.py`)

1. `SEEDS`: listed packages grouped by category: a curated core, all PyPI
   packages of best-of-atomistic-machine-learning, and the PyPI-installable
   engines of atomistic.software. Category order fixes each category's colour
   (`--c1`..`--c8` in `index.html`, 8 at most): append, never reorder.
2. `find_dependents`: breadth-first walk of reverse dependencies on ClickPy's
   `pypi.projects`. Only the latest release's non-extra `requires_dist` counts.
   Seeds in `NO_WALK` (general-purpose libraries) are not walked from.
   `MAX_FRONTIER` aborts if a seed is too general. A dependent's category comes
   from `DEPENDENT_CATEGORIES` (by what it does), else from its parent; review
   new dependents after a refresh and add them there.
3. `rank_by_downloads` keeps the top `N_DEPENDENTS`.
4. `write_data`: daily series (last `DAILY_DAYS`) and monthly series (whole
   history, as mean per day) from ClickPy materialized views; CI and
   bulk-rebuild shares over the last `AUTOMATION_DAYS` from the raw
   `pypi.pypi` table; GitHub owner and first release date from PyPI JSON.

ClickPy demo user limits that shape the code:

- At most 10,000 result rows per query: series queries return one row per
  project with a `groupArray` of points.
- 60 s per query: raw-table queries are batched by `AUTOMATION_BATCH_ROWS`.
- At most 10^9 rows read per query, silently truncated by default; `CLICKPY`
  sets `read_overflow_mode=throw` so that such a query fails instead. Sums over
  all of PyPI therefore use the small `pypi_downloads_per_month` view.
- 60 queries and 600 s of execution per hour: a refused run succeeds after the
  hour turns. Check usage with `SELECT * FROM system.quota_usage`.
- ClickPy project names are already PEP 503-normalized; `pypi.projects.name`
  is not, hence `norm_sql`. Some packages (e.g. mace-torch) are missing from
  `pypi.projects`, so metadata comes from PyPI JSON instead.

"all" excludes mirror installers (installer view); "linux"/"desktop" come from
the per-system view, which cannot exclude mirrors, but mirrors report no system.

## Data contract (`docs/data.js`)

Top level: `fetched`, `dates` (daily ISO days), `months` (`YYYY-MM`),
`automation_days`, `bulk_min`, `categories` (= `list(SEEDS)`), `pypi_monthly`
(downloads per day of all of PyPI per month, aligned with `months`), `packages[]`.
Each package: `name`, `category`, `via` (`null` for listed seeds; shown as
"Found via"), `owner`, `since`, `daily` and `monthly`
(each `{all, linux, desktop}` aligned with `dates` / `months`), `ci`, `bulk`
(shares or `null`). Changing a field means editing both files.

Each refresh also writes a frozen copy to `docs/snapshots/<fetched>.js`, which
`#snapshot=<fetched>` links load instead of `data.js` ("Fixed" share links).
Snapshots are never rewritten and are deleted after `SNAPSHOT_KEEP_DAYS` (a
year), so `index.html` must keep reading those up to a year old: add fields as
optional, and rename or drop one only once no snapshot carries the old form.
