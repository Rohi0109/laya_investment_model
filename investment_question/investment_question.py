from models.choice_question import ChoiceQuestion


def investment_question()->ChoiceQuestion:
    ins = 'figure out if this stock is worth inviesting in given the context'
    criteria = {
                "positive": "Easy money",
                "negative": "no shot",
                "neutral": "unknown",
            }
    investment_question = ChoiceQuestion(name = 'investment_question' , instructions=ins,criteria = criteria)
    return investment_question