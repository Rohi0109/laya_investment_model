from laya_model.laya_model import decision
from setup.setup import setup
from ticker.obtain_ticker import obtain_ticker
from investment_question.investment_question import investment_question
#todo clean imports 


def main(ticker_name:str= 'AAPL'):
    router = setup()

    ticker = obtain_ticker(ticker_name)

    
    question = investment_question()

    context = f"Stock: {ticker.ticker}. PEG ratio: {ticker.info['pegRatio']}"
    
    result = decision(context, [question], router)

    answer = result["answers"][question.name]
    print(f"{answer['choice']} (confidence: {answer['answer_confidence']:.1%})")

    

    
     



if __name__ == "__main__":
    main()
