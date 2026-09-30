from models.choice_question import ChoiceQuestion


def valuation_question(symbol, sector, forward_pe, peg_ratio, revenue_growth, earnings_growth) -> ChoiceQuestion:
    ins = f"""Assess valuation using only the supplied data.
Stock: {symbol}
Sector: {sector}
Forward P/E: {forward_pe}
PEG ratio: {peg_ratio}
Revenue growth (fraction): {revenue_growth}
Earnings growth (fraction): {earnings_growth}"""
    criteria = {
        "cheap": "Valuation looks low relative to the supplied growth and sector context",
        "reasonable": "Valuation looks broadly in line with the supplied growth and sector context",
        "expensive": "Valuation looks high relative to the supplied growth and sector context",
    }
    return ChoiceQuestion(name='valuation_question', instructions=ins, criteria=criteria)


def growth_question(revenue_growth, earnings_growth) -> ChoiceQuestion:
    ins = f"""Assess growth using revenue growth and earnings growth. Consider their direction and consistency.
Revenue growth (fraction): {revenue_growth}
Earnings growth (fraction): {earnings_growth}"""
    criteria = {
        "weak": "Revenue and earnings are stagnant, declining, or show limited growth",
        "moderate": "Revenue and earnings show modest growth or mixed performance",
        "strong": "Revenue and earnings both show substantial growth",
    }
    return ChoiceQuestion(name='growth_question', instructions=ins, criteria=criteria)


def financial_health_question(sector, profit_margin, debt_to_equity) -> ChoiceQuestion:
    ins = f"""Assess financial health using profit margin and debt/equity. These are partial indicators; do not assume missing cash flow or liquidity data.
Sector: {sector}
Profit margin (fraction): {profit_margin}
Debt/equity (%): {debt_to_equity}"""
    criteria = {
        "weak": "Low or negative profitability and/or a high debt burden suggest financial strain",
        "moderate": "Profitability and debt levels suggest a mixed or adequate financial position",
        "strong": "Strong profitability together with a low debt burden suggests financial resilience",
    }
    return ChoiceQuestion(name='financial_health_question', instructions=ins, criteria=criteria)


def market_momentum_question(one_year_return, distance_from_high) -> ChoiceQuestion:
    ins = f"""Assess market momentum using the one-year return and distance from the 52-week high. Describe observed price trends, not future returns.
1 year return (fraction): {one_year_return}
Distance from 52 week high (fraction): {distance_from_high}"""
    criteria = {
        "negative": "Returns indicate a downward trend, supported by a substantial retreat from the yearly high",
        "neutral": "Returns are flat or the yearly return and distance from the yearly high give mixed signals",
        "positive": "Returns indicate an upward trend, supported by trading near the yearly high",
    }
    return ChoiceQuestion(name='market_momentum_question', instructions=ins, criteria=criteria)


def risk_question(sector, beta, debt_to_equity) -> ChoiceQuestion:
    ins = f"""Assess market sensitivity and leverage risk using beta and debt/equity. These metrics do not capture all investment risks.
Sector: {sector}
Beta: {beta}
Debt/equity (%): {debt_to_equity}"""
    criteria = {
        "low": "Lower market sensitivity and a low debt burden indicate relatively limited risk on these measures",
        "medium": "Market sensitivity and debt levels indicate moderate or mixed risk",
        "high": "Elevated market sensitivity and/or a high debt burden indicate increased risk",
    }
    return ChoiceQuestion(name='risk_question', instructions=ins, criteria=criteria)


def research_priority_question(
    symbol, sector, forward_pe, peg_ratio, revenue_growth, earnings_growth,
    profit_margin, beta, debt_to_equity, one_year_return, distance_from_high,
) -> ChoiceQuestion:
    ins = f"""Prioritize further research using only the supplied data. Classify research priority, not whether to buy.
Stock: {symbol}
Sector: {sector}
Forward P/E: {forward_pe}
PEG ratio: {peg_ratio}
Revenue growth (fraction): {revenue_growth}
Earnings growth (fraction): {earnings_growth}
Profit margin (fraction): {profit_margin}
Beta: {beta}
Debt/equity (%): {debt_to_equity}
1 year return (fraction): {one_year_return}
Distance from 52 week high (fraction): {distance_from_high}"""
    criteria = {
        "ignore": "Weak fundamentals or an unfavorable balance of valuation and risk make research a low priority",
        "monitor": "Mixed signals or incomplete evidence warrant watching for more information",
        "investigate": "Promising fundamentals and valuation relative to risk warrant deeper research",
    }
    return ChoiceQuestion(name='research_priority_question', instructions=ins, criteria=criteria)


def return_all_questions(ticker_info: dict) -> list[ChoiceQuestion]:
    return [
        research_priority_question(
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
        ),
        risk_question(
            sector=ticker_info.get('sector'),
            beta=ticker_info.get('beta'),
            debt_to_equity=ticker_info.get('debtToEquity'),
        ),
        market_momentum_question(
            one_year_return=ticker_info.get('52WeekChange'),
            distance_from_high=ticker_info.get('fiftyTwoWeekHighChangePercent'),
        ),
        valuation_question(
            symbol=ticker_info.get('symbol'),
            sector=ticker_info.get('sector'),
            forward_pe=ticker_info.get('forwardPE'),
            peg_ratio=ticker_info.get('pegRatio'),
            revenue_growth=ticker_info.get('revenueGrowth'),
            earnings_growth=ticker_info.get('earningsGrowth'),
        ),
        growth_question(
            revenue_growth=ticker_info.get('revenueGrowth'),
            earnings_growth=ticker_info.get('earningsGrowth'),
        ),
        financial_health_question(
            sector=ticker_info.get('sector'),
            profit_margin=ticker_info.get('profitMargins'),
            debt_to_equity=ticker_info.get('debtToEquity'),
        ),
    ]
    




