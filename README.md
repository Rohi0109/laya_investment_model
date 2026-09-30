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
The existing `test_get_decision` runs real model inference. No CI/CD is configured.

