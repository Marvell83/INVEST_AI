"""Independent TTM historical baseline -> experimental DCF v0.2 scenarios.

This is an analyst stress exercise. TTM is accounting history, NOT future FCFF.
No source URL is independently authenticated here. No automatic share/price data.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

from degerleme_v02 import degerle_v02, ters_dcf_v02
from ttm_finansallar import CORE

VERSION = "ttm-dcf-bridge-0.1.0"
EXPECTED_SCENARIOS = ("temkinli", "baz", "iyimser")


def _date(x):
    if not isinstance(x, str):
        raise ValueError("ISO date string required")
    try:
        return dt.date.fromisoformat(x)
    except ValueError as exc:
        raise ValueError("invalid ISO date") from exc


def _source(value, name):
    if not isinstance(value, str) or not value.startswith("https://"):
        raise ValueError(name + " must be an HTTPS source")
    return value


def _numeric_positive(x, name):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0:
        raise ValueError(name + " must be a positive finite number")
    return x


def run_ttm_scenarios(ttm, config):
    if not isinstance(ttm, dict) or ttm.get("version") != "ttm-usgaap-0.1.0":
        raise ValueError("unsupported TTM report")
    if ttm.get("status") != "complete_core" or ttm.get("unit") != "USD (actual nominal dollars, NOT millions)":
        raise ValueError("complete USD TTM revenue, EBIT, CFO and CapEx required")
    if not isinstance(config, dict) or config.get("schema_version") != "invest-ai-scenarios-0.1":
        raise ValueError("unsupported scenario schema")
    issuer = config["issuer"]
    if issuer.get("cik") != ttm.get("cik"):
        raise ValueError("issuer CIK differs from TTM")
    cutoff = _date(config["research_as_of"])
    if ttm["as_of"] != cutoff.isoformat():
        raise ValueError("TTM and scenario research knowledge cutoffs must match")
    p = ttm["periods"]
    historic = config["historical"]
    interim = config["most_recent_interim_known"]
    if historic["fiscal_end"] != p["annual_end"] or interim["fiscal_end"] != p["current_9m_end"]:
        raise ValueError("interim or FY SEC periods differ from TTM")
    _source(historic.get("source"), "FY 10-K")
    _source(interim.get("source"), "Q3 10-Q")
    if historic.get("form") != "10-K" or interim.get("form") != "10-Q":
        raise ValueError("expected annual 10-K and interim 10-Q")
    for object_, key in ((historic, "filed_at"), (interim, "filed_at")):
        if _date(object_[key]) > cutoff:
            raise ValueError("future filing date used in TTM scenario")
    if not historic.get("accession") or not interim.get("accession"):
        raise ValueError("annual and interim SEC accession identifiers required")
    for metric, oldkey in (("revenue", "revenue_usd"), ("ebit", "ebit_usd"),
                           ("cfo", "operating_cash_flow_usd"), ("capex", "fiscal_2025_capex_usd")):
        actual = ttm["metrics"][metric]["annual"]["value_usd"]
        provided = historic.get(oldkey)
        if provided != actual:
            raise ValueError("historic input does not reconcile with TTM SEC record: " + metric)
        for phase in ("annual", "current_ytd9", "prior_ytd9"):
            fact = ttm["metrics"][metric][phase]
            if _date(fact["filed"]) > cutoff:
                raise ValueError("lookahead SEC TTM fact")
            if phase == "annual" and (fact["accession"] != historic["accession"]
                                      or fact["filed"] != historic["filed_at"]):
                raise ValueError("annual SEC provenance mismatch")
            if phase == "current_ytd9" and (fact["accession"] != interim["accession"]
                                            or fact["filed"] != interim["filed_at"]):
                raise ValueError("interim SEC provenance mismatch")

    balance = config["balance_sheet"]
    share = config["share_count"]
    quote = config["market_price"]
    for obj, key, label in ((balance, "date", "balance date"), (share, "date", "shares date"),
                            (quote, "date", "quote date")):
        if _date(obj[key]) > cutoff:
            raise ValueError("future " + label)
        _source(obj.get("source"), label)
    if balance["date"] != p["current_9m_end"]:
        raise ValueError("balance must be dated exactly the TTM period end")
    if not (p["current_9m_end"] <= share["date"] <= interim["filed_at"]):
        raise ValueError("share count date must be within period-end / filing window")
    if quote.get("kind") != "previous_session_closing_price_not_live_quote" or _date(quote["date"]) >= cutoff:
        raise ValueError("explicit dated previous-session price required")
    _numeric_positive(quote.get("close_usd"), "market price")
    _numeric_positive(share.get("shares"), "share count")
    debt_fields = ("commercial_paper_usd", "term_debt_current_usd", "term_debt_noncurrent_usd")
    cash_fields = ("cash_usd", "marketable_current_usd", "marketable_noncurrent_usd")
    for key in (*debt_fields, *cash_fields):
        value = balance.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid net debt component " + key)
    if balance.get("treat_all_marketable_securities_as_excess_cash") is not True:
        raise ValueError("model convention for excess cash must be acknowledged")
    net_debt = sum(balance[k] for k in debt_fields) - sum(balance[k] for k in cash_fields)
    common = config["common_assumptions"]
    if common.get("zero_opening_tax_loss") is not True or common.get("sbc_is_already_expensed_in_operating_margin") is not True:
        raise ValueError("explicit tax loss and SBC limitations required")
    if not isinstance(common.get("forecast_years"), int) or isinstance(common["forecast_years"], bool):
        raise ValueError("forecast years must be integer")
    revenue = ttm["metrics"]["revenue"]["value_usd"]
    ebit = ttm["metrics"]["ebit"]["value_usd"]
    if revenue <= 0:
        raise ValueError("positive TTM revenue required")
    base = dict(yillar=common["forecast_years"], gelir_0=revenue, marj_0=ebit/revenue,
                vergi_orani=common["tax_rate"], yakinlasma=common["margin_convergence"],
                hisse=share["shares"], net_borc=net_debt,
                iskonto_zamani=common["discount_timing"],
                sbc_marjda_dahil=True, baslangic_zarar=0, sbc_yontemi="gider")
    scenarios = config["scenarios"]
    if not isinstance(scenarios, dict) or set(scenarios) != set(EXPECTED_SCENARIOS):
        raise ValueError("all three scenario names required")
    results, inputs_by_name = {}, {}
    for name in EXPECTED_SCENARIOS:
        s = scenarios[name]
        required = ("annual_revenue_growth", "target_ebit_margin", "sales_to_capital_ratio",
                    "discount_rate", "terminal_growth", "terminal_ronic")
        if not isinstance(s, dict) or any(k not in s for k in required) or not s.get("rationale"):
            raise ValueError("scenario lacks cited explanation or required assumptions: " + name)
        inputs = dict(base, buyume=s["annual_revenue_growth"], marj_hedef=s["target_ebit_margin"],
                      satis_sermaye=s["sales_to_capital_ratio"], iskonto=s["discount_rate"],
                      uc_buyume=s["terminal_growth"], uc_roic=s["terminal_ronic"])
        valuation = degerle_v02(inputs)
        if valuation["durum"] != "gecerli":
            raise ValueError("DCF rejected " + name)
        results[name] = {"valuation": valuation, "model_inputs": inputs, "assumptions": dict(s)}
        inputs_by_name[name] = inputs
    reverse_cfg = config["reverse"]
    if reverse_cfg["scenario"] not in EXPECTED_SCENARIOS:
        raise ValueError("invalid reverse DCF scenario")
    reverse = ters_dcf_v02(inputs_by_name[reverse_cfg["scenario"]], quote["close_usd"],
                            lower=reverse_cfg["lower_annual_growth"],
                            upper=reverse_cfg["upper_annual_growth"],
                            grid_steps=reverse_cfg["grid_steps"])
    return {
        "version": VERSION, "cik": ttm["cik"], "company": ttm["company"],
        "historical_as_of": ttm["as_of"], "ttm_fy_end": p["current_9m_end"],
        "historical_metric_sources": {k: ttm["metrics"][k] for k in CORE},
        "ttm_gelir_0_usd": revenue, "ttm_marj_0": ebit/revenue,
        "ttm_cfo_usd": ttm["metrics"]["cfo"]["value_usd"],
        "ttm_capex_usd": ttm["metrics"]["capex"]["value_usd"],
        "cfo_minus_capex_is_fcff": False,
        "source_identifiers": {"FY": historic["source"], "Q3": interim["source"],
                               "share_count": share["source"], "balance": balance["source"],
                               "quote": quote["source"]},
        "source_ages": {"balance_as_of": balance["date"], "shares_as_of": share["date"],
                        "quote_as_of": quote["date"], "research_as_of": cutoff.isoformat()},
        "net_debt_model_usd": net_debt, "price_usd": quote["close_usd"],
        "scenarios": results, "reverse_dcf": reverse,
        "warnings": [
            "Research scenario only: historical TTM statement facts are not management forecasts",
            "Input sample transcribed from SEC primary filings; not independently downloaded SEC Company Facts",
            "Earnings TTM as of Q3; FY2026 Q4 not yet incorporated into this historical research vintage",
            "Balance at TTM end, shares at later interim cover date, price at a separate later closing date",
            "All marketable securities treated as excess cash solely as a model convention",
            "Tax, SBC, future dilution, terminal and investment return assumptions are not verified forecasts",
            "Not a target price, investment recommendation, or demonstrated predictive performance",
            "No inferred FCFF from CFO minus CapEx; future DCF uses operating-profit and reinvestment assumptions",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="TTM based experimental DCF scenario comparison")
    parser.add_argument("--ttm", required=True)
    parser.add_argument("--scenarios", required=True)
    parser.add_argument("--out", required=True)
    options = parser.parse_args(argv)
    report = run_ttm_scenarios(
        json.loads(Path(options.ttm).read_text(encoding="utf-8")),
        json.loads(Path(options.scenarios).read_text(encoding="utf-8")))
    out = Path(options.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    for s in EXPECTED_SCENARIOS:
        print(s, "USD/share:", report["scenarios"][s]["valuation"]["hisse_basi_deger"])
    print("Saved:", out)

if __name__ == "__main__":
    main()
