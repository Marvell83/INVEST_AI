"""Synthetic tests: dated, source-cited price import and price multiples in the full-market grid."""
from __future__ import annotations

import contextlib
from datetime import date
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from fiyat_katmani import (import_prices, main, normalize_ticker, pick_price, price_history, price_summary,
                           read_price_csv)
from hisse_tarama_tablosu import ROW_SCHEMA
from sec_piyasa_toplu_tarama import DB_REL, coverage_lines, coverage_report, ingest_zip, load_bulk_grid
from test_finansal_tablolar import company
from test_kapsam_raporu import four_year_company
from test_senaryo_degerleme import with_shares

TODAY = date(2026, 10, 25)
SOURCE = "Nasdaq stock screener CSV, synthetic test"
NASDAQ_HEADER = "Symbol,Name,Last Sale,Net Change,% Change,Market Cap,Country,IPO Year,Volume,Sector,Industry\n"


def write(folder, name, text):
    path = Path(folder) / name
    path.write_text(text, encoding="utf-8")
    return path


class PriceFileTests(unittest.TestCase):
    def test_ticker_normalization(self):
        self.assertEqual(normalize_ticker(" brk/b "), "BRK-B")
        self.assertEqual(normalize_ticker("BF.B"), "BF-B")
        for junk in ("BAC^K", "", "A B", "-X", "TOOLONGTICKER12345"):
            self.assertIsNone(normalize_ticker(junk), junk)

    def test_nasdaq_screener_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write(folder, "nasdaq.csv", NASDAQ_HEADER +
                         "AAPL,Apple Inc. Common Stock,$227.48,1.2,0.5%,3450000000000.00,United States,1980,1,"
                         "Technology,Computer Manufacturing\n"
                         "BRK/B,Berkshire Hathaway Class B,$455.10,0,0%,,United States,,1,Finance,Insurance\n"
                         "BAC^K,Bank of America preferred,$25.00,0,0%,0,United States,,1,Finance,Banks\n"
                         "ZERO,Zero Price Co,$0.00,0,0%,0,United States,,1,,\n"
                         "AAPL,Apple duplicate,$1.00,0,0%,0,United States,,1,,\n")
            rows, skipped = read_price_csv(path, price_date="2026-10-23", today=TODAY)
            by = {r["ticker"]: r for r in rows}
            self.assertEqual(set(by), {"AAPL", "BRK-B"})
            self.assertEqual((by["AAPL"]["price"], by["AAPL"]["price_date"]), (227.48, "2026-10-23"))
            self.assertEqual((by["AAPL"]["market_cap"], by["AAPL"]["sector"]), (3.45e12, "Technology"))
            self.assertIsNone(by["BRK-B"]["market_cap"])
            self.assertEqual(skipped, {"UNSUPPORTED_SYMBOL": 1, "INVALID_PRICE": 1, "DUPLICATE_SYMBOL_DATE": 1})

    def test_date_is_required_and_never_in_the_future(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write(folder, "nasdaq.csv", NASDAQ_HEADER + "AAPL,Apple,$227.48,0,0%,1,US,,1,Technology,X\n")
            with self.assertRaisesRegex(ValueError, "no date column"):
                read_price_csv(path, today=TODAY)
            with self.assertRaisesRegex(ValueError, "future"):
                read_price_csv(path, price_date="2026-10-26", today=TODAY)
            with self.assertRaisesRegex(ValueError, "ISO"):
                read_price_csv(path, price_date="23.10.2026", today=TODAY)

    def test_turkish_semicolon_csv_with_date_column(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write(folder, "fiyat.csv", "Hisse;Tarih;Kapanış\nAAPL;2026-10-23;227,48\n"
                                              "MSFT;2026-10-23;1.234,50\nKO;2026-12-01;60,1\nPG;23.10.2026;150\n")
            rows, skipped = read_price_csv(path, today=TODAY)
            by = {r["ticker"]: r["price"] for r in rows}
            self.assertEqual(by, {"AAPL": 227.48, "MSFT": 1234.5})
            self.assertEqual(skipped, {"FUTURE_DATE": 1, "INVALID_DATE": 1})

    def test_header_without_price_column_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "price column"):
                read_price_csv(write(folder, "x.csv", "Symbol,Name\nAAPL,Apple\n"), price_date="2026-10-23")

    def test_import_keeps_source_and_every_dated_price(self):
        with tempfile.TemporaryDirectory() as root:
            first = write(root, "a.csv", "ticker,date,close\nAAPL,2026-10-22,220\nMSFT,2026-10-22,400\n")
            second = write(root, "b.csv", "ticker,date,close\nAAPL,2026-10-23,227.48\n")
            with self.assertRaisesRegex(ValueError, "citation"):
                import_prices(root, first, source="short")
            result = import_prices(root, first, source=SOURCE, today=TODAY)
            self.assertEqual((result["imported"], result["dates"]), (2, ["2026-10-22", "2026-10-22"]))
            import_prices(root, second, source="Second synthetic source", today=TODAY)
            import_prices(root, second, source="Second synthetic source", today=TODAY)  # same day replaces
            history = price_history(root)
            self.assertEqual([r["price_date"] for r in history["AAPL"]], ["2026-10-23", "2026-10-22"])
            self.assertEqual((history["AAPL"][0]["price"], history["AAPL"][0]["source"]),
                             (227.48, "Second synthetic source"))
            self.assertEqual(history["MSFT"][0]["price_date"], "2026-10-22")
            summary = price_summary(root)
            self.assertEqual(summary["tickers"], 2)
            self.assertEqual(sum(i["rows"] for i in summary["imports"]), 3)
            self.assertEqual(price_history(Path(root) / "empty"), {})

    def test_price_nearest_the_sec_date_is_preferred(self):
        records = [{"price_date": "2026-11-30"}, {"price_date": "2026-10-28"}, {"price_date": "2026-10-20"}]
        self.assertEqual(pick_price(records, "2026-10-25", 10)["price_date"], "2026-10-28")
        self.assertEqual(pick_price(records, "2027-06-01", 10)["price_date"], "2026-11-30")  # none near: newest
        self.assertEqual(pick_price(records, None, 10)["price_date"], "2026-11-30")
        self.assertIsNone(pick_price([], "2026-10-25", 10))

    def test_cli_requires_a_source(self):
        with tempfile.TemporaryDirectory() as root:
            path = write(root, "a.csv", "ticker,date,close\nAAPL,2025-02-27,20\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(["--root", root, "--csv", str(path), "--source", SOURCE])
                main(["--root", root, "--summary"])
            self.assertIn('"imported": 1', out.getvalue())
            self.assertIn('"tickers": 1', out.getvalue())
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                main(["--root", root, "--csv", str(path)])


class GridValuationTests(unittest.TestCase):
    """Five-year issuer (SYN, SYN-B) with a 2025-01-31 cover-page count of 100 shares; old filer OLD."""

    def fixture(self, root, as_of="2025-03-01"):
        folder = Path(root) / "veri"
        folder.mkdir(exist_ok=True)
        tickers = {"0": {"ticker": "SYN", "cik_str": 55, "title": "SYNTHETIC CO"},
                   "1": {"ticker": "SYN-B", "cik_str": 55, "title": "SYNTHETIC CLASS B"},
                   "2": {"ticker": "OLD", "cik_str": 77, "title": "NO SHARE COUNT CO"}}
        (folder / "sec_ticker_esleme.json").write_text(json.dumps(tickers), encoding="utf-8")
        with zipfile.ZipFile(folder / "companyfacts.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("CIK0000000055.json", json.dumps(with_shares(four_year_company())))
            archive.writestr("CIK0000000077.json", json.dumps(company()))
        ingest_zip(root, archive_path=folder / "companyfacts.zip", as_of=as_of)

    def prices(self, root, text):
        import_prices(root, write(root, "p.csv", "ticker,date,close\n" + text), source=SOURCE, today=TODAY)

    def grid(self, root):
        return {r["ticker"]: r for r in load_bulk_grid(root)["rows"]}

    def test_aligned_price_fills_every_multiple(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            self.prices(root, "SYN,2025-02-27,20\nOLD,2025-02-27,5\n")
            data = load_bulk_grid(root)
            rows = {r["ticker"]: r for r in data["rows"]}
            syn = rows["SYN"]
            self.assertEqual((syn["valuation_status"], syn["market_cap"]), ("OK", 2000))
            self.assertEqual((syn["price_date"], syn["price_source"]), ("2025-02-27", SOURCE))
            self.assertAlmostEqual(syn["pe"], 2000 / 136)
            self.assertAlmostEqual(syn["pb"], 2000 / 640)
            self.assertAlmostEqual(syn["roe_10_pb"], syn["roe"] * 10 / (2000 / 640))
            self.assertAlmostEqual(syn["ev_ebit"], (2000 + 160) / 180)
            self.assertAlmostEqual(syn["fcf_yield"], (170 - 40) / 2000)
            self.assertAlmostEqual(syn["peg_historical"], syn["pe"] / (syn["eps_cagr_3y"] * 100))
            self.assertIsNone(syn["peg"])                                   # forward PEG never inferred
            self.assertEqual(rows["SYN-B"]["valuation_status"], "NO_PRICE")  # each share class priced alone
            self.assertIsNone(rows["SYN-B"]["pe"])
            self.assertEqual(rows["OLD"]["valuation_status"], "NO_SHARE_COUNT")
            self.assertIsNone(rows["OLD"]["market_cap"])
            self.assertEqual(data["priced_rows"], 2)
            self.assertEqual(data["valuation_counts"], {"NO_PRICE": 1, "NO_SHARE_COUNT": 1, "OK": 1})

    def test_price_far_from_the_sec_date_gives_no_multiples(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            self.prices(root, "SYN,2025-03-12,20\n")      # 11 days after the 2025-03-01 SEC date
            syn = self.grid(root)["SYN"]
            self.assertEqual(syn["valuation_status"], "PRICE_DATE_OUTSIDE_WINDOW")
            self.assertEqual(syn["market_price"], 20)
            self.assertIsNone(syn["pe"])
            self.prices(root, "SYN,2025-03-11,21\n")      # exactly 10 days: preferred and accepted
            syn = self.grid(root)["SYN"]
            self.assertEqual((syn["valuation_status"], syn["price_date"], syn["market_price"]),
                             ("OK", "2025-03-11", 21))

    def test_price_long_before_the_sec_date_gives_no_multiples(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            self.prices(root, "SYN,2025-02-18,20\n")      # 11 days before: later filings would leak in
            self.assertEqual(self.grid(root)["SYN"]["valuation_status"], "PRICE_DATE_OUTSIDE_WINDOW")

    def test_stale_financials_and_old_share_counts(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root, as_of="2026-10-25")       # fiscal 2024 is 663 days old at the price date
            self.prices(root, "SYN,2026-10-23,20\n")
            self.assertEqual(self.grid(root)["SYN"]["valuation_status"], "STALE_FINANCIALS")
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root, as_of="2025-09-01")       # share count from 2025-01-31: 213 days old
            self.prices(root, "SYN,2025-09-01,20\n")
            self.assertEqual(self.grid(root)["SYN"]["valuation_status"], "SHARE_COUNT_DATE_NOT_ALIGNED")

    def test_rows_from_an_older_version_need_a_rebuild(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            with sqlite3.connect(Path(root) / DB_REL) as conn:
                payload = json.loads(conn.execute("SELECT payload FROM companies WHERE cik='0000000055'").fetchone()[0])
                payload["row_schema"] = ROW_SCHEMA - 1
                conn.execute("UPDATE companies SET payload=? WHERE cik='0000000055'", (json.dumps(payload),))
            self.prices(root, "SYN,2025-02-27,20\n")
            syn = self.grid(root)["SYN"]
            self.assertEqual((syn["valuation_status"], syn["pe"]), ("ROW_NEEDS_REBUILD", None))

    def test_coverage_counts_valuation_by_issuer(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            self.prices(root, "SYN,2025-02-27,20\n")
            report = coverage_report(root)
            self.assertEqual(report["valuation_counts"], {"NO_PRICE": 1, "OK": 1})
            columns = {c["key"]: c["available"] for c in report["columns"]}
            self.assertEqual((columns["pe"], columns["peg_historical"], columns["peg"]), (1, 1, 0))
            inputs = {i["key"]: i["available"] for i in report["screen_inputs"]}
            self.assertEqual(inputs["roe_10_pb"], 1)
            self.assertIn("Fiyat ve değerleme: fiyat yok 1, uyumlu fiyat 1", "\n".join(coverage_lines(report)))


if __name__ == "__main__":
    unittest.main()
