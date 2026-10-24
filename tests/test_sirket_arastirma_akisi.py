"""Offline tests for generic SEC company research, not user positions or trades."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sirket_arastirma_akisi import build_company_research, main, render_company_research
try:
    from test_quality_layers import fixture as quality_fixture, issuance
except ImportError:
    from tests.test_quality_layers import fixture as quality_fixture, issuance


AS_OF = "2025-10-25"


def annual(value, start, end, *, form="10-K", fp="FY", filed="2025-02-15",
           accn="000042-2025-001"):
    return dict(val=value, start=start, end=end, form=form, fp=fp,
                filed=filed, accn=accn)


def with_ttm():
    """Synthetic issuer with 2024 FY and 2025 Q3 9M, plus Piotroski history."""
    raw = quality_fixture()
    facts = raw["facts"]["us-gaap"]
    # Q3 data for the existing annual revenue and operating cash-flow tags.
    revenue = facts["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"]
    cfo = facts["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"]
    new = lambda val, start, end, filed, accn: annual(
        val, start, end, form="10-Q", fp="Q3", filed=filed, accn=accn)
    revenue.extend([
        new(1300, "2025-01-01", "2025-09-30", "2025-10-20", "q2025"),
        new(1100, "2024-01-01", "2024-09-30", "2024-11-01", "q2024"),
    ])
    cfo.extend([
        new(130, "2025-01-01", "2025-09-30", "2025-10-20", "q2025"),
        new(110, "2024-01-01", "2024-09-30", "2024-11-01", "q2024"),
    ])
    facts["OperatingIncomeLoss"] = {"units": {"USD": [
        annual(300, "2024-01-01", "2024-12-31"),
        new(250, "2025-01-01", "2025-09-30", "2025-10-20", "q2025"),
        new(200, "2024-01-01", "2024-09-30", "2024-11-01", "q2024"),
    ]}}
    facts["PaymentsToAcquirePropertyPlantAndEquipment"] = {"units": {"USD": [
        annual(25, "2024-01-01", "2024-12-31"),
        new(20, "2025-01-01", "2025-09-30", "2025-10-20", "q2025"),
        new(15, "2024-01-01", "2024-09-30", "2024-11-01", "q2024"),
    ]}}
    return raw


def run(raw=None, **kwargs):
    return build_company_research(
        with_ttm() if raw is None else raw, expected_cik=42,
        as_of=kwargs.pop("as_of", AS_OF),
        sector=kwargs.pop("sector", "non_financial"), **kwargs)


class CompanyResearchPipelineTests(unittest.TestCase):
    def test_full_ttm_while_unreviewed_equity_issuance_is_unknown(self):
        r = run()
        self.assertEqual(r["annual_source_audit"]["status"], "READY_FOR_MANUAL_ASSUMPTIONS")
        self.assertEqual(r["ttm_crosscheck"]["status"], "RECONCILED_CALCULATIONS")
        self.assertEqual(r["quality"]["piotroski"]["score_range"], [8, 9])
        self.assertIsNone(r["quality"]["piotroski"]["score"])
        self.assertEqual(r["coverage_status"], "PARTIAL_OR_REVIEW_REQUIRED")
        self.assertIn("PIOTROSKI_INCOMPLETE:8/9", r["research_gaps"])
        self.assertEqual(r["ttm_crosscheck"]["primary"]["metrics"]["revenue"]["value_usd"], 1700)
        self.assertEqual(r["ttm_crosscheck"]["primary"]["metrics"]["ebit"]["value_usd"], 350)
        self.assertEqual(r["ttm_crosscheck"]["primary"]["metrics"]["cfo"]["value_usd"], 160)
        self.assertEqual(r["ttm_crosscheck"]["primary"]["metrics"]["capex"]["value_usd"], 30)
        self.assertFalse(r["forecast_created"])
        self.assertIsNone(r["actual_price"])
        self.assertIsNone(r["dcf"])
        self.assertIsNone(r["investment_recommendation"])
        self.assertIsNone(r["combined_investment_score"])

    def test_fully_calculated_status_not_a_source_authenticity_claim(self):
        r = run(equity_offering_evidence=issuance())
        self.assertEqual(r["quality"]["piotroski"]["score"], 9)
        # The offline snapshot cannot be promoted to independently verified.
        self.assertEqual(r["coverage_status"], "PARTIAL_OR_REVIEW_REQUIRED")
        self.assertIn("OFFLINE_DATA_AUTHENTICITY_NOT_INDEPENDENTLY_VERIFIED", r["research_gaps"])
        self.assertFalse(r["source"]["origin_verified_independently"])

    def test_download_flag_not_mistaken_for_independent_verification(self):
        r = run(input_mode="sec_direct_download", equity_offering_evidence=issuance())
        self.assertEqual(r["coverage_status"], "ELIGIBLE_COMPONENT_MATH_COMPLETE")
        self.assertFalse(r["source"]["origin_verified_independently"])
        self.assertEqual(r["source"]["mode"], "sec_direct_download")

    def test_earlier_cutoff_does_not_leak_future_quarter(self):
        r = run(as_of="2025-10-01")
        self.assertNotEqual(r["ttm_crosscheck"]["status"], "RECONCILED_CALCULATIONS")
        self.assertIn("TTM_NOT_RECONCILED:", " ".join(r["research_gaps"]))
        self.assertNotIn("1700", render_company_research(r))

    def test_missing_capex_blocks_ttm_but_keeps_piotroski(self):
        raw = with_ttm()
        del raw["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]
        r = run(raw)
        self.assertEqual(r["ttm_crosscheck"]["status"], "BLOCKED")
        self.assertEqual(r["quality"]["piotroski"]["known_count"], 8)
        self.assertEqual(r["ttm_crosscheck"]["primary"]["metrics"]["capex"]["value_usd"], None)
        self.assertIn("mutabakat bekliyor", render_company_research(r))

    def test_conflicting_revenue_alias_retains_warning_and_no_false_ttm(self):
        raw = with_ttm()
        raw["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [
            annual(3000, "2024-01-01", "2024-12-31")
        ]}}
        r = run(raw)
        self.assertEqual(r["annual_source_audit"]["status"], "REVENUE_ALIASES_CONFLICT")
        self.assertNotEqual(r["ttm_crosscheck"]["status"], "RECONCILED_CALCULATIONS")
        self.assertTrue(any("ANNUAL_SOURCE_REVIEW_REQUIRED" in g for g in r["research_gaps"]))

    def test_no_annual_facts_yields_partial_not_fabricated_zero(self):
        raw = {"cik": 42, "entityName": "No filings", "facts": {"us-gaap": {}}}
        r = run(raw)
        self.assertEqual(r["ttm_crosscheck"]["status"], "UNAVAILABLE_NO_ELIGIBLE_ANNUAL_DATA")
        self.assertEqual(r["annual_source_audit"]["status"], "NO_ELIGIBLE_USGAAP_ANNUAL_FACTS")
        self.assertIsNone(r["quality"]["piotroski"]["score"])
        self.assertIsNone(r["actual_price"])

    def test_unknown_and_financial_sectors_never_get_fscore(self):
        for sector in ("financial", "unknown"):
            with self.subTest(sector=sector):
                r = run(sector=sector)
                self.assertIsNone(r["quality"]["piotroski"]["score"])
                self.assertIn("SECTOR_SPECIFIC_PIOTROSKI_UNAVAILABLE", r["research_gaps"])

    def test_wrong_cik_rejected_before_computation(self):
        raw = with_ttm()
        raw["cik"] = 43
        with self.assertRaisesRegex(ValueError, "CIK differs"):
            run(raw)

    def test_missing_ratings_database_does_not_create_it(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "does_not_exist.sqlite"
            with self.assertRaisesRegex(ValueError, "does not exist"):
                run(credit_db=str(dest))
            self.assertFalse(dest.exists())

    def test_expected_fiscal_end_is_hard_guard(self):
        with self.assertRaisesRegex(ValueError, "expected_fiscal_end"):
            run(expected_fiscal_end="2025-12-31")
        self.assertEqual(run(expected_fiscal_end="2024-12-31")["annual_source_audit"]["latest_any_fy_end"],
                         "2024-12-31")

    def test_manual_data_is_explicitly_marked(self):
        raw = with_ttm()
        raw["evidence_notes"] = {"status": "MANUAL_TRANSCRIPTION_NOT_RAW_SEC"}
        r = run(raw, input_mode="sec_direct_download")
        self.assertTrue(r["source"]["manually_transcribed_source"])
        self.assertIn("INPUT_IS_MANUAL_TRANSCRIPTION_NOT_RAW_SEC_DOWNLOAD", r["research_gaps"])

    def test_html_escapes_company_and_source_text(self):
        raw = with_ttm()
        raw["entityName"] = "<img src=x onerror=alert(9)>"
        r = run(raw)
        page = render_company_research(r)
        self.assertNotIn("<img src=x onerror", page)
        self.assertIn("&lt;img src=x", page)
        self.assertIn("SEC kaynak kapsama denetimi", page)
        self.assertIn("TTM — kaynakları karşılaştırılmış finansallar", page)
        self.assertIn("SHA-256", page)
        self.assertNotIn("<script", page)

    def test_input_not_mutated(self):
        raw = with_ttm()
        orig = copy.deepcopy(raw)
        run(raw)
        self.assertEqual(raw, orig)

    def test_cli_roundtrip_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "raw.json"
            output = base / "report.json"
            page = base / "report.html"
            source.write_text(json.dumps(with_ttm()), encoding="utf-8")
            main(["--cik", "42", "--as-of", AS_OF, "--sector", "non_financial",
                  "--companyfacts", str(source), "--out-json", str(output),
                  "--out-html", str(page)])
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["ttm_crosscheck"]["status"], "RECONCILED_CALCULATIONS")
            self.assertTrue(page.read_text(encoding="utf-8").startswith("<!doctype html>"))

    def test_cli_download_mock_requires_snapshot_and_saves(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            snapshot, out, page = (base / x for x in ("snapshot.json", "report.json", "report.html"))
            with patch("sirket_arastirma_akisi.download_companyfacts", return_value=with_ttm()) as fetch:
                main(["--cik", "42", "--as-of", AS_OF, "--sector", "non_financial",
                      "--download", "--snapshot-out", str(snapshot), "--out-json",
                      str(out), "--out-html", str(page)])
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(json.loads(snapshot.read_text())["cik"], 42)
            self.assertEqual(json.loads(out.read_text())["source"]["mode"], "sec_direct_download")
            self.assertTrue(page.exists())

    def test_cli_rejects_input_output_path_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "in.json"
            source.write_text(json.dumps(with_ttm()), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["--cik", "42", "--as-of", AS_OF, "--sector", "unknown",
                      "--companyfacts", str(source), "--out-json", str(source),
                      "--out-html", str(Path(temp) / "out.html")])

    def test_future_source_filing_does_not_enter_ttm(self):
        raw = with_ttm()
        for tag in ("OperatingIncomeLoss", "PaymentsToAcquirePropertyPlantAndEquipment"):
            raw["facts"]["us-gaap"][tag]["units"]["USD"][1]["filed"] = "2025-11-01"
        r = run(raw)
        self.assertNotEqual(r["ttm_crosscheck"]["status"], "RECONCILED_CALCULATIONS")
        self.assertIn("mutabakat bekliyor", render_company_research(r))

    def test_documented_apple_transcription_stays_explicitly_manual(self):
        sample = (Path(__file__).resolve().parent.parent /
                  "ornekler/apple_ttm_evidence_2026-10-21.json")
        raw = json.loads(sample.read_text(encoding="utf-8"))
        r = build_company_research(
            raw, expected_cik=320193, as_of="2026-10-21",
            sector="non_financial")
        self.assertEqual(r["ttm_crosscheck"]["status"], "RECONCILED_CALCULATIONS")
        self.assertEqual(r["ttm_crosscheck"]["primary"]["metrics"]["revenue"]["value_usd"],
                         466_823_000_000)
        self.assertTrue(r["source"]["manually_transcribed_source"])
        self.assertIn("INPUT_IS_MANUAL_TRANSCRIPTION_NOT_RAW_SEC_DOWNLOAD", r["research_gaps"])
        self.assertIsNone(r["dcf"])

    def test_invalid_input_shape_rejected(self):
        with self.assertRaisesRegex(ValueError, "raw SEC"):
            run({"cik": 42, "facts": None})


if __name__ == "__main__":
    unittest.main()
