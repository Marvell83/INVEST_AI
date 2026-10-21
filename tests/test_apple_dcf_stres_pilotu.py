"""Synthetic/deterministic model integration tests; not investment outcomes."""
import math
import unittest

from ornekler.apple_dcf_stres_pilotu_2026_10 import (
    SOURCES, PRICE, SCENARIOS, JUN2026_NET_DEBT, equity_rollforward,
    inputs_for, build_report,
)
from degerleme_v02 import degerle_v02

class ApplePilotTests(unittest.TestCase):
    def test_share_bridge(self):
        r=equity_rollforward()
        self.assertEqual(r["beginning_000"]-r["repurchased_000"]+
                         r["issued_net_employee_tax_000"],r["ending_000"])
        self.assertIsNone(r["piotroski_issuance_score"])

    def test_share_policy_is_not_misrepresented(self):
        r=equity_rollforward()
        self.assertFalse(r["any_new_shares_absent"])
        self.assertTrue(r["outstanding_share_count_did_not_increase"])

    def test_net_debt_sign_and_amount(self):
        self.assertEqual(JUN2026_NET_DEBT, -62_173_000_000)

    def test_three_scenarios_separate(self):
        self.assertEqual(set(SCENARIOS), {"temkinli","baz","iyimser"})
        r=build_report()
        self.assertEqual(set(r["scenario_results"]),set(SCENARIOS))
        self.assertTrue(r["scenarios_are_hypothetical"])

    def test_dcf_base_positive_and_finite(self):
        result=degerle_v02(inputs_for("baz"))
        self.assertEqual(result["durum"],"gecerli")
        self.assertTrue(math.isfinite(result["hisse_basi_deger"]))
        self.assertGreater(result["hisse_basi_deger"],0)

    def test_reverse_dcf_residual_and_incomplete_guarantee(self):
        r=build_report()["reverse_dcf"]
        self.assertFalse(r["tum_kokler_bulundu_garantisi"])
        if r["dogrulanan_kokler"]:
            self.assertLess(abs(r["dogrulanan_kokler"][0]["fiyat_farki"]), 1e-4)

    def test_known_sources_and_market_date(self):
        r=build_report()
        self.assertEqual(r["reference_close_date"],"2026-10-20")
        self.assertEqual(r["reference_close_usd"],PRICE)
        self.assertTrue(all(u.startswith("https://") for u in SOURCES.values()))
        self.assertEqual(r["study_date"],"2026-10-21")

    def test_bad_scenario_rejected(self):
        with self.assertRaises(ValueError):
            inputs_for("not_a_scenario")

if __name__ == "__main__":
    unittest.main()
