# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

> Einrichtung für neue Nutzer: siehe **ANLEITUNG.md**.

Kapital is a FastAPI backend that serves a React (JSX-via-Babel) frontend.

```bash
python -m kapital.run              # from the project root
python kapital/run.py              # identical — run.py has a __main__ block

python -m kapital.run --restart    # kill a running instance, then start
python -m kapital.run --stop       # just stop it
python -m kapital.run --reload     # auto-restart on .py changes
```

Stop it with **Ctrl+C** in its terminal. Closing the terminal window is the
unreliable way: depending on the shell the process may never receive SIGTERM,
keeps running and holds the port, and the next start fails with "address
already in use". `--restart` exists for exactly that case — it reports the
stale PID, sends SIGTERM, escalates to SIGKILL if needed, then starts.

`.jsx` changes need only a browser reload (the cache-buster is per-file mtime);
`--reload` is for backend changes.

This starts uvicorn on port `8502` (override with `KAPITAL_PORT`) and opens the
browser automatically. Backend API is under `/api`, everything else serves the
frontend from `kapital/frontend/`.

Dependencies are managed via a `.envrc`-activated virtual environment
(`direnv` + `.venv`). The `.venv` must contain `yfinance` **and** `torch`
(needed for the Kronos forecast).

Tooling is **uv** (fast installer + resolver, alongside direnv):

- `requirements.txt` — direct dependencies (the human-edited source of truth).
- `requirements.lock` — fully pinned resolution, generated with
  `uv pip compile requirements.txt -o requirements.lock`. Commit it.

```bash
# Recreate the environment reproducibly from the lockfile
uv venv                              # creates .venv (Python 3.11)
uv pip sync requirements.lock        # installs the exact pinned set

# Add / change a dependency: edit requirements.txt, then
uv pip compile requirements.txt -o requirements.lock   # re-pin
uv pip sync requirements.lock                          # apply
```

direnv auto-activates `.venv` on `cd` into the project (`.envrc` →
`source .venv/bin/activate`); no manual activation needed.

**Correctness checks.** There is no unit-test suite, but two checks exist and
should be run after touching money arithmetic or any `.jsx` file:

```bash
python -m kapital.check          # 5 invariants over the real data (exit 1 on violation)
/tmp/jsxcheck/bin/python kapital/tools/jsxcheck.py   # Babel syntax check, all .jsx
```

`kapital/check.py` exists because manual browser validation structurally cannot
catch arithmetic errors: a savings rate of 27 % and one of 2,5 % look equally
plausible on screen, and a silently removed transfer leaves no gap in any chart.
The invariants are: account balances reconcile with `giro_balances.json`; every
`is_transfer` row has exactly one counter-leg; the monthly cashflow identity
holds; positions agree with the depot snapshot; every EUR-rendered price carries
a currency. Violations that remain are data-quality issues needing a human
decision, not bugs — the script names the offending rows.

**No Node.js on this machine.** The `.jsx` files are never built, so a syntax or
render error only shows up in the browser console. To check them without a
browser, run them through the same Babel the app loads, inside `dukpy`:

```bash
uv venv /tmp/jsxcheck && VIRTUAL_ENV=/tmp/jsxcheck uv pip install dukpy
curl -sSL -o /tmp/babel-standalone.js https://unpkg.com/@babel/standalone@7.29.0/babel.min.js
curl -sSL -o /tmp/react.js https://unpkg.com/react@18.3.1/umd/react.production.min.js
curl -sSL -o /tmp/react-dom-server-legacy.js \
  https://unpkg.com/react-dom@18.3.1/umd/react-dom-server-legacy.browser.production.min.js
```

`Babel.transform(src, {presets:['react']})` catches syntax errors;
`ReactDOMServer.renderToStaticMarkup` on individual components catches render
errors. Duktape needs stubs for `TextEncoder`, `Intl` and
`Date.prototype.toLocaleDateString`, every `evaljs` must end in a serialisable
value (append `;true;`), and top-level `const` components are reached with
`eval(name)`, not `window[name]`.

## Architecture

German-language personal finance analyzer. A **FastAPI + React** app (`kapital/`)
built on a shared, framework-agnostic core package (`finance/`). All data is
stored locally in `data/` as Parquet files (transactions) and JSON files
(config/rules). There is no database.

```
kapital/                 <- project root
├── data/                persisted Parquet + JSON (gitignored financial data)
├── kapital/             the application package
│   ├── run.py           entry point (uvicorn launcher)
│   ├── finance/         shared core (parsing, analytics, portfolio) — no web deps
│   ├── backend/         FastAPI app
│   │   ├── main.py      app + routers + static frontend serving
│   │   ├── deps.py      shared data loaders + category metadata
│   │   ├── routers/     one module per API area
│   │   └── kronos_model/ Kronos time-series forecast model
│   └── frontend/        React JSX pages (no build step; Babel in-browser)
├── requirements.txt
└── .venv/
```

`finance/` lives inside the `kapital` package and is imported as `from kapital.finance import …`. It computes `data/` paths relative to the project root (`Path(__file__).parents[2] / "data"`), so keep `data/` a sibling of the `kapital/` package directory.

### Application package: `kapital/`

- **`run.py`** — adds the parent dir to `sys.path` so `kapital.backend.main:app`
  is importable, then launches uvicorn.
- **`backend/main.py`** — creates the FastAPI app, mounts every router under
  `/api`, and serves `frontend/` static files (with a cache-bust query on `.jsx`).
- **`backend/deps.py`** — shared data loaders and category (color/icon) metadata.
- **`backend/routers/`** — one router per domain: `dashboard`, `transactions`,
  `categories`, `portfolio`, `forecast`, `kronos_forecast`, `upload`,
  `jahresuebersicht`, `abos`, `fire`, `steuer`, `regeln`, `settings`,
  `review`, `monatsabschluss`.
- **`backend/coach.py`** — the only module that talks to a remote API: sends the
  aggregated month snapshot to the Claude API (`claude-opus-5`, structured
  JSON output) and caches the verdict in `data/coach_reviews.json`.
- **`backend/kronos_model/`** — the Kronos ML model used by the
  `kronos_forecast` router (loaded lazily; requires `torch`).
- **`frontend/`** — plain `.jsx` files loaded directly in the browser via Babel;
  `app.jsx` is the shell, `page-*.jsx` are the tabs, `charts.jsx`/`ui.jsx`/
  `filters.jsx` are shared components. No bundler.

### Core package: `kapital/finance/` (shared, no web dependencies)

| Module | Responsibility |
|---|---|
| `models.py` | Unified transaction schema (DataFrame columns), built-in category list |
| `storage.py` | Parquet I/O — `load()`, `save()`, merge with hash-based deduplication |
| `parsers/giro.py` | Auto-detects DKB, ING, Sparkasse, Comdirect CSV formats; extracts IBAN |
| `parsers/trade_republic.py` | Trade Republic CSV parser |
| `parsers/trade_republic_pdf.py` | PDF parser for TR statements via `pypdfium2` |
| `parsers/paypal.py` | PayPal CSV parser |
| `parsers/utils.py` | Shared helpers: date/amount parsing, charset detection |
| `categorizer.py` | Keyword-based rules matched against payee + description; 70+ built-in patterns |
| `custom_rules.py` | Persistent user-defined payee→category overrides |
| `transfer_detector.py` | Cross-account transfer matching; opposite-sign pairs within 7 days share a `transfer_id` |
| `analytics.py` | Income/expense KPIs, savings rate, monthly/yearly summaries |
| `portfolio.py` | Reconstructs positions from buy/sell events (ISIN + units); pure-Python XIRR |
| `subscriptions.py` | Auto-detects recurring payments |
| `abo_overrides.py` | Persistent subscription overrides |
| `review.py` | Which bookings still need a category ('Sonstiges' or empty payee, transfers excluded) + suggestion from the user's own history |
| `budgets.py` | Per-category targets (manual, else Ø of the last N complete months) and the month's Ist/Ziel comparison |
| `monatsbericht.py` | Aggregated month snapshot — the exact payload sent to the Claude API |

### Data Flow

1. **Import**: Upload CSV/PDF → parser auto-detects format → unified transaction DataFrame
2. **Deduplicate**: `storage.merge()` computes `tx_hash` fingerprints to skip already-imported rows
3. **Categorize**: Keyword rules applied; custom rules take priority
4. **Transfer detection**: cross-account pairs marked "Umbuchung" with a shared `transfer_id`
5. **Persist**: Saved to `data/transactions.parquet`
6. **Analyze**: Routers read the persisted data and run `finance/` analytics on demand

### Monthly Close Flow (Import → Zuordnung → Ziele → Bewertung)

1. **Import gate** — `/api/upload` returns `affected_months` (months containing
   genuinely new rows) and `n_open_affected`. The frontend fires a
   `kapital:review` window event; `app.jsx` opens `ReviewModal` full-screen.
2. **Forced assignment** — `review.py` lists every open booking of those months
   with a category suggestion drawn from the user's own history (most frequent
   category for the same payee). Assigning a payee auto-applies to every other
   open booking with the same payee in the batch. `POST /api/review/assign`
   writes all of them in one pass and can create a `custom_rule` per booking.
3. **Ist/Ziel** — `budgets.py` compares the month against a per-category target:
   a manual value from `data/budgets.json` if set, otherwise the average of the
   last `avg_months` (default 6) complete months. Spend is *net* per category
   (expenses − refunds, floored at 0); transfers, income and savings categories
   are excluded.
4. **KI-Bewertung** — `POST /api/monatsabschluss/bewertung` refuses with **409**
   while the month still has open bookings, then sends the aggregated snapshot
   to Claude and caches the verdict. A snapshot fingerprint marks a stored
   verdict `stale` when the underlying data changed.

**Privacy boundary:** everything else in Kapital is local-only. The coach is the
single exception, and it only ever sends `monatsbericht.build_snapshot()` —
category sums, top payees, notable single bookings, depot trades. No IBANs, no
account labels, no raw statements. Keep it that way when extending the payload.

### Key Design Details

- **Shared core**: `kapital/finance/` has no web dependency and is reused wholesale by the FastAPI backend (`from kapital.finance import …`).
- **Deduplication**: Transactions have a stable `tx_hash` fingerprint; merging never double-imports.
- **Balance calibration**: Liquid wealth is derived from cumulative cash flows; users supply real balances to calibrate the offset.
- **German-only UI**: All user-facing text, category names, and labels are in German.
- **Lazy market data**: `yfinance` is called only when the Portfolio/forecast routers need current prices.
- **Relative paths matter**: `kapital/finance/` and the routers locate `data/` via `Path(__file__).parents[...]`; keep `data/` a sibling of the `kapital/` package directory under the project root.

### Persisted Data (`data/`)

| File | Contents |
|---|---|
| `transactions.parquet` | All transactions (gitignored) |
| `depot_snapshot.parquet` | Portfolio holdings snapshot |
| `custom_categories.json` | User-defined categories |
| `custom_rules.json` | Payee→category rules (tracked in git) |
| `abo_overrides.json` | Subscription overrides |
| `iban_labels.json` | Human-readable account labels |
| `manual_prices.json` | Manual price overrides |
| `isin_tickers.json` | ISIN→ticker mapping for yfinance lookups |
| `settings.json` / `giro_balances.json` | App settings & balances (gitignored) — `settings.json` also holds the Anthropic API key |
| `budgets.json` | Per-category budget targets + reference window |
| `isin_succession.json` | Old ISIN → new ISIN after corporate actions (reverse splits, renames) |
| `depot_snapshot_meta.json` | As-of date of the depot snapshot — decides snapshot vs transactions |
| `transactions.parquet.1…5` | Rotated previous versions, written on every save |
| `coach_reviews.json` | Cached KI month verdicts, keyed by `YYYY-MM` with a snapshot fingerprint |
