from laya_model.laya_model import decision
from setup.setup import setup
from ticker.obtain_ticker import obtain_ticker
from investment_question.investment_questions import return_all_questions
from models.state import create_state
#todo clean imports 


def main(ticker_name:str= 'AAPL'):
    #for i in companies
    router = setup()

    ticker = obtain_ticker(ticker_name)
    state = create_state(ticker.info)



    
    questions = return_all_questions()

    final_result = decision(state.model_dump_json(), questions, router)
    print(final_result)





    

    
     



if __name__ == "__main__":
    main('MNDY')
