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
    