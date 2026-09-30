from models.choice_question import ChoiceQuestion


def valuation_question() -> ChoiceQuestion:
    ins = 'Assess valuation using forward_pe and peg_ratio in the context of sector, revenue_growth, and earnings_growth. Use only the supplied state; null values are unknown.'
    criteria = {
        "cheap": "Valuation looks low relative to the supplied growth and sector context",
        "reasonable": "Valuation looks broadly in line with the supplied growth and sector context",
        "expensive": "Valuation looks high relative to the supplied growth and sector context",
    }
    return ChoiceQuestion(name='valuation_question', instructions=ins, criteria=criteria)


def growth_question() -> ChoiceQuestion:
    ins = 'Assess growth using revenue_growth and earnings_growth from the state. Both are fractions, not percentages. Consider their direction and consistency; null values are unknown.'
    criteria = {
        "weak": "Revenue and earnings are stagnant, declining, or show limited growth",
        "moderate": "Revenue and earnings show modest growth or mixed performance",
        "strong": "Revenue and earnings both show substantial growth",
    }
    return ChoiceQuestion(name='growth_question', instructions=ins, criteria=criteria)


def financial_health_question() -> ChoiceQuestion:
    ins = 'Assess financial health using sector, profit_margin (fraction), and debt_to_equity (percentage) from the state. These are partial indicators; do not assume missing cash flow or liquidity data. Null values are unknown.'
    criteria = {
        "weak": "Low or negative profitability and/or a high debt burden suggest financial strain",
        "moderate": "Profitability and debt levels suggest a mixed or adequate financial position",
        "strong": "Strong profitability together with a low debt burden suggests financial resilience",
    }
    return ChoiceQuestion(name='financial_health_question', instructions=ins, criteria=criteria)


def market_momentum_question() -> ChoiceQuestion:
    ins = 'Assess market momentum using one_year_return and distance_from_high from the state. Both are fractions; distance_from_high is relative to the 52-week high. Describe observed price trends, not future returns. Null values are unknown.'
    criteria = {
        "negative": "Returns indicate a downward trend, supported by a substantial retreat from the yearly high",
        "neutral": "Returns are flat or the yearly return and distance from the yearly high give mixed signals",
        "positive": "Returns indicate an upward trend, supported by trading near the yearly high",
    }
    return ChoiceQuestion(name='market_momentum_question', instructions=ins, criteria=criteria)


def risk_question() -> ChoiceQuestion:
    ins = 'Assess market sensitivity and leverage risk using sector, beta, and debt_to_equity (percentage) from the state. These metrics do not capture all investment risks. Null values are unknown.'
    criteria = {
        "low": "Lower market sensitivity and a low debt burden indicate relatively limited risk on these measures",
        "medium": "Market sensitivity and debt levels indicate moderate or mixed risk",
        "high": "Elevated market sensitivity and/or a high debt burden indicate increased risk",
    }
    return ChoiceQuestion(name='risk_question', instructions=ins, criteria=criteria)


def research_priority_question() -> ChoiceQuestion:
    ins = 'Prioritize further research using the valuation, growth, profitability, risk, and market metrics in the supplied state. Growth, profit_margin, one_year_return, and distance_from_high are fractions; debt_to_equity is a percentage. Null values are unknown. Classify research priority, not whether to buy.'
    criteria = {
        "ignore": "Weak fundamentals or an unfavorable balance of valuation and risk make research a low priority",
        "monitor": "Mixed signals or incomplete evidence warrant watching for more information",
        "investigate": "Promising fundamentals and valuation relative to risk warrant deeper research",
    }
    return ChoiceQuestion(name='research_priority_question', instructions=ins, criteria=criteria)


def return_all_questions() -> list[ChoiceQuestion]:
    return [
        research_priority_question(),
        risk_question(),
        market_momentum_question(),
        valuation_question(),
        growth_question(),
        financial_health_question(),
    ]
    




