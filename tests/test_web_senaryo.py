"""Web form scenario / valuation inputs; synthetic issuer, no real SEC calls."""
from __future__ import annotations

import json
import re
import tempfile
import threading
import unittest

from invest_ai_web import RequestError, build_server
import test_invest_ai_web as web_tests  # module import: unittest must not re-run its test classes here
from test_invest_ai_web import ROOT, service
from test_senaryo_degerleme import with_shares

FIVE_MAP = {"0": {"cik_str": 55, "ticker": "FIVE", "title": "Synthetic forecast"}}
GROWTH = {"long_run_growth": 0.03, "long_run_growth_source": "Sentetik uzun vadeli büyüme kaynağı"}
DISCOUNT = {"discount_rate": 0.09, "discount_rate_source": "Sentetik sermaye maliyeti kaynağı"}
REQUEST = {"ticker": "FIVE", "mode": "live", "sector": "non_financial"}


def five_service(folder):
    return service(folder, ticker_download=lambda **kwargs: FIVE_MAP,
                   fact_download=lambda cik, *, user_agent: with_shares())


class ScenarioRequestTests(unittest.TestCase):
    def test_growth_and_discount_produce_scenarios_and_valuation(self):
        with tempfile.TemporaryDirectory() as folder:
            s = five_service(folder)
            answer = s.analyze(dict(REQUEST, **GROWTH, **DISCOUNT))
            self.assertEqual((answer["projection_status"], answer["valuation_status"]), ("OK", "OK"))
            self.assertRegex(answer["report_url"], r"_s[a-f0-9]{8}\.html$")
            page = (s.root / answer["report_url"].lstrip("/")).read_text(encoding="utf-8")
            self.assertIn("Senaryo değerlemesi (deneysel DCF)", page)
            self.assertIn("Sentetik sermaye maliyeti kaynağı", page)
            report = json.loads((s.root / answer["report_url"].lstrip("/")).with_suffix(".json").read_text())
            self.assertEqual(report["scenario_valuation"]["inputs"]["discount_rate"]["value"], 0.09)

    def test_without_inputs_only_the_baseline_is_shown(self):
        with tempfile.TemporaryDirectory() as folder:
            answer = five_service(folder).analyze(REQUEST)
            self.assertIsNone(answer["projection_status"])
            self.assertNotRegex(answer["report_url"], r"_s[a-f0-9]{8}\.html$")

    def test_different_assumptions_do_not_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as folder:
            s = five_service(folder)
            first = s.analyze(dict(REQUEST, **GROWTH))
            second = s.analyze(dict(REQUEST, **dict(GROWTH, long_run_growth=0.02)))
            self.assertNotEqual(first["report_url"], second["report_url"])
            self.assertEqual(len(list((s.root / "reports/research").glob("*.html"))), 2)

    def test_invalid_scenario_inputs_are_rejected_before_analysis(self):
        bad = (
            dict(long_run_growth=0.03),                                         # missing source
            dict(GROWTH, long_run_growth_source="kısa"),                        # source too short
            dict(GROWTH, long_run_growth_source="x" * 301),                     # source too long
            dict(GROWTH, long_run_growth=0.2),                                  # out of bounds
            dict(GROWTH, long_run_growth=True),                                 # bool is not a rate
            dict(DISCOUNT),                                                     # valuation without growth
            {**GROWTH, **DISCOUNT, "long_run_growth": 0.05},                    # above 4% perpetual cap
            {**GROWTH, **DISCOUNT, "discount_rate": 0.30},
            dict(GROWTH, beta=1.1),                                             # unknown field
        )
        with tempfile.TemporaryDirectory() as folder:
            s = five_service(folder)
            for extra in bad:
                with self.subTest(extra=extra), self.assertRaises(RequestError) as error:
                    s.analyze(dict(REQUEST, **extra))
                self.assertEqual(error.exception.status, 422)
            self.assertFalse((s.root / "reports/research").exists())

    def test_demo_with_short_history_explains_instead_of_valuing(self):
        with tempfile.TemporaryDirectory() as folder:
            answer = service(folder).analyze(
                {"ticker": "AAPL", "mode": "demo", "sector": "non_financial", **GROWTH, **DISCOUNT})
            self.assertEqual((answer["projection_status"], answer["valuation_status"]),
                             ("INSUFFICIENT_HISTORY", "PROJECTION_UNAVAILABLE"))


class ScenarioHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = build_server(five_service(self.directory.name), port=0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    tearDown = web_tests.HTTPTests.tearDown
    request = web_tests.HTTPTests.request

    def test_long_cited_inputs_fit_and_oversized_body_rejected(self):
        payload = {**REQUEST, **GROWTH, **DISCOUNT, "long_run_growth_source": "ç" * 290}
        self.assertGreater(len(json.dumps(payload)), 512)
        status, raw = self.request("POST", "/api/analyze", payload=payload)
        self.assertEqual(status, 200, raw)
        oversized = dict(payload, discount_rate_source="x" * 5000)
        self.assertEqual(self.request("POST", "/api/analyze", payload=oversized)[0], 413)

    def test_invalid_input_message_reaches_browser(self):
        status, raw = self.request("POST", "/api/analyze", payload=dict(REQUEST, long_run_growth=0.03))
        self.assertEqual(status, 422)
        self.assertIn("kaynağı birlikte girilmeli", json.loads(raw)["error"])


class FormTests(unittest.TestCase):
    def test_form_offers_optional_cited_inputs(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        for element in ("analysis-growth", "analysis-growth-source", "analysis-discount", "analysis-discount-source"):
            self.assertIn(f'id="{element}"', page)
        self.assertIn("Sistem bu oranları kendisi seçmez", page)
        self.assertIn("Object.assign({ticker,mode,sector}, scenario.body)", page)

    def test_report_list_recognises_scenario_reports(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        pattern = re.search(r"const match = /(.+?)/i\.exec\(filename\);", page).group(1)
        regex = re.compile(pattern.replace("\\-", "-").replace("(?:", "(?:"), re.IGNORECASE)
        self.assertTrue(regex.match("FIVE_LIVE_2025-10-25_non_financial_0123456789ab_s89abcdef.html"))
        self.assertTrue(regex.match("FIVE_LIVE_2025-10-25_non_financial_0123456789ab.html"))


if __name__ == "__main__":
    unittest.main()
