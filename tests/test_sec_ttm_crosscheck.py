"""Offline regression tests for the two-engine SEC TTM provenance audit."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sec_ttm import compute_ttm
from sec_ttm_crosscheck import audit_ttm, main

TAGS = {
    "revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "ebit": "OperatingIncomeLoss",
    "cfo": "NetCashProvidedByUsedInOperatingActivities",
    "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
}
AMOUNTS = {
    "revenue": (400, 330, 295),
    "ebit": (120, 99, 87),
    "cfo": (110, 88, 70),
    "capex": (20, 18, 15),
}


def fact(value, start, end, filed, form, accession):
    return {
        "val": value, "start": start, "end": end, "filed": filed,
        "form": form, "fp": "FY" if form.startswith("10-K") else "Q3",
        "accn": accession,
    }


def fixture():
    result = {"cik": 320193, "entityName": "SYNTHETIC TEST ISSUER",
              "facts": {"us-gaap": {}}}
    for metric, tag in TAGS.items():
        fy, now, prior = AMOUNTS[metric]
        result["facts"]["us-gaap"][tag] = {"units": {"USD": [
            fact(fy, "2024-09-29", "2025-09-27", "2025-10-30", "10-K", "fy25"),
            fact(now, "2025-09-28", "2026-06-27", "2026-07-30", "10-Q", "q26"),
            fact(prior, "2024-09-29", "2025-06-28", "2025-07-31", "10-Q", "q25"),
        ]}}
    return result


class TTMDualEngineAuditTests(unittest.TestCase):
    def test_matching_engines_and_complete_source_triples(self):
        result = audit_ttm(fixture(), as_of="2026-08-01", expected_cik="0000320193")
        self.assertEqual(result["status"], "RECONCILED_CALCULATIONS")
        self.assertTrue(result["historical_baseline_crosschecked"])
        self.assertFalse(result["automatic_dcf_enabled"])
        self.assertEqual(result["discrepancies"], [])
        self.assertEqual(result["primary"]["metrics"]["revenue"]["value_usd"], 435)
        self.assertEqual(result["secondary"]["metrics"]["revenue"]["value_usd"], 435)
        self.assertEqual(result["primary"]["metrics"]["capex"]["value_usd"], 23)
        self.assertFalse(result["primary"]["cfo_less_capex_is_fcff"])

    def test_earlier_cutoff_blocks_future_filing(self):
        result = audit_ttm(fixture(), as_of="2026-07-01")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["discrepancies"][0]["reason"], "PRIMARY_CORE_INCOMPLETE")

    def test_missing_capex_is_not_assumed_zero(self):
        raw = fixture()
        raw["facts"]["us-gaap"].pop(TAGS["capex"])
        result = audit_ttm(raw, as_of="2026-08-01")
        self.assertFalse(result["historical_baseline_crosschecked"])
        self.assertEqual(result["primary"]["metrics"]["capex"]["status"],
                         "INCOMPLETE_SOURCE_TRIPLE")

    def test_conflicting_revenue_alias_blocks(self):
        raw = fixture()
        raw["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [
            fact(600, "2024-09-29", "2025-09-27", "2025-10-30", "10-K", "fy25")
        ]}}
        result = audit_ttm(raw, as_of="2026-08-01")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["primary"]["metrics"]["revenue"]["status"],
                         "INCOMPLETE_SOURCE_TRIPLE")

    def test_revenue_concept_change_requires_review(self):
        raw = fixture()
        recent = raw["facts"]["us-gaap"][TAGS["revenue"]]["units"]["USD"].pop(1)
        raw["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [recent]}}
        result = audit_ttm(raw, as_of="2026-08-01")
        self.assertEqual(result["primary"]["metrics"]["revenue"]["status"],
                         "REVENUE_CONCEPT_CHANGED")
        self.assertFalse(result["historical_baseline_crosschecked"])

    def test_currency_mismatch_blocks(self):
        raw = fixture()
        raw["facts"]["us-gaap"][TAGS["cfo"]]["units"] = {"EUR": []}
        self.assertEqual(audit_ttm(raw, as_of="2026-08-01")["status"], "BLOCKED")

    def test_later_amendment_visible_only_after_filing(self):
        raw = fixture()
        raw["facts"]["us-gaap"][TAGS["ebit"]]["units"]["USD"].append(
            fact(900, "2025-09-28", "2026-06-27", "2026-09-30", "10-Q/A", "q26a"))
        earlier = audit_ttm(raw, as_of="2026-08-01")
        later = audit_ttm(raw, as_of="2026-10-01")
        self.assertTrue(earlier["historical_baseline_crosschecked"])
        self.assertTrue(later["historical_baseline_crosschecked"])
        self.assertEqual(earlier["primary"]["metrics"]["ebit"]["value_usd"], 132)
        self.assertEqual(later["primary"]["metrics"]["ebit"]["value_usd"], 933)

    def test_secondary_rejection_blocks_report(self):
        with patch("sec_ttm_crosscheck.compute_ttm", side_effect=ValueError("ambiguous")):
            result = audit_ttm(fixture(), as_of="2026-08-01")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["discrepancies"][0]["reason"], "SECONDARY_ENGINE_REJECTED")

    def test_different_secondary_ttm_is_detected(self):
        fake = compute_ttm(fixture(), as_of="2026-08-01",
                           current_ytd_end="2026-06-27", prior_fy_end="2025-09-27")
        fake["metrics"]["revenue"]["value_usd"] += 1
        with patch("sec_ttm_crosscheck.compute_ttm", return_value=fake):
            result = audit_ttm(fixture(), as_of="2026-08-01")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("TTM_VALUE_MISMATCH", [x["reason"] for x in result["discrepancies"]])

    def test_provenance_change_detected_even_with_matching_total(self):
        fake = compute_ttm(fixture(), as_of="2026-08-01",
                           current_ytd_end="2026-06-27", prior_fy_end="2025-09-27")
        fake["metrics"]["ebit"]["components"]["current_ytd"]["accession"] = "different"
        with patch("sec_ttm_crosscheck.compute_ttm", return_value=fake):
            result = audit_ttm(fixture(), as_of="2026-08-01")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("FILING_PROVENANCE_MISMATCH",
                      [x["reason"] for x in result["discrepancies"]])

    def test_cik_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "CIK differs"):
            audit_ttm(fixture(), as_of="2026-08-01", expected_cik="123")

    def test_canonical_hash_does_not_depend_on_key_order(self):
        raw = fixture()
        reordered = json.loads(json.dumps(raw, sort_keys=True))
        a = audit_ttm(raw, as_of="2026-08-01")
        b = audit_ttm(reordered, as_of="2026-08-01")
        self.assertEqual(a["canonical_json_sha256"], b["canonical_json_sha256"])

    def test_offline_cli_writes_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as folder:
            infile, outfile = (Path(folder) / name for name in ("raw.json", "audit.json"))
            infile.write_text(json.dumps(fixture()), encoding="utf-8")
            code = main(["--cik", "320193", "--as-of", "2026-08-01",
                         "--companyfacts", str(infile), "--out", str(outfile)])
            self.assertEqual(code, 0)
            result = json.loads(outfile.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "RECONCILED_CALCULATIONS")
            self.assertEqual(result["input_mode"], "offline_file")

    def test_download_cli_is_mocked_and_saves_reproducible_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            outfile = Path(folder) / "audit.json"
            snapshot = Path(folder) / "snapshot.json"
            with patch("sec_ttm_crosscheck.download_companyfacts", return_value=fixture()) as fetch:
                code = main(["--cik", "320193", "--as-of", "2026-08-01",
                             "--download", "--snapshot-out", str(snapshot),
                             "--out", str(outfile)])
            self.assertEqual(code, 0)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(json.loads(snapshot.read_text())["cik"], 320193)
            result = json.loads(outfile.read_text())
            self.assertEqual(result["input_mode"], "sec_direct_download")
            self.assertIn("downloaded_at_utc", result)

    def test_snapshot_requires_download(self):
        with self.assertRaises(SystemExit):
            main(["--cik", "320193", "--as-of", "2026-08-01",
                  "--companyfacts", "raw.json", "--snapshot-out", "raw-copy.json",
                  "--out", "audit.json"])

    def test_invalid_source_mode_rejected(self):
        with self.assertRaisesRegex(ValueError, "source mode"):
            audit_ttm(fixture(), as_of="2026-08-01", source_mode="guessed")


if __name__ == "__main__":
    unittest.main()
