from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import web
from laya_model.laya_model import decision
from models.state import State, create_state


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
    monkeypatch.setattr(web, "decision", lambda *args: {"answers": {
        question.name: {"type": "choice", "choice": next(iter(question.criteria))}
        for question in web.questions
    }})
    return TestClient(web.app)


def test_portfolio_and_snapshot(client):
    assert len(client.get("/api/portfolio").json()["questions"]) == 6
    snapshot = client.get("/api/companies/NVDA").json()
    assert snapshot["state"]["revenue_growth"] == 0.55
    assert snapshot["state"]["beta"] is None
    assert client.get("/api/companies/NVDA").json() == snapshot
    assert client.get("/api/companies/UNKNOWN").status_code == 404


def test_analysis_reuses_router(client, monkeypatch):
    setups = []
    monkeypatch.setattr(web, "setup", lambda: setups.append(True) or object())
    first = client.post("/api/analyze/NVDA")
    assert first.status_code == 200
    result = first.json()
    assert result["validated"] is True
    assert len(result["answers"]) == 6
    assert result["timing"]["laya_ms"] >= 0
    assert result["timing"]["model_preloaded"] is False
    second = client.post("/api/analyze/NVDA").json()
    assert second["timing"]["model_preloaded"] is True
    assert second["timing"]["setup_ms"] == 0
    assert len(setups) == 1


@pytest.mark.parametrize("invalid", [{}, {"answers": {}}, {"answers": {
    question.name: {"type": "choice", "choice": "buy"} for question in web.questions
}}])
def test_rejects_invalid_answers(client, monkeypatch, invalid):
    monkeypatch.setattr(web, "decision", lambda *args: invalid)
    assert client.post("/api/analyze/NVDA").status_code == 502
    assert not web.analysis_lock.locked()


def test_busy_and_unknown(client):
    assert client.post("/api/analyze/UNKNOWN").status_code == 404
    with web.analysis_lock:
        assert client.post("/api/analyze/NVDA").status_code == 409


def test_setup_failure_can_retry(client, monkeypatch):
    def fail():
        raise RuntimeError("Unavailable")
    monkeypatch.setattr(web, "setup", fail)
    assert client.post("/api/analyze/NVDA").status_code == 503
    assert client.get("/api/status").json()["model_status"] == "not_loaded"
    monkeypatch.setattr(web, "setup", lambda: object())
    assert client.post("/api/analyze/NVDA").status_code == 200


def test_missing_market_data(client, monkeypatch):
    monkeypatch.setattr(web, "obtain_ticker", lambda symbol: SimpleNamespace(info={}))
    assert client.get("/api/companies/NVDA").status_code == 502
    assert client.post("/api/analyze/NVDA").status_code == 502


def test_nvidia_analysis_replays_observed_answer(
    client, monkeypatch, nvidia_info, nvidia_observed_result,
):
    ticker = Mock(return_value=SimpleNamespace(info=nvidia_info))
    router = Mock()
    router.predict.return_value = nvidia_observed_result
    monkeypatch.setattr(web, "obtain_ticker", ticker)
    monkeypatch.setattr(web, "setup", lambda: router)
    monkeypatch.setattr(web, "decision", decision)

    snapshot = client.get("/api/companies/NVDA").json()
    response = client.post("/api/analyze/NVDA")

    assert response.status_code == 200
    result = response.json()
    ticker.assert_called_once_with("NVDA")
    router.predict.assert_called_once()
    sent_state = State.model_validate_json(router.predict.call_args.args[0])
    assert sent_state == create_state(nvidia_info)
    assert result["snapshot"] == snapshot
    assert result["snapshot"]["state"] == sent_state.model_dump()
    assert result["raw"] == nvidia_observed_result
    assert result["answers"]["market_momentum_question"]["choice"] == "negative"
    assert result["validated"] is True