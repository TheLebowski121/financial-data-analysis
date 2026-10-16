import yfinance as yf
import pandas as pd

def print_heading(title):
    separator = "=" * max(60, len(title) + 4)
    print(f"\n{separator}\n  {title}\n{separator}") 
    # Prints a formatted heading with a title and separators for better readability

def print_statement(title, statement):
    print_heading(title)

    if statement.empty:
        print("No data available.")
        return

    print(
        statement.to_string(
            float_format=lambda value: f"{value:,.2f}",
            na_rep="N/A"
        )
    ) # Prints the financial statement in a formatted manner, handling empty data and formatting numbers with commas and two decimal places.

tickey_symbol = input("Enter a Company Ticker Symbol (e.g., AAPL, MSFT, GOOGL): ").strip().upper() 
# Prompts the user to input a company ticker symbol, removes any leading/trailing whitespace, and converts it to uppercase for consistency.

if not tickey_symbol:
    raise SystemExit("please enter a valid ticker symbol.") 
# Exits the program if the user does not provide a valid ticker symbol.

Company = yf.Ticker(tickey_symbol) 
# Creates a Ticker object for the specified company using the yfinance library, allowing access to various financial data and information.

print_heading(f"Financial research for: {tickey_symbol}") 
# Displays the research title using our reusable heading function.

print_statement("Annual Income Statements", Company.financials) 
# Prints the annual income statements of the specified company using the reusable print_statement function.
print_statement("Annual Balance Sheets", Company.balance_sheet) 
# Prints the annual balance sheets of the specified company using the reusable print_statement function.
print_statement("Annual Cash Flow Statements", Company.cashflow)
# Prints the annual cash flow statements of the specified company using the reusable print_statement function.
print_heading("SEC Filings")
filings = Company.get_sec_filings()

filing_year = input(
    "\nEnter filing years separated by commas (e.g., 2025,2026), "
    "or press Enter for all: "
).strip()

if filing_year:
    selected_years = {
        year.strip() for year in filing_year.split(",")
    }

    filings = [
        filing for filing in filings
        if str(filing["date"].year) in selected_years
    ]

if not filings:
    print("No SEC filings returned for this selection.")
else:
    for filing in sorted(
        filings,
        key=lambda filing: filing["date"],
        reverse=True
    ):
        print(f"\nFiled: {filing['date']}")
        print(f"Form: {filing.get('type', 'N/A')}")
        print(f"Description: {filing.get('title', 'N/A')}")
        print(f"Link: {filing.get('edgarUrl', 'N/A')}")