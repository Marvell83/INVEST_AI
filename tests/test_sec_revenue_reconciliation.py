"""Synthetic, offline tests: contested SEC revenue cannot be silently approved."""
import copy
import unittest
from sec_companyfacts import normalize_companyfacts
from sec_revenue_reconciliation import apply_revenue_review, APPROVAL_SCHEMA
from test_sec_companyfacts import fixture, fact


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.raw = fixture()
        for data in self.raw["facts"]["us-gaap"].values():
            for row in data["units"].get("USD", []):
                row["accn"] = "0000000042-25-000001"
        row = fact(950)
        row["accn"] = "0000000042-25-000001"
        self.raw["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [row]}}
        self.snapshot = normalize_companyfacts(self.raw, as_of="2025-03-01")
        self.decision = dict(schema_version=APPROVAL_SCHEMA, status="approved",
            cik="0000000042", fiscal_end="2024-12-31", revenue_concept="Revenues",
            value_usd=950, accession="0000000042-25-000001",
            statement_url="https://www.sec.gov/Archives/edgar/data/42/000000004225000001/test.htm",
            statement_label="Consolidated net sales", reviewer="Analyst signed",
            reviewed_at="2025-03-01",
            rationale="Confirmed from the full consolidated 10-K income statement.")

    def review(self, **changes):
        return apply_revenue_review(self.raw, self.snapshot, as_of="2025-03-01",
                                    review=dict(self.decision, **changes))

    def test_valid_review_and_provenance(self):
        approved, receipt = self.review()
        self.assertEqual(approved["annual"][0]["metrics"]["revenue"]["value_usd"], 950)
        self.assertEqual(self.snapshot["annual"][0]["metrics"]["revenue"]["value_usd"], 200)
        self.assertEqual(receipt["reviewer"], "Analyst signed")

    def test_unsigned_proposal_rejected(self):
        with self.assertRaises(ValueError): self.review(status="proposed")
    def test_wrong_cik_rejected(self):
        with self.assertRaises(ValueError): self.review(cik="0000000043")
    def test_wrong_fiscal_year_rejected(self):
        with self.assertRaises(ValueError): self.review(fiscal_end="2023-12-31")
    def test_wrong_accession_rejected(self):
        with self.assertRaises(ValueError): self.review(accession="0000000042-25-000002")
    def test_wrong_amount_rejected(self):
        with self.assertRaises(ValueError): self.review(value_usd=950000000)
    def test_wrong_concept_rejected(self):
        with self.assertRaises(ValueError): self.review(revenue_concept="OperatingIncomeLoss")
    def test_host_spoof_rejected(self):
        with self.assertRaises(ValueError):
            self.review(statement_url="https://www.sec.gov.attacker.example/Archives/edgar/data/42/000000004225000001/test.htm")
    def test_wrong_filing_url_rejected(self):
        with self.assertRaises(ValueError):
            self.review(statement_url="https://www.sec.gov/Archives/edgar/data/42/000000004225000002/test.htm")
    def test_missing_reviewer_rejected(self):
        with self.assertRaises(ValueError): self.review(reviewer="")
    def test_review_cannot_predate_filing(self):
        with self.assertRaises(ValueError): self.review(reviewed_at="2025-01-01")
    def test_missing_ebit_cannot_be_overridden(self):
        data = copy.deepcopy(self.raw)
        del data["facts"]["us-gaap"]["OperatingIncomeLoss"]
        with self.assertRaises(ValueError):
            apply_revenue_review(data, normalize_companyfacts(data, as_of="2025-03-01"),
                                 as_of="2025-03-01", review=self.decision)
    def test_clean_company_cannot_be_overridden(self):
        data = fixture()
        with self.assertRaises(ValueError):
            apply_revenue_review(data, normalize_companyfacts(data, as_of="2025-03-01"),
                                 as_of="2025-03-01", review=self.decision)
    def test_no_future_filing_leak(self):
        with self.assertRaises(ValueError):
            apply_revenue_review(self.raw, self.snapshot, as_of="2025-01-01",
                                 review=self.decision)


if __name__ == "__main__":
    unittest.main()
