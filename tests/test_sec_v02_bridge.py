"""Synthetic tests for SEC v0.2 bridge; no real securities included."""
import copy
import unittest
from sec_companyfacts import normalize_companyfacts
from sec_v02_bridge import value_sec_snapshot
from test_sec_companyfacts import fixture

ASSUMPTIONS = dict(yillar=3, buyume=0.1, marj_hedef=0.2,
                   yakinlasma=0.5, satis_sermaye=2,
                   vergi_orani=0.25, iskonto=0.10, uc_buyume=0.02,
                   uc_roic=0.12, hisse=10, net_borc=0)
PROPOSAL = {"scenario": "synthetic base", "assumptions": ASSUMPTIONS,
            "assumption_sources": ["SYNTHETIC research"],
            "share_count_source": "SYNTHETIC share count",
            "net_debt_source": "SYNTHETIC net debt"}

class SECBridgeTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = normalize_companyfacts(fixture(), as_of="2025-03-01")

    def test_values_with_manually_supplied_assumptions(self):
        result = value_sec_snapshot(self.snapshot, PROPOSAL)
        self.assertEqual(result["inputs"]["gelir_0"], 200)
        self.assertAlmostEqual(result["inputs"]["marj_0"], 0.15)
        self.assertEqual(result["valuation"]["durum"], "gecerli")
        self.assertEqual(result["historical_facts"]["revenue"]["filed"], "2025-02-15")

    def test_missing_assumptions_fails(self):
        with self.assertRaisesRegex(ValueError, "missing required"):
            value_sec_snapshot(self.snapshot, dict(PROPOSAL, assumptions={"hisse": 10}))

    def test_no_historical_override(self):
        with self.assertRaisesRegex(ValueError, "historical revenue"):
            value_sec_snapshot(self.snapshot, dict(PROPOSAL, assumptions=dict(ASSUMPTIONS, gelir_0=99)))

    def test_manual_share_count_source_required(self):
        with self.assertRaisesRegex(ValueError, "share_count_source"):
            value_sec_snapshot(self.snapshot, dict(PROPOSAL, share_count_source=""))

    def test_no_late_filing_lookahead(self):
        snapshot = normalize_companyfacts(fixture(), as_of="2025-01-01")
        with self.assertRaises(ValueError):
            value_sec_snapshot(snapshot, PROPOSAL)

    def test_rejects_stale_baseline(self):
        snapshot = copy.deepcopy(self.snapshot)
        row = snapshot["annual"][0]
        row["period_end"] = "2026-01-01"
        snapshot["annual"].insert(0, {"period_end": "2026-12-31", "metrics": {"revenue": None, "ebit": None}})
        with self.assertRaises(ValueError):
            value_sec_snapshot(snapshot, PROPOSAL)

    def test_wrong_snapshot_version(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            value_sec_snapshot(dict(self.snapshot, schema_version="unsupported"), PROPOSAL)

if __name__ == "__main__":
    unittest.main()
