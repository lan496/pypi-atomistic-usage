# Contributing

Additions, corrections and ideas are welcome, as pull requests or as issues.

## Adding a package

The dashboard tracks Python packages for atomistic simulation and atomistic
machine learning that are published on PyPI. To add one:

1. Put its PyPI name in `SEEDS` in `fetch_stats.py`, under the category that
   fits it best. Each package appears once.
2. If its PyPI metadata does not link its GitHub repository, add the GitHub
   owner to `GITHUB_OWNERS` so that the page shows an avatar.
3. Open a pull request. You need not regenerate `docs/data.js`: the monthly job
   fetches fresh data for the whole list.

Packages that depend on a listed one are found automatically, so a plugin or
a downstream tool often appears without being listed. A listed library that is
used far beyond atomistic simulation (RDKit, DGL, e3nn, ...) goes into `NO_WALK`
as well, so that its thousands of dependents are not followed.

If you would rather not edit code, open an issue with the PyPI name and the
category.

## Categories

The order of the categories in `SEEDS` fixes their colours on the page, and the
page has eight colours. Append a category only after discussing it in an issue,
and never reorder them.

## Running it locally

`fetch_stats.py` needs Python 3.10 or later and nothing outside the standard
library:

```sh
python3 fetch_stats.py   # about 5 minutes; rewrites docs/data.js
```

Then open `docs/index.html` in a browser; it needs no server and no build.

The script queries the public ClickPy endpoint, whose demo user may run 60
queries and 600 seconds of query time per hour. A run takes about 20 queries.
If the endpoint refuses a run, retry after the hour turns.

## Changing the page

`docs/index.html` is a single file with inline CSS and JavaScript and no
dependencies. It reads `window.PYPI_DATA` from `docs/data.js`; a field added
or renamed there has to change in both `fetch_stats.py` and the page.

## Methodology

Questions about how downloads are counted, how CI and bulk rebuilds are
detected, or which packages count as atomistic belong in an issue. The About
section of the page describes the current method.
