from unittest.mock import Mock

import pytest
from laya import Router
from pydantic import ValidationError

from investment_question.investment_questions import (
    return_all_questions,
    return_article_questions,
    return_research_questions,
)
from laya_model.laya_model import aggregate_decisions, decision, decision_each, decision_long
from models.choice_question import ChoiceQuestion
from models.state import ResearchState, State, create_state
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


def test_research_state():
    state = ResearchState(company="NVIDIA", research_text="  Margins are expanding.  ")
    assert state.research_text == "Margins are expanding."
    assert ResearchState.model_validate_json(state.model_dump_json()) == state
    assert len(ResearchState(research_text="a" * 60000).research_text) == 60000
    for text in ["", "   ", "a" * 60001]:
        with pytest.raises(ValidationError):
            ResearchState(research_text=text)
    with pytest.raises(ValidationError):
        ResearchState.model_validate({})


def test_research_questions():
    # financial_pressure_question and valuation_assessment_question are excluded: real-transcript
    # testing showed the model answers them unreliably.
    questions = return_research_questions()
    assert [question.name for question in questions] == [
        "growth_outlook_question", "profitability_outlook_question",
    ]
    assert all(isinstance(question, ChoiceQuestion) for question in questions)
    assert all("unknown" in question.instructions.lower() for question in questions)
    assert [set(question.criteria) for question in questions] == [
        {"improving", "stable", "deteriorating", "not_discussed"},
        {"expanding", "stable", "compressing", "not_discussed"},
    ]


def test_article_questions():
    # Separate from return_research_questions(): tuned for a single short news article
    # rather than a long excerpt or full transcript.
    questions = return_article_questions()
    assert [question.name for question in questions] == [
        "market_reaction_question", "materiality_question",
    ]
    assert all(isinstance(question, ChoiceQuestion) for question in questions)
    assert [set(question.criteria) for question in questions] == [
        {"bullish", "bearish", "neutral", "not_discussed"},
        {"major", "minor", "routine", "unclear"},
    ]


def test_research_decision_forwards_payload(nvidia_info):
    router = Mock(spec=Router)
    state = ResearchState(**create_state(nvidia_info).model_dump(), research_text="Margins are expanding.")
    questions = return_research_questions()
    result = decision_long(state.model_dump_json(), questions, router)
    router.predict_long.assert_called_once_with(
        state.model_dump_json(),
        {question.name: question.model_dump(exclude={"name"}) for question in questions},
    )
    assert result is router.predict_long.return_value


def test_nvidia_research_classification():
    """A fictional excerpt with explicit financial claims, not an actual NVIDIA report."""
    state = ResearchState(
        company="NVIDIA Corporation",
        symbol="NVDA",
        sector="Technology",
        forward_pe=14.562609,
        peg_ratio=0.47,
        revenue_growth=1.059,
        earnings_growth=1.278,
        profit_margin=0.63663,
        beta=2.217,
        debt_to_equity=16.971,
        one_year_return=0.21346939,
        distance_from_high=-0.034497287,
        research_text=(
            "NVIDIA's revenue growth is accelerating as customer demand strengthens. "
            "Management raised its growth outlook. Operating margins are expected to expand "
            "as pricing power and operating leverage improve. Strong free cash flow and ample "
            "liquidity comfortably cover debt obligations, with no funding pressure. "
            "However, the shares look expensive relative to peers and estimated fair value; "
            "the valuation requires unusually optimistic assumptions."
        ),
    )
    router = setup()
    result = decision_long(state.model_dump_json(), return_research_questions(), router)
    print(result)
    assert not result["usage"]["truncated"]
    assert {name: answer["choice"] for name, answer in result["answers"].items()} == {
        "growth_outlook_question": "improving",
        "profitability_outlook_question": "expanding",
    }


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


def test_decision_each_classifies_every_text_independently():
    router = Mock(spec=Router)
    router.predict.side_effect = [
        {"answers": {"news_sentiment": {"type": "choice", "choice": "positive"}}},
        {"answers": {"news_sentiment": {"type": "choice", "choice": "negative"}}},
    ]
    question = ChoiceQuestion(
        name="news_sentiment",
        instructions="What is the sentiment of this stock news?",
        criteria={"positive": "Favorable news", "negative": "Unfavorable news", "neutral": "Neither"},
    )
    texts = ["Revenue beat estimates.", "Guidance was cut sharply."]

    results = decision_each(texts, [question], router)

    assert router.predict.call_count == 2
    assert [call.args[0] for call in router.predict.call_args_list] == texts
    assert [r["answers"]["news_sentiment"]["choice"] for r in results] == ["positive", "negative"]


def test_aggregate_decisions_picks_the_relevance_weighted_winner():
    results = [
        {"answers": {"news_sentiment": {"type": "choice", "choice": "negative"}}},
        {"answers": {"news_sentiment": {"type": "choice", "choice": "positive"}}},
        {"answers": {"news_sentiment": {"type": "choice", "choice": "positive"}}},
    ]
    # A single highly-relevant "negative" article outweighs two barely-relevant "positive" ones.
    weights = [0.9, 0.1, 0.1]

    verdict = aggregate_decisions(results, weights)

    assert verdict == {"answers": {"news_sentiment": {"type": "choice", "choice": "negative"}}}


def test_aggregate_decisions_rejects_mismatched_lengths():
    results = [{"answers": {"news_sentiment": {"type": "choice", "choice": "positive"}}}]
    with pytest.raises(ValueError):
        aggregate_decisions(results, weights=[0.5, 0.5])


def test_nvidia_momentum_regression():
    state = State(
        company="NVIDIA Corporation",
        symbol="NVDA",
        sector="Technology",
        forward_pe=14.562609,
        peg_ratio=0.47,
        revenue_growth=1.059,
        earnings_growth=1.278,
        profit_margin=0.63663,
        beta=2.217,
        debt_to_equity=16.971,
        one_year_return=0.21346939,
        distance_from_high=-0.034497287,
    )
    router = setup()
    questions = return_all_questions()
    result = decision(state.model_dump_json(), questions, router)

    print(result)
    assert result["answers"]["market_momentum_question"]["choice"] == "positive"


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

    




