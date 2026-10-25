"""Synthetic tests: coverage report, rebuild from the local ZIP and new SEC-derived screener columns."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from hisse_tarama_tablosu import ROW_SCHEMA, _lineup, financials_age_days
from sec_piyasa_toplu_tarama import (DB_REL, coverage_lines, coverage_report, ingest_zip, load_bulk_grid,
                                     main)
from sirket_arastirma_akisi import build_company_research
from test_finansal_tablolar import AS_OF, company, fact
from test_senaryo_degerleme import with_shares
from test_tahmin_motoru import five_year_company

DILUTED = "WeightedAverageNumberOfDilutedSharesOutstanding"


def four_year_company():
    """Five fiscal years 2020-2024 with weighted diluted shares 110 → 100."""
    data = five_year_company()
    data["facts"]["us-gaap"][DILUTED] = {"units": {"shares": [
        fact(v, y) for y, v in zip(range(2020, 2025), (110, 108, 105, 102, 100))]}}
    return data


def row_of(data):
    report = build_company_research(data, as_of=AS_OF, expected_cik=data["cik"], sector="non_financial",
                                    include_piotroski=False)
    return _lineup(report, ticker="SYN")


class ScreenerColumnTests(unittest.TestCase):
    def test_eps_growth_and_share_change_from_comparable_years(self):
        row = row_of(four_year_company())
        self.assertAlmostEqual(row["eps_diluted"], 136 / 100)
        self.assertAlmostEqual(row["eps_cagr_3y"], ((136 / 100) / (68.8 / 108)) ** (1 / 3) - 1)
        self.assertAlmostEqual(row["shares_change_3y"], 100 / 108 - 1)
        self.assertAlmostEqual(row["net_income_growth"], 136 / 115.2 - 1)
        self.assertEqual((row["financials_age_days"], row["row_schema"]), (60, ROW_SCHEMA))

    def test_losses_and_short_history_give_no_growth(self):
        data = four_year_company()
        income = data["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]
        next(r for r in income if r["fy"] == 2023)["val"] = -10
        next(r for r in income if r["fy"] == 2021)["val"] = -5
        row = row_of(data)
        self.assertIsNone(row["net_income_growth"])   # prior year was a loss
        self.assertIsNone(row["eps_cagr_3y"])         # base year was a loss
        self.assertAlmostEqual(row["shares_change_3y"], 100 / 108 - 1)
        gap = row_of(company(years=(2022, 2024)))     # 2023 missing: no one-year comparison
        self.assertIsNone(gap["net_income_growth"])
        short = row_of(company())                     # three fiscal years only
        self.assertIsNone(short["eps_cagr_3y"])
        self.assertAlmostEqual(short["eps_diluted"], 200 / 98)

    def test_shares_date_only_with_a_reported_share_count(self):
        self.assertEqual(row_of(with_shares())["shares_date"], "2025-01-31")
        self.assertIsNone(row_of(five_year_company())["shares_date"])

    def test_financials_age(self):
        self.assertEqual(financials_age_days("2026-10-25", "2025-12-31"), 298)
        self.assertIsNone(financials_age_days(None, "2025-12-31"))
        self.assertIsNone(financials_age_days("2026-10-25", "not-a-date"))


class BulkCoverageTests(unittest.TestCase):
    def fixture(self, root):
        folder = Path(root) / "veri"
        folder.mkdir()
        tickers = {"0": {"ticker": "SYN", "cik_str": 55, "title": "SYNTHETIC CO"},
                   "1": {"ticker": "OLD", "cik_str": 77, "title": "OLD FILER CO"},
                   "2": {"ticker": "NONE", "cik_str": 42, "title": "NO FACTS CO"}}
        (folder / "sec_ticker_esleme.json").write_text(json.dumps(tickers), encoding="utf-8")
        with zipfile.ZipFile(folder / "companyfacts.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("CIK0000000055.json", json.dumps(four_year_company()))
            archive.writestr("CIK0000000077.json", json.dumps(company()))
        return folder / "companyfacts.zip"

    def payloads(self, root):
        with sqlite3.connect(Path(root) / DB_REL) as conn:
            return {cik: json.loads(p) for cik, p in conn.execute("SELECT cik,payload FROM companies")}

    def test_coverage_counts_usable_values_per_column(self):
        with tempfile.TemporaryDirectory() as root:
            ingest_zip(root, archive_path=self.fixture(root), as_of="2026-10-25")
            report = coverage_report(root)
            self.assertEqual((report["ok_issuers"], report["snapshot_as_of"]), (2, "2026-10-25"))
            self.assertEqual(report["status_counts"], {"NO_COMPANYFACTS": 1, "OK": 2})
            columns = {c["key"]: c for c in report["columns"]}
            self.assertEqual((columns["roe"]["available"], columns["roe"]["share"]), (2, 1.0))
            self.assertEqual(columns["eps_cagr_3y"]["available"], 1)   # only the five-year issuer
            self.assertEqual(columns["pe"]["available"], 0)            # no price in SEC data
            inputs = {i["key"]: i["available"] for i in report["screen_inputs"]}
            self.assertEqual((inputs["peg"], inputs["roe_10_pb"]), (0, 0))
            # Both fiscal years end 2024-12-31: 663 days before the 2026-10-25 data date.
            self.assertEqual(report["stale_financials"], 2)
            self.assertEqual(report["rows_needing_rebuild"], 0)
            text = "\n".join(coverage_lines(report))
            self.assertIn("Finansalları işlenmiş şirket (OK): 2", text)
            self.assertIn("güncel olmayan): 2", text)
            self.assertNotIn("--rebuild", text)

    def test_roic_with_caution_is_not_counted_as_usable(self):
        with tempfile.TemporaryDirectory() as root:
            ingest_zip(root, archive_path=self.fixture(root), as_of=AS_OF)
            with sqlite3.connect(Path(root) / DB_REL) as conn:
                payload = json.loads(conn.execute("SELECT payload FROM companies WHERE cik='0000000055'").fetchone()[0])
                payload["roic_warning"] = True
                conn.execute("UPDATE companies SET payload=? WHERE cik='0000000055'", (json.dumps(payload),))
            report = coverage_report(root)
            roic = next(i for i in report["screen_inputs"] if i["key"] == "roic")
            self.assertEqual((roic["available"], report["roic_with_caution"]), (1, 1))

    def test_rebuild_recomputes_old_rows_from_the_local_zip(self):
        with tempfile.TemporaryDirectory() as root:
            archive = self.fixture(root)
            first = ingest_zip(root, archive_path=archive, as_of=AS_OF)
            with sqlite3.connect(Path(root) / DB_REL) as conn:
                old = json.loads(conn.execute("SELECT payload FROM companies WHERE cik='0000000055'").fetchone()[0])
                for key in ("row_schema", "eps_cagr_3y", "financials_age_days"):
                    old.pop(key)
                old["roe"] = 9.99
                conn.execute("UPDATE companies SET payload=? WHERE cik='0000000055'", (json.dumps(old),))
            self.assertEqual(coverage_report(root)["rows_needing_rebuild"], 1)
            self.assertIn("--rebuild", "\n".join(coverage_lines(coverage_report(root))))
            grid = {r["ticker"]: r for r in load_bulk_grid(root)["rows"]}
            self.assertIsNone(grid["SYN"]["eps_cagr_3y"])              # old row: column shown as missing
            self.assertEqual(grid["SYN"]["financials_age_days"], 60)     # computed at load time
            rebuilt = ingest_zip(root, archive_path=archive, rebuild=True)
            self.assertEqual(rebuilt["statuses"], first["statuses"])
            row = self.payloads(root)["0000000055"]
            self.assertEqual(row["row_schema"], ROW_SCHEMA)
            self.assertIsNotNone(row["eps_cagr_3y"])
            self.assertNotEqual(row["roe"], 9.99)
            self.assertEqual(coverage_report(root)["rows_needing_rebuild"], 0)

    def test_rebuild_is_refused_for_another_snapshot_or_with_retry(self):
        with tempfile.TemporaryDirectory() as root:
            archive = self.fixture(root)
            ingest_zip(root, archive_path=archive, as_of=AS_OF)
            with self.assertRaisesRegex(ValueError, "different SEC ZIP"):
                ingest_zip(root, archive_path=archive, as_of="2025-06-01", rebuild=True)
            with self.assertRaisesRegex(ValueError, "do not combine"):
                ingest_zip(root, archive_path=archive, rebuild=True, retry_errors=True)

    def test_cli_coverage_prints_turkish_summary(self):
        with tempfile.TemporaryDirectory() as root:
            ingest_zip(root, archive_path=self.fixture(root), as_of=AS_OF)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["--root", root, "--coverage"]), 0)
            self.assertIn("7 koşulun girdileri:", out.getvalue())
            with self.assertRaises(FileNotFoundError):
                coverage_report(Path(root) / "elsewhere")


if __name__ == "__main__":
    unittest.main()
