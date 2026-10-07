from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import web
from laya_model.laya_model import decision_long
from models.state import ResearchState, create_state

RESEARCH = {"research_text": "Management raised its growth outlook and expects expanding operating margins."}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(web, "router", None)
    monkeypatch.setattr(web, "model_status", "not_loaded")
    monkeypatch.setattr(web, "snapshots", {})
    monkeypatch.setattr(web, "load_portfolio", lambda: {"NVDA": 1.0})
    monkeypatch.setattr(web, "obtain_ticker", lambda symbol: SimpleNamespace(info={
        "symbol": symbol, "longName": "NVIDIA", "revenueGrowth": 0.55,
    }))
    monkeypatch.setattr(web, "setup", lambda: object())
    monkeypatch.setattr(web, "decision_long", lambda *args: {"answers": {
        question.name: {"type": "choice", "choice": next(iter(question.criteria))}
        for question in web.questions
    }})
    return TestClient(web.app)


def test_portfolio_and_snapshot(client):
    portfolio = client.get("/api/portfolio").json()
    assert [question["name"] for question in portfolio["questions"]] == [
        "growth_outlook_question", "profitability_outlook_question",
    ]
    assert [question["name"] for question in portfolio["article_questions"]] == [
        "market_reaction_question", "article_focus_question",
    ]
    snapshot = client.get("/api/companies/NVDA").json()
    assert snapshot["state"]["revenue_growth"] == 0.55
    assert snapshot["state"]["beta"] is None
    assert client.get("/api/companies/NVDA").json() == snapshot
    assert client.get("/api/companies/UNKNOWN").status_code == 404


def test_analysis_reuses_router(client, monkeypatch):
    setups = []
    monkeypatch.setattr(web, "setup", lambda: setups.append(True) or object())
    first = client.post("/api/analyze/NVDA", json=RESEARCH)
    assert first.status_code == 200
    result = first.json()
    assert result["validated"] is True
    assert len(result["answers"]) == 2
    assert result["timing"]["laya_ms"] >= 0
    assert result["timing"]["model_preloaded"] is False
    second = client.post("/api/analyze/NVDA", json=RESEARCH).json()
    assert second["timing"]["model_preloaded"] is True
    assert second["timing"]["setup_ms"] == 0
    assert len(setups) == 1


@pytest.mark.parametrize("invalid", [{}, {"answers": {}}, {"answers": {
    question.name: {"type": "choice", "choice": "buy"} for question in web.questions
}}])
def test_rejects_invalid_answers(client, monkeypatch, invalid):
    monkeypatch.setattr(web, "decision_long", lambda *args: invalid)
    assert client.post("/api/analyze/NVDA", json=RESEARCH).status_code == 502
    assert not web.analysis_lock.locked()


def test_busy_and_unknown(client):
    assert client.post("/api/analyze/UNKNOWN", json=RESEARCH).status_code == 404
    with web.analysis_lock:
        assert client.post("/api/analyze/NVDA", json=RESEARCH).status_code == 409


def test_setup_failure_can_retry(client, monkeypatch):
    def fail():
        raise RuntimeError("Unavailable")
    monkeypatch.setattr(web, "setup", fail)
    assert client.post("/api/analyze/NVDA", json=RESEARCH).status_code == 503
    assert client.get("/api/status").json()["model_status"] == "not_loaded"
    monkeypatch.setattr(web, "setup", lambda: object())
    assert client.post("/api/analyze/NVDA", json=RESEARCH).status_code == 200


def test_lifespan_preloads_model_on_startup(monkeypatch):
    monkeypatch.setattr(web, "router", None)
    monkeypatch.setattr(web, "model_status", "not_loaded")
    sentinel = object()
    monkeypatch.setattr(web, "setup", lambda: sentinel)
    with TestClient(web.app) as client:
        assert web.router is sentinel
        assert client.get("/api/status").json()["model_status"] == "ready"


def test_lifespan_handles_setup_failure(monkeypatch):
    monkeypatch.setattr(web, "router", None)
    monkeypatch.setattr(web, "model_status", "not_loaded")
    def fail():
        raise RuntimeError("Unavailable")
    monkeypatch.setattr(web, "setup", fail)
    with TestClient(web.app) as client:
        assert web.router is None
        assert client.get("/api/status").json()["model_status"] == "not_loaded"


def test_missing_market_data(client, monkeypatch):
    monkeypatch.setattr(web, "obtain_ticker", lambda symbol: SimpleNamespace(info={}))
    assert client.get("/api/companies/NVDA").status_code == 502
    assert client.post("/api/analyze/NVDA", json=RESEARCH).status_code == 502


def test_nvidia_analysis_forwards_research(client, monkeypatch, nvidia_info):
    ticker = Mock(return_value=SimpleNamespace(info=nvidia_info))
    router = Mock()
    expected = {"answers": {
        question.name: {"type": "choice", "choice": next(iter(question.criteria))}
        for question in web.questions
    }}
    router.predict_long.return_value = expected
    monkeypatch.setattr(web, "obtain_ticker", ticker)
    monkeypatch.setattr(web, "setup", lambda: router)
    monkeypatch.setattr(web, "decision_long", decision_long)

    snapshot = client.get("/api/companies/NVDA").json()
    response = client.post("/api/analyze/NVDA", json={"research_text": f"  {RESEARCH['research_text']}  "})

    assert response.status_code == 200
    result = response.json()
    ticker.assert_called_once_with("NVDA")
    router.predict_long.assert_called_once()
    sent_state = ResearchState.model_validate_json(router.predict_long.call_args.args[0])
    assert sent_state.research_text == RESEARCH["research_text"]
    assert result["research_text"] == sent_state.research_text
    assert sent_state.model_dump(exclude={"research_text"}) == create_state(nvidia_info).model_dump()
    assert result["snapshot"] == snapshot
    assert result["snapshot"]["state"] == sent_state.model_dump(exclude={"research_text"})
    assert result["raw"] == expected
    assert result["answers"]["growth_outlook_question"]["choice"] == "improving"
    assert result["validated"] is True


def test_rejects_missing_or_invalid_research(client, monkeypatch):
    predict = Mock()
    monkeypatch.setattr(web, "decision_long", predict)
    assert client.post("/api/analyze/NVDA").status_code == 422
    for text in ["", "   ", "a" * 60001]:
        assert client.post("/api/analyze/NVDA", json={"research_text": text}).status_code == 422
    predict.assert_not_called()
    assert web.router is None


def test_rejects_truncated_research(client, monkeypatch):
    for usage in [{"truncated": True}, {"state_tokens_dropped": 1}, {"truncated_questions": ["growth_outlook_question"]}]:
        monkeypatch.setattr(web, "decision_long", Mock(return_value={"usage": usage}))
        response = client.post("/api/analyze/NVDA", json=RESEARCH)
        assert response.status_code == 422
        assert "Shorten" in response.json()["detail"]
        assert not web.analysis_lock.locked()


def test_changed_research_is_sent_to_model(client, monkeypatch):
    predict = Mock(wraps=web.decision_long)
    monkeypatch.setattr(web, "decision_long", predict)
    for text in [RESEARCH["research_text"], "Management lowered its growth outlook."]:
        assert client.post("/api/analyze/NVDA", json={"research_text": text}).status_code == 200
        assert ResearchState.model_validate_json(predict.call_args.args[0]).research_text == text
    assert predict.call_count == 2


def test_transcript_endpoint(client, monkeypatch):
    fetch = Mock(return_value="Speaker: Management raised its growth outlook.")
    monkeypatch.setattr(web, "obtain_transcript", fetch)
    monkeypatch.setattr(web, "is_cached", Mock(return_value=False))
    response = client.get("/api/transcript/NVDA", params={"quarter": "2024Q1"})
    assert response.status_code == 200
    assert response.json() == {
        "research_text": "Speaker: Management raised its growth outlook.",
        "cached": False,
    }
    fetch.assert_called_once_with("NVDA", "2024Q1")
    assert client.get("/api/transcript/UNKNOWN", params={"quarter": "2024Q1"}).status_code == 404


def test_transcript_endpoint_reports_whether_cached(client, monkeypatch):
    monkeypatch.setattr(web, "obtain_transcript", Mock(return_value="cached text"))
    monkeypatch.setattr(web, "is_cached", Mock(return_value=True))
    response = client.get("/api/transcript/NVDA", params={"quarter": "2024Q1"})
    assert response.json()["cached"] is True


def test_transcript_endpoint_reports_fetch_failure(client, monkeypatch):
    monkeypatch.setattr(web, "obtain_transcript", Mock(side_effect=web.TranscriptError("no transcript")))
    response = client.get("/api/transcript/NVDA", params={"quarter": "2024Q1"})
    assert response.status_code == 502
    assert "no transcript" in response.json()["detail"]


def test_sentiment_endpoint(client, monkeypatch):
    fetch = Mock(return_value=[{"text": "NVIDIA beats estimates: Revenue grew 20% YoY.", "relevance": 0.9}])
    monkeypatch.setattr(web, "obtain_top_articles_with_relevance", fetch)
    monkeypatch.setattr(web, "sentiment_is_cached", Mock(return_value=False))
    response = client.get("/api/sentiment/NVDA")
    assert response.status_code == 200
    assert response.json() == {
        "articles": [{"text": "NVIDIA beats estimates: Revenue grew 20% YoY.", "relevance": 0.9}],
        "cached": False,
    }
    fetch.assert_called_once_with("NVDA", limit=3)
    assert client.get("/api/sentiment/UNKNOWN").status_code == 404


def test_sentiment_endpoint_reports_whether_cached(client, monkeypatch):
    monkeypatch.setattr(web, "obtain_top_articles_with_relevance", Mock(return_value=[]))
    monkeypatch.setattr(web, "sentiment_is_cached", Mock(return_value=True))
    response = client.get("/api/sentiment/NVDA")
    assert response.json()["cached"] is True


def test_sentiment_endpoint_reports_fetch_failure(client, monkeypatch):
    monkeypatch.setattr(web, "obtain_top_articles_with_relevance", Mock(side_effect=web.SentimentError("no news")))
    response = client.get("/api/sentiment/NVDA")
    assert response.status_code == 502
    assert "no news" in response.json()["detail"]


def test_sentiment_each_classifies_and_aggregates(client, monkeypatch):
    provenance = {
        "title": "NVIDIA: Quarterly results", "source": "Example News",
        "url": "https://example.com/results", "time_published": "20261005T130000",
    }
    articles = [
        {"text": "Article A", "relevance": 0.9, **provenance},
        {"text": "Article B", "relevance": 0.1},
    ]
    monkeypatch.setattr(web, "obtain_top_articles_with_relevance", Mock(return_value=articles))
    monkeypatch.setattr(web, "sentiment_is_cached", Mock(return_value=False))
    decision_each = Mock(return_value=[
        {"answers": {
            "market_reaction_question": {"type": "choice", "choice": "bullish"},
            "article_focus_question": {"type": "choice", "choice": "company_specific"},
        }},
        {"answers": {
            "market_reaction_question": {"type": "choice", "choice": "bearish"},
            "article_focus_question": {"type": "choice", "choice": "sector_wide"},
        }},
    ])
    monkeypatch.setattr(web, "decision_each", decision_each)

    response = client.get("/api/sentiment-each/NVDA")

    assert response.status_code == 200
    body = response.json()
    assert len(body["articles"]) == 2
    assert {field: body["articles"][0][field] for field in provenance} == provenance
    assert "source" not in body["articles"][1]
    assert '"research_text":"Article A"' in decision_each.call_args.args[0][0]
    assert "Example News" not in decision_each.call_args.args[0][0]
    assert body["articles"][0]["answers"]["market_reaction_question"]["choice"] == "bullish"
    # Weighted vote: 0.9 bullish vs 0.1 bearish -> bullish wins with ~90% confidence.
    assert body["aggregate"]["answers"]["market_reaction_question"]["choice"] == "bullish"
    assert body["aggregate"]["answers"]["market_reaction_question"]["answer_confidence"] == pytest.approx(0.9)


def test_sentiment_each_reports_fetch_failure(client, monkeypatch):
    monkeypatch.setattr(web, "obtain_top_articles_with_relevance", Mock(side_effect=web.SentimentError("no news")))
    response = client.get("/api/sentiment-each/NVDA")
    assert response.status_code == 502
    assert "no news" in response.json()["detail"]


def test_sentiment_each_requires_at_least_one_article(client, monkeypatch):
    monkeypatch.setattr(web, "obtain_top_articles_with_relevance", Mock(return_value=[]))
    response = client.get("/api/sentiment-each/NVDA")
    assert response.status_code == 502


def test_sentiment_each_rejects_concurrent_runs(client, monkeypatch):
    monkeypatch.setattr(
        web, "obtain_top_articles_with_relevance", Mock(return_value=[{"text": "A", "relevance": 1.0}]),
    )
    monkeypatch.setattr(web, "decision_each", Mock(return_value=[{"answers": {
        "market_reaction_question": {"type": "choice", "choice": "bullish"},
        "article_focus_question": {"type": "choice", "choice": "company_specific"},
    }}]))
    with web.analysis_lock:
        assert client.get("/api/sentiment-each/NVDA").status_code == 409