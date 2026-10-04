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
    Path(_xdg_cache_home) / "finance" / "transcripts"
    if _xdg_cache_home
    else Path(__file__).resolve().parent.parent / ".cache" / "transcripts"
)
_cache_lock = Lock()


class TranscriptError(Exception):
    """Raised when a transcript cannot be fetched or is unavailable."""


def _cache_path(symbol: str, quarter: str) -> Path:
    return CACHE_DIR / f"{symbol.upper()}_{quarter.upper()}.json"


def is_cached(symbol: str, quarter: str) -> bool:
    return _cache_path(symbol, quarter).exists()


def obtain_transcript(symbol: str, quarter: str) -> str:
    """Fetch an earnings-call transcript from Alpha Vantage and join it into one string.

    `quarter` must be in YYYYQ# format (e.g. "2024Q1"). Raises TranscriptError if the API
    key is missing, the request fails, or no transcript is available for that quarter.

    A successful fetch is cached to disk indefinitely (a published transcript never
    changes), so repeat requests for the same symbol/quarter don't spend another API call.
    Failures are never cached, so a transient error or bad quarter guess can be retried.
    """
    cache_file = _cache_path(symbol, quarter)
    with _cache_lock:
        if cache_file.exists():
            return json.loads(cache_file.read_text())["research_text"]

    api_key = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not api_key:
        raise TranscriptError("ALPHAVANTAGE_API_KEY is not set")
    try:
        response = requests.get(
            ALPHAVANTAGE_URL,
            params={
                "function": "EARNINGS_CALL_TRANSCRIPT",
                "symbol": symbol,
                "quarter": quarter,
                "apikey": api_key,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise TranscriptError(f"Transcript request failed for {symbol} {quarter}") from exc
    if not isinstance(data, dict) or "Error Message" in data or "Note" in data or "Information" in data:
        raise TranscriptError(f"Alpha Vantage rejected the request for {symbol} {quarter}")
    transcript = data.get("transcript")
    if not transcript:
        raise TranscriptError(f"No transcript available for {symbol} {quarter}")
    research_text = "\n\n".join(
        f"{turn.get('speaker', 'Unknown')}: {turn.get('content', '')}" for turn in transcript
    ).strip()
    with _cache_lock:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"symbol": symbol, "quarter": quarter, "research_text": research_text}))
    return research_text
