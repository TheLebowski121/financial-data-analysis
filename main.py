import pandas as pd
import yfinance as yf

df = yf.download("AAPL", start="2020-01-01", end="2026-10-15", progress=False)

print(f"Downloaded {len(df)} rows of data.")
print(df)
df.info()
print(df.describe())

df["Daily Return"] = df["Close", "AAPL"].pct_change()
print(df[["Daily Return"]].tail(10) * 100)  # Display the last 10 daily returns as percentages
print("Average Daily Return:", df["Daily Return"].mean() * 100, "%") #calculate and print the average daily return as a percentage
appl_data = yf.Ticker("AAPL")
print("Apple P/E Ratio:", appl_data.info["trailingPE"])  # Print the trailing P/E ratio of Apple
print(appl_data.actions)  # Print the actions (dividends and splits) of Apple


print(appl_data.actions[appl_data.actions["Stock Splits"] > 0]) #Boolean indexing to filter and display only the rows where stock splits occurred
print("\n" + "=" * 60)
print("Apple Major Holders:")
print("=" * 60)
print(appl_data.major_holders)

print("\n" + "=" * 60)
print("Apple Institutional Holders:")
print("=" * 60)
print(appl_data.institutional_holders)

print("\n" + "=" * 60)
print("Apple Income Statements:")
print("=" * 60)
print(appl_data.financials) #print the financial statements of Apple

print("\n" + "=" * 60)
print("Apple Balance Sheet:")
print("=" * 60)
print(appl_data.balance_sheet) #print the balance sheet of Apple
print("\n" + "=" * 60)
print("Apple Cash Flow Statement:")
print("=" * 60)
print(appl_data.cashflow) #print the cash flow statement of Apple
print("\n" + "=" * 60)
print("Apple Free Cash Flow:")
print("=" * 60)
print(appl_data.cashflow.loc["Free Cash Flow"] / 1_000_000_000) #print the free cash flow of Apple from the cash flow statement in Billions
print("\n" + "=" * 60)
print("Apple Total Revenue:")
print("=" * 60)
print(appl_data.financials.loc["Total Revenue"] / 1_000_000_000)#print the total revenue of Apple from the financial statements in Billions
print("\n" + "=" * 60)


print("\n" + "=" * 60)
print("Apple Total Revenue Percentage Change:")
print(appl_data.financials.loc["Total Revenue"].sort_index().pct_change() * 100) #calculate and print the percentage change in total revenue over time
print("=" * 60)

print("\n" + "=" * 60)
print("Net Profit Margin:")
print(appl_data.financials.loc["Net Income"] / appl_data.financials.loc["Total Revenue"] * 100) #calculate and print the net profit margin
print("=" * 60)


print("\n" + "=" * 60)
print("Apple Free Cash Flow Margin (%):")
print("=" * 60)
print(appl_data.cashflow.loc["Free Cash Flow"] / appl_data.financials.loc["Total Revenue"] * 100) # Calculate Apple's free cash flow margin as a percentage of total revenue


print("\n" + "=" * 60)
print("Apple Calendar Events:")
print("=" * 60)
print(appl_data.calendar) #print the calendar events of Apple
