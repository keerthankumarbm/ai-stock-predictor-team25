import yfinance as yf
import pandas as pd

stocks = [
    "TCS.NS",
    "RELIANCE.NS",
    "HDFCBANK.NS",
    "IDFCFIRSTB.NS",
    "INFY.NS",
    "SBIN.NS",
    "LT.NS",
    "ITC.NS"
]

all_data = []

for stock in stocks:
    print("Downloading:", stock)
    df = yf.download(stock, period="5y", progress=False)

    df.reset_index(inplace=True)

    df["Symbol"] = stock.replace(".NS", "")

    df = df[["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]]

    all_data.append(df)

final_df = pd.concat(all_data, ignore_index=True)

final_df.to_csv("stock_data.csv", index=False)

print("Dataset created successfully!")