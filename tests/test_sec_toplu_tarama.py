"""Offline SEC batch regression tests. Zero real HTTP requests; synthetic issuers."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from sec_toplu_tarama import (
    SECThrottle, _cached, download_ticker_map, main, resolve_universe, scan_universe,
)
from test_sirket_arastirma_akisi import with_ttm


NOW = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.timezone.utc)
AS_OF = "2025-10-25"


def firms():
    return [{"cik": 42, "ticker": "SYN", "sector": "non_financial"},
            {"cik": 43, "ticker": "TEST", "sector": "unknown"}]


def ticker_data():
    return {
        "0": {"cik_str": 42, "ticker": "SYN", "title": "Synthetic Company"},
        "1": {"cik_str": 43, "ticker": "TEST", "title": "Another Synthetic Company"},
    }


def issuer(cik):
    raw = with_ttm()
    raw["cik"] = cik
    raw["entityName"] = f"Synthetic Issuer {cik}"
    return raw


def scan(folder, *, records=None, offline=False, fetch=None, as_of=AS_OF,
         mapping=None, limiter=None, max_age_hours=24):
    return scan_universe(
        firms() if records is None else records, as_of=as_of,
        archive_dir=Path(folder) / "archive",
        reports_dir=Path(folder) / "reports", offline=offline,
        ticker_data=mapping, user_agent="INVEST_AI Test tester@example.com",
        downloader=fetch or (lambda cik, *, user_agent: issuer(cik)),
        clock=lambda: NOW, limiter=limiter, max_age_hours=max_age_hours)


class BatchTests(unittest.TestCase):
    def test_explicit_cik_universe_with_optional_ticker(self):
        r = resolve_universe(firms(), ticker_data=ticker_data())
        self.assertEqual([p["cik"] for p in r], ["0000000042", "0000000043"])
        self.assertTrue(all(p["ticker_mapping_checked"] for p in r))
        self.assertEqual(r[1]["sector"], "unknown")

    def test_ticker_only_with_official_snapshot(self):
        r = resolve_universe([{"ticker": "SYN"}], ticker_data=ticker_data())
        self.assertEqual(r[0]["cik"], "0000000042")
        with self.assertRaisesRegex(ValueError, "requires an SEC ticker map"):
            resolve_universe([{"ticker": "SYN"}])

    def test_ticker_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "ticker CIK mismatch"):
            resolve_universe([{"ticker": "SYN", "cik": 999}], ticker_data=ticker_data())

    def test_duplicate_cik_from_share_class_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate CIK"):
            resolve_universe([{"ticker": "A", "cik": 42}, {"ticker": "B", "cik": 42}])

    def test_duplicate_ticker_map_conflicting_cik(self):
        d = [{"ticker": "SYN", "cik_str": 42}, {"ticker": "SYN", "cik_str": 43}]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            resolve_universe([{"ticker": "SYN"}], ticker_data=d)

    def test_over_limit_rejected_before_any_requests(self):
        with self.assertRaisesRegex(ValueError, "1..1"):
            resolve_universe(firms(), limit=1)

    def test_online_two_issuers_source_files_and_html(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            def fetch(cik, *, user_agent):
                calls.append((cik, user_agent))
                return issuer(cik)
            throttle = SECThrottle(interval=1, clock=lambda: 0, sleep=lambda t: None)
            r = scan(td, fetch=fetch, mapping=ticker_data(), limiter=throttle)
            self.assertEqual([x[0] for x in calls], [42, 43])
            self.assertEqual(r["network_requests"], 2)
            self.assertEqual(r["companies_analyzed"], 2)
            self.assertEqual(r["companies_with_errors"], 0)
            self.assertEqual(r["counts"], {"ANALYZED_PARTIAL": 2})
            a = r["records"][0]
            self.assertEqual(a["ticker"], "SYN")
            self.assertEqual(a["ttm_status"], "RECONCILED_CALCULATIONS")
            self.assertIsNone(a["fscore"])
            self.assertTrue(Path(a["research_html"]).exists())
            self.assertTrue(Path(a["snapshot_path"]).exists())
            saved = json.loads(Path(a["research_json"]).read_text())
            self.assertIsNone(saved["dcf"])
            self.assertIsNone(saved["actual_price"])
            self.assertEqual(saved["source"]["capture_timestamp_utc"], NOW.isoformat())
            self.assertTrue(saved["source"]["ticker_mapping_checked"])
            self.assertTrue(saved["source"]["origin_verified_independently"] is False)

    def test_rate_limiter_sleeps_between_sequential_calls(self):
        delays = []
        limiter = SECThrottle(interval=1.0, clock=lambda: 0.0, sleep=delays.append)
        limiter.before_request()
        limiter.before_request()
        self.assertEqual(delays, [1.0])
        self.assertEqual(limiter.calls, 2)
        with self.assertRaisesRegex(ValueError, "0.5..60"):
            SECThrottle(interval=0.1)

    def test_fresh_cache_no_second_request(self):
        with tempfile.TemporaryDirectory() as td:
            first = scan(td, records=[firms()[0]])
            self.assertEqual(first["network_requests"], 1)
            def should_not_download(*a, **k):
                raise AssertionError("fresh cache incorrectly fetched")
            second = scan(td, records=[firms()[0]], fetch=should_not_download)
            self.assertEqual(second["network_requests"], 0)
            self.assertEqual(second["records"][0]["status"], "ANALYZED_PARTIAL")
            self.assertTrue(json.loads(Path(second["records"][0]["research_json"]).read_text())
                            ["source"]["cache_used"])

    def test_offline_cache_use_zero_network_requests(self):
        with tempfile.TemporaryDirectory() as td:
            scan(td, records=[firms()[0]])
            res = scan(td, records=[firms()[0]], offline=True,
                       fetch=lambda *a, **k: self.fail("offline network"))
            self.assertEqual(res["network_requests"], 0)
            self.assertEqual(res["companies_analyzed"], 1)
            self.assertTrue(Path(res["records"][0]["snapshot_path"]).is_file())

    def test_missing_offline_snapshot_is_not_zero_data(self):
        with tempfile.TemporaryDirectory() as td:
            res = scan(td, offline=True, fetch=lambda *a, **k: self.fail("network"))
            self.assertEqual(res["counts"], {"CACHE_MISS": 2})
            self.assertEqual(res["companies_analyzed"], 0)
            self.assertEqual(res["network_requests"], 0)

    def test_content_addressed_snapshot_keeps_old_versions(self):
        with tempfile.TemporaryDirectory() as td:
            first = scan(td, records=[firms()[0]])["records"][0]
            changed = issuer(42)
            changed["entityName"] = "Second revision"
            second = scan(td, records=[firms()[0]], max_age_hours=0,
                          fetch=lambda *a, **k: changed)["records"][0]
            self.assertNotEqual(first["snapshot_sha256"], second["snapshot_sha256"])
            self.assertTrue(Path(first["snapshot_path"]).is_file())
            self.assertTrue(Path(second["snapshot_path"]).is_file())
            current = _cached(Path(td) / "archive", "0000000042")
            self.assertEqual(current[1]["sha256"], second["snapshot_sha256"])

    def test_corrupt_snapshot_fails_integrity_check_and_no_analysis(self):
        with tempfile.TemporaryDirectory() as td:
            record = scan(td, records=[firms()[0]])["records"][0]
            Path(record["snapshot_path"]).write_text("TAMPERED")
            r = scan(td, records=[firms()[0]], offline=True)
            self.assertEqual(r["records"][0]["status"], "INPUT_OR_ANALYSIS_ERROR")
            self.assertIn("SHA-256 archive integrity mismatch", r["records"][0]["error"])

    def test_wrong_downloaded_cik_not_archived(self):
        with tempfile.TemporaryDirectory() as td:
            r = scan(td, fetch=lambda cik, *, user_agent: issuer(999))
            self.assertEqual(r["companies_analyzed"], 0)
            self.assertIn("CIK mismatch", r["records"][0]["error"])
            self.assertFalse(list((Path(td) / "archive").rglob("*.json")))

    def test_per_company_errors_do_not_stop_healthy_issuers(self):
        with tempfile.TemporaryDirectory() as td:
            def fetch(cik, *, user_agent):
                if cik == 42:
                    raise urllib.error.URLError("synthetic connectivity failure")
                return issuer(cik)
            r = scan(td, fetch=fetch)
            self.assertEqual(r["records"][0]["status"], "INPUT_OR_ANALYSIS_ERROR")
            self.assertEqual(r["records"][1]["status"], "ANALYZED_PARTIAL")
            self.assertEqual(r["companies_analyzed"], 1)

    def test_429_circuit_breaker_prevents_further_requests(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            def block(cik, *, user_agent):
                calls.append(cik)
                raise urllib.error.HTTPError("https://data.sec.gov", 429,
                                             "SEC restriction", None, None)
            r = scan(td, fetch=block)
            self.assertEqual(calls, [42])
            self.assertEqual(r["network_requests"], 1)
            self.assertEqual([x["status"] for x in r["records"]],
                             ["SEC_ACCESS_RESTRICTED", "SKIPPED_SEC_ACCESS_RESTRICTION"])

    def test_403_also_stops_all_network_calls(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            def block(cik, *, user_agent):
                calls.append(cik)
                raise urllib.error.HTTPError("https://data.sec.gov", 403,
                                             "SEC access denied", None, None)
            r = scan(td, fetch=block)
            self.assertEqual(calls, [42])
            self.assertEqual(r["records"][1]["status"], "SKIPPED_SEC_ACCESS_RESTRICTION")

    def test_cutoff_before_quarter_report_blocks_ttm_without_backfill(self):
        with tempfile.TemporaryDirectory() as td:
            r = scan(td, records=[firms()[0]], as_of="2025-10-01")
            self.assertNotEqual(r["records"][0]["ttm_status"], "RECONCILED_CALCULATIONS")
            self.assertEqual(r["records"][0]["status"], "ANALYZED_PARTIAL")

    def test_no_issuer_rating_or_price_faked_in_reports(self):
        with tempfile.TemporaryDirectory() as td:
            r = scan(td, records=[firms()[0]])
            obj = json.loads(Path(r["records"][0]["research_json"]).read_text())
            self.assertIsNone(obj["combined_investment_score"])
            self.assertIsNone(obj["quality"]["credit"])
            self.assertIsNone(obj["investment_recommendation"])

    def test_unknown_sector_never_gets_a_piotroski_score(self):
        with tempfile.TemporaryDirectory() as td:
            r = scan(td, records=[{"cik": 42, "sector": "unknown"}])
            self.assertIsNone(r["records"][0]["fscore"])
            self.assertEqual(r["records"][0]["fscore_range"], [0, 9])

    def test_invalid_filing_input_does_not_turn_into_success(self):
        with tempfile.TemporaryDirectory() as td:
            r = scan(td, records=[firms()[0]],
                     fetch=lambda *a, **k: {"cik": 42, "facts": None})
            self.assertEqual(r["records"][0]["status"], "INPUT_OR_ANALYSIS_ERROR")

    def test_ticker_mapping_fetch_is_single_declared_SEC_request(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, max_bytes):
                return json.dumps(ticker_data()).encode()
        requests = []
        def opener(request, timeout):
            requests.append((request.full_url, request.get_header("User-agent")))
            return FakeResponse()
        limiter = SECThrottle(interval=1, clock=lambda: 0, sleep=lambda x: None)
        data = download_ticker_map(user_agent="Test test@example.com",
                                   limiter=limiter, opener=opener)
        self.assertEqual(data, ticker_data())
        self.assertEqual(limiter.calls, 1)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0], "https://www.sec.gov/files/company_tickers.json")

    def test_mapping_digest_is_grounded_to_exact_source_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            r = scan(td, records=[firms()[0]], offline=True, mapping=ticker_data())
            from sec_toplu_tarama import _canonical_bytes
            self.assertEqual(
                r["ticker_map_sha256"],
                hashlib.sha256(_canonical_bytes(ticker_data())).hexdigest()
            )

    def test_cli_requires_persisting_downloaded_ticker_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            source = folder / "universe.json"
            source.write_text(json.dumps([{"ticker": "SYN"}]))
            params = [
                "--universe", str(source), "--as-of", AS_OF,
                "--online", "--download-ticker-map",
                "--archive-dir", str(folder / "archive"),
                "--reports-dir", str(folder / "reports"),
                "--out-json", str(folder / "summary.json"),
                "--out-csv", str(folder / "summary.csv"),
            ]
            with patch.dict("os.environ", {"SEC_USER_AGENT": "Test test@example.com"}):
                with self.assertRaises(SystemExit):
                    main(params)
                # Once the ticker map is persisted, offline cache misses are
                # reported but there is no Company Facts download in this mock.
                with patch("sec_toplu_tarama.download_ticker_map", return_value=ticker_data()):
                    with patch("sec_toplu_tarama.scan_universe", return_value={
                        "version": "invest-ai-sec-batch-0.1.0",
                        "records": [], "counts": {}, "companies_with_errors": 0,
                        "network_requests": 1}):
                        code = main(params + [
                            "--ticker-map-out", str(folder / "mapping.json")])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads((folder / "mapping.json").read_text()), ticker_data())
            self.assertEqual(json.loads((folder / "summary.json").read_text())
                             ["ticker_map_snapshot"], str(folder / "mapping.json"))

    def test_offline_cli_export_and_failure_exit(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            src, out, csvout = (folder / name for name in
                                ("universe.json", "summary.json", "summary.csv"))
            src.write_text(json.dumps([{"cik": 42}]))
            code = main(["--universe", str(src), "--as-of", AS_OF, "--offline",
                         "--archive-dir", str(folder / "archive"),
                         "--reports-dir", str(folder / "reports"),
                         "--out-json", str(out), "--out-csv", str(csvout)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out.read_text())["counts"], {"CACHE_MISS": 1})
            self.assertIn("cik,ticker,company,status", csvout.read_text(encoding="utf-8-sig"))

    def test_invalid_sector_blocked_prior_to_download(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "sector"):
                scan(td, records=[{"cik": 42, "sector": "guess_it"}])

    def test_ticker_only_missing_map_errors_before_download(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "requires an SEC ticker map"):
                scan(td, records=[{"ticker": "SYN"}])

    def test_excel_csv_formula_in_issuer_name_is_escaped(self):
        import csv
        from sec_toplu_tarama import _export
        with tempfile.TemporaryDirectory() as td:
            malicious = issuer(42)
            malicious["entityName"] = '=HYPERLINK("https://example.test","click")'
            result = scan(td, records=[firms()[0]],
                          fetch=lambda cik, *, user_agent: malicious)
            out = Path(td) / "manifest.json"
            csv_path = Path(td) / "manifest.csv"
            _export(result, out, csv_path)
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["company"], "'" + malicious["entityName"])
            self.assertEqual(json.loads(out.read_text())["records"][0]["company"],
                             malicious["entityName"])

    def test_reject_wrong_cache_date_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            first = scan(td, records=[firms()[0]])
            index = Path(td) / "archive" / "CIK0000000042" / "index.json"
            obj = json.loads(index.read_text())
            obj["captured_at_utc"] = "2026-10-25T00:00:00+00:00"
            index.write_text(json.dumps(obj))
            r = scan(td, records=[firms()[0]], offline=True)
            self.assertEqual(r["records"][0]["status"], "INPUT_OR_ANALYSIS_ERROR")
            self.assertIn("later than the clock", r["records"][0]["error"])


if __name__ == "__main__":
    unittest.main()
