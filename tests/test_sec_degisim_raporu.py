"""SEC change HTML tests; synthetic inputs, no network."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from sec_finansal_degisim import compare_sec_snapshots
from sec_degisim_raporu import render_change_report, main
from test_sec_ttm_crosscheck import fixture


def example():
    return compare_sec_snapshots(fixture(), fixture(), as_of="2026-08-07",
                                 expected_cik=320193)


class ChangeHTMLTests(unittest.TestCase):
    def test_renders_comparable_ytd_and_same_period_warning(self):
        page = render_change_report(example())
        self.assertIn("SEC Finansal Değişimler", page)
        self.assertIn("330,00", page)
        self.assertIn("295,00", page)
        self.assertIn("Faaliyet marjı", page)
        self.assertIn("yüzde puan", page)
        self.assertIn("yatırım tahmini değildir", page)
        self.assertNotIn("<script", page)

    def test_incomplete_ttm_still_renders_caution(self):
        old = fixture()
        new = fixture()
        del new["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]
        data = compare_sec_snapshots(old, new, as_of="2026-08-07", expected_cik=320193)
        page = render_change_report(data)
        self.assertIn("UNAVAILABLE_TTM_NOT_RECONCILED", page)
        self.assertIn("Kayıt yok", page)

    def test_untrusted_company_and_event_text_escaped(self):
        original = example()
        original["company"] = "<script>alert(1)</script>"
        original["review_reasons"] = ['<img src=x onerror="x">']
        original["snapshot_record_changes"]["events"].append({
            "kind": '<svg onload="bad()">',
            "current": {"metric": "x", "value_usd": 123},
        })
        page = render_change_report(original)
        self.assertNotIn("<script>", page)
        self.assertNotIn("<svg onload=", page)
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("&lt;svg onload=", page)

    def test_wrong_schema_rejected(self):
        data = example()
        data["version"] = "incorrect"
        with self.assertRaisesRegex(ValueError, "version mismatch"):
            render_change_report(data)

    def test_cli_writes_offline_html(self):
        with tempfile.TemporaryDirectory() as td:
            src, out = Path(td) / "report.json", Path(td) / "report.html"
            src.write_text(json.dumps(example()), encoding="utf-8")
            main(["--report", str(src), "--out", str(out)])
            self.assertTrue(out.read_text().startswith("<!doctype html>"))

    def test_cli_never_overwrites_json(self):
        with self.assertRaises(SystemExit):
            main(["--report", "a.json", "--out", "a.json"])


if __name__ == "__main__":
    unittest.main()
