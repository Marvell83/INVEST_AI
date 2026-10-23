"""INVEST_AI - strict, point-in-time US-GAAP 9M TTM accounting bridge.

TTM = prior fiscal year + current 9M YTD - comparable prior 9M YTD.
No annualizing quarterly figures, no fabricated filing dates, no FCFF inference.
Read public SEC Company Facts JSON offline. Python stdlib only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

VERSION = "ttm-usgaap-0.1.0"
SOURCE_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{:010d}.json"
ANNUAL_FORMS = frozenset(("10-K", "10-K/A"))
INTERIM_FORMS = frozenset(("10-Q", "10-Q/A"))
METRICS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"),
    "ebit": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss",),
    "gross_profit": ("GrossProfit",),
    "cfo": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
}
CORE = ("revenue", "ebit", "cfo", "capex")
ALIAS_TOLERANCE = 0.005  # only an ambiguity guard, not an accounting standard


def _date(value):
    if not isinstance(value, str):
        raise ValueError("ISO date string YYYY-MM-DD required")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid ISO date") from exc


def _facts(data, cutoff):
    """Collect eligible annual and 9-month YTD observations, preserving evidence."""
    if not isinstance(data, dict) or not isinstance(data.get("facts"), dict):
        raise ValueError("raw SEC Company Facts object required")
    cik = data.get("cik")
    if isinstance(cik, bool) or not str(cik).isdigit() or not (1 <= int(cik) <= 9_999_999_999):
        raise ValueError("invalid CIK")
    sec = data["facts"].get("us-gaap", {})
    result = {key: {"annual": [], "ytd9": []} for key in METRICS}
    for metric, tags in METRICS.items():
        for priority, tag in enumerate(tags):
            rows = sec.get(tag, {}).get("units", {}).get("USD", [])
            if not isinstance(rows, list):
                continue
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                form, fp = raw.get("form"), raw.get("fp")
                if form in ANNUAL_FORMS and fp == "FY":
                    kind = "annual"
                elif form in INTERIM_FORMS and fp == "Q3":
                    kind = "ytd9"
                else:
                    continue
                try:
                    start, end, filed = (_date(raw.get(key)) for key in ("start", "end", "filed"))
                except ValueError:
                    continue
                days = (end - start).days + 1
                if not ((330 <= days <= 400) if kind == "annual" else (240 <= days <= 310)):
                    continue
                if filed > cutoff or end > cutoff or not raw.get("accn"):
                    continue
                value = raw.get("val")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    continue
                if abs(value) >= 1e30:
                    continue
                result[metric][kind].append({
                    "concept": tag, "value_usd": value, "start": start.isoformat(),
                    "end": end.isoformat(), "filed": filed.isoformat(),
                    "accession": str(raw["accn"]), "form": form, "fp": fp,
                    "days": days, "priority": priority,
                    "source": SOURCE_URL.format(int(cik)),
                })
    return result


def _select(rows, start, end):
    """Choose latest filed *per tag*; stop on materially different aliases."""
    eligible = [r for r in rows if r["start"] == start and r["end"] == end]
    if not eligible:
        return None, "MISSING_MATCHING_PERIOD"
    by_tag = {}
    for row in eligible:
        old = by_tag.get(row["concept"])
        if old is None or (row["filed"], row["form"].endswith("/A"), row["accession"]) > (
                old["filed"], old["form"].endswith("/A"), old["accession"]):
            by_tag[row["concept"]] = row
    candidates = list(by_tag.values())
    numbers = [x["value_usd"] for x in candidates]
    peak = max(abs(n) for n in numbers)
    if peak > 0 and (max(numbers) - min(numbers)) / peak > ALIAS_TOLERANCE:
        return None, "CONFLICTING_ALIASES"
    candidates.sort(key=lambda x: (x["priority"], -dt.date.fromisoformat(x["filed"]).toordinal()))
    return {k: v for k, v in candidates[0].items() if k != "priority"}, None


def _find_period(rows, *, start, min_days=240, max_days=310, end_limit=None):
    ends = {r["end"] for r in rows if r["start"] == start and min_days <= r["days"] <= max_days}
    if end_limit is not None:
        ends = {x for x in ends if _date(x) < _date(end_limit)}
    if not ends:
        return None
    result = sorted(ends, reverse=True)
    if len(result) > 1 and (_date(result[0]) - _date(result[1])).days <= 7:
        raise ValueError("ambiguous nine-month period end dates; manual review required")
    return result[0]


def calculate_ttm(data, *, as_of):
    """Return a sourced USD TTM report; never replace missing data with zeros.

    Anchor is the newest year-end in published FY observations. Current 9M
    must begin immediately after that FY, comparative 9M at that FY's start.
    9M means approximately 3/4 of a fiscal year, not Q3 alone.
    """
    cutoff = _date(as_of)
    facts = _facts(data, cutoff)
    annual = [r for group in facts.values() for r in group["annual"]]
    if not annual:
        raise ValueError("no eligible USD annual 10-K data by cutoff")
    fiscal_end = max(x["end"] for x in annual)
    year_starts = {x["start"] for x in annual if x["end"] == fiscal_end}
    if len(year_starts) != 1:
        raise ValueError("conflicting annual start dates; manual review required")
    fiscal_start = next(iter(year_starts))
    next_start = (_date(fiscal_end) + dt.timedelta(days=1)).isoformat()
    all_ytd9 = [r for group in facts.values() for r in group["ytd9"]]
    current_end = _find_period(all_ytd9, start=next_start)
    past_options = {r["end"] for r in all_ytd9 if r["start"] == fiscal_start
                    and 240 <= r["days"] <= 310
                    and 50 <= (_date(fiscal_end) - _date(r["end"])).days <= 125}
    if current_end is not None:
        past_options = {p for p in past_options if 330 <= (_date(current_end) - _date(p)).days <= 400}
    if len(past_options) > 1:
        raise ValueError("ambiguous comparative nine-month period; manual review required")
    prior_end = next(iter(past_options), None)
    periods = {"annual_start": fiscal_start, "annual_end": fiscal_end,
               "current_9m_start": next_start, "current_9m_end": current_end,
               "prior_9m_start": fiscal_start, "prior_9m_end": prior_end}
    report = {"version": VERSION, "company": data.get("entityName", ""),
              "cik": f"{int(data['cik']):010d}", "as_of": as_of,
              "unit": "USD (actual nominal dollars, NOT millions)",
              "method": "FY + current 9M YTD - prior comparable 9M YTD",
              "periods": periods, "metrics": {},
              "input_disclosure": data.get("evidence_notes", {
                  "status": "USER_SUPPLIED_OFFLINE_COMPANYFACTS_JSON_NOT_AUTHENTICATED"
              }),
              "warnings": ["Only 10-K/10-K/A FY and 10-Q/10-Q/A Q3 nine-month US-GAAP USD flows",
                           "Filed-date eligibility is not proof of a complete historical SEC archive",
                           "CFO less CapEx is NOT FCFF; no market price or automatic DCF"],
              "status": None}
    for key in METRICS:
        if not current_end or not prior_end:
            report["metrics"][key] = {"value_usd": None, "status": "UNAVAILABLE_YTD_PERIOD_PAIR"}
            continue
        fiscal, e1 = _select(facts[key]["annual"], fiscal_start, fiscal_end)
        current, e2 = _select(facts[key]["ytd9"], next_start, current_end)
        prior, e3 = _select(facts[key]["ytd9"], fiscal_start, prior_end)
        issues = {"annual": e1, "current_ytd9": e2, "prior_ytd9": e3}
        if any(issues.values()):
            report["metrics"][key] = {"value_usd": None, "status": "INCOMPLETE_SOURCE_TRIPLE",
                                      "issues": {k: v for k, v in issues.items() if v}}
            continue
        if key == "revenue" and len({r["concept"] for r in (fiscal, current, prior)}) != 1:
            report["metrics"][key] = {"value_usd": None, "status": "REVENUE_CONCEPT_CHANGED"}
            continue
        if key == "capex" and any(f["value_usd"] < 0 for f in (fiscal, current, prior)):
            report["metrics"][key] = {"value_usd": None, "status": "CAPEX_SIGN_NOT_NORMALIZED"}
            continue
        value = fiscal["value_usd"] + current["value_usd"] - prior["value_usd"]
        if key == "capex" and value < 0:
            report["metrics"][key] = {"value_usd": None, "status": "NEGATIVE_TTM_CAPEX_REQUIRES_REVIEW"}
            continue
        report["metrics"][key] = {"value_usd": value, "status": "CALCULATED",
                                  "annual": fiscal, "current_ytd9": current, "prior_ytd9": prior}
    available_core = all(report["metrics"][m]["status"] == "CALCULATED" for m in CORE)
    report["status"] = "complete_core" if available_core else (
        "unavailable" if current_end is None or prior_end is None else "partial")
    rev, ebit = (report["metrics"][m]["value_usd"] for m in ("revenue", "ebit"))
    report["operating_margin"] = ebit / rev if rev is not None and rev > 0 and ebit is not None else None
    cfo, capex = (report["metrics"][m]["value_usd"] for m in ("cfo", "capex"))
    report["cfo_less_capex_usd"] = cfo - capex if cfo is not None and capex is not None else None
    report["cfo_less_capex_is_fcff"] = False
    if report["status"] != "complete_core":
        report["warnings"].append("Incomplete core historical data: NOT approved for automated DCF baseline")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="INVEST_AI SEC Company Facts TTM normalizer")
    parser.add_argument("--companyfacts", required=True, help="offline raw SEC Company Facts JSON")
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD knowledge cutoff")
    parser.add_argument("--out", required=True, help="report JSON")
    args = parser.parse_args(argv)
    raw = json.loads(Path(args.companyfacts).read_text(encoding="utf-8"))
    result = calculate_ttm(raw, as_of=args.as_of)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(result["cik"], result["status"], "TTM revenue:",
          result["metrics"]["revenue"]["value_usd"], "->", out)

if __name__ == "__main__":
    main()
