import datetime

import yfinance as yf

sp500 = yf.Ticker("^GSPC")
today = datetime.datetime.now()
one_year_ago = today - datetime.timedelta(days=365)
sp500_history = sp500.history(start=one_year_ago, end=today)

print(sp500_history.head())