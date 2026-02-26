import yfinance as yf
import pandas as pd

stock = "TCS.NS"

# IMPORTANT: auto_adjust=False + group_by='column'
data = yf.download(
    stock,
    start="2019-01-01",
    end="2024-12-31",
    auto_adjust=False,
    group_by='column'
)

# Reset index so Date becomes column
data.reset_index(inplace=True)

# Save clean CSV
data.to_csv("stock_data.csv", index=False)

print("Clean data saved!")
print(data.head())
