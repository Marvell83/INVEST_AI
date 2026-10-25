"""INVEST_AI — financial ratios from the shared annual statements layer.

Every ratio carries its formula, the exact inputs used and, when it cannot be
computed, a reason. No ratio is guessed from a missing, conflicting or
non-positive denominator. Ratios describe history; they are not forecasts,
scores or recommendations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from finansal_tablolar import VERSION as STATEMENTS_VERSION
from finansal_tablolar import build_annual_statements, previous_year

VERSION = "finansal-oranlar-0.1.0"
TAX_RATE_BOUNDS = (0.0, 0.5)

# key: (Turkish label, group, display kind, formula)
RATIOS = {
    "gross_margin": ("Brüt kâr marjı", "Kârlılık", "percent", "brüt kâr / gelir"),
    "operating_margin": ("Faaliyet kâr marjı", "Kârlılık", "percent", "faaliyet kârı / gelir"),
    "net_margin": ("Net kâr marjı", "Kârlılık", "percent", "net kâr / gelir"),
    "revenue_growth": ("Gelir büyümesi", "Büyüme", "percent", "gelir / önceki yıl gelir − 1"),
    "operating_income_growth": ("Faaliyet kârı büyümesi", "Büyüme", "percent",
                                "faaliyet kârı / önceki yıl faaliyet kârı − 1 (önceki yıl > 0)"),
    "fcf_margin": ("Serbest nakit akışı marjı", "Nakit akışı", "percent", "(CFO − CapEx) / gelir"),
    "cash_conversion": ("Nakit dönüşümü", "Nakit akışı", "multiple", "CFO / net kâr (net kâr > 0)"),
    "capex_intensity": ("CapEx yoğunluğu", "Nakit akışı", "percent", "CapEx / gelir"),
    "sbc_to_revenue": ("Hisse bazlı ödeme / gelir", "Nakit akışı", "percent", "hisse bazlı ödeme / gelir"),
    "shareholder_payout": ("Hissedarlara dağıtım / net kâr", "Nakit akışı", "percent",
                           "(temettü + geri alım) / net kâr (net kâr > 0)"),
    "roa": ("Aktif kârlılığı (ROA)", "Getiri", "percent", "net kâr / ortalama toplam varlıklar"),
    "roe": ("Özkaynak kârlılığı (ROE)", "Getiri", "percent", "net kâr / ortalama özkaynak (özkaynak > 0)"),
    "effective_tax_rate": ("Efektif vergi oranı", "Getiri", "percent", "vergi gideri / vergi öncesi kâr"),
    "roic": ("Yatırılan sermaye getirisi (ROIC)", "Getiri", "percent",
             "faaliyet kârı × (1 − efektif vergi) / ortalama (özkaynak + toplam borç − nakit)"),
    "current_ratio": ("Cari oran", "Bilanço", "multiple", "dönen varlıklar / kısa vadeli yükümlülükler"),
    "debt_to_equity": ("Borç / özkaynak", "Bilanço", "multiple", "toplam borç / özkaynak (özkaynak > 0)"),
    "net_debt": ("Net borç", "Bilanço", "usd", "toplam borç − nakit ve nakit benzerleri"),
    "interest_coverage": ("Faiz karşılama", "Bilanço", "multiple", "faaliyet kârı / faiz gideri"),
}


# Ratios that use operating income; flagged when it is the pretax + interest proxy.
OPERATING_INCOME_RATIOS = ("operating_margin", "operating_income_growth", "roic", "interest_coverage")


def _value(cell):
    return cell["value"] if cell.get("status") in ("REPORTED", "DERIVED") else None


def _item(year, key):
    for statement in ("income", "cash_flow", "balance"):
        if key in year[statement]:
            return _value(year[statement][key])
    raise KeyError(key)


def _missing(inputs):
    return [name for name, value in inputs.items() if value is None]


def _ratio(key, inputs, compute, guard=None):
    """Compute one ratio or explain precisely why it was not computed."""
    absent = _missing(inputs)
    result = {"value": None, "formula": RATIOS[key][3], "inputs": inputs}
    if absent:
        result["reason"] = "INPUT_UNAVAILABLE:" + ",".join(absent)
        return result
    if guard is not None:
        problem = guard(inputs)
        if problem:
            result["reason"] = problem
            return result
    result["value"] = compute(inputs)
    return result


def _positive(*names):
    def check(inputs):
        bad = [n for n in names if inputs[n] <= 0]
        return "NONPOSITIVE_DENOMINATOR:" + ",".join(bad) if bad else None
    return check


def _avg(a, b):
    return None if a is None or b is None else (a + b) / 2


def _year_ratios(statements, index):
    year = statements["years"][index]
    prior = previous_year(statements, index)

    def get(key):
        return _item(year, key)

    def before(key):
        return _item(prior, key) if prior else None

    revenue = get("revenue")
    out = {}

    for key, numerator in (("gross_margin", "gross_profit"), ("operating_margin", "operating_income"),
                           ("net_margin", "net_income"), ("fcf_margin", "free_cash_flow"),
                           ("capex_intensity", "capex"), ("sbc_to_revenue", "share_based_compensation")):
        out[key] = _ratio(key, {numerator: get(numerator), "revenue": revenue},
                          lambda i, n=numerator: i[n] / i["revenue"], _positive("revenue"))

    out["revenue_growth"] = _ratio(
        "revenue_growth", {"revenue": revenue, "prior_revenue": before("revenue")},
        lambda i: i["revenue"] / i["prior_revenue"] - 1, _positive("prior_revenue"))
    out["operating_income_growth"] = _ratio(
        "operating_income_growth",
        {"operating_income": get("operating_income"), "prior_operating_income": before("operating_income")},
        lambda i: i["operating_income"] / i["prior_operating_income"] - 1,
        _positive("prior_operating_income"))
    out["cash_conversion"] = _ratio(
        "cash_conversion", {"cfo": get("cfo"), "net_income": get("net_income")},
        lambda i: i["cfo"] / i["net_income"], _positive("net_income"))
    dividends, repurchases = get("dividends_paid"), get("share_repurchases")
    out["shareholder_payout"] = _ratio(
        "shareholder_payout",
        {"dividends_paid": dividends, "share_repurchases": repurchases, "net_income": get("net_income")},
        lambda i: (i["dividends_paid"] + i["share_repurchases"]) / i["net_income"], _positive("net_income"))

    out["roa"] = _ratio(
        "roa", {"net_income": get("net_income"),
                "average_total_assets": _avg(get("total_assets"), before("total_assets"))},
        lambda i: i["net_income"] / i["average_total_assets"], _positive("average_total_assets"))
    out["roe"] = _ratio(
        "roe", {"net_income": get("net_income"),
                "average_equity": _avg(get("stockholders_equity"), before("stockholders_equity"))},
        lambda i: i["net_income"] / i["average_equity"], _positive("average_equity"))

    low, high = TAX_RATE_BOUNDS
    out["effective_tax_rate"] = _ratio(
        "effective_tax_rate", {"income_tax": get("income_tax"), "pretax_income": get("pretax_income")},
        lambda i: i["income_tax"] / i["pretax_income"],
        lambda i: (_positive("pretax_income")(i) or
                   (None if low <= i["income_tax"] / i["pretax_income"] <= high
                    else f"TAX_RATE_OUTSIDE_{low:.0%}_{high:.0%}")))
    tax_rate = out["effective_tax_rate"]["value"]

    def invested(source):
        parts = [source("stockholders_equity"), source("total_debt"), source("cash")]
        return None if None in parts else parts[0] + parts[1] - parts[2]
    out["roic"] = _ratio(
        "roic", {"operating_income": get("operating_income"), "effective_tax_rate": tax_rate,
                 "average_invested_capital": _avg(invested(get), invested(before) if prior else None)},
        lambda i: i["operating_income"] * (1 - i["effective_tax_rate"]) / i["average_invested_capital"],
        _positive("average_invested_capital"))

    out["current_ratio"] = _ratio(
        "current_ratio", {"current_assets": get("current_assets"),
                          "current_liabilities": get("current_liabilities")},
        lambda i: i["current_assets"] / i["current_liabilities"], _positive("current_liabilities"))
    out["debt_to_equity"] = _ratio(
        "debt_to_equity", {"total_debt": get("total_debt"), "stockholders_equity": get("stockholders_equity")},
        lambda i: i["total_debt"] / i["stockholders_equity"], _positive("stockholders_equity"))
    out["net_debt"] = _ratio(
        "net_debt", {"total_debt": get("total_debt"), "cash": get("cash")},
        lambda i: i["total_debt"] - i["cash"])
    out["interest_coverage"] = _ratio(
        "interest_coverage", {"operating_income": get("operating_income"),
                              "interest_expense": get("interest_expense")},
        lambda i: i["operating_income"] / i["interest_expense"], _positive("interest_expense"))
    if prior is None:
        for key in ("revenue_growth", "operating_income_growth", "roa", "roe", "roic"):
            if out[key]["value"] is None:
                out[key]["reason"] = "PRIOR_FISCAL_YEAR_REQUIRED"
    current_proxy = bool(year["income"]["operating_income"].get("approximate"))
    prior_proxy = bool(prior and prior["income"]["operating_income"].get("approximate"))
    for key in OPERATING_INCOME_RATIOS:
        uses_proxy = current_proxy or (key == "operating_income_growth" and prior_proxy)
        if uses_proxy and out[key]["value"] is not None:
            out[key]["approximate"] = "OPERATING_INCOME_PROXY"
    return {"fiscal_year_end": year["fiscal_year_end"], "ratios": out}


def compute_ratios(statements):
    if not isinstance(statements, dict) or statements.get("version") != STATEMENTS_VERSION:
        raise ValueError("finansal_tablolar statements of a supported version required")
    return {
        "version": VERSION, "cik": statements["cik"], "as_of": statements["as_of"],
        "years": [_year_ratios(statements, i) for i in range(len(statements["years"]))],
        "notes": [
            "Averages use the fiscal year-end and the prior fiscal year-end balances",
            "ROIC uses the reported effective tax rate only when it lies within "
            f"{TAX_RATE_BOUNDS[0]:.0%}..{TAX_RATE_BOUNDS[1]:.0%}; invested capital subtracts "
            "cash and cash equivalents only, not marketable securities",
            "Net debt excludes lease liabilities and marketable securities",
            "Historical ratios are not forecasts, scores or investment advice",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Source-traced annual statements and ratios from SEC Company Facts (offline)")
    parser.add_argument("--companyfacts", required=True, help="raw SEC Company Facts JSON")
    parser.add_argument("--as-of", required=True, help="knowledge cutoff YYYY-MM-DD")
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    raw = json.loads(Path(args.companyfacts).read_text(encoding="utf-8"))
    statements = build_annual_statements(raw, as_of=args.as_of, years=args.years)
    report = {"statements": statements, "ratios": compute_ratios(statements)}
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"CIK {statements['cik']} | {len(statements['years'])} fiscal years | "
          f"{len(statements['conflicts'])} alias conflicts | {target}")


if __name__ == "__main__":
    main()
