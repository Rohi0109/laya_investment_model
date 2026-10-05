# Laya / Market Pulse

A local portfolio-news research demo. FastAPI serves a plain HTML/CSS/JavaScript
interface; Yahoo Finance supplies fundamentals, Alpha Vantage supplies news,
and Laya classifies each article's market reaction and significance.

## Quick Start

Install Python 3.14+ and [uv](https://docs.astral.sh/uv/), then run from the
project root:

```sh
uv sync
```

Set `ALPHAVANTAGE_API_KEY` in the local `.env` file (automatically loaded by the
backend). Keep this file private and out of screen shares. Then start the app:

```sh
make dev
```

Open http://127.0.0.1:8000/. The equivalent command is
`uv run uvicorn web:app --host 127.0.0.1 --port 8000 --reload`.
`web:app` is the application entry point; the old interactive CLI has been removed.
If port 8000 is already in use, check whether the app is already running before
starting another copy. An explicit alternate port is supported, for example
`uv run uvicorn web:app --host 127.0.0.1 --port 8002 --reload`.

The server preloads the model at startup and reuses it. The first start may
download weights; wait for "Application startup complete" before the demo.
If preloading fails, analysis retries loading the model on demand.

## Demo Walkthrough

1. Start on **Portfolio overview** and choose **Analyze news** to screen holdings
	 sequentially. Stop takes effect after the current company finishes.
2. Compare **Market reaction** and **Significance**, using portfolio order or
	 either weight sort. Select a company for its findings and fundamentals.
3. Expand a supporting headline to read the provider's article summary. Publisher
	 links open the source page in a new tab; publication dates appear when supplied.
4. Open the collapsed diagnostics only when discussing inference timing or validation.

Each company uses up to three earnings-related articles, ranked by ticker
relevance. Laya classifies them separately; the aggregate is a relevance-weighted
vote, falling back to equal weights when all relevance scores are zero.
The API retains `answer_confidence` as the winning choice's weighted vote share.
It is not a calibrated probability of correctness and is not displayed or offered
as a sort in the UI. Significance maps the model's `major`/`minor` choices to
High/Low without changing the underlying model values.

## Data And Caching

`portfolio.json` maps ticker symbols to fractional portfolio weights.
`load_portfolio()` reads it from the working directory; missing files or invalid
JSON raise errors. Run commands from the project root.

- Fundamentals are cached in server memory until the company refresh button is
	used or the server restarts. Their timestamp is the fetch time, not the market
	publication time.
- News is cached on disk by symbol and article limit. Locally the default is
	`.cache/sentiment`; with `XDG_CACHE_HOME` set it is
	`$XDG_CACHE_HOME/finance/sentiment`. Successful fetches preserve available title,
	publisher, URL, and publication time. Legacy entries without those fields still
	work but cannot display attribution.
- Re-running analysis uses the saved news; refreshing fundamentals does not refresh
	news. To request fresh news, back up and remove the relevant `SYMBOL_3.json`
	entry before the next analysis. This spends an API call and may hit provider
	limits; prepare the cache before presenting rather than during the demo.
- Analysis results live in the browser tab and are cleared by a page reload.

`State` keeps Yahoo's raw units: growth, profit margin, yearly return, and distance
from the yearly high are fractions; debt/equity is percentage-scaled. Missing
fields remain `None` (JSON `null`). Valid choices and agreement among articles do
not establish investment accuracy. Predictions are not investment guarantees.

## Tests

```sh
make test
uv run pytest tests/test_web.py tests/test_sentiment.py
```

The focused web/news command uses mocks and does not spend API calls or run model
inference. It checks API contracts, classification wiring, news ranking/caching,
and provenance pass-through. No CI/CD is configured.

The default suite excludes tests marked `laya_integration` or `api_integration`,
but two existing NVIDIA tests invoke the real model without those markers. For
an offline-only run of the full suite, explicitly exclude them:

```sh
uv run pytest -k 'not test_nvidia_research_classification and not test_nvidia_momentum_regression'
```

## NVIDIA Regression Tests

`conftest.py` freezes the NVIDIA Yahoo fields captured on 2026-09-30:
one-year return +21.35%, 3.45% below the yearly high. These cases use fixed inputs,
not live prices.

The offline tests verify raw units, price/high arithmetic, JSON round trips,
the exact payload sent to the router, and API response passthrough. Mocked Laya
answers deliberately replay the observed `negative` momentum result; passing
these tests proves the wiring works, not that the financial answer is correct.

Run the two real-model NVIDIA checks explicitly:

```sh
uv run pytest laya_model/tests/test_laya.py -k 'test_nvidia_research_classification or test_nvidia_momentum_regression' -v
```

These use the original six research questions, not the demo's two article
questions. They may download weights and can fail while the offline tests pass.
The October 5, 2026 run returned `negative` where the momentum regression expects
`positive`: the default suite reported 66 passed, one failed, and six deselected.
The model output and test assertion have not been changed to hide that failure.

Other explicitly marked model tests can be run with
`uv run pytest -m laya_integration -v`.

Run the real Alpha Vantage API (requires `ALPHAVANTAGE_API_KEY` in `.env`) separately:

```sh
uv run pytest -m api_integration -v
```

This spends real API calls and hits Alpha Vantage's free-tier rate limit if run
back-to-back with other integration tests, so it is excluded from the default
run and run on its own.


## Runtime Notes

The backend accepts one analysis at a time. Laya call time measures routing plus
prediction, excluding explicit model setup and market fetching. Server total time
includes work performed for that request. Answer types and choices are validated
against the relevant question set. The transcript and general research API routes
remain available even though the current UI focuses on news.

The frontend is plain HTML/CSS/JavaScript served by FastAPI. Fonts and Lucide
icons use public CDNs. Company logos are served locally (Simple Icons and the
ExxonMobil site favicon); company tickers remain visible if logos fail.
This is a local prototype with no authentication; do not expose it publicly
without authentication, resource limits, and deployment hardening.

Run offline API checks with `uv run pytest tests/test_web.py`.

## Docker

With Docker and Docker Compose installed, run from the project root:

```sh
docker compose up --build -d --wait
```

Open http://localhost:8001. To choose another port, use
`PORT=8080 docker compose up --build -d --wait`.

The current Compose service does **not** forward `ALPHAVANTAGE_API_KEY` into the
container, and `.env` is excluded from the image. For news analysis without
editing Compose, export that variable in your shell, then use this alternative
launch instead of `up`:

```sh
docker compose build
docker compose run --rm --service-ports -e ALPHAVANTAGE_API_KEY web
```

Do not run both launch methods on the same host port. The run command uses the
same persistent cache volume; local host news caches are not copied into it.

The image includes the website and Python backend, installs production
dependencies from `uv.lock`, and runs as a non-root user. Local environments,
Git history, tests, and `.env` files are excluded from the build. One Uvicorn
worker owns the loaded model and analysis lock. This is a CPU container; it does
not use the Mac's GPU, so timings can differ from running directly on macOS.

Model weights download during startup preloading and persist in the `laya-cache`
volume across container replacements. The health check verifies the HTTP server,
not model readiness. This volume also holds cached news and transcripts. Internet
access is required for fresh market/news data and the initial model download.
The first build downloads the Python and ML dependencies and may
take several minutes. Portfolio and code changes require rebuilding the image.

```sh
docker compose logs -f web
docker compose down
```

Stopping with `down` preserves cached data. `docker compose down -v`
also deletes model weights and cached news/transcripts. The published port is bound to localhost only;
containerization does not add authentication or make the prototype public-ready.

