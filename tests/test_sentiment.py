from unittest.mock import Mock, patch

import pytest

import ticker.obtain_sentiment as obtain_sentiment_module
from ticker.obtain_sentiment import (
    SentimentError,
    obtain_news_sentiment,
    obtain_top_articles,
    obtain_top_articles_with_relevance,
)


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(obtain_sentiment_module, "CACHE_DIR", tmp_path / "sentiment")


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    with pytest.raises(SentimentError, match="ALPHAVANTAGE_API_KEY"):
        obtain_news_sentiment("NVDA")


def test_joins_title_and_summary(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = {
        "feed": [
            {"title": "NVIDIA beats estimates", "summary": "Revenue grew 20% YoY."},
            {"title": "Analysts raise price target", "summary": "Strong data center demand cited."},
        ],
    }
    with patch("ticker.obtain_sentiment.requests.get", return_value=response) as get:
        text = obtain_news_sentiment("NVDA", limit=2)
    assert text == (
        "NVIDIA beats estimates: Revenue grew 20% YoY.\n\n"
        "Analysts raise price target: Strong data center demand cited."
    )
    assert get.call_args.kwargs["params"] == {
        "function": "NEWS_SENTIMENT",
        "tickers": "NVDA",
        "topics": "earnings",
        "limit": 2,
        "apikey": "test-key",
    }


def test_sorts_by_relevance_and_defaults_to_top_article(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = {
        "feed": [
            {
                "title": "Amazon buys more AMZN shares",
                "summary": "Unrelated institutional filing that merely mentions NVDA.",
                "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.05"}],
            },
            {
                "title": "NVIDIA beats estimates",
                "summary": "Revenue grew 20% YoY.",
                "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.95"}],
            },
        ],
    }
    with patch("ticker.obtain_sentiment.requests.get", return_value=response):
        text = obtain_news_sentiment("NVDA")
    assert text == "NVIDIA beats estimates: Revenue grew 20% YoY."


def test_limit_is_enforced_client_side_even_if_api_ignores_it(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = {
        "feed": [
            {"title": "A", "summary": "a", "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.9"}]},
            {"title": "B", "summary": "b", "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.1"}]},
        ],
    }
    with patch("ticker.obtain_sentiment.requests.get", return_value=response):
        text = obtain_news_sentiment("NVDA", limit=1)
    assert text == "A: a"


def test_top_articles_returns_a_ranked_list(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = {
        "feed": [
            {"title": "A", "summary": "a", "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.1"}]},
            {"title": "B", "summary": "b", "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.9"}]},
            {"title": "C", "summary": "c", "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.5"}]},
        ],
    }
    with patch("ticker.obtain_sentiment.requests.get", return_value=response):
        articles = obtain_top_articles("NVDA", limit=3)
    assert articles == ["B: b", "C: c", "A: a"]


def test_top_articles_and_news_sentiment_share_a_cache_entry(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = {
        "feed": [
            {"title": "A", "summary": "a"},
            {"title": "B", "summary": "b"},
        ],
    }
    with patch("ticker.obtain_sentiment.requests.get", return_value=response) as get:
        articles = obtain_top_articles("NVDA", limit=2)
        text = obtain_news_sentiment("NVDA", limit=2)
    assert articles == ["A: a", "B: b"]
    assert text == "A: a\n\nB: b"
    get.assert_called_once()


def test_top_articles_with_relevance_exposes_scores(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = {
        "feed": [
            {"title": "A", "summary": "a", "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.9"}]},
            {"title": "B", "summary": "b", "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.2"}]},
        ],
    }
    with patch("ticker.obtain_sentiment.requests.get", return_value=response):
        articles = obtain_top_articles_with_relevance("NVDA", limit=2)
    assert articles == [
        {"text": "A: a", "relevance": 0.9, "title": "A"},
        {"text": "B: b", "relevance": 0.2, "title": "B"},
    ]


def test_article_provenance_survives_ranking_and_cache(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    provenance = {
        "title": "NVIDIA: Quarterly results",
        "source": "Example News",
        "url": "https://example.com/news/results",
        "time_published": "20261005T130000",
    }
    response = Mock(status_code=200)
    response.json.return_value = {"feed": [
        {"title": "Other news", "summary": "Other."},
        {**provenance, "summary": "Revenue grew.",
         "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.9"}]},
    ]}
    with patch("ticker.obtain_sentiment.requests.get", return_value=response) as get:
        articles = obtain_top_articles_with_relevance("NVDA")
        cached = obtain_top_articles_with_relevance("NVDA")
    assert articles == cached
    assert articles[0] == {**provenance, "text": "NVIDIA: Quarterly results: Revenue grew.", "relevance": 0.9}
    assert "source" not in articles[1]
    get.assert_called_once()


def test_legacy_article_cache_remains_usable_without_api(monkeypatch):
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    obtain_sentiment_module.CACHE_DIR.mkdir()
    cache_file = obtain_sentiment_module.CACHE_DIR / "NVDA_3.json"
    original = '{"articles": [{"text": "Saved article: Summary", "relevance": 0.9}]}'
    cache_file.write_text(original)
    with patch("ticker.obtain_sentiment.requests.get") as get:
        articles = obtain_top_articles_with_relevance("NVDA")
    assert articles == [{"text": "Saved article: Summary", "relevance": 0.9}]
    assert cache_file.read_text() == original
    get.assert_not_called()


def test_caches_successful_fetch_without_repeat_api_call(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = {"feed": [{"title": "A", "summary": "a"}]}
    with patch("ticker.obtain_sentiment.requests.get", return_value=response) as get:
        first = obtain_news_sentiment("NVDA")
        second = obtain_news_sentiment("NVDA")
    assert first == second == "A: a"
    get.assert_called_once()


def test_does_not_cache_failures(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    failure = Mock(status_code=200)
    failure.json.return_value = {"feed": []}
    with patch("ticker.obtain_sentiment.requests.get", return_value=failure):
        with pytest.raises(SentimentError):
            obtain_news_sentiment("NVDA")
    success = Mock(status_code=200)
    success.json.return_value = {"feed": [{"title": "A", "summary": "a"}]}
    with patch("ticker.obtain_sentiment.requests.get", return_value=success) as get:
        text = obtain_news_sentiment("NVDA")
    assert text == "A: a"
    get.assert_called_once()


def test_limit_is_configurable(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = {"feed": [{"title": "A", "summary": "B"}]}
    with patch("ticker.obtain_sentiment.requests.get", return_value=response) as get:
        obtain_news_sentiment("NVDA", limit=10)
    assert get.call_args.kwargs["params"]["limit"] == 10


@pytest.mark.parametrize("payload", [
    {},
    {"feed": []},
    {"feed": None},
    {"Error Message": "Invalid API call"},
    {"Note": "rate limit"},
    {"Information": "rate limit"},
])
def test_rejects_missing_or_errored_feed(monkeypatch, payload):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    response = Mock(status_code=200)
    response.json.return_value = payload
    with patch("ticker.obtain_sentiment.requests.get", return_value=response):
        with pytest.raises(SentimentError):
            obtain_news_sentiment("NVDA")


def test_wraps_request_failures(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    import requests
    with patch("ticker.obtain_sentiment.requests.get", side_effect=requests.ConnectionError("down")):
        with pytest.raises(SentimentError):
            obtain_news_sentiment("NVDA")


@pytest.mark.api_integration
def test_real_api_fetches_earnings_news():
    """Hits the live Alpha Vantage API. Run with: uv run pytest -m api_integration"""
    text = obtain_news_sentiment("NVDA")
    assert len(text) > 0
    assert ":" in text


@pytest.mark.api_integration
@pytest.mark.laya_integration
def test_real_top_article_classified_by_laya():
    """Proves the top relevant article is usable as Laya input, not just text.

    Hits the live Alpha Vantage API and loads the real model. Run with:
    uv run pytest -m "api_integration and laya_integration" -v
    """
    from laya import Router

    from laya_model.laya_model import decision
    from models.choice_question import ChoiceQuestion

    text = obtain_news_sentiment("NVDA")
    question = ChoiceQuestion(
        name="news_sentiment",
        instructions="What is the sentiment of this stock news?",
        criteria={
            "positive": "Favorable news",
            "negative": "Unfavorable news",
            "neutral": "Neither favorable nor unfavorable",
        },
    )
    result = decision(text, [question], router=Router())
    assert result["answers"]["news_sentiment"]["choice"] in {"positive", "negative", "neutral"}


@pytest.mark.api_integration
@pytest.mark.laya_integration
def test_real_top_3_articles_each_classified_by_laya():
    """Proves the top-3 relevance-ranked articles can each be classified on their own.

    Hits the live Alpha Vantage API and loads the real model. Run with:
    uv run pytest -m "api_integration and laya_integration" -v
    """
    from laya import Router

    from laya_model.laya_model import decision_each
    from models.choice_question import ChoiceQuestion

    articles = obtain_top_articles("NVDA", limit=3)
    assert 1 <= len(articles) <= 3
    question = ChoiceQuestion(
        name="news_sentiment",
        instructions="What is the sentiment of this stock news?",
        criteria={
            "positive": "Favorable news",
            "negative": "Unfavorable news",
            "neutral": "Neither favorable nor unfavorable",
        },
    )
    results = decision_each(articles, [question], router=Router())
    assert len(results) == len(articles)
    for result in results:
        assert result["answers"]["news_sentiment"]["choice"] in {"positive", "negative", "neutral"}


@pytest.mark.api_integration
@pytest.mark.laya_integration
def test_real_top_3_articles_aggregated_into_one_verdict():
    """Proves the top-3 articles can be classified and then combined into one answer,
    weighted by each article's own relevance score.

    Hits the live Alpha Vantage API and loads the real model. Run with:
    uv run pytest -m "api_integration and laya_integration" -v
    """
    from laya import Router

    from laya_model.laya_model import aggregate_decisions, decision_each
    from models.choice_question import ChoiceQuestion

    articles = obtain_top_articles_with_relevance("NVDA", limit=3)
    assert 1 <= len(articles) <= 3
    question = ChoiceQuestion(
        name="news_sentiment",
        instructions="What is the sentiment of this stock news?",
        criteria={
            "positive": "Favorable news",
            "negative": "Unfavorable news",
            "neutral": "Neither favorable nor unfavorable",
        },
    )
    texts = [article["text"] for article in articles]
    weights = [article["relevance"] for article in articles]
    results = decision_each(texts, [question], router=Router())
    verdict = aggregate_decisions(results, weights)
    assert verdict["answers"]["news_sentiment"]["choice"] in {"positive", "negative", "neutral"}

