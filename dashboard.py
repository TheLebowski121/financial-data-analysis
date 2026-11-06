"""Streamlit dashboard for the financial-data-analysis project.

Run from the repository root with:
    streamlit run dashboard.py

The SEC helper modules are imported as-is. This file owns the presentation and
the small amount of data shaping needed by the dashboard.
"""

from __future__ import annotations

import os
from math import sqrt
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from sec_data import get_company_cik, get_company_facts
from sec_filings import get_company_submissions


st.set_page_config(
    page_title="Financial Research Dashboard",
    page_icon="📊",
    layout="wide",
)

REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "Revenues",
)
OPERATING_INCOME_TAGS = ("OperatingIncomeLoss",)
NET_INCOME_TAGS = ("NetIncomeLoss", "ProfitLoss")
OPERATING_CASH_FLOW_TAGS = ("NetCashProvidedByUsedInOperatingActivities",)
CAPEX_TAGS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsToAcquireFixedAssets",
)


def _usd_records(facts: dict[str, Any], candidate_tags: tuple[str, ...]) -> tuple[str | None, list[dict[str, Any]]]:
    """Return the first available US-GAAP USD fact series from candidate tags."""
    concepts = facts.get("facts", {}).get("us-gaap", {})
    for tag in candidate_tags:
        concept = concepts.get(tag, {})
        records = concept.get("units", {}).get("USD", [])
        if records:
            return tag, records
    return None, []


def _quarterly_series(
    facts: dict[str, Any], candidate_tags: tuple[str, ...], output_name: str
) -> tuple[str | None, pd.DataFrame]:
    """Extract standalone quarter-length reported values, avoiding duplicate filings."""
    tag, records = _usd_records(facts, candidate_tags)
    rows: list[dict[str, Any]] = []

    for record in records:
        if not record.get("start") or not record.get("end"):
            continue
        try:
            start = pd.Timestamp(record["start"])
            end = pd.Timestamp(record["end"])
        except (TypeError, ValueError):
            continue

        duration_days = (end - start).days + 1
        # This follows the SEC helper's current definition of a quarterly record.
        if not 80 <= duration_days <= 100:
            continue

        rows.append(
            {
                "period_start": start,
                "period_end": end,
                output_name: record.get("val"),
                "filed": record.get("filed", ""),
                "form": record.get("form", ""),
                "frame": record.get("frame", ""),
            }
        )

    if not rows:
        return tag, pd.DataFrame(
            columns=["period_start", "period_end", output_name, "filed", "form", "frame"]
        )

    # Facts can recur in later filings. Keep the newest filed value for each period.
    result = pd.DataFrame(rows)
    result = result.sort_values(["period_end", "filed"])
    result = result.drop_duplicates(subset=["period_start", "period_end"], keep="last")
    result = result.sort_values("period_end").reset_index(drop=True)
    result[output_name] = pd.to_numeric(result[output_name], errors="coerce")
    return tag, result


def company_quarters(facts: dict[str, Any]) -> tuple[dict[str, str | None], pd.DataFrame]:
    """Build a quarterly table for revenue and income facts available in SEC XBRL."""
    tags: dict[str, str | None] = {}
    combined: pd.DataFrame | None = None

    for name, candidates in (
        ("Revenue", REVENUE_TAGS),
        ("Operating income", OPERATING_INCOME_TAGS),
        ("Net income", NET_INCOME_TAGS),
        ("Operating cash flow", OPERATING_CASH_FLOW_TAGS),
        ("Capital expenditures", CAPEX_TAGS),
    ):
        tag, series = _quarterly_series(facts, candidates, name)
        tags[name] = tag
        if series.empty:
            continue
        metric = series[["period_start", "period_end", name]]
        combined = metric if combined is None else combined.merge(
            metric, on=["period_start", "period_end"], how="outer"
        )

    if combined is None:
        return tags, pd.DataFrame(
            columns=["period_start", "period_end", "Revenue", "Operating income", "Net income"]
        )

    combined = combined.sort_values("period_end").reset_index(drop=True)
    for column in (
        "Revenue",
        "Operating income",
        "Net income",
        "Operating cash flow",
        "Capital expenditures",
    ):
        if column not in combined:
            combined[column] = float("nan")
    combined["Net margin"] = combined["Net income"] / combined["Revenue"] * 100
    combined["Operating margin"] = combined["Operating income"] / combined["Revenue"] * 100
    combined["Free cash flow"] = combined["Operating cash flow"] - combined[
        "Capital expenditures"
    ].abs()
    combined["Free cash flow margin"] = combined["Free cash flow"] / combined["Revenue"] * 100
    return tags, combined


def _latest_non_null(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame:
        return None
    values = frame[column].dropna()
    return float(values.iloc[-1]) if not values.empty else None


def _ltm_revenue(frame: pd.DataFrame) -> float | None:
    return _ltm_metric(frame, "Revenue")


def _ltm_metric(frame: pd.DataFrame, metric: str) -> float | None:
    """Sum four complete, approximately consecutive reported quarters for a metric."""
    if frame.empty or metric not in frame:
        return None
    recent = frame.dropna(subset=[metric]).sort_values("period_end").tail(4)
    if len(recent) != 4:
        return None
    dates = pd.DatetimeIndex(recent["period_end"])
    gaps = (dates[1:] - dates[:-1]).days
    if not dates.is_unique or not all(70 <= gap <= 110 for gap in gaps):
        return None
    return float(recent[metric].sum())


def _with_growth_rates(frame: pd.DataFrame) -> pd.DataFrame:
    """Add approximate same-period-last-year growth rates where a peer period exists."""
    result = frame.copy()
    metrics = ("Revenue", "Operating income", "Net income", "Free cash flow")
    for metric in metrics:
        growth = pd.Series(float("nan"), index=result.index, dtype="float64")
        if metric not in result:
            result[f"{metric} growth YoY"] = growth
            continue

        valid = result.dropna(subset=[metric]).sort_values("period_end")
        for row_index, row in valid.iterrows():
            target = row["period_end"] - pd.DateOffset(years=1)
            earlier = valid[valid["period_end"] < row["period_end"]].copy()
            if earlier.empty:
                continue
            earlier["date_distance"] = (earlier["period_end"] - target).abs().dt.days
            prior = earlier.sort_values("date_distance").iloc[0]
            prior_value = float(prior[metric])
            if prior["date_distance"] <= 30 and prior_value > 0:
                growth.loc[row_index] = (float(row[metric]) / prior_value - 1) * 100
        result[f"{metric} growth YoY"] = growth
    return result


def _format_money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B"
    if absolute >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    return f"${value:,.0f}"


@st.cache_data(ttl=3600, show_spinner=False)
def _load_facts(ticker: str, contact_email: str) -> tuple[int, dict[str, Any]]:
    cik = get_company_cik(ticker, contact_email)
    facts = get_company_facts(cik, contact_email)
    return int(cik), facts


@st.cache_data(ttl=3600, show_spinner=False)
def _load_submissions(cik: int, contact_email: str) -> dict[str, Any]:
    return get_company_submissions(cik, contact_email)


def _filing_rows(submissions: dict[str, Any], cik: int) -> list[dict[str, str]]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accessions = recent.get("accessionNumber", [])
    documents = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])

    rows = []
    count = min(len(forms), len(dates), len(accessions), len(documents))
    for index in range(count):
        accession = accessions[index]
        document = documents[index]
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
            f"{accession.replace('-', '')}/{document}"
        )
        rows.append(
            {
                "Form": forms[index],
                "Filed": dates[index],
                "Report period": report_dates[index] if index < len(report_dates) else "",
                "Description": descriptions[index] if index < len(descriptions) else document,
                "URL": url,
            }
        )
    return rows


def _load_price_history(ticker: str) -> pd.DataFrame:
    history = yf.Ticker(ticker).history(period="5y", auto_adjust=True)
    if history.empty or "Close" not in history:
        return pd.DataFrame()
    close = history["Close"].dropna()
    returns = close.pct_change()
    return pd.DataFrame(
        {
            "Adjusted close": close,
            "Cumulative return (%)": (close / close.iloc[0] - 1) * 100,
            "Daily return (%)": returns * 100,
            "30-day volatility (%)": returns.rolling(30).std() * sqrt(252) * 100,
        }
    )


@st.cache_data(ttl=1800, show_spinner=False)
def _market_snapshot(ticker: str) -> dict[str, Any]:
    """Fetch the current market fields used by the valuation screens."""
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        info = {}
    if not isinstance(info, dict):
        info = {}
    fields = (
        "marketCap",
        "enterpriseValue",
        "totalRevenue",
        "ebitda",
        "trailingPE",
        "currentPrice",
        "regularMarketPrice",
        "totalDebt",
        "totalCash",
        "sharesOutstanding",
    )
    return {field: info.get(field) for field in fields}


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def _dcf_value(base_fcf: float, growth: float, wacc: float, terminal_growth: float, years: int) -> tuple[pd.DataFrame, float, float]:
    """Return a simple FCFF projection, present value of terminal value, and firm value."""
    rows = []
    for year in range(1, years + 1):
        projected_fcf = base_fcf * (1 + growth) ** year
        present_value = projected_fcf / (1 + wacc) ** year
        rows.append({"Year": year, "Projected FCF ($M)": projected_fcf, "Present value ($M)": present_value})

    projection = pd.DataFrame(rows)
    terminal_fcf = float(projection.iloc[-1]["Projected FCF ($M)"]) * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    terminal_value_pv = terminal_value / (1 + wacc) ** years
    enterprise_value = float(projection["Present value ($M)"].sum()) + terminal_value_pv
    return projection, terminal_value_pv, enterprise_value


@st.cache_data(ttl=1800, show_spinner=False)
def _load_peer_price_performance(tickers: tuple[str, ...]) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for ticker in tickers:
        try:
            history = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
            if history.empty or "Close" not in history:
                continue
            close = history["Close"].dropna()
            if len(close) > 1:
                series[ticker] = (close / close.iloc[0] - 1) * 100
        except Exception:
            continue
    return pd.DataFrame(series).sort_index()


st.title("Financial Research Dashboard")
st.caption("Company fundamentals and filing links, organized from SEC data.")

with st.sidebar:
    st.header("Company")
    with st.form("company_lookup"):
        tickers_input = st.text_input(
            "Ticker(s)",
            value=st.session_state.get("tickers_input", "AMZN"),
            help="First ticker is the target; add comma-separated peer tickers after it.",
        )
        email_input = st.text_input(
            "SEC contact email",
            value=os.environ.get("SEC_CONTACT_EMAIL", ""),
            help="Used in the SEC request User-Agent through the existing helper functions.",
        )
        submitted = st.form_submit_button("Load companies", type="primary")

if submitted:
    st.session_state["tickers_input"] = tickers_input
    st.session_state["sec_contact_email"] = email_input.strip()
    st.session_state["loaded_tickers"] = list(
        dict.fromkeys(
            ticker.strip().upper()
            for ticker in tickers_input.split(",")
            if ticker.strip()
        )
    )

tickers = st.session_state.get("loaded_tickers", [])
contact_email = st.session_state.get(
    "sec_contact_email", os.environ.get("SEC_CONTACT_EMAIL", "").strip()
)

if not tickers:
    st.info("Enter a ticker in the sidebar and choose **Load companies** to begin.")
    st.stop()

if not contact_email:
    st.error(
        "Add a contact email in the sidebar, or set the `SEC_CONTACT_EMAIL` environment variable."
    )
    st.stop()

company_data: dict[str, dict[str, Any]] = {}
with st.spinner("Loading SEC company facts…"):
    for ticker in tickers:
        try:
            cik, facts = _load_facts(ticker, contact_email)
            tags, quarters = company_quarters(facts)
            quarters = _with_growth_rates(quarters)
            company_data[ticker] = {
                "cik": cik,
                "name": facts.get("entityName", ticker),
                "facts": facts,
                "tags": tags,
                "quarters": quarters,
            }
        except Exception as exc:
            st.warning(f"Could not load {ticker}: {exc}")

if not company_data:
    st.stop()

primary_ticker = next(iter(company_data))
primary = company_data[primary_ticker]
st.subheader(f"{primary['name']} ({primary_ticker})")
st.caption(f"CIK {primary['cik']} · Figures are reported values from SEC company facts.")

filing_rows: list[dict[str, str]] = []
filing_load_error: str | None = None
try:
    primary_submissions = _load_submissions(primary["cik"], contact_email)
    filing_rows = _filing_rows(primary_submissions, primary["cik"])
except Exception as exc:
    filing_load_error = str(exc)

periodic_filings = [
    row for row in filing_rows if row["Form"] in {"10-K", "10-Q", "20-F", "40-F"}
]
latest_periodic_filing = max(periodic_filings, key=lambda row: row["Filed"], default=None)
if latest_periodic_filing:
    st.link_button(
        f"Open original SEC {latest_periodic_filing['Form']} filing · {latest_periodic_filing['Filed']}",
        latest_periodic_filing["URL"],
        help="Opens the original filing document on SEC EDGAR.",
    )
elif filing_load_error:
    st.caption(f"SEC filing link unavailable: {filing_load_error}")

latest_quarter = primary["quarters"]
revenue = _latest_non_null(latest_quarter, "Revenue")
operating_income = _latest_non_null(latest_quarter, "Operating income")
net_income = _latest_non_null(latest_quarter, "Net income")
net_margin = _latest_non_null(latest_quarter, "Net margin")
free_cash_flow_margin = _latest_non_null(latest_quarter, "Free cash flow margin")
ltm_revenue = _ltm_revenue(latest_quarter)

cards = st.columns(6)
cards[0].metric("Latest quarter revenue", _format_money(revenue))
cards[1].metric("LTM revenue", _format_money(ltm_revenue))
cards[2].metric("Operating income", _format_money(operating_income))
cards[3].metric("Net income", _format_money(net_income))
cards[4].metric("Net margin", "—" if net_margin is None else f"{net_margin:.1f}%")
cards[5].metric(
    "FCF margin",
    "—" if free_cash_flow_margin is None else f"{free_cash_flow_margin:.1f}%",
)

overview_tab, peers_tab, dcf_tab, precedents_tab, filings_tab = st.tabs(
    [
        "Company overview",
        "Comparable companies",
        "Discounted cash flow",
        "Precedent transactions",
        "SEC filings",
    ]
)

with overview_tab:
    left, right = st.columns([1.6, 1])
    with left:
        st.markdown("#### Quarterly financials")
        if latest_quarter.empty:
            st.info("No standalone quarter-length values were found for these SEC tags.")
        else:
            chart_data = latest_quarter.set_index("period_end")
            chart_columns = [
                column
                for column in ("Revenue", "Operating income", "Net income", "Free cash flow")
                if column in chart_data and chart_data[column].notna().any()
            ]
            if chart_columns:
                chart = chart_data[chart_columns] / 1_000_000_000
                chart.columns = [f"{column} ($B)" for column in chart.columns]
                st.line_chart(chart, height=280)

            st.markdown("#### Growth and margins")
            growth_columns = [
                column
                for column in (
                    "Revenue growth YoY",
                    "Operating income growth YoY",
                    "Net income growth YoY",
                    "Free cash flow growth YoY",
                )
                if column in latest_quarter and latest_quarter[column].notna().any()
            ]
            if growth_columns:
                growth_chart = latest_quarter.set_index("period_end")[growth_columns]
                growth_chart.columns = [column.replace(" growth YoY", "") for column in growth_chart.columns]
                st.line_chart(growth_chart, height=260)
                st.caption("Year-over-year change for a reported period with a comparable period about one year earlier.")
            else:
                st.info("Not enough matching quarterly periods to calculate year-over-year growth.")

            margin_columns = [
                column
                for column in ("Operating margin", "Net margin", "Free cash flow margin")
                if column in latest_quarter and latest_quarter[column].notna().any()
            ]
            if margin_columns:
                margin_chart = latest_quarter.set_index("period_end")[margin_columns]
                st.line_chart(margin_chart, height=240)

            display = latest_quarter.copy()
            display["Quarter ended"] = display["period_end"].dt.strftime("%Y-%m-%d")
            display = display[
                [
                    "Quarter ended",
                    "Revenue",
                    "Operating income",
                    "Net income",
                    "Free cash flow",
                    "Operating margin",
                    "Net margin",
                    "Free cash flow margin",
                    "Revenue growth YoY",
                    "Net income growth YoY",
                ]
            ].sort_values("Quarter ended", ascending=False)
            st.dataframe(
                display,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Revenue": st.column_config.NumberColumn(format="$%.0f"),
                    "Operating income": st.column_config.NumberColumn(format="$%.0f"),
                    "Net income": st.column_config.NumberColumn(format="$%.0f"),
                    "Free cash flow": st.column_config.NumberColumn(format="$%.0f"),
                    "Operating margin": st.column_config.NumberColumn(format="%.1f%%"),
                    "Net margin": st.column_config.NumberColumn(format="%.1f%%"),
                    "Free cash flow margin": st.column_config.NumberColumn(format="%.1f%%"),
                    "Revenue growth YoY": st.column_config.NumberColumn(format="%.1f%%"),
                    "Net income growth YoY": st.column_config.NumberColumn(format="%.1f%%"),
                },
            )

        st.caption(
            "The current SEC helper logic includes records lasting 80–100 days. "
            "Some companies report year-to-date figures, so this view may omit quarters "
            "that would need to be reconstructed from cumulative values."
        )

    with right:
        st.markdown("#### Share price · 5 years")
        try:
            prices = _load_price_history(primary_ticker)
            if prices.empty:
                st.info("No price history returned for this ticker.")
            else:
                st.line_chart(prices[["Adjusted close"]], height=260)
                latest_return = prices["Cumulative return (%)"].dropna().iloc[-1]
                latest_vol = prices["30-day volatility (%)"].dropna()
                metric_a, metric_b = st.columns(2)
                metric_a.metric("5-year price return", f"{latest_return:+.1f}%")
                metric_b.metric(
                    "30-day annualized volatility",
                    f"{latest_vol.iloc[-1]:.1f}%" if not latest_vol.empty else "—",
                )
                st.markdown("#### Cumulative price return")
                st.line_chart(prices[["Cumulative return (%)"]], height=210)
                st.markdown("#### Rolling 30-day volatility")
                st.line_chart(prices[["30-day volatility (%)"]], height=210)
                returns = prices["Daily return (%)"].dropna()
                if len(returns) > 1:
                    counts, edges = np.histogram(returns, bins=30)
                    centers = (edges[:-1] + edges[1:]) / 2
                    distribution = pd.DataFrame(
                        {"Trading days": counts},
                        index=pd.Index(centers.round(2), name="Daily return (%)"),
                    )
                    st.markdown("#### Daily return distribution")
                    st.bar_chart(distribution, height=210)
                st.caption("Adjusted price history is provided by yfinance. Volatility uses daily returns, annualized with 252 trading days.")
        except Exception as exc:
            st.info(f"Price history unavailable: {exc}")

with peers_tab:
    st.markdown("#### Reported financials")
    peer_rows = []
    for ticker, company in company_data.items():
        quarters = company["quarters"]
        latest = quarters.iloc[-1] if not quarters.empty else None
        peer_rows.append(
            {
                "Ticker": ticker,
                "Company": company["name"],
                "Quarter ended": (
                    latest["period_end"].strftime("%Y-%m-%d") if latest is not None else "—"
                ),
                "LTM revenue": _ltm_revenue(quarters),
                "Revenue": latest.get("Revenue") if latest is not None else None,
                "Operating income": (
                    latest.get("Operating income") if latest is not None else None
                ),
                "Net income": latest.get("Net income") if latest is not None else None,
                "Net margin": latest.get("Net margin") if latest is not None else None,
                "Operating margin": latest.get("Operating margin") if latest is not None else None,
                "FCF margin": latest.get("Free cash flow margin") if latest is not None else None,
            }
        )

    peer_frame = pd.DataFrame(peer_rows)
    st.dataframe(
        peer_frame,
        hide_index=True,
        use_container_width=True,
        column_config={
            "LTM revenue": st.column_config.NumberColumn(format="$%.0f"),
            "Revenue": st.column_config.NumberColumn(format="$%.0f"),
            "Operating income": st.column_config.NumberColumn(format="$%.0f"),
            "Net income": st.column_config.NumberColumn(format="$%.0f"),
            "Net margin": st.column_config.NumberColumn(format="%.1f%%"),
            "Operating margin": st.column_config.NumberColumn(format="%.1f%%"),
            "FCF margin": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
    ltm_chart = peer_frame.dropna(subset=["LTM revenue"]).set_index("Ticker")[["LTM revenue"]]
    if not ltm_chart.empty:
        st.markdown("#### LTM revenue by company")
        st.bar_chart(ltm_chart, height=260)

    margin_columns = [
        column
        for column in ("Operating margin", "Net margin", "FCF margin")
        if peer_frame[column].notna().any()
    ]
    if margin_columns:
        st.markdown("#### Latest quarter margins by company")
        st.bar_chart(peer_frame.set_index("Ticker")[margin_columns], height=260)

    quarterly_revenues = {}
    for ticker, company in company_data.items():
        quarters = company["quarters"].dropna(subset=["Revenue"])
        if not quarters.empty:
            quarterly_revenues[ticker] = quarters.set_index("period_end")["Revenue"]
    if quarterly_revenues:
        revenue_trends = pd.DataFrame(quarterly_revenues).sort_index() / 1_000_000_000
        st.markdown("#### Quarterly revenue trend by company ($B)")
        st.line_chart(revenue_trends, height=280)

    st.markdown("#### Trading multiples")
    st.caption(
        "Market capitalization, enterprise value, revenue, EBITDA, and P/E come from yfinance. "
        "Multiples are descriptive; comparables should be selected and reviewed manually."
    )
    market_rows = []
    market_snapshots: dict[str, dict[str, Any]] = {}
    for ticker, company in company_data.items():
        try:
            snapshot = _market_snapshot(ticker)
            market_snapshots[ticker] = snapshot
            market_cap = _finite_number(snapshot.get("marketCap"))
            enterprise_value = _finite_number(snapshot.get("enterpriseValue"))
            total_debt = _finite_number(snapshot.get("totalDebt")) or 0.0
            total_cash = _finite_number(snapshot.get("totalCash")) or 0.0
            if enterprise_value is None and market_cap is not None:
                enterprise_value = market_cap + total_debt - total_cash

            ltm_rev = _finite_number(snapshot.get("totalRevenue")) or _ltm_revenue(company["quarters"])
            ebitda = _finite_number(snapshot.get("ebitda"))
            pe = _finite_number(snapshot.get("trailingPE"))
            market_rows.append(
                {
                    "Ticker": ticker,
                    "Company": company["name"],
                    "Market cap ($B)": market_cap / 1_000_000_000 if market_cap is not None else None,
                    "Enterprise value ($B)": enterprise_value / 1_000_000_000 if enterprise_value is not None else None,
                    "EV / Revenue": (
                        enterprise_value / ltm_rev
                        if enterprise_value is not None and ltm_rev is not None and ltm_rev > 0
                        else None
                    ),
                    "EV / EBITDA": (
                        enterprise_value / ebitda if enterprise_value is not None and ebitda and ebitda > 0 else None
                    ),
                    "P / E": pe,
                }
            )
        except Exception as exc:
            st.warning(f"Market multiples unavailable for {ticker}: {exc}")

    if market_rows:
        multiples_frame = pd.DataFrame(market_rows)
        st.dataframe(
            multiples_frame,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Market cap ($B)": st.column_config.NumberColumn(format="$%.2f"),
                "Enterprise value ($B)": st.column_config.NumberColumn(format="$%.2f"),
                "EV / Revenue": st.column_config.NumberColumn(format="%.2fx"),
                "EV / EBITDA": st.column_config.NumberColumn(format="%.2fx"),
                "P / E": st.column_config.NumberColumn(format="%.2fx"),
            },
        )
        ev_multiples_chart = multiples_frame.set_index("Ticker")[["EV / Revenue", "EV / EBITDA"]]
        pe_chart = multiples_frame.set_index("Ticker")[["P / E"]]
        chart_left, chart_right = st.columns(2)
        with chart_left:
            if ev_multiples_chart.notna().any().any():
                st.markdown("#### Enterprise value multiples")
                st.bar_chart(ev_multiples_chart, height=280)
        with chart_right:
            if pe_chart.notna().any().any():
                st.markdown("#### Equity multiple")
                st.bar_chart(pe_chart, height=280)

        peer_multiples = multiples_frame[multiples_frame["Ticker"] != primary_ticker]
        if peer_multiples.empty:
            st.info("Add at least one peer ticker after the target ticker to calculate implied values.")
        else:
            median_ev_revenue = peer_multiples["EV / Revenue"].median()
            median_ev_ebitda = peer_multiples["EV / EBITDA"].median()
            target_snapshot = market_snapshots.get(primary_ticker, {})
            target_revenue = (
                _finite_number(target_snapshot.get("totalRevenue"))
                or _ltm_revenue(primary["quarters"])
            )
            target_ebitda = _finite_number(target_snapshot.get("ebitda"))
            target_ev_revenue = None
            target_ev_ebitda = None
            if pd.notna(median_ev_revenue) and target_revenue:
                target_ev_revenue = median_ev_revenue * target_revenue
            if pd.notna(median_ev_ebitda) and target_ebitda and target_ebitda > 0:
                target_ev_ebitda = median_ev_ebitda * target_ebitda

            st.markdown("#### Target value from peer medians")
            if target_ev_revenue is not None or target_ev_ebitda is not None:
                target_debt = _finite_number(target_snapshot.get("totalDebt")) or 0.0
                target_cash = _finite_number(target_snapshot.get("totalCash")) or 0.0
                target_shares = _finite_number(target_snapshot.get("sharesOutstanding")) or 0.0
                valuation_rows = []
                for method, multiple, target_metric, implied_ev in (
                    ("EV / Revenue", median_ev_revenue, target_revenue, target_ev_revenue),
                    ("EV / EBITDA", median_ev_ebitda, target_ebitda, target_ev_ebitda),
                ):
                    if implied_ev is None:
                        continue
                    equity_value = implied_ev - target_debt + target_cash
                    valuation_rows.append(
                        {
                            "Method": method,
                            "Peer median": multiple,
                            "Target metric ($B)": target_metric / 1_000_000_000,
                            "Implied enterprise value ($B)": implied_ev / 1_000_000_000,
                            "Implied equity value ($B)": equity_value / 1_000_000_000,
                            "Implied value per share": equity_value / target_shares if target_shares > 0 else None,
                        }
                    )
                st.dataframe(
                    pd.DataFrame(valuation_rows),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Peer median": st.column_config.NumberColumn(format="%.2fx"),
                        "Target metric ($B)": st.column_config.NumberColumn(format="$%.2f"),
                        "Implied enterprise value ($B)": st.column_config.NumberColumn(format="$%.2f"),
                        "Implied equity value ($B)": st.column_config.NumberColumn(format="$%.2f"),
                        "Implied value per share": st.column_config.NumberColumn(format="$%.2f"),
                    },
                )
                st.caption(
                    "Each multiple method is shown separately. The first ticker is the target; "
                    "later tickers set the peer medians."
                )
            else:
                st.info("The target needs positive revenue or EBITDA data to calculate an implied enterprise value.")

    try:
        peer_prices = _load_peer_price_performance(tuple(company_data))
        if not peer_prices.empty:
            st.markdown("#### Normalized one-year share-price performance")
            st.line_chart(peer_prices, height=280)
    except Exception as exc:
        st.info(f"Peer price comparison unavailable: {exc}")
    st.caption(
        "This is a basic reported-financial comparison. It does not normalize fiscal calendars "
        "or company-specific accounting tags."
    )

with dcf_tab:
    st.markdown("#### Simplified discounted cash flow model")
    st.caption(
        "The model projects free cash flow, discounts forecast cash flows, and adds a perpetual-growth "
        "terminal value. Use consistent cash-flow and discount-rate assumptions; the auto-filled cash-flow "
        "figure is a rough operating-cash-flow-minus-capex proxy, not a normalized FCFF calculation."
    )
    base_fcf = _ltm_metric(latest_quarter, "Free cash flow")
    dcf_snapshot = _market_snapshot(primary_ticker)
    default_base_fcf_m = (base_fcf / 1_000_000) if base_fcf is not None else 0.0
    default_debt = _finite_number(dcf_snapshot.get("totalDebt")) or 0.0
    default_cash = _finite_number(dcf_snapshot.get("totalCash")) or 0.0
    default_net_debt_m = (default_debt - default_cash) / 1_000_000
    default_shares_m = (_finite_number(dcf_snapshot.get("sharesOutstanding")) or 0.0) / 1_000_000

    dcf_inputs = st.columns(5)
    with dcf_inputs[0]:
        base_fcf_m = st.number_input(
            "Base LTM FCF ($M)",
            value=float(default_base_fcf_m),
            step=10.0,
            help="Prefilled from SEC operating cash flow less capital expenditures when available. Edit as needed.",
            key=f"dcf_base_fcf_{primary_ticker}",
        )
    with dcf_inputs[1]:
        fcf_growth_pct = st.number_input(
            "Annual FCF growth (%)", value=8.0, min_value=-100.0, max_value=100.0, step=1.0,
            key=f"dcf_growth_{primary_ticker}",
        )
    with dcf_inputs[2]:
        wacc_pct = st.number_input(
            "Discount rate / WACC (%)", value=10.0, min_value=0.1, max_value=100.0, step=0.5,
            key=f"dcf_wacc_{primary_ticker}",
        )
    with dcf_inputs[3]:
        terminal_growth_pct = st.number_input(
            "Terminal growth (%)", value=2.5, min_value=-20.0, max_value=50.0, step=0.25,
            key=f"dcf_terminal_growth_{primary_ticker}",
        )
    with dcf_inputs[4]:
        projection_years = st.number_input(
            "Forecast years", min_value=3, max_value=10, value=5, step=1,
            key=f"dcf_years_{primary_ticker}",
        )

    balance_inputs = st.columns(3)
    with balance_inputs[0]:
        net_debt_m = st.number_input(
            "Net debt ($M)",
            value=float(default_net_debt_m),
            step=100.0,
            help="Prefilled as yfinance total debt minus cash; adjust if desired.",
            key=f"dcf_net_debt_{primary_ticker}",
        )
    with balance_inputs[1]:
        shares_m = st.number_input(
            "Shares outstanding (M)",
            value=float(default_shares_m),
            min_value=0.0,
            step=10.0,
            key=f"dcf_shares_{primary_ticker}",
        )
    with balance_inputs[2]:
        current_price = (
            _finite_number(dcf_snapshot.get("currentPrice"))
            or _finite_number(dcf_snapshot.get("regularMarketPrice"))
        )
        st.metric("Current share price", "—" if current_price is None else f"${current_price:,.2f}")

    wacc = wacc_pct / 100
    terminal_growth = terminal_growth_pct / 100
    if base_fcf_m <= 0:
        st.warning("Enter positive base-year free cash flow to calculate this growth DCF scenario.")
    elif wacc <= terminal_growth:
        st.error("The discount rate must be greater than the terminal growth rate.")
    else:
        projection, terminal_pv_m, enterprise_value_m = _dcf_value(
            base_fcf_m,
            fcf_growth_pct / 100,
            wacc,
            terminal_growth,
            int(projection_years),
        )
        equity_value_m = enterprise_value_m - net_debt_m
        per_share = equity_value_m / shares_m if shares_m > 0 else None
        dcf_cards = st.columns(4)
        dcf_cards[0].metric("Enterprise value", f"${enterprise_value_m:,.0f}M")
        dcf_cards[1].metric("Present value of terminal value", f"${terminal_pv_m:,.0f}M")
        dcf_cards[2].metric("Equity value", f"${equity_value_m:,.0f}M")
        dcf_cards[3].metric("Implied value per share", "—" if per_share is None else f"${per_share:,.2f}")

        st.markdown("#### Forecast")
        st.bar_chart(projection.set_index("Year")[["Projected FCF ($M)", "Present value ($M)"]], height=280)
        st.dataframe(projection, hide_index=True, use_container_width=True)

        sensitivity_rows = []
        for scenario_wacc_pct in [wacc_pct - 2, wacc_pct - 1, wacc_pct, wacc_pct + 1, wacc_pct + 2]:
            scenario_wacc = scenario_wacc_pct / 100
            row: dict[str, Any] = {"Discount rate": f"{scenario_wacc_pct:.1f}%"}
            for scenario_growth_pct in [terminal_growth_pct - 1, terminal_growth_pct, terminal_growth_pct + 1]:
                scenario_growth = scenario_growth_pct / 100
                label = f"Terminal growth {scenario_growth_pct:.1f}%"
                if scenario_wacc <= 0 or scenario_wacc <= scenario_growth:
                    row[label] = None
                    continue
                _, _, scenario_ev = _dcf_value(
                    base_fcf_m,
                    fcf_growth_pct / 100,
                    scenario_wacc,
                    scenario_growth,
                    int(projection_years),
                )
                row[label] = scenario_ev - net_debt_m
            sensitivity_rows.append(row)
        st.markdown("#### Equity value sensitivity ($M)")
        st.dataframe(pd.DataFrame(sensitivity_rows), hide_index=True, use_container_width=True)
    st.caption("Illustrative scenario output only. The result depends heavily on user assumptions.")

with precedents_tab:
    st.markdown("#### Precedent transactions")
    st.caption(
        "No transaction database is connected. Enter announced deals below; the dashboard calculates "
        "EV / LTM revenue and EV / LTM EBITDA, then applies the median multiples to the target inputs."
    )
    blank_deals = pd.DataFrame(
        {
            "Acquired company": ["", "", ""],
            "Announcement date": ["", "", ""],
            "Enterprise value ($M)": pd.Series([np.nan, np.nan, np.nan], dtype="float64"),
            "LTM revenue ($M)": pd.Series([np.nan, np.nan, np.nan], dtype="float64"),
            "LTM EBITDA ($M)": pd.Series([np.nan, np.nan, np.nan], dtype="float64"),
        }
    )
    transaction_data = st.data_editor(
        blank_deals,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "Enterprise value ($M)": st.column_config.NumberColumn(format="$%.1f"),
            "LTM revenue ($M)": st.column_config.NumberColumn(format="$%.1f"),
            "LTM EBITDA ($M)": st.column_config.NumberColumn(format="$%.1f"),
        },
        key=f"precedent_transaction_inputs_{primary_ticker}",
    )
    transaction_data["Enterprise value ($M)"] = pd.to_numeric(
        transaction_data["Enterprise value ($M)"], errors="coerce"
    )
    transaction_data["LTM revenue ($M)"] = pd.to_numeric(
        transaction_data["LTM revenue ($M)"], errors="coerce"
    )
    transaction_data["LTM EBITDA ($M)"] = pd.to_numeric(
        transaction_data["LTM EBITDA ($M)"], errors="coerce"
    )
    transaction_data["EV / Revenue"] = transaction_data["Enterprise value ($M)"] / transaction_data[
        "LTM revenue ($M)"
    ].where(transaction_data["LTM revenue ($M)"] > 0)
    transaction_data["EV / EBITDA"] = transaction_data["Enterprise value ($M)"] / transaction_data[
        "LTM EBITDA ($M)"
    ].where(transaction_data["LTM EBITDA ($M)"] > 0)
    st.dataframe(
        transaction_data,
        hide_index=True,
        use_container_width=True,
        column_config={
            "EV / Revenue": st.column_config.NumberColumn(format="%.2fx"),
            "EV / EBITDA": st.column_config.NumberColumn(format="%.2fx"),
        },
    )

    target_ltm_revenue_m = _ltm_revenue(latest_quarter)
    target_ltm_revenue_m = target_ltm_revenue_m / 1_000_000 if target_ltm_revenue_m else 0.0
    target_snapshot = _market_snapshot(primary_ticker)
    target_ebitda_m = (_finite_number(target_snapshot.get("ebitda")) or 0.0) / 1_000_000
    target_inputs = st.columns(2)
    with target_inputs[0]:
        target_revenue_m = st.number_input(
            "Target LTM revenue ($M)",
            value=float(target_ltm_revenue_m),
            min_value=0.0,
            step=10.0,
            key=f"target_ltm_revenue_m_{primary_ticker}",
        )
    with target_inputs[1]:
        target_ebitda_m = st.number_input(
            "Target LTM EBITDA ($M)",
            value=float(target_ebitda_m),
            step=10.0,
            help="Prefilled from yfinance where available; replace with a normalized figure if needed.",
            key=f"target_ltm_ebitda_m_{primary_ticker}",
        )

    median_ev_revenue = transaction_data["EV / Revenue"].median()
    median_ev_ebitda = transaction_data["EV / EBITDA"].median()
    result_cards = st.columns(4)
    result_cards[0].metric(
        "Median EV / Revenue", "—" if pd.isna(median_ev_revenue) else f"{median_ev_revenue:.2f}x"
    )
    result_cards[1].metric(
        "Revenue-based implied EV",
        "—" if pd.isna(median_ev_revenue) or target_revenue_m <= 0 else f"${median_ev_revenue * target_revenue_m:,.0f}M",
    )
    result_cards[2].metric(
        "Median EV / EBITDA", "—" if pd.isna(median_ev_ebitda) else f"{median_ev_ebitda:.2f}x"
    )
    result_cards[3].metric(
        "EBITDA-based implied EV",
        "—" if pd.isna(median_ev_ebitda) or target_ebitda_m <= 0 else f"${median_ev_ebitda * target_ebitda_m:,.0f}M",
    )

with filings_tab:
    st.markdown("#### Recent SEC filings")
    if filing_load_error:
        st.error(f"Could not load SEC filing history: {filing_load_error}")
    elif not filing_rows:
        st.info("No recent filing records were returned.")
    else:
        form_filter = st.multiselect(
            "Forms",
            options=sorted({row["Form"] for row in filing_rows}),
            default=[
                form
                for form in ("10-K", "10-Q", "8-K")
                if any(row["Form"] == form for row in filing_rows)
            ],
        )
        filtered_rows = [row for row in filing_rows if not form_filter or row["Form"] in form_filter]
        filing_frame = pd.DataFrame(filtered_rows[:30])
        st.dataframe(
            filing_frame,
            hide_index=True,
            use_container_width=True,
            column_config={
                "URL": st.column_config.LinkColumn("Original SEC filing", display_text="Open"),
            },
        )

with st.sidebar:
    st.divider()
    st.caption("Data from SEC EDGAR and yfinance. Values are informational and may be incomplete.")
