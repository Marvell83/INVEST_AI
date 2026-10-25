"""INVEST_AI — consistency checks between the shared statements layer and older engines.

Piotroski and the TTM engines still read SEC facts with their own rules. Before
they are moved onto finansal_tablolar, this module shows, for the same report,
whether they used the same values and SEC filings as the shared layer. It
changes no engine output; differences are reported, never silently resolved.
"""
from __future__ import annotations

import datetime as dt
import math

VERSION = "katman-mutabakati-0.1.0"
# Piotroski provenance prefix -> (statement, shared line item)
PIOTROSKI_ITEMS = {
    "ni": ("income", "net_income"), "cfo": ("cash_flow", "cfo"), "rev": ("income", "revenue"),
    "gp": ("income", "gross_profit"), "a": ("balance", "total_assets"),
    "d": ("balance", "long_term_debt_noncurrent"), "ca": ("balance", "current_assets"),
    "cl": ("balance", "current_liabilities"),
}
TTM_ITEMS = {"revenue": ("income", "revenue"), "ebit": ("income", "operating_income"),
             "cfo": ("cash_flow", "cfo"), "capex": ("cash_flow", "capex")}
ROUNDING_TOLERANCE = 0.001  # quarterly 3-month values may not add up exactly to YTD totals
ATTENTION = ("VALUE_DIFFERS", "SHARED_CONFLICT")


def _known(cell):
    return cell.get("status") in ("REPORTED", "DERIVED")


def _relative_gap(a, b):
    scale = max(abs(a), abs(b))
    return 0.0 if scale == 0 else abs(a - b) / scale


def reconcile_piotroski(piotroski, statements):
    """Compare every Piotroski input fact with the shared annual cell of the same year."""
    provenance = piotroski.get("provenance") or {}
    if not provenance:
        return {"status": "NOT_APPLICABLE", "checks": [], "reason": "NO_PIOTROSKI_SEC_INPUTS"}
    rows = {y["fiscal_year_end"]: y for y in statements.get("years", [])}
    checks = []
    for key, fact in sorted(provenance.items()):
        statement, item = PIOTROSKI_ITEMS[key.split("_")[0]]
        check = {"piotroski_input": key, "item": item, "fiscal_year_end": fact["end"],
                 "piotroski": fact["value_usd"], "piotroski_accession": fact["accession"]}
        row = rows.get(fact["end"])
        if row is None:
            check["status"] = "YEAR_NOT_IN_SHARED_STATEMENTS"
        else:
            cell = row[statement][item]
            check["shared"] = cell.get("value")
            check["shared_accession"] = cell.get("accession")
            if not _known(cell):
                check["status"] = "SHARED_" + cell["status"]
            elif _relative_gap(cell["value"], fact["value_usd"]) > 1e-9:
                check["status"] = "VALUE_DIFFERS"
            elif cell.get("accession") != fact["accession"]:
                check["status"] = "SAME_VALUE_OTHER_FILING"
            else:
                check["status"] = "MATCH"
        checks.append(check)
    attention = [c for c in checks if c["status"] in ATTENTION]
    status = ("DIFFERENCES" if attention else
              "MATCHED" if all(c["status"] == "MATCH" for c in checks) else "MATCHED_WITH_NOTES")
    return {"status": status, "checks": checks, "attention": attention}


def reconcile_ttm(ttm_audit, quarterly):
    """Compare reconciled TTM flows with the sum of the same four shared quarters."""
    if ttm_audit.get("status") != "RECONCILED_CALCULATIONS":
        return {"status": "NOT_APPLICABLE", "checks": [], "reason": "TTM_ENGINES_NOT_RECONCILED"}
    end = ttm_audit["primary"]["periods"]["current_9m_end"]
    quarters = quarterly.get("quarters", [])
    index = next((i for i, q in enumerate(quarters) if q["end"] == end), None)
    window = quarters[index:index + 4] if index is not None else []
    consecutive = len(window) == 4 and all(
        dt.date.fromisoformat(newer["start"]) == dt.date.fromisoformat(older["end"]) + dt.timedelta(days=1)
        for newer, older in zip(window, window[1:]))
    if not consecutive:
        return {"status": "NOT_COMPARABLE", "checks": [], "ttm_end": end,
                "reason": "NO_FOUR_CONSECUTIVE_SHARED_QUARTERS_TO_TTM_END"}
    checks = []
    for metric, (statement, item) in TTM_ITEMS.items():
        cells = [q[statement][item] for q in window]
        ttm_value = ttm_audit["primary"]["metrics"][metric]["value_usd"]
        check = {"metric": metric, "item": item, "ttm": ttm_value,
                 "quarters": [q["end"] for q in window]}
        if not all(_known(c) for c in cells):
            check["status"] = "SHARED_INCOMPLETE"
        else:
            check["shared"] = math.fsum(c["value"] for c in cells)
            gap = _relative_gap(check["shared"], ttm_value)
            check["difference"] = check["shared"] - ttm_value
            check["status"] = ("MATCH" if gap <= 1e-9 else
                               "ROUNDING" if gap <= ROUNDING_TOLERANCE else "VALUE_DIFFERS")
        checks.append(check)
    attention = [c for c in checks if c["status"] in ATTENTION]
    status = ("DIFFERENCES" if attention else
              "MATCHED" if all(c["status"] == "MATCH" for c in checks) else "MATCHED_WITH_NOTES")
    return {"status": status, "checks": checks, "attention": attention, "ttm_end": end}


PIOTROSKI_ALIAS_TOLERANCE = 0.05  # piotroski_fscore accepts revenue aliases this far apart


def _alias_spread(cell):
    values = [a["value"] for a in cell.get("alternatives", [])]
    peak = max((abs(v) for v in values), default=0)
    return (max(values) - min(values)) / peak if peak else 0.0


def layer_health(research):
    """Compact health of the shared layers in one research report, for multi-company real-data checks.

    `revenue_alias_bucket` answers the open threshold question directly:
    HALF_TO_FIVE_PERCENT means Piotroski accepts the revenue while the shared
    statements report a conflict.
    """
    statements = research.get("financial_statements") or {}
    years = statements.get("years", [])
    quarterly = research.get("quarterly_statements") or {}
    layers = research.get("layer_reconciliation") or {}
    ratio_years = (research.get("financial_ratios") or {}).get("years", [])
    latest_ratios = ratio_years[0]["ratios"] if ratio_years else {}
    # Piotroski compares the latest two fiscal years.
    gaps = [_alias_spread(y["income"]["revenue"]) for y in years[:2]
            if y["income"]["revenue"].get("status") == "CONFLICT"]
    gap = max(gaps) if gaps else None
    bucket = ("NO_REVENUE_CONFLICT" if gap is None else
              "HALF_TO_FIVE_PERCENT" if gap <= PIOTROSKI_ALIAS_TOLERANCE else "ABOVE_FIVE_PERCENT")
    piotroski = layers.get("piotroski", {})
    return {
        "statement_years": len(years),
        "latest_fiscal_year_end": years[0]["fiscal_year_end"] if years else None,
        "statement_conflicts": sorted({c["item"] for c in statements.get("conflicts", [])}),
        "revenue_alias_gap": gap, "revenue_alias_bucket": bucket,
        "quarters": len(quarterly.get("quarters", [])),
        "shares_status": (statements.get("shares_outstanding") or {}).get("status"),
        "piotroski_reconciliation": piotroski.get("status"),
        "piotroski_attention": [c["piotroski_input"] for c in piotroski.get("attention", [])],
        "ttm_reconciliation": layers.get("ttm", {}).get("status"),
        "baseline_status": (research.get("historical_baseline") or {}).get("status"),
        "latest_ratios_available": sum(r.get("value") is not None for r in latest_ratios.values()),
        "latest_ratios_total": len(latest_ratios),
    }


def reconcile_layers(piotroski, statements, ttm_audit, quarterly):
    return {"version": VERSION,
            "piotroski": reconcile_piotroski(piotroski, statements),
            "ttm": reconcile_ttm(ttm_audit, quarterly),
            "note": "Consistency between engines on one SEC snapshot; not an independent audit of SEC data"}
