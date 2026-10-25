"""Synthetic tests: SEC nightly companyfacts.zip -> SQLite full issuer universe."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from sec_piyasa_toplu_tarama import ingest_zip, load_bulk_grid, run
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
