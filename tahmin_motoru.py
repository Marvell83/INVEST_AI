"""INVEST_AI — transparent baseline projections from source-traced history (roadmap lesson 6).

The system never invents a forecast assumption. A projection combines
(1) statistics measured on the company's own annual SEC history (revenue
growth, operating margin, tax rate, reinvestment), kept with their SEC filings,
and (2) one explicit analyst input: the long-run nominal growth rate, which
must carry a source. Cautious / base / optimistic scenarios start from the
lower quartile, median and upper quartile of the company's own history and
fade linearly to the long-run rate and the scenario margin. These are
scenarios, not predictions; they can be written to the append-only Tahmin
Defteri so that later SEC filings can score them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import sqlite3
import statistics

from finansal_oranlar import compute_ratios
from finansal_tablolar import build_annual_statements, previous_year
from tahmin_defteri import TahminDefteri

VERSION = "tahmin-motoru-0.1.0"
MAX_YEARS = 10
LONG_RUN_BOUNDS = (-0.05, 0.08)
SCENARIOS = {"temkinli": 0.25, "baz": 0.5, "iyimser": 0.75}  # quantile of the company's own history
MIN_OBSERVATIONS = 2           # growth and margin observations needed for the base scenario
MIN_SCENARIO_OBSERVATIONS = 3  # needed before quartiles are shown as cautious / optimistic
LEDGER_METRICS = ("revenue", "operating_income")


def _quantile(values, q):
    """Linear interpolation between order statistics (inclusive method)."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _stats(values):
    if not values:
        return {"n": 0}
    result = {"n": len(values), "median": statistics.median(values), "min": min(values),
              "max": max(values), "q1": _quantile(values, 0.25), "q3": _quantile(values, 0.75)}
    if len(values) > 1:
        result["stdev"] = statistics.stdev(values)
    return result


def _value(year, statement, key):
    cell = year[statement][key]
    return cell["value"] if cell.get("status") in ("REPORTED", "DERIVED") else None


def _invested_capital(year):
    parts = [_value(year, "balance", k) for k in ("stockholders_equity", "total_debt", "cash")]
    return None if None in parts else parts[0] + parts[1] - parts[2]


def historical_baseline(statements, ratios):
    """Summarise the company's own annual history; no assumption is added here."""
    years = statements["years"]
    if ratios.get("cik") != statements.get("cik") or len(ratios.get("years", [])) != len(years):
        raise ValueError("ratios do not belong to these statements")
    series, sources = [], set()
    reinvestment = []
    for index, (year, item) in enumerate(zip(years, ratios["years"])):
        r = item["ratios"]
        row = {"fiscal_year_end": year["fiscal_year_end"],
               "revenue": _value(year, "income", "revenue"),
               "operating_income": _value(year, "income", "operating_income")}
        for key in ("revenue_growth", "operating_margin", "effective_tax_rate", "fcf_margin"):
            row[key] = r[key]["value"]
        prior = previous_year(statements, index)
        if prior is not None:
            change_revenue = (None if row["revenue"] is None or _value(prior, "income", "revenue") is None
                              else row["revenue"] - _value(prior, "income", "revenue"))
            ic_now, ic_before = _invested_capital(year), _invested_capital(prior)
            change_capital = None if ic_now is None or ic_before is None else ic_now - ic_before
            # Only periods where both revenue and invested capital grew give a usable sales/capital ratio.
            if change_revenue and change_capital and change_revenue > 0 and change_capital > 0:
                row["sales_to_capital"] = change_revenue / change_capital
                reinvestment.append(row["sales_to_capital"])
        for statement, key in (("income", "revenue"), ("income", "operating_income")):
            cell = year[statement][key]
            if cell.get("status") in ("REPORTED", "DERIVED"):
                sources.update(cell.get("sources") or (cell["accession"],))
        if year["income"]["operating_income"].get("approximate"):
            row["operating_income_approximate"] = True
        series.append(row)

    cagr = None
    chain = 0
    while chain + 1 < len(years) and previous_year(statements, chain) is not None:
        chain += 1
    if chain:
        first, last = series[chain]["revenue"], series[0]["revenue"]
        if first and last and first > 0 and last > 0:
            cagr = {"value": (last / first) ** (1 / chain) - 1, "years": chain,
                    "from": series[chain]["fiscal_year_end"], "to": series[0]["fiscal_year_end"]}

    def observed(key):
        return [row[key] for row in series if row.get(key) is not None]
    growth, margins = observed("revenue_growth"), observed("operating_margin")
    base = series[0] if series else {}
    reasons = []
    if not base.get("revenue") or base["revenue"] <= 0:
        reasons.append("LATEST_REVENUE_UNAVAILABLE_OR_NONPOSITIVE")
    if base.get("operating_margin") is None:
        reasons.append("LATEST_OPERATING_MARGIN_UNAVAILABLE")
    if len(growth) < MIN_OBSERVATIONS:
        reasons.append(f"FEWER_THAN_{MIN_OBSERVATIONS}_REVENUE_GROWTH_OBSERVATIONS")
    if len(margins) < MIN_OBSERVATIONS:
        reasons.append(f"FEWER_THAN_{MIN_OBSERVATIONS}_OPERATING_MARGIN_OBSERVATIONS")
    return {
        "version": VERSION, "cik": statements["cik"], "company": statements.get("company", ""),
        "as_of": statements["as_of"], "source_url": statements.get("source_url"),
        "status": "INSUFFICIENT_HISTORY" if reasons else "OK", "reasons": reasons,
        "base_fiscal_year_end": base.get("fiscal_year_end"),
        "base": {"revenue": base.get("revenue"), "operating_margin": base.get("operating_margin")},
        "series": list(reversed(series)),
        "revenue_growth": _stats(growth), "revenue_cagr": cagr,
        "operating_margin": _stats(margins),
        "effective_tax_rate": _stats(observed("effective_tax_rate")),
        "fcf_margin": _stats(observed("fcf_margin")),
        "sales_to_capital": _stats(reinvestment),
        "approximate_operating_income_years": [row["fiscal_year_end"] for row in series
                                               if row.get("operating_income_approximate")],
        "sources": sorted(sources),
    }


def _observations(baseline, key):
    return [row[key] for row in baseline["series"] if row.get(key) is not None]


def project_scenarios(baseline, *, years=5, long_run_growth, long_run_growth_source, today=None):
    """Fade from the company's own historical quartiles to the analyst's long-run growth."""
    if isinstance(years, bool) or not isinstance(years, int) or not 1 <= years <= MAX_YEARS:
        raise ValueError(f"years must be an integer in 1..{MAX_YEARS}")
    low, high = LONG_RUN_BOUNDS
    if (isinstance(long_run_growth, bool) or not isinstance(long_run_growth, (int, float))
            or not math.isfinite(long_run_growth) or not low <= long_run_growth <= high):
        raise ValueError(f"long_run_growth must be a number in {low:.0%}..{high:.0%}")
    if not isinstance(long_run_growth_source, str) or len(long_run_growth_source.strip()) < 8:
        raise ValueError("long_run_growth_source: a citation of at least 8 characters is required")
    result = {"version": VERSION, "cik": baseline["cik"], "company": baseline.get("company", ""),
              "as_of": baseline["as_of"], "base_fiscal_year_end": baseline["base_fiscal_year_end"],
              "base": baseline["base"], "years": years, "scenarios": {}, "warnings": []}
    if baseline["status"] != "OK":
        return dict(result, status="INSUFFICIENT_HISTORY", reasons=baseline["reasons"])

    growth, margins = _observations(baseline, "revenue_growth"), _observations(baseline, "operating_margin")
    observations = min(len(growth), len(margins))
    names = list(SCENARIOS) if observations >= MIN_SCENARIO_OBSERVATIONS else ["baz"]
    revenue_0, margin_0 = baseline["base"]["revenue"], baseline["base"]["operating_margin"]
    for name in names:
        start_growth = _quantile(growth, SCENARIOS[name])
        target_margin = _quantile(margins, SCENARIOS[name])
        revenue, rows = revenue_0, []
        for k in range(1, years + 1):
            weight = k / years
            g = start_growth + (long_run_growth - start_growth) * weight
            margin = margin_0 + (target_margin - margin_0) * weight
            revenue *= 1 + g
            rows.append({"year": k, "target_period": f"FY+{k}_AFTER_{baseline['base_fiscal_year_end']}",
                         "revenue_growth": g, "revenue": revenue, "operating_margin": margin,
                         "operating_income": revenue * margin})
        result["scenarios"][name] = {"history_quantile": SCENARIOS[name], "starting_growth": start_growth,
                                     "target_operating_margin": target_margin, "rows": rows}

    if observations < MIN_SCENARIO_OBSERVATIONS:
        result["warnings"].append("SHORT_HISTORY_ONLY_BASE_SCENARIO")
    if baseline["revenue_growth"]["median"] > 0.25:
        result["warnings"].append("HIGH_HISTORICAL_GROWTH_RARELY_PERSISTS")
    if long_run_growth > 0.05:
        result["warnings"].append("LONG_RUN_GROWTH_ABOVE_TYPICAL_NOMINAL_ECONOMY")
    if baseline.get("approximate_operating_income_years"):
        result["warnings"].append("OPERATING_MARGIN_FROM_APPROXIMATE_EBIT")
    today = today or dt.datetime.now(dt.timezone.utc).date()
    retrospective = dt.date.fromisoformat(baseline["as_of"]) < today
    return dict(result, status="OK", retrospective=retrospective, sources=baseline["sources"],
                source_url=baseline.get("source_url"),
                assumptions={"long_run_growth": long_run_growth,
                             "long_run_growth_source": long_run_growth_source.strip(),
                             "history_observations": {"revenue_growth": len(growth),
                                                      "operating_margin": len(margins)}},
                method={"name": "HISTORICAL_QUANTILE_LINEAR_FADE",
                        "growth": "starts at the scenario quantile of annual revenue growth, "
                                  "fades linearly to long_run_growth in the final year",
                        "margin": "moves linearly from the latest operating margin to the scenario "
                                  "quantile of historical operating margins"})


def record_projection(projection, *, db_path, scenarios=("baz",)):
    """Write projected revenue and operating income to the append-only ledger, all or nothing."""
    if projection.get("status") != "OK":
        raise ValueError("only a complete projection can be recorded")
    if not scenarios or any(s not in projection["scenarios"] for s in scenarios):
        raise ValueError("scenario not available in this projection: " + ", ".join(scenarios))
    sources = ["SEC Company Facts: " + str(projection.get("source_url"))]
    sources += ["SEC filing: " + accession for accession in projection["sources"]]
    sources.append("Long-run growth: " + projection["assumptions"]["long_run_growth_source"])
    ids = []
    with TahminDefteri(db_path) as ledger:
        ledger.db.execute("BEGIN IMMEDIATE")
        try:
            for name in scenarios:
                scenario = projection["scenarios"][name]
                assumptions = {
                    "engine": VERSION, "scenario": name, "as_of": projection["as_of"],
                    "base_fiscal_year_end": projection["base_fiscal_year_end"],
                    "method": projection["method"]["name"],
                    "long_run_growth": projection["assumptions"]["long_run_growth"],
                    "starting_growth": scenario["starting_growth"],
                    "target_operating_margin": scenario["target_operating_margin"],
                    # A projection built today from an old as_of date is not an out-of-sample forecast.
                    "retrospective": projection["retrospective"],
                }
                if "OPERATING_MARGIN_FROM_APPROXIMATE_EBIT" in projection["warnings"]:
                    assumptions["operating_income_basis"] = "APPROXIMATE_PRETAX_PLUS_INTEREST"
                for row in scenario["rows"]:
                    for metric in LEDGER_METRICS:
                        ids.append(ledger.tahmin_kaydet(
                            company="CIK:" + projection["cik"], metric=metric,
                            target_period=row["target_period"], currency="USD",
                            predicted=row[metric], model_version=VERSION,
                            assumptions=assumptions, sources=sources))
            ledger.db.commit()
        except sqlite3.IntegrityError as exc:
            ledger.db.rollback()
            raise ValueError("an identical projection is already recorded in the ledger") from exc
        except Exception:
            ledger.db.rollback()
            raise
    return ids


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Transparent scenario projections from SEC history (offline; not investment advice)")
    parser.add_argument("--companyfacts", required=True, help="raw SEC Company Facts JSON")
    parser.add_argument("--as-of", required=True, help="knowledge cutoff YYYY-MM-DD")
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--long-run-growth", type=float, required=True,
                        help="analyst's long-run nominal revenue growth, e.g. 0.03")
    parser.add_argument("--long-run-source", required=True, help="citation for the long-run growth")
    parser.add_argument("--ledger", help="optional Tahmin Defteri SQLite path to record the projection")
    parser.add_argument("--record-scenarios", default="baz", help="comma separated, e.g. baz or temkinli,baz,iyimser")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    raw = json.loads(Path(args.companyfacts).read_text(encoding="utf-8"))
    statements = build_annual_statements(raw, as_of=args.as_of)
    baseline = historical_baseline(statements, compute_ratios(statements))
    projection = project_scenarios(baseline, years=args.years, long_run_growth=args.long_run_growth,
                                   long_run_growth_source=args.long_run_source)
    report = {"baseline": baseline, "projection": projection, "ledger_ids": []}
    if args.ledger:
        report["ledger_ids"] = record_projection(
            projection, db_path=args.ledger, scenarios=tuple(s.strip() for s in args.record_scenarios.split(",")))
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"CIK {projection['cik']} | {projection['status']} | scenarios {list(projection['scenarios'])} | "
          f"ledger rows {len(report['ledger_ids'])} | {target}")


if __name__ == "__main__":
    main()
