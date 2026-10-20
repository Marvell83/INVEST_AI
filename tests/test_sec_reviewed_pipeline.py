"""Entirely synthetic SEC data; stored forecasts are not investment advice."""
import copy
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sec_reviewed_pipeline import analyze_and_record, _validate_periods
from tahmin_defteri import TahminDefteri
from test_sec_companyfacts import fixture, fact
from test_sec_v02_bridge import PROPOSAL


class ReviewedPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "forecast.sqlite")
        self.kwargs = dict(raw_companyfacts=fixture(), as_of="2025-03-01",
                           proposal=copy.deepcopy(PROPOSAL),
                           future_period_ends=["2025-12-31", "2026-12-31", "2027-12-31"],
                           db_path=self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_record_three_fiscal_years_and_sources(self):
        result = analyze_and_record(**self.kwargs)
        self.assertEqual(result["forecast_rows"], 9)
        self.assertEqual(result["cik"], "0000000042")
        with TahminDefteri(self.path) as ledger:
            forecasts = ledger.tahminleri_listele()
            self.assertEqual(len(forecasts), 9)
            self.assertEqual({r["metric"] for r in forecasts}, {"revenue", "ebit", "fcff"})
            self.assertEqual({r["target_period"] for r in forecasts},
                             {"FY_END:2025-12-31", "FY_END:2026-12-31", "FY_END:2027-12-31"})
            self.assertEqual({r["company"] for r in forecasts}, {"CIK:0000000042"})
            raw = ledger.db.execute("SELECT assumptions_json,sources_json FROM forecasts LIMIT 1").fetchone()
            self.assertIn("000001-25-000001", raw[1])
            self.assertFalse(json.loads(raw[0])["historical_prediction_verifiable"])

    def test_conflicted_revenue_rejected_without_record(self):
        data = fixture()
        data["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [fact(900)]}}
        with self.assertRaisesRegex(ValueError, "REVENUE_ALIASES_CONFLICT"):
            analyze_and_record(**dict(self.kwargs, raw_companyfacts=data))
        self.assertFalse(os.path.exists(self.path))

    def test_missing_ebit_rejected_without_record(self):
        data = fixture()
        del data["facts"]["us-gaap"]["OperatingIncomeLoss"]
        with self.assertRaisesRegex(ValueError, "LATEST_EBIT_MISSING"):
            analyze_and_record(**dict(self.kwargs, raw_companyfacts=data))
        self.assertFalse(os.path.exists(self.path))

    def test_missing_manual_assumption_rejected(self):
        proposal = copy.deepcopy(PROPOSAL)
        del proposal["assumptions"]["iskonto"]
        with self.assertRaises(ValueError):
            analyze_and_record(**dict(self.kwargs, proposal=proposal))
        self.assertFalse(os.path.exists(self.path))

    def test_fiscal_period_invalid(self):
        with self.assertRaises(ValueError):
            analyze_and_record(**dict(self.kwargs, future_period_ends=["2025-01-01", "2025-02-01", "2025-03-01"]))
        self.assertFalse(os.path.exists(self.path))

    def test_missing_future_periods_rejected(self):
        with self.assertRaises(ValueError):
            _validate_periods(["2025-12-31"], baseline_end="2024-12-31", years=3)

    def test_lookahead_filing_rejected(self):
        with self.assertRaises(ValueError):
            analyze_and_record(**dict(self.kwargs, as_of="2025-01-01"))

    def test_duplicate_forecast_rollback(self):
        analyze_and_record(**self.kwargs)
        with self.assertRaises(sqlite3.IntegrityError):
            analyze_and_record(**self.kwargs)
        with TahminDefteri(self.path) as ledger:
            self.assertEqual(len(ledger.tahminleri_listele()), 9)

    def test_second_write_failure_rolls_back(self):
        original = TahminDefteri.tahmin_kaydet
        count = [0]
        def second_fails(instance, **kwargs):
            count[0] += 1
            if count[0] == 2:
                raise RuntimeError("simulated crash during forecast insert")
            return original(instance, **kwargs)
        with patch.object(TahminDefteri, "tahmin_kaydet", second_fails):
            with self.assertRaises(RuntimeError):
                analyze_and_record(**self.kwargs)
        with TahminDefteri(self.path) as ledger:
            self.assertEqual(len(ledger.tahminleri_listele()), 0)


if __name__ == "__main__":
    unittest.main()
