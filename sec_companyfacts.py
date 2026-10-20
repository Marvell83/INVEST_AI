"""SEC XBRL Company Facts annual normalizer (US-GAAP, USD only).

No price lookup, implied fair value, currency conversion, or InvestingPro API.
Only time-eligible SEC 10-K/10-K/A facts. A filed-date as-of cutoff prevents
looking ahead when constructing historical backtests.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import urllib.request

VERSION = "sec-companyfacts-0.1.0"
SEC_DATA = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
FORMS = frozenset(("10-K", "10-K/A"))
METRICS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"),
    "ebit": ("OperatingIncomeLoss",),
    "cfo": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
}


def _date(value):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("expected ISO date YYYY-MM-DD") from None


def _validate_cik(cik):
    if isinstance(cik, bool) or not str(cik).isdigit() or not 1 <= int(cik) <= 9999999999:
        raise ValueError("CIK must be a positive integer of at most ten digits")
    return int(cik)


def load_companyfacts(path):
    """Load a trusted local Company Facts JSON snapshot."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def download_companyfacts(cik, *, user_agent, timeout=20):
    """Make one explicit SEC request; provide a real contact in User-Agent."""
    number = _validate_cik(cik)
    if not user_agent or not re.search(r"\S+@\S+\.\S+", user_agent):
        raise ValueError("SEC_USER_AGENT must contain application and contact email")
    url = SEC_DATA.format(cik=number)
    request = urllib.request.Request(url, headers={
        "User-Agent": user_agent,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f"SEC returned HTTP {response.status}")
        data = response.read(50_000_001)
    if len(data) > 50_000_000:
        raise ValueError("SEC response exceeds 50 MB safeguard")
    return json.loads(data.decode("utf-8"))


def _annual_candidates(data, concept, as_of):
    facts = data.get("facts", {}).get("us-gaap", {})
    annual = facts.get(concept, {}).get("units", {}).get("USD", [])
    by_period = {}
    for row in annual:
        if row.get("form") not in FORMS or row.get("fp") != "FY":
            continue
        try:
            start, end, filed = (_date(row.get(key)) for key in ("start", "end", "filed"))
        except ValueError:
            continue
        duration = (end - start).days + 1
        if not 330 <= duration <= 400 or end > as_of or filed > as_of:
            continue
        value = row.get("val")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not (-1e30 < value < 1e30):
            continue
        if not row.get("accn"):
            continue
        key = end.isoformat()
        fact = {"value_usd": value, "start": start.isoformat(),
                "end": key, "days": duration,
                "filed": filed.isoformat(), "accession": row["accn"],
                "form": row["form"], "concept": concept,
                "source": SEC_DATA.format(cik=int(data["cik"]))}
        old = by_period.get(key)
        if old is None or (fact["filed"], fact["form"] == "10-K/A") > (old["filed"], old["form"] == "10-K/A"):
            by_period[key] = fact
    return by_period


def _selected_series(data, aliases, as_of):
    alternatives = []
    for priority, concept in enumerate(aliases):
        by_period = _annual_candidates(data, concept, as_of)
        if by_period:
            latest = max(by_period)
            alternatives.append((latest, len(by_period), -priority, concept, by_period))
    if not alternatives:
        return None, {}
    best = max(alternatives)
    return best[3], best[4]


def normalize_companyfacts(data, *, as_of, years=10):
    """Annual historical snapshot of one SEC issuer; no assumptions invented."""
    as_of_date = _date(as_of)
    if isinstance(years, bool) or not isinstance(years, int) or not 1 <= years <= 30:
        raise ValueError("years must be integer 1..30")
    if not isinstance(data, dict) or not isinstance(data.get("facts"), dict):
        raise ValueError("invalid companyfacts object")
    cik = _validate_cik(data.get("cik"))
    concepts = {}
    series = {}
    for metric, aliases in METRICS.items():
        concepts[metric], series[metric] = _selected_series(data, aliases, as_of_date)
    periods = sorted(set().union(*(set(value) for value in series.values())), reverse=True)[:years]
    history = []
    for end in periods:
        metrics = {m: series[m].get(end) for m in METRICS}
        fcfo = (metrics["cfo"]["value_usd"] - metrics["capex"]["value_usd"]
                if metrics["cfo"] and metrics["capex"] else None)
        history.append({"period_end": end, "metrics": metrics,
                        "cfo_less_capex_usd": fcfo,
                        "cfo_less_capex_is_fcff": False})
    warning = []
    for metric, concept in concepts.items():
        if concept is None:
            warning.append(f"MISSING_{metric.upper()}")
    if "ifrs-full" in data.get("facts", {}):
        warning.append("IFRS_NOT_NORMALIZED")
    if history:
        for row in history:
            if any(value is None for value in row["metrics"].values()):
                warning.append("INCOMPLETE_PERIODS")
                break
    return {"schema_version": VERSION, "company": data.get("entityName"),
            "cik": f"{cik:010d}", "as_of": as_of,
            "source_url": SEC_DATA.format(cik=cik),
            "fiscal_period_label": "period end date, not SEC fy field",
            "unit": "USD (nominal dollars; not millions)",
            "selected_us_gaap_concepts": concepts, "annual": history,
            "warnings": sorted(set(warning)),
            "limitations": [
                "No automatic unit conversion, current market price, share count, or net debt",
                "10-K/10-K/A FY annual durations only; excludes 20-F, 40-F and quarterly reports",
                "Most recent eligible amended filing may revise past values as of the requested date",
                "CFO minus CapEx is not FCFF and must not be used as unlevered cash flow",
                "No automatic mapping to DCF without user-supplied assumptions"],
            }


def build_dcf_baseline(snapshot):
    """Only verified historic revenue and EBIT/margin, not a DCF input set."""
    for row in snapshot["annual"]:
        revenue = row["metrics"]["revenue"]
        ebit = row["metrics"]["ebit"]
        if (revenue and ebit and revenue["value_usd"] > 0
                and revenue["start"] == ebit["start"]):
            return {"period_end": row["period_end"],
                    "gelir_0": revenue["value_usd"],
                    "marj_0": ebit["value_usd"] / revenue["value_usd"],
                    "unit": "USD", "source_revenue": revenue,
                    "source_ebit": ebit,
                    "not_provided": ["iskonto", "buyume", "marj_hedef",
                                     "yakinlasma", "satis_sermaye", "vergi_orani",
                                     "uc_buyume", "uc_roic", "hisse", "net_borc"]}
    raise ValueError("no same-period annual USD revenue and operating income available")


def main(argv=None):
    parser = argparse.ArgumentParser(description="SEC Company Facts annual normalizer")
    parser.add_argument("--cik", required=True)
    parser.add_argument("--as-of", required=True, dest="as_of")
    parser.add_argument("--years", type=int, default=10)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="offline Company Facts JSON path")
    source.add_argument("--download", action="store_true", help="fetch public SEC JSON")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    cik = _validate_cik(args.cik)
    data = download_companyfacts(cik, user_agent=os.getenv("SEC_USER_AGENT", "")) if args.download else load_companyfacts(args.file)
    if _validate_cik(data.get("cik")) != cik:
        parser.error("the Company Facts CIK differs from --cik")
    snapshot = normalize_companyfacts(data, as_of=args.as_of, years=args.years)
    destination = pathlib.Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"{snapshot['company']}: {len(snapshot['annual'])} annual periods -> {destination}")
    if snapshot["warnings"]:
        print("Warnings: " + ", ".join(snapshot["warnings"]))


if __name__ == "__main__":
    main()
