import logging

import pytest
from laya_model.laya_model import decision
from models.choice_question import ChoiceQuestion
from laya import Router
from investment_question.investment_questions import return_all_questions
from models.state import State, create_state
from pydantic import ValidationError


def test_create_state():
    info = {
        "longName": "NVIDIA Corporation", "symbol": "NVDA", "sector": "Technology",
        "forwardPE": 31.2, "pegRatio": 1.4, "revenueGrowth": 0.55,
        "earningsGrowth": 0.62, "profitMargins": 0.55, "beta": 2.1,
        "debtToEquity": 15, "52WeekChange": 0.42,
        "fiftyTwoWeekHighChangePercent": -0.07,
    }
    state = create_state(info)
    assert state.model_dump() == {
        "company": "NVIDIA Corporation", "symbol": "NVDA", "sector": "Technology",
        "forward_pe": 31.2, "peg_ratio": 1.4, "revenue_growth": 0.55,
        "earnings_growth": 0.62, "profit_margin": 0.55, "beta": 2.1,
        "debt_to_equity": 15, "one_year_return": 0.42, "distance_from_high": -0.07,
    }
    assert State.model_validate_json(state.model_dump_json()) == state


def test_create_state_missing_and_zero_values():
    assert all(value is None for value in create_state({}).model_dump().values())
    assert create_state({"revenueGrowth": 0, "beta": None}).revenue_growth == 0
    with pytest.raises(ValidationError):
        create_state({"forwardPE": "invalid"})


def test_return_all_questions():
    questions = return_all_questions()
    assert [question.name for question in questions] == [
        "research_priority_question", "risk_question", "market_momentum_question",
        "valuation_question", "growth_question", "financial_health_question",
    ]
    assert all(isinstance(question, ChoiceQuestion) for question in questions)
    assert all(len(question.criteria) == 3 for question in questions)


def test_get_decision():
    router = Router ()
    questions = [
     ChoiceQuestion(
        name = 'test1' ,
         instructions="What is the sentiment of this stock news?",
        criteria={
            "positive": "Favorable news",
            "negative": "Unfavorable news",
            "neutral": "Neither favorable nor unfavorable",
        },
    )
    ]

    result = decision("Revenue was 100000000% more than expectations", questions,router=router)

    print(result)
    
    assert isinstance(result["answers"], dict)

    




