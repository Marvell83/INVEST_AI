"""Sector-block transparency and immutable sector-specific report naming."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from piotroski_fscore import compute_piotroski, NAMES
from sirket_analiz_paneli import render_dashboard
from kredi_notlari import company_quality_snapshot

try:
    from test_quality_layers import fixture
    from test_invest_ai_web import service
except ImportError:
    from tests.test_quality_layers import fixture
    from tests.test_invest_ai_web import service


class PiotroskiSectorUXTests(unittest.TestCase):
    def test_unconfirmed_sector_explains_every_unknown_signal(self):
        score = compute_piotroski(fixture(), as_of="2025-03-01", sector="unknown")
        self.assertEqual(score["status"], "sector_unconfirmed")
        self.assertIsNone(score["score"])
        self.assertEqual(score["score_range"], [0, 9])
        self.assertEqual(set(score["missing_reasons"]), set(NAMES))
        self.assertEqual(set(score["missing_reasons"].values()), {"SECTOR_NOT_CONFIRMED"})

        quality = company_quality_snapshot(fixture(), as_of="2025-03-01", sector="unknown")
        html = render_dashboard(quality)
        self.assertIn("Şirket sektörü doğrulanmadığı", html)
        self.assertIn("Bu bir 0/9 puanı değildir.", html)
        self.assertIn("puanlama başlatılmadı.", html)
        self.assertEqual(html.count("puanlama başlatılmadı."), 9)

    def test_financial_sector_is_blocked_with_reason_not_fake_score(self):
        score = compute_piotroski(fixture(), as_of="2025-03-01", sector="financial")
        self.assertEqual(score["status"], "not_applicable_financial_sector")
        self.assertIsNone(score["score"])
        self.assertEqual(set(score["missing_reasons"].values()),
                         {"FINANCIAL_SECTOR_METHOD_UNAVAILABLE"})
        quality = company_quality_snapshot(fixture(), as_of="2025-03-01", sector="financial")
        html = render_dashboard(quality)
        self.assertIn("Finans kuruluşlarında bu genel Piotroski yöntemi kullanılmaz", html)

    def test_classifying_apple_nonfinancial_does_not_overwrite_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            research = service(folder, user_agent="")
            unknown = research.analyze({
                "ticker": "AAPL", "mode": "demo", "sector": "unknown"})
            nonfinancial = research.analyze({
                "ticker": "AAPL", "mode": "demo", "sector": "non_financial"})
            self.assertNotIn("piotroski_status", unknown)
            self.assertEqual(unknown["sector"], "unknown")
            self.assertEqual(nonfinancial["sector"], "non_financial")
            self.assertNotEqual(unknown["report_url"], nonfinancial["report_url"])
            a = Path(folder) / unknown["report_url"].lstrip("/")
            b = Path(folder) / nonfinancial["report_url"].lstrip("/")
            self.assertTrue(a.is_file())
            self.assertTrue(b.is_file())
            a_json = json.loads(a.with_suffix(".json").read_text(encoding="utf-8"))
            b_json = json.loads(b.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertNotIn("piotroski", a_json["quality"])
            self.assertNotIn("piotroski", b_json["quality"])
            self.assertNotIn("Şirket sektörü doğrulanmadığı", b.read_text(encoding="utf-8"))
            # Different assumptions are kept independent even with identical source hash.
            self.assertEqual(a_json["source"]["canonical_json_sha256"],
                             b_json["source"]["canonical_json_sha256"])

    def test_frontend_uses_four_stage_research_pipeline(self):
        page = (Path(__file__).resolve().parent.parent / "index.html").read_text(encoding="utf-8")
        for label in ("SEC · Temel analiz · Sektör · Gelecek",
                      "Temel analiz ve eleme", "Sektörel karşılaştırma", "Gelecek analizi"):
            self.assertIn(label, page)
        self.assertNotIn('data.piotroski_status', page)


if __name__ == "__main__":
    unittest.main()
