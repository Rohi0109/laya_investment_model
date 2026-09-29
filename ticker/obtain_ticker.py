import yfinance as yf


def obtain_ticker(ticker:str)-> yf.Ticker:
   # Call the stock ticker
   ticker = yf.Ticker(ticker)

   # Get the latest day's close price or general info   
   return ticker


  