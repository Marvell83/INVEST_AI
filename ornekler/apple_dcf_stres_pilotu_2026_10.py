"""Apple 21 Oct 2026: sourced financial facts + HYPOTHETICAL DCF stress tests.

This file is a reproducible educational example, NOT a current fair value
assessment. FY2025 revenue is paired with FY2026 Q3 cash/debt and a July 2026
share count; Oct 20 closing price. Explicit period mismatch is intentional.
"""
from __future__ import annotations
import argparse
import json
from degerleme_v02 import degerle_v02, ters_dcf_v02

SOURCES = {
    "FY2025_10K": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
    "FY2026_Q3_10Q": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm",
    "PRICE_2026_10_20": "https://www.investing.com/equities/apple-computer-inc-historical-data",
}
AS_OF = "2026-10-21"
PRICE = 339.50  # 2026-10-20 close; NOT a 21 Oct live quote.
FY2025_REVENUE = 416_161_000_000
FY2025_EBIT = 133_050_000_000
JUL2026_SHARES = 14_594_180_000
JUN2026_NET_DEBT = (1_997 + 11_007 + 71_340 - 39_544 - 22_855 - 84_118) * 1_000_000

SCENARIOS = {
    "temkinli": dict(buyume=.02, marj_hedef=.28, satis_sermaye=2.5,
                      iskonto=.105, uc_buyume=.02, uc_roic=.105),
    "baz": dict(buyume=.08, marj_hedef=.34, satis_sermaye=3.0,
                iskonto=.085, uc_buyume=.025, uc_roic=.10),
    "iyimser": dict(buyume=.15, marj_hedef=.37, satis_sermaye=3.5,
                    iskonto=.075, uc_buyume=.03, uc_roic=.12),
}

def equity_rollforward():
    """FY2025 share figures in thousands; employee share issuance is NOT zero."""
    beginning, repurchased, issued, ending = 15_116_786, 401_672, 58_146, 14_773_260
    if beginning - repurchased + issued != ending:
        raise ValueError("SEC share roll-forward did not reconcile")
    return {
        "beginning_000": beginning, "repurchased_000": repurchased,
        "issued_net_employee_tax_000": issued, "ending_000": ending,
        "any_new_shares_absent": False,
        "outstanding_share_count_did_not_increase": True,
        "external_equity_offering_status": "not independently classified",
        "piotroski_issuance_score": None,
        "warning": "Net falling share count does not mean no employee shares were issued.",
    }

def inputs_for(name):
    if name not in SCENARIOS:
        raise ValueError("unknown scenario")
    return {
        "yillar": 5, "gelir_0": FY2025_REVENUE,
        "marj_0": FY2025_EBIT / FY2025_REVENUE,
        "yakinlasma": .30, "vergi_orani": .21,
        "hisse": JUL2026_SHARES, "net_borc": JUN2026_NET_DEBT,
        "iskonto_zamani": "yil_sonu", "sbc_marjda_dahil": True,
        "sbc_yontemi": "gider", "baslangic_zarar": 0,
        **SCENARIOS[name],
    }

def build_report():
    share_check = equity_rollforward()
    results = {}
    for name in ("temkinli", "baz", "iyimser"):
        outputs = degerle_v02(inputs_for(name))
        if outputs["durum"] != "gecerli":
            raise ValueError("DCF returned invalid output")
        results[name] = {
            "assumptions": SCENARIOS[name],
            "dcf_share_usd": outputs["hisse_basi_deger"],
            "terminal_share_of_ev": outputs["uc_deger_payi"],
            "warnings": outputs["uyarilar"],
            "annual_cashflows": outputs["tablo"],
            "engine": outputs["motor_surumu"],
        }
    reverse = ters_dcf_v02(inputs_for("baz"), PRICE,
                           lower=-.15, upper=.70, grid_steps=2048)
    return {
        "issuer": "Apple Inc.", "ticker": "AAPL", "cik": "0000320193",
        "study_date": AS_OF, "reference_close_date": "2026-10-20",
        "reference_close_usd": PRICE, "fy2025_revenue_usd": FY2025_REVENUE,
        "fy2025_ebit_usd": FY2025_EBIT,
        "jun2026_approx_net_debt_usd": JUN2026_NET_DEBT,
        "jul2026_shares": JUL2026_SHARES,
        "share_rollforward": share_check,
        "scenarios_are_hypothetical": True,
        "scenario_results": results, "reverse_dcf": reverse,
        "sources": SOURCES,
        "limitations": [
            "FY2025 revenue/EBIT + FY2026 Q3 balance + Jul shares + Oct price have different dates.",
            "FY2026 Q3 facts are known; FY2026 full-year forecasts in this 5Y model are partly retrospective.",
            "WACC, growth, margins, tax and reinvestment are analyst-designed stress assumptions, not consensus.",
            "All marketable securities treated as excess cash; actual operating cash needs may differ.",
            "No projected buybacks/dilution. FCFF is estimated, not CFO minus CapEx.",
            "Reverse DCF is conditional and does not prove all mathematical roots were found.",
        ],
    }

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="output JSON path")
    args = parser.parse_args(argv)
    from pathlib import Path
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_report(), ensure_ascii=False, indent=2,
                                 allow_nan=False), encoding="utf-8")
    print("Wrote:", target)

if __name__ == "__main__":
    main()
