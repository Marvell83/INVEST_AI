"""INVEST_AI — point-in-time, source-traced annual financial statements.

One shared layer that reads SEC Company Facts (US-GAAP, annual 10-K / 10-K/A)
with uniform rules, so that ratio, quality, forecast and valuation engines do
not each pick XBRL tags on their own. Every value keeps its concept, accession,
form, filed date and period. Missing is never zero; conflicting aliases are
reported, not resolved. Facts filed after `as_of` are invisible.

SEC `fy` / `fp` fields describe the FILING, not the fact, so fiscal years are
identified only from each fact's own start/end dates.
"""
from __future__ import annotations

import datetime as dt
import math

from sec_companyfacts import METRICS, SEC_DATA, _date, _validate_cik

VERSION = "finansal-tablolar-0.1.0"
ANNUAL_FORMS = frozenset(("10-K", "10-K/A"))
ALIAS_TOLERANCE = 0.005  # ambiguity guard between XBRL aliases, not an accounting standard
MAX_YEARS = 10
STATEMENTS = ("income", "cash_flow", "balance")

# key: (statement, flow/instant, unit, Turkish label, aliases in priority order)
LINE_ITEMS = {
    "revenue": ("income", "flow", "USD", "Gelir", METRICS["revenue"]),
    "cost_of_revenue": ("income", "flow", "USD", "Satışların maliyeti",
                        ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold")),
    "gross_profit": ("income", "flow", "USD", "Brüt kâr", ("GrossProfit",)),
    "research_development": ("income", "flow", "USD", "Ar-Ge gideri",
                             ("ResearchAndDevelopmentExpense",)),
    "operating_income": ("income", "flow", "USD", "Faaliyet kârı", ("OperatingIncomeLoss",)),
    "interest_expense": ("income", "flow", "USD", "Faiz gideri",
                         ("InterestExpense", "InterestExpenseNonoperating")),
    "pretax_income": ("income", "flow", "USD", "Vergi öncesi kâr", (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments")),
    "income_tax": ("income", "flow", "USD", "Gelir vergisi gideri", ("IncomeTaxExpenseBenefit",)),
    "net_income": ("income", "flow", "USD", "Net kâr (ana ortaklık)", ("NetIncomeLoss",)),
    "diluted_shares": ("income", "flow", "shares", "Seyreltilmiş ortalama hisse",
                       ("WeightedAverageNumberOfDilutedSharesOutstanding",)),
    "cfo": ("cash_flow", "flow", "USD", "Faaliyet nakit akışı",
            ("NetCashProvidedByUsedInOperatingActivities",)),
    "capex": ("cash_flow", "flow", "USD", "Maddi duran varlık yatırımı (CapEx)",
              ("PaymentsToAcquirePropertyPlantAndEquipment",)),
    "depreciation_amortization": ("cash_flow", "flow", "USD", "Amortisman",
                                  ("DepreciationDepletionAndAmortization", "DepreciationAndAmortization")),
    "share_based_compensation": ("cash_flow", "flow", "USD", "Hisse bazlı ödeme",
                                 ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense")),
    "dividends_paid": ("cash_flow", "flow", "USD", "Ödenen temettü",
                       ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock")),
    "share_repurchases": ("cash_flow", "flow", "USD", "Hisse geri alımı",
                          ("PaymentsForRepurchaseOfCommonStock",)),
    "cash": ("balance", "instant", "USD", "Nakit ve nakit benzerleri",
             ("CashAndCashEquivalentsAtCarryingValue",)),
    "current_assets": ("balance", "instant", "USD", "Dönen varlıklar", ("AssetsCurrent",)),
    "total_assets": ("balance", "instant", "USD", "Toplam varlıklar", ("Assets",)),
    "current_liabilities": ("balance", "instant", "USD", "Kısa vadeli yükümlülükler",
                            ("LiabilitiesCurrent",)),
    "total_liabilities": ("balance", "instant", "USD", "Toplam yükümlülükler", ("Liabilities",)),
    "commercial_paper": ("balance", "instant", "USD", "Ticari senet", ("CommercialPaper",)),
    "short_term_borrowings": ("balance", "instant", "USD", "Kısa vadeli borçlanma",
                              ("ShortTermBorrowings",)),
    "long_term_debt_current": ("balance", "instant", "USD", "Uzun vadeli borcun kısa vadeli kısmı",
                               ("LongTermDebtCurrent",)),
    "long_term_debt_noncurrent": ("balance", "instant", "USD", "Uzun vadeli borç (uzun vadeli kısım)",
                                  ("LongTermDebtNoncurrent",)),
    "long_term_debt": ("balance", "instant", "USD", "Uzun vadeli borç (kısa vadeli kısım dahil)",
                       ("LongTermDebt",)),
    "stockholders_equity": ("balance", "instant", "USD", "Özkaynak (ana ortaklık)",
                            ("StockholdersEquity",)),
}
DERIVED_ITEMS = {
    "free_cash_flow": ("cash_flow", "USD", "Serbest nakit akışı (CFO − CapEx; FCFF değildir)"),
    "total_debt": ("balance", "USD", "Toplam finansal borç (kira yükümlülükleri hariç)"),
}
ANCHOR_ITEMS = ("revenue", "net_income", "operating_income", "cfo")


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and abs(value) < 1e30)


def _facts(raw, tag, unit, cutoff, instant):
    """All time-eligible annual-filing facts of one concept, keyed by period."""
    rows = raw["facts"].get("us-gaap", {}).get(tag, {}).get("units", {}).get(unit, [])
    by_period = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("form") not in ANNUAL_FORMS:
            continue
        if not isinstance(row.get("accn"), str) or not row["accn"] or not _number(row.get("val")):
            continue
        try:
            end, filed = _date(row.get("end")), _date(row.get("filed"))
            start = None if instant else _date(row.get("start"))
        except ValueError:
            continue
        if end > cutoff or filed > cutoff:
            continue
        if not instant and not 330 <= (end - start).days + 1 <= 400:
            continue
        fact = {"value": float(row["val"]), "unit": unit, "concept": tag,
                "start": None if instant else start.isoformat(), "end": end.isoformat(),
                "filed": filed.isoformat(), "accession": row["accn"], "form": row["form"]}
        by_period.setdefault((fact["start"], fact["end"]), []).append(fact)
    return by_period


def _latest(versions):
    """Latest filing wins (restatements); keep the first-reported value visible."""
    ordered = sorted(versions, key=lambda f: (f["filed"], f["form"] == "10-K/A", f["accession"]))
    chosen = dict(ordered[-1])
    first = ordered[0]
    chosen["revised"] = any(f["value"] != chosen["value"] for f in ordered)
    if chosen["revised"]:
        chosen["first_reported"] = {"value": first["value"], "filed": first["filed"],
                                    "accession": first["accession"]}
    return chosen


def _fiscal_years(raw, cutoff):
    """Annual (start, end) periods seen on anchor items, most recent first."""
    starts_by_end = {}
    for key in ANCHOR_ITEMS:
        for tag in LINE_ITEMS[key][4]:
            for start, end in _facts(raw, tag, "USD", cutoff, False):
                starts_by_end.setdefault(end, {}).setdefault(start, 0)
                starts_by_end[end][start] += 1
    years = []
    for end, starts in starts_by_end.items():
        start = max(sorted(starts), key=lambda s: starts[s])
        years.append({"start": start, "end": end, "start_ambiguous": len(starts) > 1})
    return sorted(years, key=lambda y: y["end"], reverse=True)


def _cell(raw, key, year, cutoff):
    statement, kind, unit, label, tags = LINE_ITEMS[key]
    instant = kind == "instant"
    period = (None if instant else year["start"], year["end"])
    found = []
    for tag in tags:
        versions = _facts(raw, tag, unit, cutoff, instant).get(period)
        if versions:
            found.append(_latest(versions))
    if not found:
        return {"status": "MISSING", "value": None, "unit": unit, "reason": "NOT_REPORTED"}
    values = [f["value"] for f in found]
    peak = max(abs(v) for v in values)
    if peak and (max(values) - min(values)) / peak > ALIAS_TOLERANCE:
        return {"status": "CONFLICT", "value": None, "unit": unit,
                "reason": "XBRL_ALIASES_DISAGREE", "alternatives": found}
    cell = dict(found[0], status="REPORTED")
    if len(found) > 1:
        cell["agreeing_aliases"] = [f["concept"] for f in found[1:]]
    return cell


def _same_filing(*cells):
    return len({c["accession"] for c in cells}) == 1


def _derive(year):
    income, cash_flow, balance = year["income"], year["cash_flow"], year["balance"]
    revenue, cost = income["revenue"], income["cost_of_revenue"]
    if income["gross_profit"]["status"] == "MISSING":
        if revenue["status"] == "REPORTED" and cost["status"] == "REPORTED" and _same_filing(revenue, cost):
            income["gross_profit"] = {
                "status": "DERIVED", "value": revenue["value"] - cost["value"], "unit": "USD",
                "method": "REVENUE_MINUS_COST_OF_REVENUE_SAME_FILING",
                "accession": revenue["accession"], "filed": revenue["filed"],
                "derivation": {"revenue": revenue["concept"], "cost_of_revenue": cost["concept"]}}

    cfo, capex = cash_flow["cfo"], cash_flow["capex"]
    if cfo["status"] == "REPORTED" and capex["status"] == "REPORTED" and _same_filing(cfo, capex):
        cash_flow["free_cash_flow"] = {
            "status": "DERIVED", "value": cfo["value"] - capex["value"], "unit": "USD",
            "method": "CFO_MINUS_CAPEX_SAME_FILING", "is_fcff": False,
            "accession": cfo["accession"], "filed": cfo["filed"]}
    else:
        reason = ("CFO_AND_CAPEX_FROM_DIFFERENT_FILINGS"
                  if cfo["status"] == capex["status"] == "REPORTED" else "CFO_OR_CAPEX_UNAVAILABLE")
        cash_flow["free_cash_flow"] = {"status": "MISSING", "value": None, "unit": "USD",
                                       "reason": reason}

    # Total debt never treats an unreported component as zero: it lists what was
    # summed and what was not reported. LongTermDebt already includes the current
    # portion, so it is only a fallback when the noncurrent line is absent.
    reported = {k: balance[k] for k in ("long_term_debt_noncurrent", "long_term_debt_current",
                                        "long_term_debt", "commercial_paper", "short_term_borrowings")
                if balance[k]["status"] == "REPORTED"}
    conflicts = [k for k in ("long_term_debt_noncurrent", "long_term_debt_current",
                             "long_term_debt", "commercial_paper", "short_term_borrowings")
                 if balance[k]["status"] == "CONFLICT"]
    if "long_term_debt_noncurrent" in reported:
        used = ["long_term_debt_noncurrent", "long_term_debt_current"]
    else:
        used = ["long_term_debt"]
    used += ["commercial_paper", "short_term_borrowings"]
    summed = [k for k in used if k in reported]
    if conflicts:
        balance["total_debt"] = {"status": "MISSING", "value": None, "unit": "USD",
                                 "reason": "DEBT_COMPONENT_CONFLICT", "components_in_conflict": conflicts}
    elif not summed:
        balance["total_debt"] = {"status": "MISSING", "value": None, "unit": "USD",
                                 "reason": "NO_DEBT_COMPONENT_REPORTED"}
    elif not _same_filing(*(reported[k] for k in summed)):
        balance["total_debt"] = {"status": "MISSING", "value": None, "unit": "USD",
                                 "reason": "DEBT_COMPONENTS_FROM_DIFFERENT_FILINGS"}
    else:
        balance["total_debt"] = {
            "status": "DERIVED", "value": sum(reported[k]["value"] for k in summed), "unit": "USD",
            "method": "SUM_OF_REPORTED_DEBT_COMPONENTS_SAME_FILING", "components": summed,
            "accession": reported[summed[0]]["accession"], "filed": reported[summed[0]]["filed"],
            "components_not_reported": [k for k in used if k not in reported],
            "excludes": "operating and finance lease liabilities"}


def build_annual_statements(raw, *, as_of, years=5):
    """Return up to `years` most recent fiscal years of annual statements.

    A company with no eligible annual 10-K data returns status NO_ANNUAL_PERIODS
    rather than raising, so a research report can still show the gap.
    """
    cutoff = _date(as_of)
    if isinstance(years, bool) or not isinstance(years, int) or not 1 <= years <= MAX_YEARS:
        raise ValueError(f"years must be an integer in 1..{MAX_YEARS}")
    if not isinstance(raw, dict) or not isinstance(raw.get("facts"), dict):
        raise ValueError("raw SEC Company Facts object required")
    cik = _validate_cik(raw.get("cik"))
    periods = _fiscal_years(raw, cutoff)[:years]
    rows = []
    for period in periods:
        year = {"fiscal_year_start": period["start"], "fiscal_year_end": period["end"],
                "start_ambiguous": period["start_ambiguous"]}
        for statement in STATEMENTS:
            year[statement] = {key: _cell(raw, key, period, cutoff)
                               for key, spec in LINE_ITEMS.items() if spec[0] == statement}
        _derive(year)
        rows.append(year)

    coverage = {}
    for key in list(LINE_ITEMS) + list(DERIVED_ITEMS):
        statement = LINE_ITEMS[key][0] if key in LINE_ITEMS else DERIVED_ITEMS[key][0]
        statuses = [row[statement][key]["status"] for row in rows]
        coverage[key] = {"available": sum(s in ("REPORTED", "DERIVED") for s in statuses),
                         "conflicts": statuses.count("CONFLICT")}
    conflicts = [{"fiscal_year_end": row["fiscal_year_end"], "item": key,
                  "concepts": [a["concept"] for a in cell["alternatives"]]}
                 for row in rows for statement in STATEMENTS
                 for key, cell in row[statement].items() if cell["status"] == "CONFLICT"]
    return {
        "version": VERSION, "cik": f"{cik:010d}", "company": raw.get("entityName", ""),
        "as_of": as_of, "source_url": SEC_DATA.format(cik=cik),
        "status": "OK" if rows else "NO_ANNUAL_PERIODS",
        "years": rows, "coverage": coverage, "conflicts": conflicts,
        "rules": [
            "Only 10-K / 10-K/A facts filed on or before as_of; fiscal years from fact dates, not SEC fy/fp",
            "Latest filing wins for a period; earlier differing values are kept as first_reported",
            f"XBRL aliases differing by more than {ALIAS_TOLERANCE:.1%} are a CONFLICT with no value",
            "Missing values are null, never zero; derived values require one SEC filing",
            "Outflows (CapEx, dividends, repurchases) are positive payments as reported",
        ],
    }


def line_item_label(key):
    if key in LINE_ITEMS:
        return LINE_ITEMS[key][3]
    return DERIVED_ITEMS[key][2]


def previous_year(statements, index):
    """The year before rows[index] if it ends 330..400 days earlier, else None."""
    rows = statements["years"]
    if index + 1 >= len(rows):
        return None
    current = dt.date.fromisoformat(rows[index]["fiscal_year_end"])
    prior = dt.date.fromisoformat(rows[index + 1]["fiscal_year_end"])
    return rows[index + 1] if 330 <= (current - prior).days <= 400 else None
