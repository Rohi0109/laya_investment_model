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
    