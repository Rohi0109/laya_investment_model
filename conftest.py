import pytest


@pytest.fixture
def nvidia_info():
    """Yahoo fields captured on 2026-09-30; fixed data, not a live quote."""
    return {
        "longName": "NVIDIA Corporation",
        "symbol": "NVDA",
        "sector": "Technology",
        "forwardPE": 14.562609,
        "pegRatio": 0.47,
        "revenueGrowth": 1.059,
        "earningsGrowth": 1.278,
        "profitMargins": 0.63663,
        "beta": 2.217,
        "debtToEquity": 16.971,
        "52WeekChange": 0.21346939,
        "fiftyTwoWeekHighChangePercent": -0.034497287,
        "regularMarketPrice": 228.38,
        "fiftyTwoWeekHigh": 236.54,
    }


@pytest.fixture
def nvidia_observed_result():
    """Replay the observed choices, including the incorrect momentum answer."""
    choices = {
        "research_priority_question": "investigate",
        "risk_question": "medium",
        "market_momentum_question": "negative",
        "valuation_question": "reasonable",
        "growth_question": "strong",
        "financial_health_question": "strong",
    }
    return {
        "answers": {
            name: {"type": "choice", "choice": choice}
            for name, choice in choices.items()
        }
    }