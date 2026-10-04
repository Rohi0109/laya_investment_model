# Finance

Stock research experiments using yfinance and Laya.

Run `uv sync` to install dependencies, then `uv run python main.py`.
The main script fetches ticker data, maps it once with `create_state(ticker.info)`,
and passes `state.model_dump_json()` plus six reusable questions to Laya.
The first prediction may download model weights.

`load_portfolio()` reads the project-root `portfolio.json` and returns its
company-to-weight dictionary. Missing files and invalid JSON raise errors.

`State` keeps Yahoo's raw units: growth, profit margin, yearly return, and distance
from the yearly high are fractions; debt/equity is percentage-scaled. Missing
fields remain `None` (JSON `null`). Predictions are not investment guarantees.

Run the offline state and question checks with:
`uv run pytest laya_model/tests/test_laya.py -k 'create_state or return_all_questions'`.
The existing `test_get_decision` runs real model inference and is excluded from
the default offline test run. No CI/CD is configured.

## NVIDIA Regression Tests

`conftest.py` freezes the NVIDIA Yahoo fields captured on 2026-09-30:
one-year return +21.35%, 3.45% below the yearly high. No test fetches live prices.

```sh
uv run pytest
uv run pytest -k nvidia
```

The offline tests verify raw units, price/high arithmetic, JSON round trips,
the exact payload sent to the router, and API response passthrough. Mocked Laya
answers deliberately replay the observed `negative` momentum result; passing
these tests proves the wiring works, not that the financial answer is correct.

Run the real model against the fixed NVIDIA inputs separately:

```sh
uv run pytest -m laya_integration -k nvidia -v
```

This checks the captured case (expected `positive`) and two synthetic NVIDIA
variants: a large yearly loss/fall from the high (expected `negative`), and a
flat year near the high (expected `neutral`). All six original questions are
sent together, as in the website. The router is loaded once for the suite.
These are model-quality assertions and can fail while the offline tests pass;
they are not marked as expected failures or silently corrected. The first run
may download weights; model inference and timing depend on the local runtime.

Run the real Alpha Vantage API (requires `ALPHAVANTAGE_API_KEY` in `.env`) separately:

```sh
uv run pytest -m api_integration -v
```

This spends real API calls and hits Alpha Vantage's free-tier rate limit if run
back-to-back with other integration tests, so it is excluded from the default
run and run on its own.


The 2026-09-30 local run reproduced `negative` for all three cases: the negative
case passed, while the captured positive and synthetic neutral cases failed.
Production prompts and inputs have not been changed to hide these failures.

## Website

From the project root, run `uv run uvicorn web:app --host 127.0.0.1 --port 8000`
(or `make dev` for the same command with auto-reload) and open
http://127.0.0.1:8000. The website uses the portfolio and question
definitions above; the command-line entry point is unchanged.

Select a company to fetch its fundamentals, then run analysis to call Laya.
The model is preloaded when the server starts (may download weights, so the
first `uv run uvicorn ...` can take a while to report "Application startup
complete"), not on the first analysis click. The process reuses that router
for later calls and accepts one analysis at a time. Market snapshots are
cached until the refresh button is used or the server restarts. The displayed
timestamp is the fetch time, not a market-data publication time.

Laya call time measures routing plus prediction, excluding explicit model setup
and market fetching. The server total includes work performed for that request.
"Reused model" means the router was already loaded, not a guaranteed warmed-up
benchmark. All six answer types and choice values are validated before results
are displayed. Choice validation does not establish investment accuracy.

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

The image includes the website and Python backend, installs production
dependencies from `uv.lock`, and runs as a non-root user. Local environments,
Git history, tests, and `.env` files are excluded from the build. One Uvicorn
worker owns the loaded model and analysis lock. This is a CPU container; it does
not use the Mac's GPU, so timings can differ from running directly on macOS.

Model weights download on the first analysis and persist in the `laya-cache`
volume across container replacements. The health check verifies the HTTP server,
not model readiness. Internet access is required for market data and the initial
model download. The first build downloads the Python and ML dependencies and may
take several minutes. Portfolio and code changes require rebuilding the image.

```sh
docker compose logs -f web
docker compose down
```

Stopping with `down` preserves downloaded weights. `docker compose down -v`
also deletes the model cache. The published port is bound to localhost only;
containerization does not add authentication or make the prototype public-ready.

