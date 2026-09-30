from unittest.mock import Mock

import pytest
from laya import Router
from pydantic import ValidationError

from investment_question.investment_questions import return_all_questions
from laya_model.laya_model import decision
from models.choice_question import ChoiceQuestion
from models.state import State, create_state
from setup.setup import setup


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


def test_nvidia_snapshot_units(nvidia_info):
    state = create_state(nvidia_info)
    assert state.symbol == "NVDA"
    assert state.one_year_return == 0.21346939
    assert state.distance_from_high == -0.034497287
    assert state.revenue_growth == 1.059
    assert state.earnings_growth == 1.278
    assert state.profit_margin == 0.63663
    assert state.debt_to_equity == 16.971
    assert state.distance_from_high == pytest.approx(
        nvidia_info["regularMarketPrice"] / nvidia_info["fiftyTwoWeekHigh"] - 1,
        abs=1e-6,
    )
    assert State.model_validate_json(state.model_dump_json()) == state


def test_nvidia_decision_forwards_payload(nvidia_info, nvidia_observed_result):
    router = Mock(spec=Router)
    router.predict.return_value = nvidia_observed_result
    state_json = create_state(nvidia_info).model_dump_json()
    questions = return_all_questions()

    result = decision(state_json, questions, router)

    router.predict.assert_called_once_with(
        state_json,
        {question.name: question.model_dump(exclude={"name"}) for question in questions},
    )
    assert result is nvidia_observed_result
    momentum = router.predict.call_args.args[1]["market_momentum_question"]
    assert momentum["type"] == "choice"
    assert set(momentum["criteria"]) == {"negative", "neutral", "positive"}


@pytest.fixture(scope="module")
def nvidia_router():
    return setup()


@pytest.mark.laya_integration
@pytest.mark.parametrize("overrides, expected", [
    pytest.param({}, "positive", id="captured-nvidia-positive"),
    pytest.param(
        {"52WeekChange": -0.40, "fiftyTwoWeekHighChangePercent": -0.45},
        "negative", id="synthetic-nvidia-negative",
    ),
    pytest.param(
        {"52WeekChange": 0.0, "fiftyTwoWeekHighChangePercent": -0.03},
        "neutral", id="synthetic-nvidia-flat",
    ),
])
def test_nvidia_momentum_regression(nvidia_info, nvidia_router, overrides, expected):
    state = create_state(nvidia_info | overrides)
    result = decision(state.model_dump_json(), return_all_questions(), nvidia_router)
    answer = result["answers"]["market_momentum_question"]

    assert result["usage"]["truncated"] is False
    assert answer["type"] == "choice"
    assert answer["choice"] == expected, (
        f"NVDA one_year_return={state.one_year_return}, "
        f"distance_from_high={state.distance_from_high}: "
        f"expected {expected!r}, received {answer!r}"
    )


@pytest.mark.laya_integration
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

    




