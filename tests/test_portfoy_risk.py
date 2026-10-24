"""Synthetic portfolio audit tests. Quantities and prices are NOT user holdings."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from portfoy_risk import VERSION, analyze_portfolio, main


def fixture():
    specs = [
        ("NVDA", "2", 200, 190, "semiconductors", ["ai_chips", "ai_infrastructure"]),
        ("TSM", "1", 400, 350, "semiconductors", ["ai_chips"]),
        ("ASML", "0.25", 1600, 1500, "semiconductor_equipment", ["ai_chips"]),
        ("VRT", "2", 200, 175, "datacenter_equipment", ["ai_infrastructure"]),
        ("STRL", "1", 350, 300, "construction", ["ai_infrastructure"]),
        ("VST", "3", 140, 150, "electric_power", ["ai_energy"]),
        ("RDDT", "2", 150, 125, "internet", ["adtech"]),
        ("LLY", "0.25", 1200, 1050, "pharma", ["healthcare"]),
    ]
    positions = [
        {"ticker": ticker, "quantity": qty, "price_usd": price,
         "cost_per_share_usd": cost, "price_date": "2026-10-23",
         "price_source": "SYNTHETIC TEST", "instrument_type": "equity",
         "sector": sector, "themes": tags}
        for ticker, qty, price, cost, sector, tags in specs
    ]
    return {
        "schema_version": VERSION, "base_currency": "USD", "as_of": "2026-10-24",
        "cash_usd": 30, "positions": positions,
        "theme_unions": {"ai_connected": ["ai_chips", "ai_infrastructure", "ai_energy"]},
        "fx_usdtry": {"rate": 49.6, "date": "2026-10-23"},
        "scenarios": [{
            "name": "ai_capex_slowdown",
            "horizon": "12 months",
            "rationale": "Purely hypothetical: not a forecast",
            "shocks_pct": {"NVDA": -30, "TSM": -25, "ASML": -20,
                           "VRT": -40, "STRL": -35, "VST": -20,
                           "RDDT": -10, "LLY": 5},
        }],
    }


class PortfolioRiskTests(unittest.TestCase):
    def test_weights_fractional_positions_and_cash(self):
        r = analyze_portfolio(fixture())
        self.assertEqual(r["total_market_value_usd"], 3000)
        self.assertEqual(r["invested_market_value_usd"], 2970)
        self.assertEqual(r["cash_weight_pct"], 1)
        self.assertEqual(len(r["positions"]), 8)
        values = {x["ticker"]: x for x in r["positions"]}
        self.assertEqual(values["ASML"]["market_value_usd"], 400)
        self.assertEqual(values["ASML"]["quantity"], "0.25")
        self.assertAlmostEqual(sum(x["weight_total_pct"] for x in r["positions"]) +
                               r["cash_weight_pct"], 100, places=2)
        self.assertTrue(r["known_cost_basis_for_all_positions"])

    def test_usd_pnl_known_and_no_fx_pnl(self):
        r = analyze_portfolio(fixture())
        self.assertEqual(r["unrealized_pnl_usd"], 252.5)
        self.assertEqual(r["fx_usdtry"]["total_market_value_try"], 148800)
        self.assertIn("not calculated", r["fx_usdtry"]["notice"])
        self.assertNotIn("unrealized_pnl_try", r)

    def test_theme_union_deduplicates_overlaps(self):
        r = analyze_portfolio(fixture())
        u = r["theme_unions"][0]
        self.assertEqual(u["label"], "ai_connected")
        self.assertEqual(u["market_value_usd"], 2370)
        self.assertEqual(u["weight_total_pct"], 79)
        self.assertEqual(len(u["tickers"]), 6)
        self.assertEqual(r["theme_coverage_pct_of_invested"], 100)
        self.assertGreater(sum(x["market_value_usd"] for x in r["theme_exposures"]), 2970)

    def test_sector_allocations_complete_when_labeled(self):
        r = analyze_portfolio(fixture())
        self.assertEqual(sum(x["market_value_usd"] for x in r["sector_allocation"]), 2970)
        self.assertAlmostEqual(sum(x["weight_invested_pct"] for x in r["sector_allocation"]), 100, places=2)

    def test_hhi_and_top_three_are_invested_only(self):
        r = analyze_portfolio(fixture())
        self.assertGreater(r["hhi_invested"], 1 / 8)
        self.assertLess(r["effective_number_of_positions"], 8)
        self.assertAlmostEqual(r["largest_holding_pct_of_invested"], 420 / 2970 * 100, places=3)
        self.assertAlmostEqual(r["top_three_pct_of_invested"], 1220 / 2970 * 100, places=3)

    def test_scenario_uses_explicit_shocks_and_preserves_cash(self):
        r = analyze_portfolio(fixture())
        s = r["scenarios"][0]
        self.assertEqual(s["cash_unchanged_usd"], 30)
        self.assertEqual(s["assumption_type"], "user_supplied_hypothetical_not_a_forecast")
        expected = (-120 - 100 - 80 - 160 - 122.5 - 84 - 30 + 15)
        self.assertEqual(s["impact_usd"], expected)
        self.assertEqual(s["post_stress_value_usd"], 3000 + expected)
        self.assertAlmostEqual(s["portfolio_return_pct"], expected / 3000 * 100, places=3)

    def test_shocks_must_cover_all_holdings(self):
        d = fixture()
        del d["scenarios"][0]["shocks_pct"]["LLY"]
        with self.assertRaisesRegex(ValueError, "EVERY position"):
            analyze_portfolio(d)

    def test_shocks_must_not_contain_unknown_symbols(self):
        d = fixture()
        d["scenarios"][0]["shocks_pct"]["AAPL"] = 0
        with self.assertRaisesRegex(ValueError, "EVERY position"):
            analyze_portfolio(d)

    def test_no_price_after_cutoff(self):
        d = fixture()
        d["positions"][0]["price_date"] = "2026-10-25"
        with self.assertRaisesRegex(ValueError, "later than research cutoff"):
            analyze_portfolio(d)

    def test_old_price_warning(self):
        d = fixture()
        d["positions"][0]["price_date"] = "2026-10-12"
        r = analyze_portfolio(d)
        self.assertTrue(any("NVDA: price is 12 days old" in x for x in r["warnings"]))

    def test_zero_and_negative_and_nonfinite_input_rejected(self):
        for value in (0, -1, float("nan"), True, "Infinity"):
            with self.subTest(value=value):
                d = fixture()
                d["positions"][0]["quantity"] = value
                with self.assertRaises(ValueError):
                    analyze_portfolio(d)

    def test_missing_cost_causes_unknown_portfolio_pnl(self):
        d = fixture()
        del d["positions"][0]["cost_per_share_usd"]
        r = analyze_portfolio(d)
        self.assertIsNone(r["unrealized_pnl_usd"])
        self.assertFalse(r["known_cost_basis_for_all_positions"])
        nvda = next(x for x in r["positions"] if x["ticker"] == "NVDA")
        self.assertIsNone(nvda["unrealized_pnl_usd"])
        self.assertEqual(nvda["market_value_usd"], 400)

    def test_zero_cost_does_not_infer_infinite_return(self):
        d = fixture()
        d["positions"][0]["cost_per_share_usd"] = 0
        r = analyze_portfolio(d)
        nvda = next(x for x in r["positions"] if x["ticker"] == "NVDA")
        self.assertIsNone(nvda["unrealized_return_pct"])

    def test_duplicate_symbol_rejected(self):
        d = fixture()
        d["positions"].append(copy.deepcopy(d["positions"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate ticker"):
            analyze_portfolio(d)

    def test_future_fx_quote_rejected(self):
        d = fixture()
        d["fx_usdtry"]["date"] = "2026-10-25"
        with self.assertRaisesRegex(ValueError, "later than cutoff"):
            analyze_portfolio(d)

    def test_fund_no_lookthrough(self):
        d = fixture()
        d["positions"][0]["instrument_type"] = "fund"
        r = analyze_portfolio(d)
        self.assertTrue(any("not decomposed" in x for x in r["warnings"]))

    def test_unclassified_theme_is_not_assumed_zero_risk(self):
        d = fixture()
        del d["positions"][0]["themes"]
        r = analyze_portfolio(d)
        self.assertLess(r["theme_coverage_pct_of_invested"], 100)
        self.assertTrue(any("thematic classification not provided" in x for x in r["warnings"]))

    def test_unsupported_currency_rejected(self):
        d = fixture()
        d["base_currency"] = "TRY"
        with self.assertRaisesRegex(ValueError, "only USD"):
            analyze_portfolio(d)

    def test_negative_hundred_percent_is_allowed_but_not_worse(self):
        d = fixture()
        d["scenarios"][0]["shocks_pct"]["NVDA"] = -100
        self.assertIn("NVDA", [p["ticker"] for p in analyze_portfolio(d)["scenarios"][0]["by_position"]])
        d["scenarios"][0]["shocks_pct"]["NVDA"] = -101
        with self.assertRaisesRegex(ValueError, ">= -100%"):
            analyze_portfolio(d)

    def test_double_count_union_not_summed(self):
        d = fixture()
        d["positions"][0]["themes"].append("ai_energy")
        r = analyze_portfolio(d)
        self.assertEqual(r["theme_unions"][0]["market_value_usd"], 2370)

    def test_invalid_unions_rejected(self):
        d = fixture()
        d["theme_unions"]["wrong"] = ["ai_chips", "ai_chips"]
        with self.assertRaisesRegex(ValueError, "unique"):
            analyze_portfolio(d)

    def test_union_with_unknown_tag_fails_closed(self):
        d = fixture()
        d["theme_unions"]["ai_connected"].append("ai_typo")
        with self.assertRaisesRegex(ValueError, "unknown theme tag"):
            analyze_portfolio(d)

    def test_malformed_scenario_shock_is_cleanly_rejected(self):
        d = fixture()
        d["scenarios"][0]["shocks_pct"]["NVDA"] = "not a number"
        with self.assertRaisesRegex(ValueError, "invalid scenario shock"):
            analyze_portfolio(d)

    def test_no_mutation_of_inputs(self):
        d = fixture()
        original = copy.deepcopy(d)
        analyze_portfolio(d)
        self.assertEqual(d, original)

    def test_cli_generates_offline_json(self):
        with tempfile.TemporaryDirectory() as td:
            src, dest = Path(td) / "portfolio.json", Path(td) / "audit.json"
            src.write_text(json.dumps(fixture()), encoding="utf-8")
            main(["--portfolio", str(src), "--out", str(dest)])
            r = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(r["status"], "ANALYSIS_FROM_USER_INPUTS")
            self.assertEqual(r["theme_unions"][0]["market_value_usd"], 2370)


if __name__ == "__main__":
    unittest.main()
