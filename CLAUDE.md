# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A static dashboard of PyPI download counts for atomistic-simulation packages.
Two pieces, joined only by `docs/data.js`:

- `fetch_stats.py` (stdlib only, no dependencies, no venv) queries the network
  and writes `docs/data.js` as `window.PYPI_DATA = {...};`.
- `docs/index.html` is a single self-contained page (inline CSS and JS, no
  build step, no libraries) that loads `data.js` via `<script>` and renders
  everything as hand-built SVG. It opens straight from disk.

There are no tests, linters, or build. The README's prose quotes numbers from
the committed snapshot (date, package count, top totals); update it whenever
`docs/data.js` is regenerated.

## Commands

- Regenerate data: `python3 fetch_stats.py` (network; several minutes because of
  the 2 s pause between per-package requests).
- View: open `docs/index.html` in a browser.

## Data pipeline (`fetch_stats.py`)

1. `SEEDS`: curated packages grouped by category. Category order fixes each
   category's colour (`--c1`..`--c8` in `index.html`, 8 at most) -- append
   new categories, never reorder.
2. `find_dependents`: breadth-first walk of reverse dependencies via SQL on
   ClickPy (`sql-clickhouse.clickhouse.com`, public `demo` user). Only the latest
   release's non-extra `requires_dist` counts. Each dependent inherits its
   parent's category and records it in `via`. `MAX_FRONTIER` aborts the walk if
   a seed is too general.
3. `rank_by_downloads`: ClickPy download totals pick the top dependents so the
   total is `N_PACKAGES` (100).
4. `write_data`: for each kept package, pypistats.org's per-OS 180-day daily
   series (mirrors excluded) and a GitHub owner for the avatar (from
   `GITHUB_OWNERS` overrides, else parsed from PyPI `project_urls`).

Gotchas:

- ClickPy has an hourly read quota; a refused run succeeds after the hour turns.
  `http_get` retries with backoff on other transient HTTP errors, but not 404.
- Package keys are PEP 503-normalized (`normalize` / `norm_sql`); SQL literals
  go through `sql_tuple`, which rejects quotes and backslashes.

## Data contract (`docs/data.js`)

`fetched`, `dates` (contiguous ISO days), `categories` (= `list(SEEDS)`), and
`packages[]` with `name`, `category`, `via` (`null` for curated seeds; the page
uses this for the "Curated" vs "With dependents" filter), `owner`, and three
daily arrays aligned with `dates`: `all`, `linux`, `desktop` (Darwin + Windows).
The "macOS + Windows" platform filter is the stand-in for excluding CI installs,
since pypistats cannot identify them. Changing a field name means editing both
files.
