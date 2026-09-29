import logging

import pytest
from laya_model.laya_model import decision
from models.choice_question import ChoiceQuestion
from laya import Router


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

    




