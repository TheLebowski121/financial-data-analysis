import pandas as pd
import yfinance as yf
# Download historical stock data for Apple (AAPL) from January 1, 2020, to October 15, 2026, without showing the progress bar
ticker_input = input(
    "enter comparable company tickers separated by commas (e.g., AAPL, MSFT, GOOGL): "
).strip().upper()  
# Prompt the user to input comparable company tickers, remove whitespace, and convert to uppercase for consistency.

tickers = list(dict.fromkeys(
    ticker.strip()
    for ticker in ticker_input.split(",")
    if ticker.strip()
))
# Create a list of unique ticker symbols by splitting the input string, stripping whitespace, and removing duplicates while preserving the order.

if not tickers:
    raise SystemExit("Please enter at least one valid ticker symbol.")
# Exit the program if no valid ticker symbols are provided.

print("\nselected comparable companies")
print(",".join(tickers))  
# Display the selected comparable companies.
comps_data = {}
# Loop through each ticker symbol, download its historical stock data, and store it in a dictionary.
for ticker in tickers:
    print(f"\nCollecting data for {ticker}...")
    company = yf.Ticker(ticker)
    comps_data[ticker] = {
        "annual_income": company.financials,
        "quarterly_income": company.quarterly_financials,
        "annual_balance_sheet": company.balance_sheet,
        "quarterly_balance_sheet": company.quarterly_balance_sheet,
    }
    # Print the collected data for each company.
for ticker, statements in comps_data.items():
    quarterly_income = statements["quarterly_income"]

    print(f"\n{ticker} — Available quarterly income periods:")

    if quarterly_income.empty:
        print("No quarterly income data returned.")
    else:
        for period in quarterly_income.columns:
            print(period.strftime("%Y-%m-%d"))
            # Print the available quarterly income periods for each company, formatting the dates for better readability.
for ticker, statements in comps_data.items():
    quarterly_income = statements["quarterly_income"]

    if quarterly_income.empty:
        continue

    latest_four = quarterly_income.sort_index(
        axis=1, ascending=False
    ).iloc[:, :4]

    print(f"\n{ticker} — Revenue for latest four quarters:")
    print(latest_four.reindex(["Total Revenue"]).to_string(
        float_format=lambda value: f"{value:,.0f}",
        na_rep="MISSING"
    )) # Print the total revenue for the latest four quarters of each company, formatting the numbers with commas and handling missing values appropriately.

    revenue = latest_four.reindex(["Total Revenue"]).iloc[0]

    periods = pd.DatetimeIndex(latest_four.columns).sort_values()
    gaps = (periods[1:] - periods[:-1]).days

    consecutive_quarters = (
        len(periods) == 4
        and periods.is_unique
        and all(70 <= gap <= 110 for gap in gaps)
    ) # Check if the latest four quarters are consecutive by verifying that there are four unique periods and that the gaps between them are within a reasonable range (70 to 110 days).

    if consecutive_quarters and revenue.notna().all():
        ltm_revenue = revenue.sum() # Calculate the Last Twelve Months (LTM) revenue by summing the total revenue of the latest four quarters.
        print(f"LTM Revenue: {ltm_revenue:,.0f}") # Print the calculated LTM revenue, formatting the number with commas for better readability.
    else:
        print("LTM Revenue unavailable: four complete quarters required.") 
        # Print a message if the LTM revenue is unavailable due to missing data.

statements["ltm_revenue"] = ltm_revenue #Store the calculated LTM revenue in the statements dictionary for each company, allowing for easy access and further analysis.
statements["ltm_end_date"] = periods.max() #Store the end date of the LTM period in the statements dictionary for each company, which can be useful for tracking the time frame of the revenue calculation.