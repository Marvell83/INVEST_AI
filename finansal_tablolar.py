"""INVEST_AI — point-in-time, source-traced annual and quarterly financial statements.

One shared layer that reads SEC Company Facts (US-GAAP, 10-K / 10-Q) with
uniform rules, so that ratio, quality, forecast and valuation engines do not
each pick XBRL tags on their own. Every value keeps its concept, accession,
form, filed date and period. Missing is never zero; conflicting aliases are
reported, not resolved. Facts filed after `as_of` are invisible.

SEC `fy` / `fp` fields describe the FILING, not the fact, so fiscal years and
quarters are identified only from each fact's own start/end dates.
"""
from __future__ import annotations

from collections import Counter
import datetime as dt
import math

from sec_companyfacts import METRICS, SEC_DATA, _date, _validate_cik

VERSION = "finansal-tablolar-0.5.1"
ANNUAL_FORMS = frozenset(("10-K", "10-K/A"))
QUARTERLY_FORMS = frozenset(("10-Q", "10-Q/A", "10-K", "10-K/A"))
ALIAS_TOLERANCE = 0.005  # ambiguity guard between XBRL aliases, not an accounting standard
# Revenue tags differ in scope by design (e.g. net sales vs. total revenues that add
# membership income). Up to this gap the priority alias is used and the gap stays
# visible as `alias_gap`; piotroski_fscore applies the same 5% rule.
ITEM_ALIAS_TOLERANCE = {"revenue": 0.05}
# Broader concepts read only when none of an item's aliases is reported for the period:
# NVIDIA and Amazon tag CapEx as productive-asset payments (property plus intangibles),
# P&G its balance-sheet cash including restricted cash, some issuers only total equity.
FALLBACK_ALIASES = {
    "capex": ("PaymentsToAcquireProductiveAssets",),
    "cash": ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",),
    "stockholders_equity": ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",),
}
MAX_YEARS = 10
MAX_QUARTERS = 40
STATEMENTS = ("income", "cash_flow", "balance")
# Fiscal year-to-date lengths in days for Q1, Q2 and Q3 (52/53-week years included).
YTD_DAYS = {1: (80, 110), 2: (170, 200), 3: (240, 310)}

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
                                 ("ShareBasedCompensation",)),
    "dividends_paid": ("cash_flow", "flow", "USD", "Ödenen temettü",
                       ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock")),
    "share_repurchases": ("cash_flow", "flow", "USD", "Hisse geri alımı",
                          ("PaymentsForRepurchaseOfCommonStock",)),
    "cash": ("balance", "instant", "USD", "Nakit ve nakit benzerleri",
             ("CashAndCashEquivalentsAtCarryingValue",)),
    "short_term_investments": ("balance", "instant", "USD", "Kısa vadeli yatırımlar", ("ShortTermInvestments",)),
    "other_short_term_investments": ("balance", "instant", "USD", "Diğer kısa vadeli yatırımlar",
                                     ("OtherShortTermInvestments",)),
    "marketable_securities_current": ("balance", "instant", "USD", "Menkul kıymetler (kısa vadeli)",
                                      ("MarketableSecuritiesCurrent",)),
    "marketable_securities_noncurrent": ("balance", "instant", "USD", "Menkul kıymetler (uzun vadeli)",
                                         ("MarketableSecuritiesNoncurrent",)),
    "marketable_securities_unclassified": ("balance", "instant", "USD", "Menkul kıymetler (vade ayrımı yok)",
                                           ("MarketableSecurities",)),
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
    "operating_lease_liability_current": ("balance", "instant", "USD", "Faaliyet kiralaması yükümlülüğü (kısa vadeli)",
                                          ("OperatingLeaseLiabilityCurrent",)),
    "operating_lease_liability_noncurrent": ("balance", "instant", "USD",
                                             "Faaliyet kiralaması yükümlülüğü (uzun vadeli)",
                                             ("OperatingLeaseLiabilityNoncurrent",)),
    "finance_lease_liability_current": ("balance", "instant", "USD", "Finansal kiralama yükümlülüğü (kısa vadeli)",
                                        ("FinanceLeaseLiabilityCurrent",)),
    "finance_lease_liability_noncurrent": ("balance", "instant", "USD", "Finansal kiralama yükümlülüğü (uzun vadeli)",
                                           ("FinanceLeaseLiabilityNoncurrent",)),
    "stockholders_equity": ("balance", "instant", "USD", "Özkaynak (ana ortaklık)",
                            ("StockholdersEquity",)),
}
DERIVED_ITEMS = {
    "free_cash_flow": ("cash_flow", "USD", "Serbest nakit akışı (CFO − CapEx; FCFF değildir)"),
    "total_debt": ("balance", "USD", "Toplam finansal borç (kira yükümlülükleri hariç)"),
    "liquid_investments": ("balance", "USD", "Menkul kıymetler ve kısa vadeli yatırımlar (toplam)"),
    "lease_liabilities": ("balance", "USD", "Kira yükümlülükleri (faaliyet + finansal; net borca dahil değil)"),
    "net_debt": ("balance", "USD", "Net borç (toplam borç − nakit − menkul kıymetler)"),
}
DEBT_COMPONENTS = ("long_term_debt_noncurrent", "long_term_debt_current", "long_term_debt",
                   "commercial_paper", "short_term_borrowings")
SECURITIES_COMPONENTS = ("short_term_investments", "other_short_term_investments",
                         "marketable_securities_current", "marketable_securities_noncurrent")
ROIC_CAUTION = 1.0  # above 100% the invested capital base is too small to read the ratio plainly
LEASE_COMPONENTS = ("operating_lease_liability_current", "operating_lease_liability_noncurrent",
                    "finance_lease_liability_current", "finance_lease_liability_noncurrent")
ANCHOR_ITEMS = ("revenue", "net_income", "operating_income", "cfo")
# Weighted-average share counts are not additive: a YTD difference is meaningless.
NON_ADDITIVE = frozenset(("diluted_shares",))
SHARES_OUTSTANDING_CONCEPT = "EntityCommonStockSharesOutstanding"
TTM_CORE = ("revenue", "operating_income", "cfo", "capex")  # the items both older TTM engines require


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and abs(value) < 1e30)


def _facts(raw, tag, unit, cutoff, instant, forms, days):
    """All time-eligible facts of one concept from `forms`, keyed by period.

    `days` bounds flow durations; None keeps every duration for exact-period lookups.
    """
    rows = raw["facts"].get("us-gaap", {}).get(tag, {}).get("units", {}).get(unit, [])
    by_period = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("form") not in forms:
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
        if not instant and (start > end or (days and not days[0] <= (end - start).days + 1 <= days[1])):
            continue
        fact = {"value": float(row["val"]), "unit": unit, "concept": tag,
                "start": None if instant else start.isoformat(), "end": end.isoformat(),
                "filed": filed.isoformat(), "accession": row["accn"], "form": row["form"]}
        by_period.setdefault((fact["start"], fact["end"]), []).append(fact)
    return by_period


def _reader(raw, cutoff, forms, days):
    """Memoised `read(tag, unit, instant)` for one form set and duration rule."""
    cache = {}

    def read(tag, unit, instant):
        key = (tag, unit, instant)
        if key not in cache:
            cache[key] = _facts(raw, tag, unit, cutoff, instant, forms, days)
        return cache[key]
    return read


def _latest(versions):
    """Latest filing wins (restatements); keep the first-reported value visible."""
    ordered = sorted(versions, key=lambda f: (f["filed"], f["form"].endswith("/A"), f["accession"]))
    chosen = dict(ordered[-1])
    first = ordered[0]
    chosen["revised"] = any(f["value"] != chosen["value"] for f in ordered)
    if chosen["revised"]:
        chosen["first_reported"] = {"value": first["value"], "filed": first["filed"],
                                    "accession": first["accession"]}
    return chosen


def _fiscal_years(read):
    """Annual (start, end) periods seen on anchor items, most recent first."""
    starts_by_end = {}
    for key in ANCHOR_ITEMS:
        for tag in LINE_ITEMS[key][4]:
            for start, end in read(tag, "USD", False):
                starts_by_end.setdefault(end, {}).setdefault(start, 0)
                starts_by_end[end][start] += 1
    years = []
    for end, starts in starts_by_end.items():
        start = max(sorted(starts), key=lambda s: starts[s])
        years.append({"start": start, "end": end, "start_ambiguous": len(starts) > 1})
    return sorted(years, key=lambda y: y["end"], reverse=True)


def _cell(read, key, start, end):
    """One line item for one exact period; `start` is ignored for balance items."""
    statement, kind, unit, label, tags = LINE_ITEMS[key]
    instant = kind == "instant"
    period = (None if instant else start, end)
    found = []
    for group in (tags, FALLBACK_ALIASES.get(key, ())):
        for tag in group:
            versions = read(tag, unit, instant).get(period)
            if versions:
                found.append(_latest(versions))
        if found:
            break
    if not found:
        return {"status": "MISSING", "value": None, "unit": unit, "reason": "NOT_REPORTED"}
    values = [f["value"] for f in found]
    peak = max(abs(v) for v in values)
    spread = (max(values) - min(values)) / peak if peak else 0.0
    if spread > ITEM_ALIAS_TOLERANCE.get(key, ALIAS_TOLERANCE):
        return {"status": "CONFLICT", "value": None, "unit": unit,
                "reason": "XBRL_ALIASES_DISAGREE", "alternatives": found}
    cell = dict(found[0], status="REPORTED")
    if cell["concept"] not in tags:
        cell["fallback_concept"] = True
    if spread > ALIAS_TOLERANCE:
        cell["alias_gap"] = {"spread": spread, "rule": "PRIORITY_ALIAS_USED",
                             "other_aliases": [{k: f[k] for k in ("concept", "value", "accession")}
                                               for f in found[1:]]}
    elif len(found) > 1:
        cell["agreeing_aliases"] = [f["concept"] for f in found[1:]]
    return cell


def _known(cell):
    return cell["status"] in ("REPORTED", "DERIVED")


def _sources(cell):
    """SEC filings behind a value: one for a reported fact, two for a YTD difference."""
    return tuple(sorted(cell.get("sources") or (cell["accession"],)))


def _same_filing(*cells):
    return len({_sources(c) for c in cells}) == 1


def _derive(year, ebit_proxy=True, net_debt=True):
    income, cash_flow, balance = year["income"], year["cash_flow"], year["balance"]
    revenue, cost = income["revenue"], income["cost_of_revenue"]
    if income["gross_profit"]["status"] == "MISSING":
        if _known(revenue) and _known(cost) and _same_filing(revenue, cost):
            income["gross_profit"] = {
                "status": "DERIVED", "value": revenue["value"] - cost["value"], "unit": "USD",
                "method": "REVENUE_MINUS_COST_OF_REVENUE_SAME_FILING",
                "accession": revenue["accession"], "filed": revenue["filed"],
                "sources": list(_sources(revenue)),
                "derivation": {"revenue": revenue["concept"], "cost_of_revenue": cost["concept"]}}

    # Some issuers (e.g. pharma, oil majors) report no operating income subtotal. An
    # approximate EBIT is pretax income plus interest expense from one filing; it
    # still includes non-operating items, so it is flagged and never called reported.
    operating, pretax, interest = income["operating_income"], income["pretax_income"], income["interest_expense"]
    if operating["status"] == "MISSING":
        if not ebit_proxy:
            # Banks and insurers: interest expense is operating, so the proxy has no meaning.
            operating["proxy_unavailable"] = "EBIT_PROXY_DISABLED_FOR_SECTOR"
        elif _known(pretax) and _known(interest) and _same_filing(pretax, interest):
            income["operating_income"] = {
                "status": "DERIVED", "value": pretax["value"] + interest["value"], "unit": "USD",
                "method": "EBIT_PROXY_PRETAX_PLUS_INTEREST", "approximate": True,
                "accession": pretax["accession"], "filed": pretax["filed"], "sources": list(_sources(pretax)),
                "derivation": {"pretax_income": pretax["concept"], "interest_expense": interest["concept"]},
                "includes": "non-operating items such as interest income, equity-method results and other gains"}
        else:
            operating["proxy_unavailable"] = ("PRETAX_AND_INTEREST_FROM_DIFFERENT_FILINGS"
                                              if _known(pretax) and _known(interest)
                                              else "PRETAX_OR_INTEREST_UNAVAILABLE")

    cfo, capex = cash_flow["cfo"], cash_flow["capex"]
    if _known(cfo) and _known(capex) and _same_filing(cfo, capex):
        cash_flow["free_cash_flow"] = {
            "status": "DERIVED", "value": cfo["value"] - capex["value"], "unit": "USD",
            "method": "CFO_MINUS_CAPEX_SAME_FILING", "is_fcff": False,
            "accession": cfo["accession"], "filed": cfo["filed"], "sources": list(_sources(cfo))}
    else:
        reason = ("CFO_AND_CAPEX_FROM_DIFFERENT_FILINGS"
                  if _known(cfo) and _known(capex) else "CFO_OR_CAPEX_UNAVAILABLE")
        cash_flow["free_cash_flow"] = {"status": "MISSING", "value": None, "unit": "USD",
                                       "reason": reason}

    # Total debt never treats an unreported component as zero: it lists what was
    # summed and what was not reported. LongTermDebt already includes the current
    # portion, so it is only a fallback when the noncurrent line is absent.
    if balance["long_term_debt_noncurrent"]["status"] == "REPORTED":
        used = ["long_term_debt_noncurrent", "long_term_debt_current"]
    else:
        used = ["long_term_debt"]
    debt = _component_sum(balance, used + ["commercial_paper", "short_term_borrowings"], "DEBT",
                          "SUM_OF_REPORTED_DEBT_COMPONENTS_SAME_FILING", conflict_keys=DEBT_COMPONENTS)
    if debt["status"] == "DERIVED":
        debt["excludes"] = "operating and finance lease liabilities"
    balance["total_debt"] = debt
    balance["liquid_investments"] = _liquid_investments(balance)
    # Shown, not added to net debt: GAAP operating income already deducts operating lease
    # cost, and some issuers include finance leases in their reported debt.
    balance["lease_liabilities"] = _component_sum(balance, LEASE_COMPONENTS, "LEASE",
                                                  "SUM_OF_REPORTED_LEASE_LIABILITIES_SAME_FILING")
    # A bank's cash and debt are operating balances (deposits, central-bank reserves), so
    # "debt minus cash" has no valuation meaning there.
    balance["net_debt"] = (_net_debt(balance) if net_debt else
                           {"status": "MISSING", "value": None, "unit": "USD",
                            "reason": "NOT_MEANINGFUL_FOR_FINANCIAL_SECTOR"})


def _component_sum(balance, keys, prefix, method, conflict_keys=None):
    """Sum of the reported components among `keys`; an unreported one is listed, never counted as zero."""
    conflicts = [k for k in (conflict_keys or keys) if balance[k]["status"] == "CONFLICT"]
    reported = [k for k in keys if balance[k]["status"] == "REPORTED"]
    if conflicts:
        return {"status": "MISSING", "value": None, "unit": "USD",
                "reason": f"{prefix}_COMPONENT_CONFLICT", "components_in_conflict": conflicts}
    if not reported:
        return {"status": "MISSING", "value": None, "unit": "USD", "reason": f"NO_{prefix}_COMPONENT_REPORTED"}
    cells = [balance[k] for k in reported]
    # A later 10-K repeats only some prior-year lines. Components from different filings
    # are summed only when none was revised, so restated and original values never mix.
    across = not _same_filing(*cells)
    if across and any(c.get("revised") for c in cells):
        return {"status": "MISSING", "value": None, "unit": "USD",
                "reason": f"{prefix}_COMPONENTS_FROM_DIFFERENT_FILINGS",
                "revised_components": [k for k in reported if balance[k].get("revised")]}
    cell = {"status": "DERIVED", "value": math.fsum(c["value"] for c in cells), "unit": "USD",
            "method": method.replace("_SAME_FILING", "_UNREVISED_ACROSS_FILINGS") if across else method,
            "components": reported, "components_not_reported": [k for k in keys if k not in reported],
            "accession": cells[0]["accession"], "filed": max(c["filed"] for c in cells)}
    if across:
        cell["sources"] = sorted({src for c in cells for src in _sources(c)})
    return cell


def _liquid_investments(balance):
    """Securities that offset debt. ShortTermInvestments may already include current
    marketable securities, so when both are reported only the larger one is used:
    the total is then a lower bound, never a double count. OtherShortTermInvestments
    excludes securities by definition and is always added."""
    split = any(balance[k]["status"] == "REPORTED"
                for k in ("marketable_securities_current", "marketable_securities_noncurrent"))
    # A securities total without a maturity split (Coca-Cola) is used only when no split is reported.
    keys = list(SECURITIES_COMPONENTS) + ([] if split else ["marketable_securities_unclassified"])
    cell = _component_sum(balance, keys, "SECURITIES", "SUM_OF_REPORTED_SECURITIES_SAME_FILING")
    short_term = balance["short_term_investments"]
    marketable = balance["marketable_securities_current" if split else "marketable_securities_unclassified"]
    if cell["status"] == "DERIVED" and short_term["status"] == marketable["status"] == "REPORTED":
        smaller = min((short_term, marketable), key=lambda c: c["value"])
        cell["value"] -= smaller["value"]
        cell["overlap"] = {"rule": "LARGER_OF_POSSIBLY_OVERLAPPING_CURRENT_LINES", "lower_bound": True,
                           "not_added": smaller["concept"], "not_added_value": smaller["value"]}
    return cell


def _net_debt(balance):
    """Total debt minus cash and, where reported, securities. Lease liabilities are excluded."""
    debt, cash, liquid = balance["total_debt"], balance["cash"], balance["liquid_investments"]
    none_reported = liquid.get("reason") == "NO_SECURITIES_COMPONENT_REPORTED"
    if not (_known(debt) and _known(cash)) or not (_known(liquid) or none_reported):
        return {"status": "MISSING", "value": None, "unit": "USD", "reason": "DEBT_CASH_OR_SECURITIES_UNAVAILABLE"}
    parts = [debt, cash] + ([liquid] if _known(liquid) else [])
    deducted = liquid["value"] if _known(liquid) else 0.0
    return {"status": "DERIVED", "value": debt["value"] - cash["value"] - deducted, "unit": "USD",
            "method": ("TOTAL_DEBT_MINUS_CASH_AND_SECURITIES" if _known(liquid)
                       else "TOTAL_DEBT_MINUS_CASH_NO_SECURITIES_REPORTED"),
            "deducted": ["cash", "liquid_investments"] if _known(liquid) else ["cash"],
            "securities_lower_bound": bool(liquid.get("overlap")),
            "accession": debt["accession"], "filed": max(c["filed"] for c in parts),
            "sources": sorted({src for c in parts for src in _sources(c)}),
            "excludes": "lease liabilities"}


def build_annual_statements(raw, *, as_of, years=5, ebit_proxy=True, net_debt=True):
    """Return up to `years` most recent fiscal years of annual statements.

    A company with no eligible annual 10-K data returns status NO_ANNUAL_PERIODS
    rather than raising, so a research report can still show the gap.
    `ebit_proxy=False` (financial or unconfirmed sector) never derives an
    approximate operating income; `net_debt=False` (financial sector) leaves
    net debt unavailable.
    """
    cutoff, cik = _validate(raw, as_of, years, MAX_YEARS, "years")
    read = _reader(raw, cutoff, ANNUAL_FORMS, (330, 400))
    rows = []
    for period in _fiscal_years(read)[:years]:
        year = {"fiscal_year_start": period["start"], "fiscal_year_end": period["end"],
                "start_ambiguous": period["start_ambiguous"]}
        for statement in STATEMENTS:
            year[statement] = {key: _cell(read, key, period["start"], period["end"])
                               for key, spec in LINE_ITEMS.items() if spec[0] == statement}
        _derive(year, ebit_proxy, net_debt)
        rows.append(year)

    coverage = {}
    for key in list(LINE_ITEMS) + list(DERIVED_ITEMS):
        statement = LINE_ITEMS[key][0] if key in LINE_ITEMS else DERIVED_ITEMS[key][0]
        statuses = [row[statement][key]["status"] for row in rows]
        coverage[key] = {"available": sum(s in ("REPORTED", "DERIVED") for s in statuses),
                         "conflicts": statuses.count("CONFLICT")}
    return {
        "version": VERSION, "cik": f"{cik:010d}", "company": raw.get("entityName", ""),
        "as_of": as_of, "source_url": SEC_DATA.format(cik=cik),
        "status": "OK" if rows else "NO_ANNUAL_PERIODS",
        "years": rows, "coverage": coverage, "conflicts": _conflicts(rows),
        "alias_gaps": _alias_gaps(rows), "approximations": _approximations(rows),
        "fallback_concepts": _fallbacks(rows), "ebit_proxy": ebit_proxy, "net_debt_derived": net_debt,
        "shares_outstanding": shares_outstanding(raw, as_of=as_of),
        "rules": [
            "Only 10-K / 10-K/A facts filed on or before as_of; fiscal years from fact dates, not SEC fy/fp",
            "Latest filing wins for a period; earlier differing values are kept as first_reported",
            f"XBRL aliases differing by more than {ALIAS_TOLERANCE:.1%} are a CONFLICT with no value; "
            "revenue aliases up to 5% apart use the priority alias and keep the gap visible",
            "Missing values are null, never zero; derived values require one SEC filing",
            "Without a reported operating income, an approximate EBIT is pretax income plus interest expense",
            "A broader fallback concept (CapEx: productive assets) is read only when no alias is reported",
            "Outflows (CapEx, dividends, repurchases) are positive payments as reported",
            "Net debt = total debt - cash - reported securities; lease liabilities are shown but not included",
        ],
    }


def _validate(raw, as_of, count, maximum, name):
    cutoff = _date(as_of)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= maximum:
        raise ValueError(f"{name} must be an integer in 1..{maximum}")
    if not isinstance(raw, dict) or not isinstance(raw.get("facts"), dict):
        raise ValueError("raw SEC Company Facts object required")
    return cutoff, _validate_cik(raw.get("cik"))


def _conflicts(rows):
    return [{"start": row.get("start", row.get("fiscal_year_start")),
             "end": row.get("end", row.get("fiscal_year_end")), "item": key,
             "concepts": [a["concept"] for a in cell.get("alternatives", [])]}
            for row in rows for statement in STATEMENTS
            for key, cell in row[statement].items() if cell["status"] == "CONFLICT"]


def _alias_gaps(rows):
    """Cells that use the priority alias although another alias differs (revenue, up to 5%)."""
    return [{"start": row.get("start", row.get("fiscal_year_start")),
             "end": row.get("end", row.get("fiscal_year_end")), "item": key,
             "spread": cell["alias_gap"]["spread"], "used": cell["concept"],
             "others": [a["concept"] for a in cell["alias_gap"]["other_aliases"]]}
            for row in rows for statement in STATEMENTS
            for key, cell in row[statement].items() if cell.get("alias_gap")]


def _fallbacks(rows):
    return [{"start": row.get("start", row.get("fiscal_year_start")),
             "end": row.get("end", row.get("fiscal_year_end")), "item": key, "concept": cell["concept"]}
            for row in rows for statement in STATEMENTS
            for key, cell in row[statement].items() if cell.get("fallback_concept")]


def _approximations(rows):
    return [{"start": row.get("start", row.get("fiscal_year_start")),
             "end": row.get("end", row.get("fiscal_year_end")), "item": key, "method": cell["method"]}
            for row in rows for statement in STATEMENTS
            for key, cell in row[statement].items() if cell.get("approximate")]


def shares_outstanding(raw, *, as_of):
    """Latest cover-page share count (dei) filed on or before `as_of`.

    Multi-class issuers may report one value per class in the same filing; those
    are not summed or picked from, they are reported as a CONFLICT.
    """
    cutoff = _date(as_of)
    rows = raw["facts"].get("dei", {}).get(SHARES_OUTSTANDING_CONCEPT, {}).get("units", {}).get("shares", [])
    eligible = []
    for row in rows:
        if not isinstance(row, dict) or row.get("form") not in QUARTERLY_FORMS:
            continue
        if not isinstance(row.get("accn"), str) or not row["accn"] or not _number(row.get("val")):
            continue
        try:
            end, filed = _date(row.get("end")), _date(row.get("filed"))
        except ValueError:
            continue
        if end <= cutoff and filed <= cutoff:
            eligible.append({"value": float(row["val"]), "unit": "shares",
                             "concept": "dei:" + SHARES_OUTSTANDING_CONCEPT, "date": end.isoformat(),
                             "filed": filed.isoformat(), "accession": row["accn"], "form": row["form"]})
    if not eligible:
        return {"status": "MISSING", "value": None, "unit": "shares", "reason": "NOT_REPORTED"}
    latest = max(eligible, key=lambda f: (f["filed"], f["date"], f["accession"]))
    same = [f for f in eligible if f["accession"] == latest["accession"] and f["date"] == latest["date"]]
    if len({f["value"] for f in same}) > 1:
        return {"status": "CONFLICT", "value": None, "unit": "shares",
                "reason": "MULTIPLE_VALUES_POSSIBLY_SHARE_CLASSES", "alternatives": same}
    return dict(latest, status="REPORTED")


def _quarter_calendar(read, annual_read):
    """Fiscal quarters from YTD facts that begin on a fiscal-year start, newest first.

    Fiscal years come from 10-K annual periods (`annual_read`), plus the year in
    progress after the latest 10-K. A quarter is listed only when both of its
    boundaries are known.
    """
    ytd_ends = {}
    for key in ANCHOR_ITEMS:
        for tag in LINE_ITEMS[key][4]:
            for start, end in read(tag, "USD", False):
                days = (_date(end) - _date(start)).days + 1
                for quarter, (low, high) in YTD_DAYS.items():
                    if low <= days <= high:
                        ytd_ends.setdefault(start, {}).setdefault(quarter, Counter())[end] += 1
    annual = _fiscal_years(annual_read)
    years = [{"start": y["start"], "end": y["end"]} for y in annual]
    if annual:
        following = (_date(annual[0]["end"]) + dt.timedelta(days=1)).isoformat()
        if following in ytd_ends:
            years.insert(0, {"start": following, "end": None})
    quarters = []
    for year in years:
        found = ytd_ends.get(year["start"], {})
        bounds = [found[q].most_common(1)[0][0] if q in found else None for q in (1, 2, 3)]
        bounds.append(year["end"])
        # A fiscal year is named after the calendar year in which it ends.
        expected_end = _date(year["end"]) if year["end"] else _date(year["start"]) + dt.timedelta(days=364)
        label_year = expected_end.year
        for index, end in enumerate(bounds, start=1):
            previous_end = bounds[index - 2] if index > 1 else None
            if end is None or (index > 1 and previous_end is None):
                continue
            start = year["start"] if index == 1 else (_date(previous_end) + dt.timedelta(days=1)).isoformat()
            if start >= end or (year["end"] and end > year["end"]):
                continue
            quarters.append({"fiscal_year_start": year["start"], "fiscal_year_end": year["end"],
                             "fiscal_year_label": f"MY{label_year}", "fiscal_quarter": index,
                             "start": start, "end": end, "previous_ytd_end": previous_end})
    return sorted(quarters, key=lambda q: q["end"], reverse=True)


def _brief(cell):
    return {k: cell[k] for k in ("value", "concept", "start", "end", "filed", "accession")}


def _quarter_cell(read, key, quarter):
    """A discrete quarter: reported 3-month fact, else a YTD difference of one concept."""
    kind, unit = LINE_ITEMS[key][1], LINE_ITEMS[key][2]
    if kind == "instant":
        return _cell(read, key, None, quarter["end"])
    direct = _cell(read, key, quarter["start"], quarter["end"])
    if direct["status"] != "MISSING" or quarter["fiscal_quarter"] == 1:
        return direct
    if key in NON_ADDITIVE:
        return {"status": "MISSING", "value": None, "unit": unit, "reason": "NON_ADDITIVE_NOT_DERIVED"}
    current = _cell(read, key, quarter["fiscal_year_start"], quarter["end"])
    previous = _cell(read, key, quarter["fiscal_year_start"], quarter["previous_ytd_end"])
    for cell in (current, previous):
        if cell["status"] == "CONFLICT":
            return dict(cell, reason="YTD_" + cell["reason"])
    if current["status"] != "REPORTED" or previous["status"] != "REPORTED":
        return {"status": "MISSING", "value": None, "unit": unit, "reason": "NO_QUARTER_OR_YTD_PAIR"}
    if current["concept"] != previous["concept"]:
        return {"status": "MISSING", "value": None, "unit": unit, "reason": "YTD_CONCEPTS_DIFFER"}
    cell = {"status": "DERIVED", "value": current["value"] - previous["value"], "unit": unit,
            "concept": current["concept"], "start": quarter["start"], "end": quarter["end"],
            "method": "ANNUAL_MINUS_NINE_MONTHS" if quarter["fiscal_quarter"] == 4 else "YTD_DIFFERENCE",
            "accession": current["accession"], "filed": current["filed"],
            "sources": [current["accession"], previous["accession"]],
            "revised": current["revised"] or previous["revised"],
            "derivation": {"ytd_current": _brief(current), "ytd_previous": _brief(previous)}}
    if current.get("alias_gap") or previous.get("alias_gap"):
        cell["alias_gap"] = current.get("alias_gap") or previous["alias_gap"]
    if current.get("fallback_concept"):
        cell["fallback_concept"] = True
    return cell


def build_quarterly_statements(raw, *, as_of, quarters=8, ebit_proxy=True, net_debt=True):
    """Return up to `quarters` most recent discrete fiscal quarters.

    Flow items use a reported 3-month fact when one exists; otherwise the
    difference of two year-to-date facts of the same concept (Q4 = annual 10-K
    minus nine months). Balance items are the reported quarter-end values.
    """
    cutoff, cik = _validate(raw, as_of, quarters, MAX_QUARTERS, "quarters")
    read = _reader(raw, cutoff, QUARTERLY_FORMS, None)
    annual_read = _reader(raw, cutoff, ANNUAL_FORMS, (330, 400))
    rows = []
    for quarter in _quarter_calendar(read, annual_read)[:quarters]:
        row = {k: v for k, v in quarter.items() if k != "previous_ytd_end"}
        for statement in STATEMENTS:
            row[statement] = {key: _quarter_cell(read, key, quarter)
                              for key, spec in LINE_ITEMS.items() if spec[0] == statement}
        _derive(row, ebit_proxy, net_debt)
        rows.append(row)
    result = {
        "version": VERSION, "cik": f"{cik:010d}", "company": raw.get("entityName", ""),
        "as_of": as_of, "source_url": SEC_DATA.format(cik=cik),
        "status": "OK" if rows else "NO_QUARTERLY_PERIODS",
        "quarters": rows, "conflicts": _conflicts(rows),
        "alias_gaps": _alias_gaps(rows), "approximations": _approximations(rows),
        "fallback_concepts": _fallbacks(rows), "ebit_proxy": ebit_proxy, "net_debt_derived": net_debt,
        "shares_outstanding": shares_outstanding(raw, as_of=as_of),
        "rules": [
            "10-Q and 10-K facts filed on or before as_of; quarters from fact dates, not SEC fy/fp",
            "A reported 3-month value is used first; otherwise a YTD difference of one XBRL concept",
            "Q4 is the annual 10-K value minus the nine-month 10-Q value",
            "Weighted-average share counts are never derived from YTD differences",
            "Derived gross profit and free cash flow require the same SEC filings for both inputs",
            "TTM is the sum of the latest four consecutive quarters, whichever fiscal quarter is latest",
        ],
    }
    result["ttm"] = trailing_twelve_months(result)
    return result


def _consecutive(window):
    return all(_date(newer["start"]) == _date(older["end"]) + dt.timedelta(days=1)
               for newer, older in zip(window, window[1:]))


def _ttm_cell(cells, window, unit):
    unavailable = [q["end"] for q, c in zip(window, cells) if not _known(c)]
    if unavailable:
        conflict = any(c["status"] == "CONFLICT" for c in cells)
        return {"status": "CONFLICT" if conflict else "MISSING", "value": None, "unit": unit,
                "reason": "QUARTER_CONFLICT" if conflict else "QUARTER_UNAVAILABLE",
                "quarters_unavailable": unavailable}
    cell = {"status": "DERIVED", "value": math.fsum(c["value"] for c in cells), "unit": unit,
            "method": "SUM_OF_FOUR_QUARTERS", "filed": max(c["filed"] for c in cells),
            "sources": sorted({s for c in cells for s in _sources(c)})}
    if any(c.get("approximate") for c in cells):
        cell["approximate"] = True
    return cell


def trailing_twelve_months(quarterly, *, end=None):
    """Flow items summed over four consecutive shared quarters ending at `end` (default: latest).

    Works whichever fiscal quarter is latest. A missing or conflicting quarter
    leaves that item unavailable; nothing is filled in. Weighted-average share
    counts are not additive and are not summed.
    """
    quarters = quarterly.get("quarters", [])
    index = 0 if end is None else next((i for i, q in enumerate(quarters) if q["end"] == end), None)
    window = quarters[index:index + 4] if index is not None else []
    if len(window) < 4 or not _consecutive(window):
        return {"status": "INSUFFICIENT_QUARTERS", "reason": "NO_FOUR_CONSECUTIVE_QUARTERS",
                "end": end if end is not None else (quarters[0]["end"] if quarters else None), "items": {}}
    items = {}
    for statement in ("income", "cash_flow"):
        keys = [k for k, spec in LINE_ITEMS.items() if spec[0] == statement and k not in NON_ADDITIVE]
        keys += [k for k, spec in DERIVED_ITEMS.items() if spec[0] == statement]
        for key in keys:
            unit = LINE_ITEMS[key][2] if key in LINE_ITEMS else DERIVED_ITEMS[key][1]
            items[key] = _ttm_cell([q[statement][key] for q in window], window, unit)
    latest = window[0]
    unavailable = [k for k in TTM_CORE if not _known(items[k])]
    return {"status": "PARTIAL" if unavailable else "OK", "core_unavailable": unavailable,
            "start": window[-1]["start"], "end": latest["end"],
            "fiscal_year_label": latest["fiscal_year_label"], "fiscal_quarter": latest["fiscal_quarter"],
            "quarters": [q["end"] for q in window], "items": items,
            "method": "SUM_OF_FOUR_CONSECUTIVE_DISCRETE_QUARTERS"}


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
