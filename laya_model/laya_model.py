from laya import Router
from models.choice_question import ChoiceQuestion





def decision(state: str, questions: list[ChoiceQuestion],router:Router) -> dict:
    return router.predict(
        state,
        {
            question.name: question.model_dump(exclude={"name"})
            for question in questions
        },
    )


def decision_long(state: str, questions: list[ChoiceQuestion], router: Router) -> dict:
    """Like decision(), but scans the full state across overlapping windows instead of
    truncating to a single one. Use this for research_text that may exceed one window
    (e.g. a full transcript), since decision()'s single-window predict() silently drops
    anything past the model's token budget.
    """
    return router.predict_long(
        state,
        {
            question.name: question.model_dump(exclude={"name"})
            for question in questions
        },
    )


def decision_each(texts: list[str], questions: list[ChoiceQuestion], router: Router) -> list[dict]:
    """Classify each text independently with the same questions, one result per text.

    Each article is short enough for a single window, so this calls decision() rather
    than decision_long() per text. The same questions are reused for every article for
    now; weighting/aggregating per-article results by relevance is a likely next step.
    """
    return [decision(text, questions, router) for text in texts]


def aggregate_decisions(results: list[dict], weights: list[float]) -> dict:
    """Combine per-article decision() results into one verdict per question.

    Each question's choice is picked by a relevance-weighted vote across articles
    (sum each choice's weights, keep the highest), so one highly-relevant article
    can outweigh several barely-relevant ones instead of a flat majority vote.
    """
    if len(results) != len(weights):
        raise ValueError("results and weights must be the same length")
    if not results:
        raise ValueError("results must not be empty")
    answers = {}
    for name in results[0]["answers"]:
        totals: dict[str, float] = {}
        for result, weight in zip(results, weights):
            choice = result["answers"][name]["choice"]
            totals[choice] = totals.get(choice, 0.0) + weight
        answers[name] = {"type": "choice", "choice": max(totals, key=totals.get)}
    return {"answers": answers}
