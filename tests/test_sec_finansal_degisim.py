"""Offline SEC change and 9M-YoY tests (synthetic SEC facts only)."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sec_arsiv import canonical_bytes
from sec_finansal_degisim import _load_snapshot, compare_sec_snapshots, main
from test_sec_ttm_crosscheck import fixture, fact, TAGS


CUTOFF = "2026-08-07"
CIK = "320193"


def compare(before=None, after=None, as_of=CUTOFF):
    old = fixture() if before is None else before
    new = fixture() if after is None else after
    return compare_sec_snapshots(old, new, as_of=as_of, expected_cik=CIK)


class ChangeTests(unittest.TestCase):
    def test_identical_snapshots_do_not_claim_changes(self):
        r = compare()
        self.assertTrue(r["identical_snapshots"])
        self.assertEqual(r["snapshot_record_changes"]["total"], 0)
        self.assertEqual(r["snapshot_record_changes"]["events"], [])
        self.assertFalse(r["requires_manual_review"])
        self.assertEqual(r["new_snapshot_9m_yoy"]["status"], "AVAILABLE_9M_YOY")
        self.assertEqual(r["same_period_ttm_reconciliation"]["status"], "SAME_PERIOD_RECONCILED")

    def test_9m_yoy_math_and_margin_pp_are_not_q3_growth(self):
        r = compare()
        obs = r["new_snapshot_9m_yoy"]
        revenue = obs["items"]["revenue"]
        self.assertEqual(revenue["current_ytd9_usd"], 330)
        self.assertEqual(revenue["prior_ytd9_usd"], 295)
        self.assertEqual(revenue["change_usd"], 35)
        self.assertEqual(revenue["change_pct"], 11.8644)
        self.assertEqual(obs["items"]["capex"]["change_pct"], 20)
        self.assertEqual(obs["margin"]["current_operating_margin_pct"], 30)
        self.assertEqual(obs["margin"]["change_percentage_points"], 0.5085)
        self.assertIn("NOT standalone Q3", revenue["note"])

    def test_no_false_quarterly_or_price_target(self):
        r = compare()
        self.assertIsNone(r["price_target"])
        self.assertIsNone(r["forecast"])
        self.assertIsNone(r["investment_recommendation"])
        self.assertIn("9M YoY != quarterly", " ".join(r["limitations"]))

    def test_add_new_10qa_same_period_different_amount_is_flag_not_official_restatement(self):
        raw = fixture()
        raw["facts"]["us-gaap"][TAGS["revenue"]]["units"]["USD"].append(
            fact(350, "2025-09-28", "2026-06-27", "2026-08-03", "10-Q/A", "q26amended"))
        r = compare(after=raw)
        changes = r["snapshot_record_changes"]
        self.assertEqual(changes["total"], 1)
        self.assertEqual(changes["by_kind"], {"NEWER_SOURCE_DIFFERENT_AMOUNT_REVIEW": 1})
        self.assertTrue(r["requires_manual_review"])
        event = changes["events"][0]
        self.assertEqual(event["current"]["form"], "10-Q/A")
        self.assertEqual(event["current"]["accession"], "q26amended")
        self.assertEqual(event["comparable_old_record"]["value_usd"], 330)
        self.assertIn("not automatically a restatement", r["limitations"][0].replace(
            "NOT an issuer-authorized restatement determination", "not automatically a restatement"))
        self.assertEqual(r["same_period_ttm_reconciliation"]["metrics"]["revenue"]["change_usd"], 20)
        self.assertEqual(r["new_snapshot_9m_yoy"]["items"]["revenue"]["current_ytd9_usd"], 350)

    def test_later_filed_amendment_not_seen_as_of_earlier_date(self):
        raw = fixture()
        raw["facts"]["us-gaap"][TAGS["revenue"]]["units"]["USD"].append(
            fact(350, "2025-09-28", "2026-06-27", "2026-08-03", "10-Q/A", "q26amended"))
        r = compare(after=raw, as_of="2026-08-01")
        self.assertFalse(r["identical_snapshots"])
        self.assertEqual(r["snapshot_record_changes"]["total"], 0)
        self.assertFalse(r["requires_manual_review"])
        self.assertEqual(r["same_period_ttm_reconciliation"]["metrics"]["revenue"]["change_usd"], 0)

    def test_same_identity_value_changed_is_not_growth(self):
        raw = fixture()
        raw["facts"]["us-gaap"][TAGS["revenue"]]["units"]["USD"][1]["val"] = 345
        r = compare(after=raw)
        self.assertEqual(r["snapshot_record_changes"]["by_kind"],
                         {"SAME_FILING_IDENTITY_VALUE_CHANGED_REVIEW": 1})
        self.assertTrue(r["requires_manual_review"])
        self.assertEqual(r["same_period_ttm_reconciliation"]["metrics"]["revenue"]["change_usd"], 15)
        self.assertEqual(r["same_period_ttm_reconciliation"]["metrics"]["revenue"]
                         ["classification"], "SAME_PERIOD_ARCHIVE_VALUE_DIFFERENCE_NOT_BUSINESS_GROWTH")

    def test_new_filing_when_older_period_no_same_prior_fact(self):
        raw = fixture()
        raw["facts"]["us-gaap"][TAGS["revenue"]]["units"]["USD"].append(
            fact(90, "2023-09-30", "2024-06-29", "2024-07-31", "10-Q", "q24"))
        r = compare(after=raw)
        self.assertEqual(r["snapshot_record_changes"]["by_kind"], {"FILING_RECORD_ADDED": 1})
        self.assertFalse(r["requires_manual_review"])

    def test_amendment_same_value_is_not_assumed_economic_revision(self):
        raw = fixture()
        raw["facts"]["us-gaap"][TAGS["revenue"]]["units"]["USD"].append(
            fact(330, "2025-09-28", "2026-06-27", "2026-08-03", "10-Q/A", "q26amended"))
        r = compare(after=raw)
        self.assertEqual(r["snapshot_record_changes"]["by_kind"], {"AMENDMENT_RECORD_ADDED": 1})
        self.assertTrue(r["requires_manual_review"])
        self.assertEqual(r["same_period_ttm_reconciliation"]["metrics"]["revenue"]["change_usd"], 0)

    def test_missing_old_observation_flagged_not_assumed_filing_withdrawal(self):
        raw = fixture()
        raw["facts"]["us-gaap"][TAGS["capex"]]["units"]["USD"].pop()
        r = compare(after=raw)
        self.assertEqual(r["snapshot_record_changes"]["by_kind"],
                         {"RECORD_ABSENT_FROM_NEW_SNAPSHOT": 1})
        self.assertTrue(r["requires_manual_review"])
        self.assertEqual(r["new_snapshot_9m_yoy"]["status"], "UNAVAILABLE_TTM_NOT_RECONCILED")

    def test_manual_transcription_is_not_labeled_original_sec(self):
        raw = fixture()
        raw["evidence_notes"] = {
            "status": "MANUAL_TRANSCRIPTION_FROM_OFFICIAL_SEC_FILINGS_NOT_RAW_SEC_COMPANYFACTS"
        }
        r = compare(before=raw, after=raw)
        self.assertTrue(r["old_source_manual_transcription"])
        self.assertTrue(r["new_source_manual_transcription"])
        self.assertTrue(r["requires_manual_review"])
        self.assertIn("MANUALLY_TRANSCRIBED_NOT_RAW_SEC_API", r["review_reasons"])

    def test_wrong_issuer_blocked(self):
        raw = fixture()
        raw["cik"] = 123
        with self.assertRaisesRegex(ValueError, "CIK mismatch"):
            compare(after=raw)

    def test_duplicate_identity_conflicting_values_fails_closed(self):
        raw = fixture()
        facts = raw["facts"]["us-gaap"][TAGS["ebit"]]["units"]["USD"]
        clone = copy.deepcopy(facts[0])
        clone["val"] += 100
        facts.append(clone)
        with self.assertRaisesRegex(ValueError, "conflicting amounts"):
            compare(after=raw)

    def test_same_identity_duplicate_equal_is_deduplicated(self):
        raw = fixture()
        raw["facts"]["us-gaap"][TAGS["ebit"]]["units"]["USD"].append(
            copy.deepcopy(raw["facts"]["us-gaap"][TAGS["ebit"]]["units"]["USD"][0]))
        r = compare(after=raw)
        self.assertEqual(r["snapshot_record_changes"]["total"], 0)

    def test_no_negative_or_zero_base_division_as_growth(self):
        old = fixture()
        new = fixture()
        for raw in (old, new):
            raw["facts"]["us-gaap"][TAGS["cfo"]]["units"]["USD"][2]["val"] = -1
        r = compare(before=old, after=new)
        self.assertEqual(r["new_snapshot_9m_yoy"]["status"], "AVAILABLE_9M_YOY")
        self.assertIsNone(r["new_snapshot_9m_yoy"]["items"]["cfo"]["change_pct"])
        self.assertEqual(r["new_snapshot_9m_yoy"]["items"]["cfo"]["change_usd"], 89)

    def test_period_mismatch_suppresses_false_ttm_growth(self):
        old = fixture()
        new = fixture()
        # A 2026-2027 YTD Q3 period is added but has no matching FY.
        # Simulate the selector pointing at different reported quarters without
        # fabricating an arithmetic series: mock the already audited engine.
        from unittest.mock import patch
        with patch("sec_finansal_degisim._safe_audit") as mock_audit:
            audit = {
                "status": "RECONCILED_CALCULATIONS",
                "primary": {
                    "as_of": CUTOFF,
                    "periods": {"current_9m_end": "2026-06-27", "prior_9m_end": "2025-06-28"},
                    "metrics": {m: {"value_usd": n,
                          "current_ytd9": {"value_usd": n, "end": "2026-06-27",
                               "start": "2025-09-28", "accession": "q26"},
                          "prior_ytd9": {"value_usd": n-1, "end": "2025-06-28",
                               "start": "2024-09-29", "accession": "q25"}}
                                for m,n in (("revenue", 300), ("ebit", 90),
                                            ("cfo", 70), ("capex", 30))}
                },
            }
            another = copy.deepcopy(audit)
            another["primary"]["periods"]["current_9m_end"] = "2027-06-26"
            mock_audit.side_effect = [audit, another]
            r = compare(before=old, after=new)
        self.assertEqual(r["same_period_ttm_reconciliation"]["status"],
                         "DIFFERENT_PERIODS_NO_DIRECT_COMPARISON")
        self.assertEqual(r["same_period_ttm_reconciliation"]["metrics"], {})

    def test_raw_diff_truncation_is_explicit(self):
        raw = fixture()
        tag = TAGS["revenue"]
        # Multiple valid observations with distinct accession IDs.
        for i in range(3):
            raw["facts"]["us-gaap"][tag]["units"]["USD"].append(
                fact(200+i, "2023-09-30", "2024-06-29",
                     "2024-07-31", "10-Q", f"extra{i}"))
        with patch("sec_finansal_degisim.REPORT_LIMIT", 1):
            r = compare(after=raw)
        self.assertEqual(r["snapshot_record_changes"]["total"], 3)
        self.assertEqual(len(r["snapshot_record_changes"]["events"]), 1)
        self.assertEqual(r["snapshot_record_changes"]["events_omitted"], 2)
        self.assertTrue(r["snapshot_record_changes"]["events_truncated"])

    def test_canonical_sha_order_independent(self):
        a = fixture()
        b = json.loads(json.dumps(a, sort_keys=True))
        self.assertEqual(compare(before=a, after=b)["old_snapshot_sha256"],
                         compare(before=a, after=b)["new_snapshot_sha256"])

    def test_hash_named_cache_archive_verified(self):
        with tempfile.TemporaryDirectory() as td:
            raw = fixture()
            blob = canonical_bytes(raw)
            digest = hashlib.sha256(blob).hexdigest()
            path = Path(td) / (digest + ".json")
            path.write_bytes(blob)
            self.assertEqual(_load_snapshot(path, CIK)["cik"], 320193)
            path.write_bytes(canonical_bytes({**raw, "entityName": "different"}))
            with self.assertRaisesRegex(ValueError, "archive filename SHA-256 mismatch"):
                _load_snapshot(path, CIK)

    def test_cli_writes_offline_report(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            src, dst, out = base/"old.json", base/"new.json", base/"report.json"
            src.write_text(json.dumps(fixture()))
            dst.write_text(json.dumps(fixture()))
            self.assertEqual(main(["--old", str(src), "--new", str(dst),
                                   "--cik", CIK, "--as-of", CUTOFF,
                                   "--out", str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())["snapshot_record_changes"]["total"], 0)

    def test_output_cannot_overwrite_input(self):
        with self.assertRaises(SystemExit):
            main(["--old", "raw.json", "--new", "new.json",
                  "--cik", CIK, "--as-of", CUTOFF, "--out", "raw.json"])

    def test_legacy_raw_with_only_annual_can_give_partial(self):
        raw = fixture()
        for metric in TAGS.values():
            raw["facts"]["us-gaap"][metric]["units"]["USD"] = [
                x for x in raw["facts"]["us-gaap"][metric]["units"]["USD"]
                if x["form"] == "10-K"]
        r = compare(before=raw, after=raw)
        self.assertEqual(r["new_snapshot_9m_yoy"]["status"], "UNAVAILABLE_TTM_NOT_RECONCILED")


if __name__ == "__main__":
    unittest.main()
