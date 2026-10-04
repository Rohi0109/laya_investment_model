from unittest.mock import Mock, patch

import pytest

import ticker.obtain_transcript as obtain_transcript_module
from ticker.obtain_transcript import TranscriptError, obtain_transcript


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(obtain_transcript_module, "CACHE_DIR", tmp_path / "transcripts")


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    with pytest.raises(TranscriptError, match="ALPHAVANTAGE_API_KEY"):
        obtain_transcript("IBM", "2024Q1")


def test_joins_speaker_and_content(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = {
        "symbol": "IBM",
        "quarter": "2024Q1",
        "transcript": [
            {"speaker": "Arvind Krishna", "content": "Revenue grew 3%.", "sentiment": "0.6"},
            {"speaker": "James Kavanaugh", "content": "Cash flow was strong.", "sentiment": "0.5"},
        ],
    }
    with patch("ticker.obtain_transcript.requests.get", return_value=response) as get:
        text = obtain_transcript("IBM", "2024Q1")
    assert text == "Arvind Krishna: Revenue grew 3%.\n\nJames Kavanaugh: Cash flow was strong."
    assert get.call_args.kwargs["params"] == {
        "function": "EARNINGS_CALL_TRANSCRIPT",
        "symbol": "IBM",
        "quarter": "2024Q1",
        "apikey": "test-key",
    }


def test_caches_successful_fetch_without_repeat_api_call(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = {
        "symbol": "IBM",
        "quarter": "2024Q1",
        "transcript": [{"speaker": "Arvind Krishna", "content": "Revenue grew 3%."}],
    }
    with patch("ticker.obtain_transcript.requests.get", return_value=response) as get:
        first = obtain_transcript("IBM", "2024Q1")
        second = obtain_transcript("IBM", "2024Q1")
    assert first == second == "Arvind Krishna: Revenue grew 3%."
    get.assert_called_once()


def test_does_not_cache_failures(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    failure = Mock(status_code=200)
    failure.json.return_value = {"transcript": []}
    with patch("ticker.obtain_transcript.requests.get", return_value=failure) as get:
        with pytest.raises(TranscriptError):
            obtain_transcript("IBM", "2024Q1")
    success = Mock(status_code=200)
    success.json.return_value = {
        "transcript": [{"speaker": "Arvind Krishna", "content": "Revenue grew 3%."}],
    }
    with patch("ticker.obtain_transcript.requests.get", return_value=success) as get:
        text = obtain_transcript("IBM", "2024Q1")
    assert text == "Arvind Krishna: Revenue grew 3%."
    get.assert_called_once()


@pytest.mark.parametrize("payload", [
    {},
    {"transcript": []},
    {"transcript": None},
    {"Error Message": "Invalid API call"},
    {"Note": "rate limit"},
])
def test_rejects_missing_or_errored_transcript(monkeypatch, payload):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = payload
    with patch("ticker.obtain_transcript.requests.get", return_value=response):
        with pytest.raises(TranscriptError):
            obtain_transcript("IBM", "2024Q1")


def test_wraps_request_failures(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    import requests
    with patch("ticker.obtain_transcript.requests.get", side_effect=requests.ConnectionError("down")):
        with pytest.raises(TranscriptError):
            obtain_transcript("IBM", "2024Q1")


@pytest.mark.api_integration
def test_real_api_fetches_a_transcript():
    """Hits the live Alpha Vantage API. Run with: uv run pytest -m api_integration"""
    text = obtain_transcript("IBM", "2024Q1")
    assert len(text) > 500
    assert ":" in text

