from laya_model.laya_model import decision
from setup.setup import setup
from ticker.obtain_ticker import obtain_ticker
from investment_question.investment_questions import return_all_questions
from laya_model.laya_model import decision
#todo clean imports 


def main(ticker_name:str= 'AAPL'):
    #for i in companies
    router = setup()

    ticker = obtain_ticker(ticker_name)



    
    questions = return_all_questions(ticker.info)

    final_result= decision("#todo add",questions,router)
    print(final_result)





    

    
     



if __name__ == "__main__":
    main('MNDY')
