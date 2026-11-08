from excel_export import export_financial_statements
from sec_filings import get_sec_json
from datetime import date
import os
from dotenv import load_dotenv

load_dotenv()

def get_company_cik(ticker, contact_email):
    url = "https://www.sec.gov/files/company_tickers.json"
    company_tickers = get_sec_json(url, contact_email) 
    ticker = ticker.strip().upper()
    for company in company_tickers.values():
        if company["ticker"].upper() == ticker:
            return company["cik_str"]

    raise ValueError(f"ticker '{ticker}' not found in SEC database.")

def get_company_facts(cik, contact_email):
    padded_cik = str(cik).zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{padded_cik}.json"
    return get_sec_json(url, contact_email)

def is_quarterly_record(record):
    start_date = date.fromisoformat(record["start"])
    end_date = date.fromisoformat(record["end"])
    duration_days = (end_date - start_date).days + 1
    return 80 <= duration_days <= 100

def is_annual_record(record):
    duration_days = (date.fromisoformat(record["end"]) - date.fromisoformat(record["start"])).days + 1
    return 350 <= duration_days <= 380

def get_annual_records(records, selected_years):
    records_by_year = {}
    for record in records:
        if record.get("form") == "10-K" and is_annual_record(record):
            year = record["end"][:4]
            if year in selected_years:
                if year not in records_by_year or record["filed"] > records_by_year[year]["filed"]:
                    records_by_year[year] = record
    return list(records_by_year.values())


if __name__ == "__main__":
    
    years_input = input("Enter reporting years (comma-separated, e.g., 2020,2021): ")
    selected_years = [year.strip() for year in years_input.split(",")]
    contact_email = os.environ["SEC_CONTACT_EMAIL"]

    cik = get_company_cik("AMZN", contact_email)
    facts = get_company_facts(cik, contact_email)
    gaap_facts = facts["facts"]["us-gaap"]
    
    revenue_records = facts["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"]
    operating_expense_records = gaap_facts["CostsAndExpenses"]["units"]["USD"]

    annual_operating_expense_records = get_annual_records(operating_expense_records, selected_years)

    operating_income_records = facts["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"]

    annual_operating_income_records = get_annual_records(operating_income_records, selected_years)

    net_income_records = facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]
    annual_net_income_records = get_annual_records(net_income_records, selected_years)

    quarterly_revenue_records =[]
    quarters_seen = set()

    for record in revenue_records:
        frame = record.get("frame")
        quarterly_key = (record["start"], record["end"])

        if is_quarterly_record(record) and record["end"][:4] in selected_years and quarterly_key not in quarters_seen:
            quarters_seen.add(quarterly_key)
            quarterly_revenue_records.append(record)

    annual_revenue_records = get_annual_records(revenue_records, selected_years)

    annual_financial_data = {}
    annual_financial_data["Revenue"] = annual_revenue_records
    annual_financial_data["Operating Expenses"] = annual_operating_expense_records
    annual_financial_data["Operating Income"] = annual_operating_income_records
    annual_financial_data["Net Income"] = annual_net_income_records
    financial_data_by_year = {}
    for metric, records in annual_financial_data.items():
        for record in records:
            year = record["end"][:4]
            if year not in financial_data_by_year:
                financial_data_by_year[year] = {}
            financial_data_by_year[year][metric] = record["val"]

    for year, metrics in sorted(financial_data_by_year.items()):
        print(f"\nFinancial Statement - {year}")
        for metric, value in metrics.items():
            formatted_value = f"(${abs(value):,.0f})" if value < 0 else f"${value:,.0f}"
            print(f"{metric}: {formatted_value}")
    print("Financial data by year:", financial_data_by_year)

    export_financial_statements(
        annual_data=financial_data_by_year,
        template_path="templates/NYSF_Amazon_Template.xlsx",
        output_path="output/AMZN_Financial_Statements.xlsx",
    )