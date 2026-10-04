from dotenv import load_dotenv

from laya_model.laya_model import decision_long
from setup.setup import setup
from ticker.obtain_ticker import obtain_ticker
from ticker.obtain_transcript import TranscriptError, obtain_transcript
from investment_question.investment_questions import return_research_questions
from models.state import ResearchState, create_state
from utils.load_portfolio import load_portfolio

load_dotenv()

#todo clean imports 


def main():
    companies = load_portfolio()
    router = setup()
    questions = return_research_questions()

    for ticker_name, weight in companies.items():
        quarter = input(f"{ticker_name} transcript quarter, e.g. 2024Q1 (blank to skip): ").strip()
        if not quarter:
            continue
        try:
            research_text = obtain_transcript(ticker_name, quarter)
        except TranscriptError as exc:
            print(ticker_name, "skipped:", exc)
            continue
        ticker = obtain_ticker(ticker_name)
        state = ResearchState(**create_state(ticker.info).model_dump(), research_text=research_text)
        result = decision_long(state.model_dump_json(), questions, router)
        print(ticker_name, weight, result)


if __name__ == "__main__":
    main()

