import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, ValidationError

from investment_question.investment_questions import return_all_questions
from laya_model.laya_model import decision
from models.state import State, create_state
from setup.setup import setup
from ticker.obtain_ticker import obtain_ticker
from utils.load_portfolio import load_portfolio


ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)
app = FastAPI(title="Laya Investment Research")
questions = return_all_questions()
router = None
model_status = "not_loaded"
analysis_lock = Lock()
snapshot_lock = Lock()
snapshots = {}


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["choice"]
    choice: str


def validate_answers(result: dict) -> dict:
    answers = result.get("answers")
    if not isinstance(answers, dict) or set(answers) != {question.name for question in questions}:
        raise ValueError("Expected one answer for each investment question")
    for question in questions:
        answer = ChoiceAnswer.model_validate(answers[question.name])
        if answer.choice not in question.criteria:
            raise ValueError(f"Invalid choice for {question.name}")
    return answers


def check_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol not in load_portfolio():
        raise HTTPException(404, "Company is not in the portfolio")
    return symbol


def get_snapshot(symbol: str, refresh: bool = False) -> dict:
    with snapshot_lock:
        if symbol in snapshots and not refresh:
            return snapshots[symbol]
        started = perf_counter()
        try:
            state = create_state(obtain_ticker(symbol).info)
            if not state.symbol or not state.company:
                raise ValueError("Company data is unavailable")
        except Exception as exc:
            logger.exception("Market data fetch failed for %s", symbol)
            raise HTTPException(502, "Market data is unavailable. Try refreshing again.") from exc
        snapshot = {
            "state": state.model_dump(),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fetch_ms": round((perf_counter() - started) * 1000, 2),
        }
        snapshots[symbol] = snapshot
        return snapshot


@app.get("/api/portfolio")
def portfolio():
    return {
        "companies": [{"symbol": symbol, "weight": weight} for symbol, weight in load_portfolio().items()],
        "questions": [question.model_dump() for question in questions],
    }


@app.get("/api/status")
def status():
    return {"model_status": model_status, "busy": analysis_lock.locked()}


@app.get("/api/companies/{symbol}")
def company(symbol: str, refresh: bool = False):
    return get_snapshot(check_symbol(symbol), refresh)


@app.post("/api/analyze/{symbol}")
def analyze(symbol: str):
    global router, model_status
    symbol = check_symbol(symbol)
    if not analysis_lock.acquire(blocking=False):
        raise HTTPException(409, "An analysis is already running. Please try again shortly.")
    started = perf_counter()
    try:
        snapshot = get_snapshot(symbol)
        setup_ms = 0
        preloaded = router is not None
        if router is None:
            model_status = "loading"
            setup_started = perf_counter()
            try:
                router = setup()
            except Exception:
                model_status = "not_loaded"
                raise
            setup_ms = round((perf_counter() - setup_started) * 1000, 2)
            model_status = "ready"
        state = State.model_validate(snapshot["state"])
        inference_started = perf_counter()
        result = decision(state.model_dump_json(), questions, router)
        inference_ms = round((perf_counter() - inference_started) * 1000, 2)
        try:
            answers = validate_answers(result)
        except (ValueError, ValidationError, TypeError, AttributeError) as exc:
            raise HTTPException(502, "Laya returned an invalid decision. No results were accepted.") from exc
        return {
            "symbol": symbol,
            "snapshot": snapshot,
            "answers": answers,
            "validated": True,
            "raw": result,
            "timing": {
                "setup_ms": setup_ms,
                "laya_ms": inference_ms,
                "total_ms": round((perf_counter() - started) * 1000, 2),
                "model_preloaded": preloaded,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Analysis failed for %s", symbol)
        raise HTTPException(503, "Analysis failed. Check model availability and retry.") from exc
    finally:
        analysis_lock.release()


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static", check_dir=False), name="static")