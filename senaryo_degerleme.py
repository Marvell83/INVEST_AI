"""INVEST_AI — scenario valuation: forecast scenarios through the v0.2 DCF (roadmap lesson 7).

Each cautious / base / optimistic scenario from tahmin_motoru is valued with
degerleme_v02 on exactly the same revenue and operating-margin path. Every
input keeps its origin:

  ANALYST         discount rate (required, sourced) and any override
  SEC_HISTORY     tax rate and sales-to-capital: medians of the company's own history
  SEC_FILING      net debt (total debt - cash) and cover-page shares from the shared layer
  METHOD_DEFAULT  terminal RONIC = discount rate (growth creates no value) unless overridden

The base scenario also gets a discount-rate x terminal-growth sensitivity grid.
Results are experimental scenario values, not price targets or advice.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

from degerleme_v02 import degerle_v02, ters_dcf_v02
from finansal_oranlar import compute_ratios
from finansal_tablolar import build_annual_statements
from tahmin_motoru import historical_baseline, project_scenarios

VERSION = "senaryo-degerleme-0.1.0"
DISCOUNT_BOUNDS = (0.04, 0.20)
TERMINAL_GROWTH_CAP = 0.04  # degerleme_v02 default cap on perpetual growth
SENSITIVITY_STEPS = (-0.01, -0.005, 0.0, 0.005, 0.01)
OVERRIDABLE = ("tax_rate", "sales_to_capital", "net_debt", "shares", "terminal_roic", "terminal_growth")
IMPLIED_GROWTH_RANGE = (-0.5, 1.0)  # searched constant annual revenue growth
PRICE_DATE_TOLERANCE_DAYS = 7


def _source(text, name):
    if not isinstance(text, str) or len(text.strip()) < 8:
        raise ValueError(f"{name}: a citation of at least 8 characters is required")
    return text.strip()


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite number required")
    return float(value)


def _latest_year(statements):
    return statements["years"][0] if statements.get("years") else None


def valuation_inputs(projection, baseline, statements, *, discount_rate, discount_source, overrides=None):
    """Assemble DCF inputs with their origin; report anything the analyst must still supply."""
    if not (projection.get("cik") == baseline.get("cik") == statements.get("cik")):
        raise ValueError("projection, baseline and statements must belong to one issuer")
    low, high = DISCOUNT_BOUNDS
    discount = _number(discount_rate, "discount_rate")
    if not low <= discount <= high:
        raise ValueError(f"discount_rate must be in {low:.0%}..{high:.0%}")
    overrides = dict(overrides or {})
    unknown = set(overrides) - set(OVERRIDABLE)
    if unknown:
        raise ValueError("unknown override: " + ", ".join(sorted(unknown)))
    inputs = {"discount_rate": {"value": discount, "origin": "ANALYST",
                                "source": _source(discount_source, "discount_source")}}
    for name, item in overrides.items():
        if not isinstance(item, dict):
            raise ValueError(f"{name}: override must be {{'value': ..., 'source': ...}}")
        inputs[name] = {"value": _number(item.get("value"), name), "origin": "ANALYST",
                        "source": _source(item.get("source"), name + " source")}
    assumptions = projection.get("assumptions", {})
    inputs.setdefault("terminal_growth", {"value": assumptions.get("long_run_growth"), "origin": "ANALYST",
                                          "source": assumptions.get("long_run_growth_source")})

    def history(name, key):
        stats = baseline.get(key, {})
        if stats.get("n", 0) and name not in inputs:
            inputs[name] = {"value": stats["median"], "origin": "SEC_HISTORY",
                            "source": f"şirketin {stats['n']} mali yılının medyanı ({', '.join(baseline['sources'])})"}
    history("tax_rate", "effective_tax_rate")
    history("sales_to_capital", "sales_to_capital")

    year = _latest_year(statements)
    if year and "net_debt" not in inputs:
        debt, cash = year["balance"]["total_debt"], year["balance"]["cash"]
        if debt.get("status") in ("REPORTED", "DERIVED") and cash.get("status") == "REPORTED":
            inputs["net_debt"] = {"value": debt["value"] - cash["value"], "origin": "SEC_FILING",
                                  "source": f"{year['fiscal_year_end']} itibarıyla toplam borç − nakit "
                                            f"({debt.get('accession')}, {cash.get('accession')})"}
    shares = statements.get("shares_outstanding", {})
    if shares.get("status") == "REPORTED" and "shares" not in inputs:
        inputs["shares"] = {"value": shares["value"], "origin": "SEC_FILING",
                            "source": f"{shares['date']} tarihli kapak sayfası, dolaşımdaki hisse ({shares['accession']})"}
    inputs.setdefault("terminal_roic", {"value": discount, "origin": "METHOD_DEFAULT",
                                        "source": "uç dönem RONIC = iskonto oranı: büyüme tek başına değer yaratmaz"})
    missing = [name for name in OVERRIDABLE if name not in inputs]
    return inputs, missing


def _engine_inputs(projection, scenario, inputs, discount=None, terminal_growth=None):
    rows = projection["scenarios"][scenario]["rows"]
    discount = inputs["discount_rate"]["value"] if discount is None else discount
    roic = inputs["terminal_roic"]
    return {
        "yillar": len(rows), "gelir_0": projection["base"]["revenue"],
        "buyume": [r["revenue_growth"] for r in rows],
        "marj_0": projection["base"]["operating_margin"], "marj_hedef": rows[-1]["operating_margin"],
        "yakinlasma": 1.0, "marj_yolu": [r["operating_margin"] for r in rows],
        "satis_sermaye": inputs["sales_to_capital"]["value"], "vergi_orani": inputs["tax_rate"]["value"],
        "iskonto": discount,
        "uc_buyume": inputs["terminal_growth"]["value"] if terminal_growth is None else terminal_growth,
        # A neutral terminal RONIC follows the discount rate across the sensitivity grid.
        "uc_roic": discount if roic["origin"] == "METHOD_DEFAULT" else roic["value"],
        "hisse": inputs["shares"]["value"], "net_borc": inputs["net_debt"]["value"],
    }


def value_scenarios(projection, baseline, statements, *, discount_rate, discount_source, overrides=None):
    """Value every projected scenario and the base-scenario sensitivity grid."""
    result = {"version": VERSION, "cik": projection.get("cik"), "company": projection.get("company", ""),
              "as_of": projection.get("as_of"), "scenarios": {}, "sensitivity": None, "warnings": []}
    if projection.get("status") != "OK":
        return dict(result, status="PROJECTION_UNAVAILABLE")
    inputs, missing = valuation_inputs(projection, baseline, statements, discount_rate=discount_rate,
                                       discount_source=discount_source, overrides=overrides)
    result["inputs"] = inputs
    if missing:
        return dict(result, status="INPUTS_MISSING", missing=missing)
    growth = inputs["terminal_growth"]["value"]
    if growth > TERMINAL_GROWTH_CAP:
        raise ValueError(f"terminal growth {growth:.1%} exceeds the {TERMINAL_GROWTH_CAP:.0%} perpetual cap; "
                         "override terminal_growth with a sourced value")
    if inputs["sales_to_capital"]["value"] <= 0 or inputs["shares"]["value"] <= 0:
        raise ValueError("sales_to_capital and shares must be positive")
    for name in projection["scenarios"]:
        engine_inputs = _engine_inputs(projection, name, inputs)
        valuation = degerle_v02(engine_inputs)
        for row, projected in zip(valuation["tablo"], projection["scenarios"][name]["rows"]):
            if abs(row["gelir"] - projected["revenue"]) > 1e-9 * max(1.0, abs(projected["revenue"])):
                raise ValueError("DCF revenue path differs from the projection")
        result["scenarios"][name] = {
            "enterprise_value": valuation["firma_degeri"], "equity_value": valuation["ozsermaye_degeri"],
            "per_share": valuation["hisse_basi_deger"], "terminal_value_share": valuation["uc_deger_payi"],
            "engine_warnings": valuation["uyarilar"], "engine_version": valuation["motor_surumu"],
            "fcff": [row["fcff"] for row in valuation["tablo"]],
        }
    base = "baz" if "baz" in projection["scenarios"] else next(iter(projection["scenarios"]))
    discounts = [round(inputs["discount_rate"]["value"] + step, 6) for step in SENSITIVITY_STEPS]
    growths = [round(growth + step, 6) for step in SENSITIVITY_STEPS]
    grid = []
    for d in discounts:
        line = []
        for g in growths:
            if d <= 0 or g >= d or g > TERMINAL_GROWTH_CAP or g <= -1:
                line.append(None)
            else:
                line.append(degerle_v02(_engine_inputs(projection, base, inputs, d, g))["hisse_basi_deger"])
        grid.append(line)
    result["sensitivity"] = {"scenario": base, "discount_rates": discounts, "terminal_growths": growths,
                             "per_share": grid}
    if inputs["net_debt"]["origin"] == "SEC_FILING":
        result["warnings"].append("NET_DEBT_EXCLUDES_SECURITIES_AND_LEASES")
    if inputs["terminal_roic"]["origin"] == "METHOD_DEFAULT":
        result["warnings"].append("TERMINAL_RONIC_NEUTRAL_DEFAULT")
    if projection.get("retrospective"):
        result["warnings"].append("RETROSPECTIVE_PROJECTION")
    return dict(result, status="OK", notes=[
        "Same revenue and operating-margin path as the projection; FCFF = NOPAT - revenue change / sales-to-capital",
        "Scenario values are experimental, not price targets, fair values or recommendations",
        "Net debt from SEC statements excludes marketable securities and lease liabilities",
    ])


def _history_position(value, observations):
    """Where a growth rate sits within the company's own annual growth history."""
    if not observations:
        return {"band": "NO_HISTORY", "n": 0}
    ordered = sorted(observations)
    q1, q3 = _quantile(ordered, 0.25), _quantile(ordered, 0.75)
    band = ("BELOW_HISTORY" if value < ordered[0] else "ABOVE_HISTORY" if value > ordered[-1]
            else "BELOW_Q1" if value < q1 else "ABOVE_Q3" if value > q3 else "WITHIN_Q1_Q3")
    return {"band": band, "n": len(ordered), "share_of_years_below": sum(g < value for g in ordered) / len(ordered),
            "min": ordered[0], "q1": q1, "median": _quantile(ordered, 0.5), "q3": q3, "max": ordered[-1]}


def _quantile(ordered, q):
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def implied_growth(projection, baseline, valuation, *, price, price_source, price_date):
    """Constant annual revenue growth that an analyst-supplied price implies.

    Everything except growth stays as in the valued base scenario (margin path,
    tax, sales-to-capital, discount, terminal assumptions, net debt, shares).
    The root search covers a bounded range and cannot prove that no other root exists.
    """
    if valuation.get("status") != "OK":
        return {"status": "VALUATION_UNAVAILABLE"}
    price = _number(price, "price")
    if not 0 < price < 1e7:
        raise ValueError("price must be a positive per-share amount")
    source = _source(price_source, "price_source")
    try:
        quoted = dt.date.fromisoformat(price_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("price_date must be YYYY-MM-DD") from exc
    scenario = valuation["sensitivity"]["scenario"]
    engine = _engine_inputs(projection, scenario, valuation["inputs"])
    low, high = IMPLIED_GROWTH_RANGE
    search = ters_dcf_v02(engine, price, lower=low, upper=high)
    result = {"status": "OK", "price": {"value": price, "source": source, "date": price_date},
              "scenario": scenario, "years": engine["yillar"],
              "search": {"state": search["durum"], "range": [low, high],
                         "roots": [r["buyume"] for r in search["dogrulanan_kokler"]],
                         "all_roots_guaranteed": False},
              "warnings": []}
    gap = (quoted - dt.date.fromisoformat(projection["as_of"])).days
    if gap > 0:
        result["warnings"].append("PRICE_AFTER_SEC_AS_OF")
    if abs(gap) > PRICE_DATE_TOLERANCE_DAYS:
        result["warnings"].append("PRICE_DATE_FAR_FROM_SEC_AS_OF")
    if search["durum"] != "tek_cozum_dogrulandi":
        result["status"] = "NO_UNIQUE_SOLUTION"
        return result
    implied = search["ima_edilen_buyume"]
    history = [row["revenue_growth"] for row in baseline["series"] if row.get("revenue_growth") is not None]
    result.update(implied_growth=implied, history_position=_history_position(implied, history),
                  base_scenario_starting_growth=projection["scenarios"][scenario]["starting_growth"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scenario DCF from SEC history (offline; not advice)")
    parser.add_argument("--companyfacts", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--long-run-growth", type=float, required=True)
    parser.add_argument("--long-run-source", required=True)
    parser.add_argument("--discount-rate", type=float, required=True)
    parser.add_argument("--discount-source", required=True)
    for name in OVERRIDABLE:
        if name == "terminal_growth":
            continue
        flag = "--" + name.replace("_", "-")
        parser.add_argument(flag, type=float)
        parser.add_argument(flag + "-source")
    parser.add_argument("--price", type=float, help="optional analyst-entered share price for a reverse DCF")
    parser.add_argument("--price-date", help="date of --price (YYYY-MM-DD)")
    parser.add_argument("--price-source")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    price_args = (args.price, args.price_date, args.price_source)
    if any(x is not None for x in price_args) and None in price_args:
        parser.error("--price, --price-date and --price-source must be given together")
    overrides = {}
    for name in OVERRIDABLE:
        value = getattr(args, name, None)
        source = getattr(args, name + "_source", None)
        if (value is None) != (source is None):
            parser.error(f"--{name.replace('_', '-')} and its -source must be given together")
        if value is not None:
            overrides[name] = {"value": value, "source": source}
    raw = json.loads(Path(args.companyfacts).read_text(encoding="utf-8"))
    statements = build_annual_statements(raw, as_of=args.as_of)
    baseline = historical_baseline(statements, compute_ratios(statements))
    projection = project_scenarios(baseline, years=args.years, long_run_growth=args.long_run_growth,
                                   long_run_growth_source=args.long_run_source)
    report = value_scenarios(projection, baseline, statements, discount_rate=args.discount_rate,
                             discount_source=args.discount_source, overrides=overrides)
    implied = None
    if args.price is not None:
        implied = implied_growth(projection, baseline, report, price=args.price,
                                 price_source=args.price_source, price_date=args.price_date)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"projection": projection, "valuation": report, "implied_growth": implied},
                                 ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    values = {k: round(v["per_share"], 2) for k, v in report["scenarios"].items()}
    implied_text = f" | implied growth {implied.get('implied_growth')}" if implied else ""
    print(f"CIK {report['cik']} | {report['status']} | per share {values}{implied_text} | {target}")


if __name__ == "__main__":
    main()
