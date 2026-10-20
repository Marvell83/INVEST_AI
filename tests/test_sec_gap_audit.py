"""Synthetic fixtures only: missing SEC concepts and revenue label ambiguity."""
import gzip
import json
import pathlib
import tempfile
import unittest
import zipfile

from sec_gap_audit import audit_company, analyze_zip, export_report
from test_sec_companyfacts import fixture, fact

AS_OF = "2025-03-01"


class GapAuditTests(unittest.TestCase):
    def test_ready_baseline(self):
        self.assertEqual(audit_company(fixture(), as_of=AS_OF)["status"],
                         "READY_FOR_MANUAL_ASSUMPTIONS")

    def test_missing_operating_income_no_ebit_guess(self):
        company = fixture()
        del company["facts"]["us-gaap"]["OperatingIncomeLoss"]
        self.assertEqual(audit_company(company, as_of=AS_OF)["status"],
                         "LATEST_EBIT_MISSING")

    def test_conflicting_revenue_tags_flagged(self):
        company = fixture()
        company["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [fact(900)]}}
        result = audit_company(company, as_of=AS_OF)
        self.assertEqual(result["status"], "REVENUE_ALIASES_CONFLICT")
        self.assertEqual(len(result["revenue_alias_disagreements"]), 2)

    def test_similar_revenue_aliases_allowed(self):
        company = fixture()
        company["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [fact(201)]}}
        self.assertEqual(audit_company(company, as_of=AS_OF)["status"],
                         "READY_FOR_MANUAL_ASSUMPTIONS")

    def test_wrong_currency_not_used(self):
        company = fixture()
        company["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"] = {"EUR": [fact(30)]}
        self.assertEqual(audit_company(company, as_of=AS_OF)["status"],
                         "LATEST_EBIT_MISSING")

    def test_no_future_filing_leak(self):
        self.assertEqual(audit_company(fixture(), as_of="2025-01-01")["status"],
                         "NO_ELIGIBLE_USGAAP_ANNUAL_FACTS")

    def test_zero_revenue_rejected(self):
        company = fixture()
        company["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"][0]["val"] = 0
        self.assertEqual(audit_company(company, as_of=AS_OF)["status"],
                         "NONPOSITIVE_REVENUE_BASELINE")

    def test_zip_report(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "source.zip"
            data = json.dumps(fixture()).encode("utf-8")
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("ham_SEC/companyfacts/CIK0000000042.json.gz", gzip.compress(data))
            rows = analyze_zip(archive, as_of=AS_OF)
            self.assertEqual(len(rows), 1)
            summary = export_report(rows, pathlib.Path(temp) / "result.csv",
                                    pathlib.Path(temp) / "result.json", as_of=AS_OF)
            self.assertEqual(summary["total"], 1)
            self.assertEqual(summary["requires_manual_review"], 0)

    def test_archive_cik_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "source.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("ham_SEC/companyfacts/CIK0000000041.json.gz",
                           gzip.compress(json.dumps(fixture()).encode()))
            rows = analyze_zip(archive, as_of=AS_OF)
            self.assertEqual(rows[0]["status"], "INPUT_ERROR")


if __name__ == "__main__":
    unittest.main()
