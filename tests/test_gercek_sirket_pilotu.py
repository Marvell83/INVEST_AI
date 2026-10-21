"""Tests for issuer pilot; entirely synthetic facts in tests, no network."""
import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

from gercek_sirket_pilotu import build_pilot, main
try:
    from test_quality_layers import fixture
except ImportError:
    from test_quality_layers import us_gaap_fixture as fixture

class PilotTests(unittest.TestCase):
    def result(self, data=None, **kwargs):
        return build_pilot(data or fixture(), as_of="2025-03-01",
                           expected_cik="42", expected_fiscal_end="2024-12-31", sector="non_financial",
                           **kwargs)

    def test_preserves_unknown_equity_issuance(self):
        out, page = self.result()
        self.assertIsNone(out["quality"]["piotroski"]["score"])
        self.assertEqual(out["quality"]["piotroski"]["score_range"],[8,9])
        self.assertIn("Tamamlanmadı",page)
        self.assertNotIn("Birleşik yatırım puanı",page)

    def test_unconfirmed_sector_not_scored(self):
        with self.assertRaisesRegex(ValueError, "non_financial sector"):
            build_pilot(fixture(), as_of="2025-03-01", expected_cik=42, sector="unknown")

    def test_wrong_company_rejected(self):
        with self.assertRaisesRegex(ValueError,"CIK mismatch"):
            build_pilot(fixture(),as_of="2025-03-01",expected_cik=43,sector="non_financial")

    def test_wrong_fiscal_year_rejected(self):
        with self.assertRaisesRegex(ValueError,"fiscal period"):
            build_pilot(fixture(),as_of="2025-03-01",expected_cik=42,
                        expected_fiscal_end="2025-12-31",sector="non_financial")

    def test_future_release_never_visible(self):
        with self.assertRaisesRegex(ValueError,"no point-in-time comparable"):
            build_pilot(fixture(),as_of="2024-12-31",expected_cik=42,sector="non_financial")

    def test_report_lists_source_and_filed_date(self):
        out,page=self.result(source_sha256="abc123")
        self.assertEqual(out["latest_fiscal_end"],"2024-12-31")
        self.assertIn("abc123",page)
        self.assertIn("000042-2025-001",page)
        self.assertIn("2025-02-15",page)
        self.assertIsNone(out["actual_stock_price"])
        self.assertIsNone(out["dcf_result"])

    def test_issuer_html_escaped(self):
        data=fixture();data["entityName"]="<script>bad()</script>"
        _,page=self.result(data=data)
        self.assertNotIn("<script>",page)
        self.assertIn("&lt;script&gt;",page)

    def test_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            src=root/"company.json";out=root/"report.json";page=root/"report.html"
            data=json.dumps(fixture()).encode()
            src.write_bytes(data)
            main(["--companyfacts",str(src),"--as-of","2025-03-01",
                  "--expected-cik","42","--expected-fiscal-end","2024-12-31",
                  "--sector","non_financial",
                  "--out-json",str(out),"--out-html",str(page)])
            obj=json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(obj["source_snapshot_sha256"],hashlib.sha256(data).hexdigest())
            self.assertIn("<!doctype html>",page.read_text(encoding="utf-8"))

if __name__=="__main__":
    unittest.main()