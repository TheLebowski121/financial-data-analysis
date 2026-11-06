import requests


def get_sec_json(url, contact_email):
    headers = {
        "User-Agent": f"Jorge Aguilar Financial Research {contact_email}"
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    return response.json()
def get_company_submissions(cik, contact_email):
    cik_text = str(cik).strip()

    if not cik_text.isdigit() or not 1 <= len(cik_text) <= 10:
        raise ValueError("CIK must contain 1–10 digits.")

    padded_cik = cik_text.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"

    return get_sec_json(url, contact_email)