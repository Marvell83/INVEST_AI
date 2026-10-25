"""Synthetic tests: SEC nightly companyfacts.zip -> SQLite full issuer universe."""
from __future__ import annotations

from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

from sec_piyasa_toplu_tarama import (diagnose_database, fetch_bulk_zip, ingest_zip,
                                    load_bulk_grid, run)
from test_finansal_tablolar import AS_OF, company


class SECBulkScreeningTests(unittest.TestCase):
    def fixture(self, root):
        root = Path(root)
        folder = root / "veri"
        folder.mkdir()
        ticker = {
            "0":{"ticker":"SYN","cik_str":77,"title":"SYNTHETIC CO"},
            "1":{"ticker":"NONE","cik_str":42,"title":"NO FACTS CORPORATION"},
            "2":{"ticker":"SYN.B","cik_str":77,"title":"SYNTHETIC CLASS B"},
        }
        (folder / "sec_ticker_esleme.json").write_text(json.dumps(ticker),encoding="utf-8")
        with zipfile.ZipFile(folder / "companyfacts.zip", "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("CIK0000000077.json",json.dumps(company()))
        return folder / "companyfacts.zip"


    def test_bulk_http_download_streams_zip_and_accepts_range_resume(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("CIK0000000077.json", json.dumps(company()))
        archive_bytes = data.getvalue()
        with tempfile.TemporaryDirectory() as folder, patch(
                "sec_piyasa_toplu_tarama.shutil.disk_usage",
                return_value=SimpleNamespace(free=10_000_000_000)):
            dest = Path(folder) / "companyfacts.zip"
            partial = dest.with_name(dest.name + ".part")
            halfway = len(archive_bytes)//2
            partial.write_bytes(archive_bytes[:halfway])
            requests = []
            class Source:
                status = 206
                headers = {"Content-Range": f"bytes {halfway}-{len(archive_bytes)-1}/{len(archive_bytes)}"}
                def __init__(self):
                    self.stream = io.BytesIO(archive_bytes[halfway:])
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def read(self, n):
                    return self.stream.read(n)
            def opener(request, timeout):
                requests.append(request)
                return Source()
            result = fetch_bulk_zip(dest, user_agent="INVEST_AI Research test@example.com",
                                    opener=opener)
            self.assertEqual(result.read_bytes(), archive_bytes)
            self.assertEqual(requests[0].get_header("Range"), f"bytes={halfway}-")
            self.assertFalse(partial.exists())
            # Existing local ZIP should not trigger another network request.
            self.assertEqual(fetch_bulk_zip(dest, user_agent="INVEST_AI Research test@example.com",
                                            opener=lambda *args, **kwargs: self.fail("network")), dest)

    def test_complete_zip_ingest_and_missing_issuers(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.fixture(folder)
            events = []
            result = ingest_zip(folder, archive_path=archive, as_of=AS_OF,
                                progress=events.append)
            self.assertEqual(result["phase"], "complete")
            self.assertEqual(result["total"], 2)  # two issuers, one multi-class ticker
            self.assertEqual(result["statuses"], {"NO_COMPANYFACTS":1,"OK":1})
            screen = load_bulk_grid(folder)
            self.assertEqual(screen["available"], 3)  # SYN, SYN.B and NONE
            self.assertEqual(screen["scope"], "BULK_SEC_COMPANYFACTS")
            self.assertFalse(screen["market_price_fetched"])
            found = {r["ticker"]:r for r in screen["rows"]}
            row = found["SYN"]
            self.assertEqual(row["ticker"], "SYN")
            self.assertEqual(found["SYN.B"]["roe"], row["roe"])
            self.assertAlmostEqual(row["roe"], 200 / 640)
            self.assertAlmostEqual(row["operating_margin"], 260 / 1200)
            self.assertIsNone(row["market_cap"])
            self.assertIsNone(row["peg"])
            self.assertEqual(found["NONE"]["screening_status"], "NO_COMPANYFACTS")
            self.assertIsNone(found["NONE"]["roe"])
            self.assertEqual(events[-1]["phase"], "complete")

    def test_limit_checkpoint_and_resume_without_recomputation(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.fixture(folder)
            first = ingest_zip(folder, archive_path=archive, as_of=AS_OF, max_companies=1)
            self.assertEqual((first["phase"], first["processed"], first["total"]),("partial",1,2))
            initial = load_bulk_grid(folder)
            self.assertEqual(initial["screening_counts"]["PENDING"],1)
            second = ingest_zip(folder, archive_path=archive, as_of=AS_OF)
            self.assertEqual((second["phase"],second["processed"]),("complete",2))
            again = ingest_zip(folder, archive_path=archive, as_of=AS_OF, max_companies=1)
            self.assertEqual(again["processed"], 2)
            self.assertEqual(again["statuses"], second["statuses"])

    def test_diagnose_and_retry_only_error_rows_preserves_successes(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.fixture(folder)
            original = __import__("sec_piyasa_toplu_tarama").build_annual_statements
            def selective_failure(raw, **kw):
                if raw.get("cik") == 77:
                    raise ValueError("bad XBRL fiscal start date")
                return original(raw, **kw)
            with patch("sec_piyasa_toplu_tarama.build_annual_statements",
                       side_effect=selective_failure):
                first = ingest_zip(folder, archive_path=archive, as_of=AS_OF)
            self.assertEqual(first["statuses"], {"ERROR": 1, "NO_COMPANYFACTS": 1})
            diagnostic = diagnose_database(folder)
            self.assertEqual(diagnostic["status_counts"]["ERROR"], 1)
            self.assertIn("bad XBRL fiscal start date", diagnostic["error_reasons"][0]["error"])
            self.assertEqual(diagnostic["error_examples"][0]["ticker"], "SYN")
            fixed = ingest_zip(folder, archive_path=archive, retry_errors=True)
            self.assertEqual(fixed["statuses"], {"OK": 1, "NO_COMPANYFACTS": 1})
            self.assertEqual(fixed["retries_attempted"], 1)
            self.assertEqual(fixed["as_of"], AS_OF)
            self.assertFalse(fixed["error_types"])
            self.assertEqual(diagnose_database(folder)["snapshot_as_of"], AS_OF)
            self.assertEqual(ingest_zip(folder, archive_path=archive, retry_errors=True)
                             ["retries_attempted"], 0)

    def test_retry_does_not_reset_snapshot_across_date_change(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.fixture(folder)
            ingest_zip(folder, archive_path=archive, as_of=AS_OF)
            with self.assertRaisesRegex(ValueError, "different SEC ZIP/as-of"):
                ingest_zip(folder, archive_path=archive, as_of="2026-10-25",
                           retry_errors=True)
            self.assertEqual(diagnose_database(folder)["snapshot_as_of"], AS_OF)
            self.assertEqual(diagnose_database(folder)["status_counts"]["OK"], 1)

    def test_issuer_without_eligible_10k_fiscal_year_is_coverage_gap_not_error(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.fixture(folder)
            # Synthetic issuer 77 has an SEC Company Facts file but only IFRS facts.
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("CIK0000000077.json", json.dumps({
                    "cik": 77, "entityName": "FOREIGN ISSUER", "facts": {
                        "ifrs-full": {"Revenue": {"units": {"USD": []}}},
                        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": []}}}
                    }}))
            result = ingest_zip(folder, archive_path=archive, as_of=AS_OF)
            self.assertEqual(result["statuses"],
                             {"NO_SUPPORTED_ANNUAL_DATA": 1, "NO_COMPANYFACTS": 1})
            self.assertEqual(result["errors"], 0)
            company_row = next(x for x in load_bulk_grid(folder)["rows"] if x["ticker"] == "SYN")
            self.assertEqual(company_row["screening_reason"], "NO_US_GAAP_NAMESPACE")
            self.assertIn("ifrs-full", company_row["screening_detail"])
            self.assertIsNone(company_row["roe"])
            self.assertEqual(diagnose_database(folder)["status_counts"]["NO_SUPPORTED_ANNUAL_DATA"], 1)

    def test_existing_errors_reclassify_without_touching_ok_issuers(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.fixture(folder)
            # First run creates an OK issuer and a missing-facts issuer.
            original = ingest_zip(folder, archive_path=archive, as_of=AS_OF)
            self.assertEqual(original["statuses"], {"OK": 1, "NO_COMPANYFACTS": 1})
            import sqlite3
            db = Path(folder) / "veri/invest_ai_evren.sqlite3"
            with sqlite3.connect(db) as con:
                con.execute("UPDATE companies SET status='ERROR',error='ValueError',payload=NULL "
                            "WHERE cik='0000000042'")
            fixed = ingest_zip(folder, archive_path=archive, retry_errors=True)
            self.assertEqual(fixed["statuses"], {"OK": 1, "NO_COMPANYFACTS": 1})
            self.assertEqual(fixed["retries_attempted"], 1)
            self.assertEqual(fixed["errors"], 0)
            self.assertEqual(diagnose_database(folder)["status_counts"]["OK"], 1)

    def test_us_gaap_namespace_with_no_annual_anchor_is_coverage_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.fixture(folder)
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("CIK0000000077.json", json.dumps({
                    "cik": 77, "entityName": "PARTIAL GAAP", "facts": {
                        "us-gaap": {"CustomBalanceOnly": {"units": {"USD": []}}}
                    }}))
            result = ingest_zip(folder, archive_path=archive, as_of=AS_OF)
            self.assertEqual(result["statuses"]["NO_SUPPORTED_ANNUAL_DATA"], 1)
            row = next(x for x in load_bulk_grid(folder)["rows"] if x["ticker"] == "SYN")
            self.assertEqual(row["screening_reason"], "NO_ELIGIBLE_US_GAAP_10K_FISCAL_YEAR")


    def test_source_cik_mismatch_is_quarantined_not_financial_error(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.fixture(folder)
            misplaced = company()
            misplaced["cik"] = 4321
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("CIK0000000077.json", json.dumps(misplaced))
            state = ingest_zip(folder, archive_path=archive, as_of=AS_OF)
            self.assertEqual(state["statuses"],
                             {"SOURCE_CIK_MISMATCH": 1, "NO_COMPANYFACTS": 1})
            self.assertEqual(state["errors"], 0)
            diag = diagnose_database(folder)
            self.assertEqual(len(diag["identity_mismatches"]), 1)
            self.assertIn("expected=0000000077", diag["identity_mismatches"][0]["detail"])
            self.assertIn("reported=0000004321", diag["identity_mismatches"][0]["detail"])
            issuer = next(row for row in load_bulk_grid(folder)["rows"]
                          if row["ticker"] == "SYN")
            self.assertEqual(issuer["screening_status"], "SOURCE_CIK_MISMATCH")
            self.assertIsNone(issuer["roe"])
            self.assertIsNone(issuer["revenue"])

    def test_retry_progress_is_bounded_and_reports_retries_separately(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.fixture(folder)
            ingest_zip(folder, archive_path=archive, as_of=AS_OF)
            import sqlite3
            db = Path(folder) / "veri/invest_ai_evren.sqlite3"
            with sqlite3.connect(db) as conn:
                conn.execute("UPDATE companies SET status='ERROR',error='ValueError' "
                             "WHERE cik='0000000042'")
            events = []
            result = ingest_zip(folder, archive_path=archive, retry_errors=True,
                                progress=events.append)
            self.assertEqual(result["retries_attempted"], 1)
            self.assertEqual(result["retry_total"], 1)
            self.assertEqual(result["processed"], 2)
            self.assertTrue(all(event.get("processed", 0) <= event.get("total", 2)
                                for event in events))
            self.assertTrue(all(event.get("retry_attempted", 0) <= 1
                                for event in events))

    def test_no_download_when_local_zip_and_ticker_map_present(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.fixture(folder)
            result = run(folder, zip_path=archive, user_agent="")
            self.assertEqual(result["total"],2)

    def test_invalid_or_truncated_zip_is_not_database(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder)
            damaged = Path(folder) / "veri/broken.zip"
            damaged.write_bytes(b"not a real SEC zip")
            with self.assertRaises(zipfile.BadZipFile):
                ingest_zip(folder, archive_path=damaged, as_of=AS_OF)

    def test_unknown_missing_issuer_as_of_date(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=self.fixture(folder)
            ingest_zip(folder, archive_path=archive, as_of=AS_OF)
            self.assertEqual(datetime.fromisoformat(AS_OF).date().isoformat(), AS_OF)
            self.assertIsNone(next(row for row in load_bulk_grid(folder)["rows"]
                                   if row["ticker"]=="NONE")["fiscal_year"])


if __name__ == "__main__":
    unittest.main()
