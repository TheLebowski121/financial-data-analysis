from pathlib import Path
import win32com.client as win32

def configure_income_statement_years(ws, annual_data, forecast_years=5):
    historical_years = sorted(int(year) for year in annual_data)

    if not historical_years:
        raise ValueError("No historical years were supplied.")

    if len(historical_years) > 3:
        extra_columns = len(historical_years) - 3
        ws.Columns("G").Resize(None, extra_columns).Insert()

    first_forecast_year = historical_years[-1] + 1

    for index, year in enumerate(historical_years):
        column = 4 + index
        ws.Cells(5, column).Value = f"{year}A"

    for index in range(forecast_years):
        column = 4 + len(historical_years) + index
        ws.Cells(5, column).Value = f"{first_forecast_year + index}E"

def populate_income_statement(ws, annual_data):
    income_statement_mapping = {
        "Revenue": 11,
        "Operating Income": 33,
        "Net Income": 54,
    }

    years = sorted(annual_data.keys(), key=int)

    for col, year in enumerate(years, start=4):
        for metric, row in income_statement_mapping.items():
            value = annual_data[year].get(metric)

            if value is not None:
                cell = ws.Cells(row, col)
                cell.Value = value / 1_000_000
                cell.NumberFormat = '#,##0.0;(#,##0.0);"-"'

def export_financial_statements(annual_data, template_path, output_path):
    template_path = Path(template_path).resolve()
    output_path = Path(output_path).resolve()

    if not template_path.is_file():
        raise FileNotFoundError(f"Template not found: {template_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    excel = win32.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False

    wb = None

    try:
        wb = excel.Workbooks.Open(
            str(template_path),
            UpdateLinks=0,
            ReadOnly=True
        )

        income_ws = wb.Worksheets("Income Statement")
        configure_income_statement_years(income_ws, annual_data)
        populate_income_statement(income_ws, annual_data)

        # Create a new worksheet for SEC data.
        ws = wb.Worksheets.Add(
            After=wb.Worksheets(wb.Worksheets.Count)
        )
        ws.Name = "SEC Historical Data"

        # Worksheet headings.
        ws.Range("A1").Value = "AMAZON.COM, INC."
        ws.Range("A2").Value = "SEC Historical Financial Data"
        ws.Range("A3").Value = "US$ in millions"

        years = sorted(annual_data.keys())

        # Write reporting years.
        for col, year in enumerate(years, start=2):
            ws.Cells(5, col).Value = int(year)

        metrics = [
            "Revenue",
            "Operating Expenses",
            "Operating Income",
            "Net Income"
        ]

        # Write financial data.
        for row, metric in enumerate(metrics, start=6):
            ws.Cells(row, 1).Value = metric

            for col, year in enumerate(years, start=2):
                value = annual_data[year].get(metric)

                if value is not None:
                    cell = ws.Cells(row, col)
                    cell.Value = value / 1_000_000
                    cell.NumberFormat = '#,##0.0;(#,##0.0);"-"'

        # Basic formatting.
        ws.Columns("A").ColumnWidth = 32
        ws.Range("A1:A2").Font.Bold = True
        ws.Range("A5:Z5").Font.Bold = True
        ws.Range("B:Z").ColumnWidth = 18

        # Save as a new workbook.
        wb.SaveAs(str(output_path), FileFormat=51)

        print(f"Financial workbook saved: {output_path}")

    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)

        excel.Quit()