# Financial Data Acquisition and Modeling

A Python project for acquiring public-company financial data and preparing it for financial statement and modeling workflows. The current SEC-to-Excel milestone uses Amazon (AMZN) as a demonstration: it retrieves selected annual facts from SEC EDGAR, organizes them by reporting year, and writes historical results into a locally supplied Excel model.

The project is under active development. It is intended to automate data collection and statement preparation while leaving forecasting, valuation, and investment analysis to the analyst in Excel. It does not yet provide complete or production-ready financial statement extraction.

## Current capabilities

- Retrieves company CIKs by ticker from the SEC company ticker list.
- Retrieves company facts from the SEC XBRL Company Facts API.
- Selects annual observations filed on Form 10-K, based on annual duration and reporting end year; where there are repeated observations for a year, it retains the latest filing date.
- Organizes selected annual Revenue, Operating Expenses, Operating Income, and Net Income observations in Python dictionaries.
- Exports data in US$ millions to a separate workbook through Microsoft Excel automation (`pywin32`).
- Adds a `SEC Historical Data` worksheet and populates Revenue, Operating Income, and Net Income in the template's `Income Statement`.
- Configures historical year labels and five following estimate-year headings in the template.

The demonstrated workflow is currently hard-coded for AMZN and for a particular workbook layout. Quarterly revenue observations are identified in `sec_data.py`, but are not currently exported or used to build quarterly statements.

## Demonstrated milestone

The implementation was developed and manually validated with the NYSF Amazon financial modeling template on Windows with Microsoft Excel installed. The reported validation populated Amazon's 2020–2022 Revenue and Operating Income in the original `Income Statement`, displayed historical and forecast headings, and opened the saved workbook in Excel without repair errors after the export was migrated from `openpyxl` to `pywin32`.

The exporter also maps Net Income and creates a separate sheet with all four collected metrics. Estimate-year headings are labels only: the application does not calculate forecasts or populate forecast assumptions.

## Architecture and workflow

```text
SEC EDGAR APIs
      |
      v
sec_filings.py  -> HTTP requests with the SEC User-Agent
      |
      v
sec_data.py     -> CIK/facts retrieval, annual-period selection,
                   metric organization, and export invocation
      |
      v
excel_export.py -> Microsoft Excel automation, year-column
                   configuration, and financial statement population
      |
      +----------> templates/  (locally supplied source workbooks)
      |
      +----------> output/     (generated workbooks)
```

Separating SEC communication, data selection, and workbook writing is intended to make it easier to add companies and compatible financial models over time. That extensibility is an architectural direction, not a feature currently completed: the script selects AMZN and the exporter relies on the target template's `Income Statement` sheet and fixed row locations.

## Project structure

| Path | Purpose |
| --- | --- |
| `sec_filings.py` | Sends requests to SEC endpoints with a User-Agent and checks HTTP responses. |
| `sec_data.py` | Looks up the company CIK, fetches Company Facts, selects and organizes annual observations, and invokes the Excel export. |
| `excel_export.py` | Automates desktop Excel through `pywin32`, writes historical data, and sets year headings. |
| `templates/` | Local source Excel templates. Workbook files are intentionally excluded from Git until their redistribution rights are clear. |
| `output/` | Generated financial workbooks; outputs are excluded from Git. |
| `comps_analysis.py`, `comps_research.py`, `main.py` | Separate stock-data and financial research scripts; they are not part of the current SEC-to-Excel run path. |
| `requirements.txt` | Python package dependencies. |
| `.env.example` | Placeholder for the SEC contact email configuration. |

## Setup (Windows)

The Excel export requires Windows, desktop Microsoft Excel, and a compatible 32/64-bit Python and Office installation. Python dependencies are listed in `requirements.txt`.

In PowerShell, from the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell prevents activation, follow your organization's policy for activating a virtual environment, or invoke the environment's Python directly as `.venv\Scripts\python.exe`.

## SEC contact configuration

The SEC asks automated clients to identify themselves. Set `SEC_CONTACT_EMAIL` to an email address where you can be contacted. The application loads this value from the process environment or a local `.env` file using `python-dotenv`; `sec_data.py` requires it when run.

```powershell
Copy-Item .env.example .env
```

Edit `.env` locally:

```dotenv
SEC_CONTACT_EMAIL=your.email@example.com
```

Do not commit `.env` or credentials. `.env` is ignored by Git; `.env.example` contains only a placeholder.

## Excel template

Obtain a template that you are authorized to use and place it at:

```text
templates/NYSF_Amazon_Template.xlsx
```

The exporter expects a worksheet named `Income Statement` and the row layout encoded in `excel_export.py`. The NYSF workbook in the development workspace is not included in this repository because its redistribution permission has not been established. Confirm the template's license or obtain authorization before sharing it; do not assume that a publicly available workbook may be redistributed.

The source template is opened read-only by the exporter. Results are saved separately to `output/AMZN_Financial_Statements.xlsx`, leaving the source template unchanged.

## Run and select reporting years

After setup and placing the authorized template, run:

```powershell
python sec_data.py
```

When prompted, enter reporting years as comma-separated year values, for example:

```text
2020,2021,2022
```

The current script looks up AMZN, requests its SEC company facts, and selects annual observations whose reporting end year is among the entered years. The output is saved to `output/AMZN_Financial_Statements.xlsx`.

## Workbook contents

- The original template's `Income Statement` receives historical Revenue, Operating Income, and Net Income in the mapped rows, expressed in US$ millions.
- The `SEC Historical Data` worksheet contains the selected annual Revenue, Operating Expenses, Operating Income, and Net Income values, also in US$ millions.
- Historical year labels are marked with `A`; five following estimate-year headings are marked with `E`.
- The estimate headings are not projections. Forecast calculations and assumptions remain the analyst's responsibility.

## Limitations and next steps

- Only AMZN is wired into the current command-line workflow; company selection is not exposed as a user option.
- The exported metrics are a limited subset, not a complete income statement, balance sheet, or cash flow statement. XBRL tags, company-specific taxonomies, and accounting presentation require broader handling.
- Annual facts are filtered by form, duration, and reporting end year; quarterly data is not yet incorporated into workbook output. Restatements, amendments, fiscal-year edge cases, and duplicate observations need more comprehensive validation.
- The workbook mapping is template-specific and uses fixed worksheet names and cell rows. Additional models and companies need explicit mappings and tests.
- Excel automation requires an installed desktop Excel application and a matching Windows/Python environment; this export path is not cross-platform.
- Automated tests and broader validation against multiple issuers and fiscal years remain to be added.

Planned development includes separating configuration from the AMZN demonstration, validating the data-selection logic across issuers, expanding statement coverage, adding automated tests, and supporting additional authorized templates.
