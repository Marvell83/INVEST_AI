"""Offline, source-preserving financial screener from existing INVEST_AI research JSONs.

No stock prices are fetched here. Price-dependent ratios require an analyst's
already recorded, cited and dated market price in the research report.
Unknown data is None, not zero or an automatic fail.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re

from sec_arsiv import load_json, ticker_mapping

VERSION = "invest-ai-screener-0.1.0"
MAX_REPORT_FILES = 3000
MAX_REPORT_BYTES = 15_000_000
TICKER_FROM_REPORT = re.compile(r"^([A-Z][A-Z0-9.\-]{0,14})_(LIVE|CACHE|DEMO)_")
PERCENT = "percent"
NUMBER = "number"
USD = "usd"
MULTIPLE = "multiple"

# (key, display title, unit, group); price-based fields stay blank without price.
COLUMNS = [
    ("ticker", "Hisse", "text", "Kimlik"),
    ("company", "Şirket", "text", "Kimlik"),
    ("fiscal_year", "Mali yıl", "text", "Kimlik"),
    ("as_of", "Bilgi tarihi", "text", "Kimlik"),
    ("source_mode", "Veri kaynağı", "text", "Kimlik"),
    ("roe", "ROE", PERCENT, "Getiri"),
    ("roic", "ROIC", PERCENT, "Getiri"),
    ("roa", "ROA", PERCENT, "Getiri"),
    ("gross_margin", "Brüt marj", PERCENT, "Kârlılık"),
    ("operating_margin", "Faaliyet marjı", PERCENT, "Kârlılık"),
    ("net_margin", "Net kâr marjı", PERCENT, "Kârlılık"),
    ("revenue_growth", "Gelir büyümesi (1Y)", PERCENT, "Büyüme"),
    ("revenue_cagr_3y", "Gelir CAGR (3Y)", PERCENT, "Büyüme"),
    ("operating_income_growth", "Faaliyet kârı büyümesi", PERCENT, "Büyüme"),
    ("net_income_cagr_3y", "Net kâr CAGR (3Y)", PERCENT, "Büyüme"),
    ("cash_conversion", "CFO / Net kâr", MULTIPLE, "Nakit"),
    ("cash_conversion_3y", "CFO / Net kâr (3Y)", MULTIPLE, "Nakit"),
    ("fcf_margin", "FCF marjı", PERCENT, "Nakit"),
    ("fcf_yield", "FCF getirisi", PERCENT, "Değerleme"),
    ("capex_intensity", "CapEx / Gelir", PERCENT, "Nakit"),
    ("sbc_to_revenue", "Hisse bazlı ödeme / Gelir", PERCENT, "Nakit"),
    ("shareholder_payout", "Temettü + Geri alım / Kâr", PERCENT, "Nakit"),
    ("current_ratio", "Cari oran", MULTIPLE, "Bilanço"),
    ("debt_to_equity", "Borç / Özkaynak", MULTIPLE, "Bilanço"),
    ("net_debt_to_ebitda", "Net borç / FAVÖK*", MULTIPLE, "Bilanço"),
    ("interest_coverage", "Faiz karşılama", MULTIPLE, "Bilanço"),
    ("effective_tax_rate", "Efektif vergi oranı", PERCENT, "Getiri"),
    ("revenue", "Yıllık gelir", USD, "Tutar"),
    ("net_income", "Yıllık net kâr", USD, "Tutar"),
    ("operating_income", "Faaliyet kârı", USD, "Tutar"),
    ("cfo", "Faaliyet nakit akışı", USD, "Tutar"),
    ("fcf", "Serbest nakit akışı", USD, "Tutar"),
    ("fcf_3y", "3 yıllık toplam FCF", USD, "Tutar"),
    ("capex", "CapEx", USD, "Tutar"),
    ("total_assets", "Toplam varlık", USD, "Tutar"),
    ("equity", "Özkaynak", USD, "Tutar"),
    ("total_debt", "Toplam borç", USD, "Tutar"),
    ("net_debt", "Net borç", USD, "Tutar"),
    ("shares", "Dolaşımdaki pay adedi", NUMBER, "Tutar"),
    ("market_price", "Hisse fiyatı (kaynaklı)", USD, "Değerleme"),
    ("market_cap", "Piyasa değeri", USD, "Değerleme"),
    ("pe", "F/K", MULTIPLE, "Değerleme"),
    ("pb", "PD/DD", MULTIPLE, "Değerleme"),
    ("ps", "Fiyat / Satışlar", MULTIPLE, "Değerleme"),
    ("roe_10_pb", "(ROE / 10) / PD/DD", MULTIPLE, "Değerleme"),
    ("ev_ebit", "EV / EBIT", MULTIPLE, "Değerleme"),
    ("ev_ebitda", "EV / FAVÖK*", MULTIPLE, "Değerleme"),
    ("p_fcf", "Fiyat / FCF", MULTIPLE, "Değerleme"),
    ("peg", "PEG (ileri EPS)", MULTIPLE, "Değerleme"),
    ("shares_change_3y", "Hisse adedi değişimi (3Y)", PERCENT, "Büyüme"),
]
COLUMN_KEYS = {c[0] for c in COLUMNS}


def _finite(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def _cell(row, statement, key):
    cell = row.get(statement, {}).get(key, {})
    if cell.get("status") not in ("REPORTED", "DERIVED"):
        return None
    return _finite(cell.get("value"))


def _ratio(ratios, name):
    cell = ratios.get(name, {})
    return _finite(cell.get("value")) if isinstance(cell, dict) else None


def _division(a, b, *, positive=False):
    if a is None or b is None or b == 0 or (positive and b <= 0):
        return None
    return _finite(a / b)


def _cagr(recent, earlier, years):
    if recent is None or earlier is None or recent <= 0 or earlier <= 0 or years <= 0:
        return None
    return _finite((recent / earlier) ** (1 / years) - 1)


def _lineup(report, *, ticker=None, path=None):
    statements = report.get("financial_statements", {})
    ratio_data = report.get("financial_ratios", {})
    years = statements.get("years", [])
    ratio_years = ratio_data.get("years", [])
    if not years or not ratio_years:
        return None
    latest = years[0]
    current_ratios = ratio_years[0].get("ratios", {})
    cik = report.get("cik")
    if not isinstance(cik, str) or not re.fullmatch(r"\d{10}", cik):
        return None
    row = {key: None for key in COLUMN_KEYS}
    row.update(ticker=ticker or cik, company=report.get("company") or cik,
               cik=cik, fiscal_year=latest.get("fiscal_year_end"),
               as_of=report.get("as_of"), sector=report.get("sector_assumption", "unknown"),
               source_mode=(report.get("source") or {}).get("web_data_mode")
               or (report.get("source") or {}).get("mode") or "unknown",
               report_url=path,
               price_source=None, price_date=None, roic_warning=False, ebitda_approximate=False)
    for key, name, *_ in COLUMNS:
        if key in current_ratios:
            row[key] = _ratio(current_ratios, key)
    for key, statement, item in (
        ("revenue", "income", "revenue"), ("net_income", "income", "net_income"),
        ("operating_income", "income", "operating_income"),
        ("cfo", "cash_flow", "cfo"), ("fcf", "cash_flow", "free_cash_flow"),
        ("capex", "cash_flow", "capex"), ("total_assets", "balance", "total_assets"),
        ("equity", "balance", "stockholders_equity"),
        ("total_debt", "balance", "total_debt"), ("net_debt", "balance", "net_debt"),
    ):
        row[key] = _cell(latest, statement, item)
    row["roic_warning"] = bool(current_ratios.get("roic", {}).get("caution")) or bool(
        current_ratios.get("roic", {}).get("approximate"))
    # Do not apply ROIC as a clean filter pass if the small-capital or EBIT-proxy flag is present.
    row["ebitda_approximate"] = bool(latest.get("income", {}).get("operating_income", {}).get("approximate"))
    depreciation = _cell(latest, "cash_flow", "depreciation_amortization")
    ebitda = row["operating_income"] + depreciation if (
        row["operating_income"] is not None and depreciation is not None) else None
    if ebitda is not None:
        row["ebitda_approximate"] = True  # EBIT + CFO-statement D&A is a proxy, not issuer adjusted EBITDA.
    row["net_debt_to_ebitda"] = _division(row["net_debt"], ebitda, positive=True)
    row["ev_ebitda"] = None

    # Require four comparable annual periods for three-year CAGR; no negative-income CAGR.
    if len(years) >= 4 and isinstance(row["fiscal_year"], str):
        from datetime import date
        try:
            recent = date.fromisoformat(row["fiscal_year"])
            old = date.fromisoformat(years[3]["fiscal_year_end"])
            valid = 1050 <= (recent - old).days <= 1140
        except (TypeError, ValueError):
            valid = False
        if valid:
            row["revenue_cagr_3y"] = _cagr(row["revenue"], _cell(years[3], "income", "revenue"), 3)
            row["net_income_cagr_3y"] = _cagr(row["net_income"], _cell(years[3], "income", "net_income"), 3)

    # Three consecutive annual years: direct FY values, no interpolation.
    if len(years) >= 3:
        first_three = years[:3]
        try:
            from datetime import date
            dates = [date.fromisoformat(y["fiscal_year_end"]) for y in first_three]
            contiguous = all(330 <= (dates[i] - dates[i+1]).days <= 400 for i in range(2))
        except (ValueError, TypeError):
            contiguous = False
        if contiguous:
            cash = [_cell(y, "cash_flow", "cfo") for y in first_three]
            income = [_cell(y, "income", "net_income") for y in first_three]
            fcfs = [_cell(y, "cash_flow", "free_cash_flow") for y in first_three]
            if all(x is not None for x in cash + income) and sum(income) > 0:
                row["cash_conversion_3y"] = _finite(sum(cash) / sum(income))
            if all(x is not None for x in fcfs):
                row["fcf_3y"] = sum(fcfs)

    shares = statements.get("shares_outstanding", {})
    row["shares"] = _finite(shares.get("value")) if shares.get("status") == "REPORTED" else None

    # Price is solely the dated, source-described user price saved by reverse DCF.
    recorded = (report.get("implied_growth") or {}).get("price", {})
    if (isinstance(recorded, dict) and _finite(recorded.get("value")) is not None
            and isinstance(recorded.get("source"), str) and recorded.get("source", "").strip()
            and isinstance(recorded.get("date"), str)):
        price = recorded["value"]
        if price > 0:
            row.update(market_price=price, price_source=recorded["source"], price_date=recorded["date"])
            # A price dated after the financial snapshot is NOT treated as a period-matched valuation.
            # Require a dated cover-page share count not later than the observed price,
            # and no more than ~one quarter apart. Otherwise market multiples are misleading.
            aligned = False
            if row["as_of"] and row["shares"] is not None:
                from datetime import date
                try:
                    pricing = date.fromisoformat(recorded["date"])
                    cutoff = date.fromisoformat(row["as_of"])
                    shares_date = date.fromisoformat(shares["date"])
                    aligned = shares_date <= pricing <= cutoff and (pricing - shares_date).days <= 100
                except (KeyError, TypeError, ValueError):
                    pass
            if aligned:
                cap = _finite(price * row["shares"])
                row["market_cap"] = cap
                row["pe"] = _division(cap, row["net_income"], positive=True)
                row["pb"] = _division(cap, row["equity"], positive=True)
                row["ps"] = _division(cap, row["revenue"], positive=True)
                row["p_fcf"] = _division(cap, row["fcf"], positive=True)
                row["fcf_yield"] = _division(row["fcf"], cap, positive=True)
                pb = row["pb"]
                row["roe_10_pb"] = _division(row["roe"] * 10 if row["roe"] is not None else None,
                                             pb, positive=True)
                ev = cap + row["net_debt"] if cap is not None and row["net_debt"] is not None else None
                row["ev_ebit"] = _division(ev, row["operating_income"], positive=True)
                row["ev_ebitda"] = _division(ev, ebitda, positive=True)
    # PEG needs explicit forward EPS growth. Historic revenue growth is not a substitute.
    # Three-year shares change needs historical comparable share counts, not current DEI only.
    return row


def load_screening(root, *, limit=MAX_REPORT_FILES):
    """Latest available dated fundamentals by CIK from locally saved research files.

    Does not call SEC, silently download prices, or silently score missing data.
    This first screen is populated only by completed locally saved analyses.
    """
    root = Path(root).resolve()
    folder = root / "reports"
    if not folder.is_dir():
        return {"version": VERSION, "columns": COLUMNS, "rows": [],
                "available": 0, "scanned_files": 0, "warnings": []}
    ticker_names = {}
    map_path = root / "veri/sec_ticker_esleme.json"
    if map_path.is_file():
        mapping = ticker_mapping(load_json(map_path, max_bytes=12_000_000))
        for symbol, number in mapping.items():
            ticker_names.setdefault(f"{number:010d}", symbol)
    files = sorted(folder.rglob("*.json"), key=lambda p: p.as_posix())[:limit]
    records = {}
    warnings = []
    for path in files:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
            continue
        try:
            with path.open(encoding="utf-8") as handle:
                obj = json.load(handle)
        except (OSError, ValueError, UnicodeError):
            continue
        if not isinstance(obj, dict) or "financial_statements" not in obj or "financial_ratios" not in obj:
            continue
        cik = obj.get("cik")
        match = TICKER_FROM_REPORT.match(path.name)
        symbol = ticker_names.get(cik) or (match.group(1) if match else None)
        row = _lineup(obj, ticker=symbol, path="/"+path.with_suffix(".html").relative_to(root).as_posix())
        if row is None:
            continue
        key = row["cik"]
        old = records.get(key)
        ordering = (row["as_of"] or "", bool(row["market_price"] is not None),
                    row["source_mode"] != "demo", path.name)
        if old is None or ordering > old[0]:
            records[key] = (ordering, row)
    if len(files) == limit:
        warnings.append("SEARCH_BOUND_REACHED: add batch persistence before expanding file limits")
    rows = [pair[1] for pair in records.values()]
    rows.sort(key=lambda row: (row["ticker"] or "", row["cik"]))
    return {"version": VERSION, "columns": COLUMNS,
            "rows": rows, "available": len(rows),
            "scanned_files": len(files), "warnings": warnings,
            "scope": "SAVED_RESEARCH_ONLY", "market_price_fetched": False,
            "notes": [
                "Null means missing/non-comparable, never zero; do not automatically fail missing values",
                "Only already saved research reports; SEC ticker list alone has no financial ratios",
                "Price-derived multiples require source-cited analyst price and usable DEI shares",
                "FAVÖK* = operating income + statement depreciation/amortization proxy",
                "PEG requires forward EPS growth and is not fabricated from revenue CAGR",
            ]}

