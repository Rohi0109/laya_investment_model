import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, ValidationError

load_dotenv()

from investment_question.investment_questions import return_article_questions, return_research_questions
from laya_model.laya_model import aggregate_decisions, decision_each, decision_long
from models.state import ResearchState, ResearchText, create_state
from setup.setup import setup
from ticker.obtain_sentiment import SentimentError, is_cached as sentiment_is_cached, obtain_top_articles_with_relevance
from ticker.obtain_ticker import obtain_ticker
from ticker.obtain_transcript import TranscriptError, is_cached, obtain_transcript
from utils.load_portfolio import load_portfolio


ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)
questions = return_research_questions()
# Separate question set for per-article news analysis (see /api/sentiment-each):
# market reaction is tuned for a single short article, not a long excerpt.
article_questions = return_article_questions()
router = None
model_status = "not_loaded"
analysis_lock = Lock()
snapshot_lock = Lock()
snapshots = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global router, model_status
    model_status = "loading"
    try:
        router = setup()
        model_status = "ready"
    except Exception:
        model_status = "not_loaded"
        logger.exception("Failed to preload Laya model at startup; will load lazily on first analysis")
    yield


app = FastAPI(title="Laya Investment Research", lifespan=lifespan)


class AnalysisRequest(BaseModel):
    research_text: ResearchText


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["choice"]
    choice: str


def validate_answers(result: dict, expected_questions: list) -> dict:
    answers = result.get("answers")
    if not isinstance(answers, dict) or set(answers) != {question.name for question in expected_questions}:
        raise ValueError("Expected one answer for each investment question")
    for question in expected_questions:
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
        "article_questions": [question.model_dump() for question in article_questions],
    }


@app.get("/api/status")
def status():
    return {"model_status": model_status, "busy": analysis_lock.locked()}


@app.get("/api/companies/{symbol}")
def company(symbol: str, refresh: bool = False):
    return get_snapshot(check_symbol(symbol), refresh)


@app.get("/api/transcript/{symbol}")
def transcript(symbol: str, quarter: str):
    symbol = check_symbol(symbol)
    cached = is_cached(symbol, quarter)
    try:
        research_text = obtain_transcript(symbol, quarter)
    except TranscriptError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"research_text": research_text, "cached": cached}


@app.get("/api/sentiment/{symbol}")
def sentiment(symbol: str):
    symbol = check_symbol(symbol)
    # Top 3 relevance-ranked articles: more research signal than just the single
    # most-relevant one, while still far shorter than a full transcript. Kept
    # separate (not joined) so each article can be analyzed on its own below.
    cached = sentiment_is_cached(symbol, limit=3)
    try:
        articles = obtain_top_articles_with_relevance(symbol, limit=3)
    except SentimentError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"articles": articles, "cached": cached}


@app.get("/api/sentiment-each/{symbol}")
def sentiment_each(symbol: str):
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
        cached = sentiment_is_cached(symbol, limit=3)
        try:
            articles = obtain_top_articles_with_relevance(symbol, limit=3)
        except SentimentError as exc:
            raise HTTPException(502, str(exc)) from exc
        if not articles:
            raise HTTPException(502, "No news articles available for analysis.")
        # Article-only state: valuation/growth/risk metrics are irrelevant to market_reaction_question
        # and reliably distract the model from the article's own event
        # (verified: laya_model/tests/test_laya.py::test_article_questions_resolve_known_nvidia_cases).
        article_states = [
            ResearchState(
                company=snapshot["state"].get("company"), symbol=symbol, research_text=article["text"],
            ).model_dump_json(exclude_none=True)
            for article in articles
        ]
        inference_started = perf_counter()
        per_article_raw = decision_each(article_states, article_questions, router)
        inference_ms = round((perf_counter() - inference_started) * 1000, 2)
        for raw in per_article_raw:
            usage = raw.get("usage") if isinstance(raw, dict) else None
            if isinstance(usage, dict) and (
                usage.get("truncated") or usage.get("state_tokens_dropped") or usage.get("truncated_questions")
            ):
                raise HTTPException(422, "An article exceeded the model context window.")
        try:
            validated_results = [validate_answers(r, article_questions) for r in per_article_raw]
        except (ValueError, ValidationError, TypeError, AttributeError) as exc:
            raise HTTPException(502, "Laya returned an invalid decision for an article.") from exc
        weights = [article["relevance"] for article in articles]
        total_weight = sum(weights)
        if total_weight == 0:
            weights = [1.0] * len(articles)
            total_weight = float(len(articles))
        raw_aggregate = aggregate_decisions(
            [{"answers": ans} for ans in validated_results],
            weights,
        )
        aggregate_answers = {}
        for name in raw_aggregate["answers"]:
            totals: dict[str, float] = {}
            for ans, weight in zip(validated_results, weights):
                choice = ans[name]["choice"]
                totals[choice] = totals.get(choice, 0.0) + weight
            winning_choice = raw_aggregate["answers"][name]["choice"]
            aggregate_answers[name] = {
                "type": "choice",
                "choice": winning_choice,
                "answer_confidence": totals[winning_choice] / total_weight,
            }
        return {
            "symbol": symbol,
            "snapshot": snapshot,
            "articles": [
                {
                    "text": article["text"], "relevance": article["relevance"], "answers": ans,
                    **{
                        field: article[field]
                        for field in ("title", "source", "url", "time_published")
                        if field in article
                    },
                }
                for article, ans in zip(articles, validated_results)
            ],
            "aggregate": {"answers": aggregate_answers},
            "cached": cached,
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
        logger.exception("News article analysis failed for %s", symbol)
        raise HTTPException(503, "Analysis failed. Check model availability and retry.") from exc
    finally:
        analysis_lock.release()


@app.post("/api/analyze/{symbol}")
def analyze(symbol: str, request: AnalysisRequest):
    global router, model_status
    symbol = check_symbol(symbol)
    if not analysis_lock.acquire(blocking=False):
        raise HTTPException(409, "An analysis is already running. Please try again shortly.")
    started = perf_counter()
    try:
        snapshot = get_snapshot(symbol)
        setup_ms = 0
        preloaded = router is not None
        # The model is preloaded at server startup (see lifespan()); this is a fallback
        # for the rare case that preload failed or didn't run (e.g. under TestClient).
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
        state = ResearchState(**snapshot["state"], research_text=request.research_text)
        inference_started = perf_counter()
        result = decision_long(state.model_dump_json(), questions, router)
        inference_ms = round((perf_counter() - inference_started) * 1000, 2)
        usage = result.get("usage") if isinstance(result, dict) else None
        if isinstance(usage, dict) and (
            usage.get("truncated") or usage.get("state_tokens_dropped") or usage.get("truncated_questions")
        ):
            raise HTTPException(422, "The excerpt exceeded the model context. Shorten it and retry.")
        try:
            answers = validate_answers(result, questions)
        except (ValueError, ValidationError, TypeError, AttributeError) as exc:
            raise HTTPException(502, "Laya returned an invalid decision. No results were accepted.") from exc
        return {
            "symbol": symbol,
            "snapshot": snapshot,
            "research_text": state.research_text,
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