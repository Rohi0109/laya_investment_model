from typing import Annotated

from pydantic import BaseModel, StringConstraints


class State(BaseModel):
    company: str | None = None
    symbol: str | None = None
    sector: str | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    profit_margin: float | None = None
    beta: float | None = None
    debt_to_equity: float | None = None
    one_year_return: float | None = None
    distance_from_high: float | None = None


ResearchText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60000)
]


class ResearchState(State):
    research_text: ResearchText


def create_state(ticker_info: dict) -> State:
    return State(
        company=ticker_info.get('longName'),
        symbol=ticker_info.get('symbol'),
        sector=ticker_info.get('sector'),
        forward_pe=ticker_info.get('forwardPE'),
        peg_ratio=ticker_info.get('pegRatio'),
        revenue_growth=ticker_info.get('revenueGrowth'),
        earnings_growth=ticker_info.get('earningsGrowth'),
        profit_margin=ticker_info.get('profitMargins'),
        beta=ticker_info.get('beta'),
        debt_to_equity=ticker_info.get('debtToEquity'),
        one_year_return=ticker_info.get('52WeekChange'),
        distance_from_high=ticker_info.get('fiftyTwoWeekHighChangePercent'),
    )