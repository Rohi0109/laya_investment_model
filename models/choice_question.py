from typing import Literal
from pydantic import BaseModel

class ChoiceQuestion(BaseModel):
    name: str
    type: Literal["choice"] = "choice"
    instructions: str
    criteria: dict[str, str]

