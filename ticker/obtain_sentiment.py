import json
import os
from pathlib import Path
from threading import Lock

import requests

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
# XDG_CACHE_HOME is set (and volume-mounted) in Docker so this survives container
# restarts there; unset locally, so it falls back to the repo-root .cache/ dir.
_xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
CACHE_DIR = (
    Path(_xdg_cache_home) / "finance" / "sentiment"
    if _xdg_cache_home
    else Path(__file__).resolve().parent.parent / ".cache" / "sentiment"
)
_cache_lock = Lock()


class SentimentError(Exception):
    """Raised when earnings-related news sentiment cannot be fetched."""


def _cache_path(symbol: str, limit: int) -> Path:
    return CACHE_DIR / f"{symbol.upper()}_{limit}.json"


def is_cached(symbol: str, limit: int = 1) -> bool:
    return _cache_path(symbol, limit).exists()


def _relevance(article: dict, symbol: str) -> float:
    for entry in article.get("ticker_sentiment") or []:
        if entry.get("ticker") == symbol:
            try:
                return float(entry.get("relevance_score", 0))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _fetch_ranked_articles(symbol: str, limit: int) -> list[dict]:
    """Fetch, rank, and cache the top `limit` articles for `symbol`.

    Entries contain text, relevance, and available provider provenance. Existing
    text-only cache entries remain readable without triggering new API requests.
    Shared by
    obtain_news_sentiment, obtain_top_articles, and obtain_top_articles_with_relevance,
    so all three read/write the same cache entry for a given symbol/limit pair.
    """
    cache_file = _cache_path(symbol, limit)
    with _cache_lock:
        if cache_file.exists():
            return json.loads(cache_file.read_text())["articles"]

    api_key = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not api_key:
        raise SentimentError("ALPHAVANTAGE_API_KEY is not set")
    try:
        response = requests.get(
            ALPHAVANTAGE_URL,
            params={
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "topics": "earnings",
                "limit": limit,
                "apikey": api_key,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise SentimentError(f"News sentiment request failed for {symbol}") from exc
    if not isinstance(data, dict) or "Error Message" in data or "Note" in data or "Information" in data:
        raise SentimentError(f"Alpha Vantage rejected the request for {symbol}")
    feed = data.get("feed")
    if not feed:
        raise SentimentError(f"No earnings-related news available for {symbol}")
    ranked = sorted(feed, key=lambda article: _relevance(article, symbol), reverse=True)
    articles = [
        {
            "text": f"{article.get('title', 'Untitled')}: {article.get('summary', '')}".strip(),
            "relevance": _relevance(article, symbol),
            **{
                field: article[field].strip()
                for field in ("title", "source", "url", "time_published")
                if isinstance(article.get(field), str) and article[field].strip()
            },
        }
        for article in ranked[:limit]
    ]
    with _cache_lock:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"symbol": symbol, "limit": limit, "articles": articles}))
    return articles


def obtain_news_sentiment(symbol: str, limit: int = 1) -> str:
    """Fetch earnings-related news for a symbol, ranked by relevance to that ticker.

    Alpha Vantage's `tickers` filter matches any article that merely mentions the
    symbol (e.g. unrelated institutional-holdings filings), so results are re-sorted
    by each article's own `ticker_sentiment` relevance score for `symbol` and only
    the top `limit` are kept. The API's own `limit` request parameter is not
    reliably honored, so it is enforced here instead. Raises SentimentError if the
    API key is missing, the request fails, or no articles are available.

    A successful fetch is cached to disk (this is a demo: news can go stale, but
    repeat requests for the same symbol are far more common here than fresh news).
    Failures are never cached, so a transient error can be retried.
    """
    return "\n\n".join(article["text"] for article in _fetch_ranked_articles(symbol, limit))


def obtain_top_articles(symbol: str, limit: int = 3) -> list[str]:
    """Like obtain_news_sentiment, but keeps the top `limit` articles separate.

    Each article is classified individually rather than joined into one blob, so a
    single irrelevant/noisy article in the top `limit` can't dilute the others.
    """
    return [article["text"] for article in _fetch_ranked_articles(symbol, limit)]


def obtain_top_articles_with_relevance(symbol: str, limit: int = 3) -> list[dict]:
    """Like obtain_top_articles, but also returns each article's relevance score.

    Use this when aggregating per-article decisions weighted by relevance (e.g.
    laya_model.laya_model.aggregate_decisions), since a plain text list drops the
    weighting signal.
    """
    return _fetch_ranked_articles(symbol, limit)


