from laya_model.laya_model import decision
from setup.setup import setup
from ticker.obtain_ticker import obtain_ticker
from investment_question.investment_questions import return_all_questions
from models.state import create_state
from utils.load_portfolio import load_portfolio

#todo clean imports 


def main():
    companies = load_portfolio()
    router = setup()
    questions = return_all_questions()

    for ticker_name, weight in companies.items():
        ticker = obtain_ticker(ticker_name)
        state = create_state(ticker.info)
        result = decision(state.model_dump_json(), questions, router)
        print(ticker_name, weight, result)


if __name__ == "__main__":
    main()

