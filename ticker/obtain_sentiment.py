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
    cache_file = _cache_path(symbol, limit)
    with _cache_lock:
        if cache_file.exists():
            return json.loads(cache_file.read_text())["research_text"]

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
    research_text = "\n\n".join(
        f"{article.get('title', 'Untitled')}: {article.get('summary', '')}"
        for article in ranked[:limit]
    ).strip()
    with _cache_lock:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"symbol": symbol, "limit": limit, "research_text": research_text}))
    return research_text

