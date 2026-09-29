# Finance

Experiments with stock data and model-based decisions.

## Setup

Requires Python 3.14 or newer. Install dependencies with `uv sync`.

## Decision Helper

`investment_question/investment_question.py` defines `investment_question()`,
which builds a named `ChoiceQuestion`. Its answer key is `investment_question`.
`laya_model/laya_model.py` defines `decision(state, questions, router)`, which
passes text context and a list of questions to the supplied router and returns
its result. Prediction errors propagate to the caller. The first prediction
may download model weights.

Python package folders include `__init__.py` files for explicit imports.
No helper-specific environment variables are required.

The main script prints the selected choice and its `answer_confidence` as a
percentage. This is a model probability, not a guarantee of investment success.

## Tests

Run `uv run pytest`. The test in `laya_model/tests` uses a real router and may
download model weights and run inference. Use `uv run pytest --collect-only`
to check test discovery without inference. No CI/CD pipeline is configured yet.
