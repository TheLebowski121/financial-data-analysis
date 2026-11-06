from sec_filings import get_sec_json
from datetime import date
import os

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

    
if __name__ == "__main__":
    
    years_input = input("Enter reporting years (comma-separated, e.g., 2020,2021): ")
    selected_years = [year.strip() for year in years_input.split(",")]
    contact_email = os.environ["SEC_CONTACT_EMAIL"]

    cik = get_company_cik("AMZN", contact_email)
    facts = get_company_facts(cik, contact_email)
    
    revenue_records = facts["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"]
    operating_income_records = facts["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"]
    net_income_records = facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]

    print("Operating Income observations:", len(operating_income_records))
    print("Net Income observations:", len(net_income_records))
    print(revenue_records[-1]["val"])
    print(len(revenue_records))

    quarters_seen = set()

    for record in revenue_records:
        frame = record.get("frame")
        quarterly_key = (record["start"], record["end"])

        if is_quarterly_record(record) and record["end"][:4] in selected_years and quarterly_key not in quarters_seen:
            print("quarterly:", record["start"], "to" , record["end"], "val:", record["val"])
            quarters_seen.add(quarterly_key)

    print("\nOperating Income:")
    for record in operating_income_records[-5:]:
        if is_quarterly_record(record) and record["end"][:4] in selected_years:
            print("quarterly:", record.get("frame"), record["val"])

    print("\nNet Income:")
    for record in net_income_records[-15:]:
        if is_quarterly_record(record) and record["end"][:4] in selected_years:
            print("quarterly:", record.get("frame"), record["val"], "End:", record.get("end"), "Filed:", record.get("filed"), "Form:", record.get("form"))

