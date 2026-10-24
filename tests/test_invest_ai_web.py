"""INVEST_AI private web research integration tests; no real SEC calls."""
from __future__ import annotations

from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from urllib.error import HTTPError

from invest_ai_web import ROOT, ResearchService, RequestError, build_server
from sec_arsiv import SECThrottle
from test_sirket_arastirma_akisi import with_ttm


NOW = datetime(2025, 10, 25, 12, 0, tzinfo=timezone.utc)
SECRET = "test-key-with-at-least-24-characters"
FAKE_MAP = {"0": {"cik_str": 42, "ticker": "SYN", "title": "Synthetic research"}}


def project(folder):
    root = Path(folder)
    (root / "ornekler").mkdir(parents=True)
    (root / "reports").mkdir()
    shutil.copy(ROOT / "index.html", root / "index.html")
    shutil.copy(ROOT / "ornekler/apple_ttm_evidence_2026-10-21.json",
                root / "ornekler/apple_ttm_evidence_2026-10-21.json")
    return root


def service(folder, **overrides):
    args = dict(root=project(folder), secret=SECRET,
                user_agent="INVEST_AI Tester tester@example.com",
                clock=lambda: NOW,
                ticker_download=lambda **kwargs: FAKE_MAP,
                fact_download=lambda cik, *, user_agent: with_ttm(),
                throttle=SECThrottle(interval=1.0, clock=lambda: 0, sleep=lambda t: None))
    args.update(overrides)
    return ResearchService(**args)


class ResearchServiceTests(unittest.TestCase):
    def test_demo_apple_creates_comprehensive_json_and_html(self):
        with tempfile.TemporaryDirectory() as folder:
            s = service(folder, user_agent="")
            response = s.analyze({"ticker": "aapl", "mode": "demo", "sector": "unknown"})
            self.assertTrue(response["ok"])
            self.assertEqual(response["ticker"], "AAPL")
            self.assertEqual(response["source"], "MANUAL_APPLE_EXAMPLE_NOT_LIVE_SEC")
            self.assertEqual(response["as_of"], "2026-10-21")
            self.assertIsNone(response["piotroski_score"])
            self.assertEqual(response["ttm_status"], "RECONCILED_CALCULATIONS")
            html = s.root / response["report_url"].lstrip("/")
            research = json.loads(html.with_suffix(".json").read_text())
            self.assertTrue(html.is_file())
            self.assertFalse(research["source"]["origin_verified_independently"])
            self.assertEqual(research["source"]["web_data_mode"], "demo")
            self.assertIsNone(research["dcf"])
            self.assertIn("TTM", html.read_text())

    def test_demo_does_not_call_network(self):
        with tempfile.TemporaryDirectory() as folder:
            def fail(*args, **kwargs):
                raise AssertionError("offline demo attempted a network call")
            s = service(folder, user_agent="", ticker_download=fail, fact_download=fail)
            s.analyze({"ticker": "AAPL", "mode": "demo", "sector": "non_financial"})
            self.assertEqual(s.throttle.calls, 0)

    def test_other_demo_company_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            s = service(folder)
            with self.assertRaisesRegex(RequestError, "yalnız AAPL"):
                s.analyze({"ticker": "MSFT", "mode": "demo", "sector": "unknown"})

    def test_online_ticker_uses_official_mapping_and_archives(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            def map_get(*, user_agent, limiter):
                calls.append("map")
                limiter.before_request()
                return FAKE_MAP
            def fact_get(cik, *, user_agent):
                calls.append(("facts", cik))
                return with_ttm()
            s = service(folder, ticker_download=map_get, fact_download=fact_get)
            result = s.analyze({"ticker": "SYN", "mode": "live", "sector": "non_financial"})
            self.assertEqual(result["cik"], "0000000042")
            self.assertEqual(result["as_of"], "2025-10-25")
            self.assertEqual(result["ttm_status"], "RECONCILED_CALCULATIONS")
            self.assertEqual(calls, ["map", ("facts", 42)])
            self.assertEqual(s.throttle.calls, 2)
            self.assertTrue((s.root / "veri/sec_ticker_esleme.json").is_file())
            self.assertTrue(list((s.root / "veri/sec_kaynaklari").rglob("*.json")))
            research = json.loads((s.root / result["report_url"].lstrip("/")).with_suffix(".json").read_text())
            self.assertEqual(research["source"]["web_data_mode"], "live")
            self.assertIsNone(research["actual_price"])
            self.assertIsNone(research["investment_recommendation"])

    def test_cache_mode_never_downloads_and_preserves_source_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            s = service(folder)
            s.analyze({"ticker": "SYN", "mode": "live", "sector": "non_financial"})
            def fail(*args, **kwargs):
                raise AssertionError("Cache mode triggered a download")
            cached = ResearchService(root=s.root, secret=SECRET, user_agent="",
                                     ticker_download=fail, fact_download=fail, clock=lambda: NOW)
            result = cached.analyze({"ticker": "SYN", "mode": "cache", "sector": "unknown"})
            self.assertEqual(result["mode"], "cache")
            self.assertEqual(result["ttm_status"], "RECONCILED_CALCULATIONS")

    def test_live_without_real_user_agent_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            s = service(folder, user_agent="")
            with self.assertRaisesRegex(RequestError, "SEC_USER_AGENT"):
                s.analyze({"ticker": "SYN", "mode": "live", "sector": "unknown"})

    def test_missing_or_bad_symbol_does_not_create_fake_report(self):
        with tempfile.TemporaryDirectory() as folder:
            s = service(folder)
            with self.assertRaisesRegex(RequestError, "listesinde"):
                s.analyze({"ticker": "FRAUD", "mode": "live", "sector": "unknown"})
            for value in ("../../secret", "", "AAPL;rm -rf", " NVDA 123", "a" * 17):
                with self.subTest(value=value):
                    with self.assertRaises(RequestError):
                        s.analyze({"ticker": value, "mode": "demo", "sector": "unknown"})
            self.assertFalse((s.root / "reports/research").exists())

    def test_unknown_sector_is_not_assumed_nonfinancial(self):
        with tempfile.TemporaryDirectory() as folder:
            result = service(folder).analyze({"ticker": "SYN", "mode": "live", "sector": "unknown"})
            self.assertIsNone(result["piotroski_score"])
            self.assertIn("SECTOR_SPECIFIC_PIOTROSKI_UNAVAILABLE", result["research_gaps"])

    def test_sec_429_disables_further_live_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            def block(*a, **k):
                calls.append(1)
                raise HTTPError("https://www.sec.gov", 429, "Too Many Requests", None, None)
            s = service(folder, ticker_download=block)
            with self.assertRaises(RequestError) as first:
                s.analyze({"ticker": "SYN", "mode": "live", "sector": "unknown"})
            self.assertEqual(first.exception.status, 503)
            with self.assertRaisesRegex(RequestError, "engeli"):
                s.analyze({"ticker": "SYN", "mode": "live", "sector": "unknown"})
            self.assertEqual(len(calls), 1)

    def test_mutex_prevents_simultaneous_analyses(self):
        with tempfile.TemporaryDirectory() as folder:
            s = service(folder)
            s.lock.acquire()
            try:
                with self.assertRaises(RequestError) as blocked:
                    s.analyze({"ticker": "AAPL", "mode": "demo", "sector": "unknown"})
                self.assertEqual(blocked.exception.status, 409)
            finally:
                s.lock.release()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.service = service(self.directory.name, user_agent="")
        self.server = build_server(self.service, port=0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)
        self.directory.cleanup()

    def request(self, method, path, *, payload=None, secret=SECRET, origin=None, ct="application/json"):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers = {"Content-Type":ct, "X-Invest-AI-Key":secret}
        if origin is not None:
            headers["Origin"] = origin
        body = json.dumps(payload) if payload is not None else None
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        result = (response.status, response.read())
        conn.close()
        return result

    def test_site_and_api_respond(self):
        status, content = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"web-analysis-form", content)
        status, blob = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        info = json.loads(blob)
        self.assertFalse(info["online_configured"])
        self.assertNotIn("secret", info)

    def test_restricted_source_files_and_hidden_paths(self):
        for path in ("/.git/config", "/.env", "/invest_ai_web.py", "/ornekler/apple_ttm_evidence_2026-10-21.json",
                     "/reports/../index.html", "/reports/%2e%2e/.git/config", "/reports/private.json"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.request("GET", "/reports/")[0], 200)

    def test_post_analysis_generates_html_accessible_on_same_site(self):
        payload = {"ticker": "AAPL", "mode": "demo", "sector": "unknown"}
        status, raw = self.request("POST", "/api/analyze", payload=payload)
        self.assertEqual(status, 200)
        answer = json.loads(raw)
        self.assertTrue(answer["ok"])
        report_status, page = self.request("GET", answer["report_url"])
        self.assertEqual(report_status, 200)
        self.assertIn(b"Apple", page)
        self.assertEqual(self.request("GET", answer["report_url"].replace(".html", ".json"))[0], 404)

    def test_unauthorized_post_forbidden(self):
        payload = {"ticker": "AAPL", "mode": "demo", "sector": "unknown"}
        status, data = self.request("POST", "/api/analyze", payload=payload, secret="wrong")
        self.assertEqual(status, 403)
        self.assertFalse(json.loads(data)["ok"])

    def test_cross_site_and_invalid_json_type_rejected(self):
        payload = {"ticker": "AAPL", "mode": "demo", "sector": "unknown"}
        self.assertEqual(self.request("POST", "/api/analyze", payload=payload,
                                      origin="https://evil.example")[0], 403)
        self.assertEqual(self.request("POST", "/api/analyze", payload=payload,
                                      ct="text/plain")[0], 415)

    def test_loopback_only(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            build_server(self.service, host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
