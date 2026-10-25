"""Synthetic tests: SEC issuer profiles (SIC) and the SEC-only quality screen report."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from sec_eleme_raporu import judge, main, passed_csv, render_html, screen
from sec_piyasa_toplu_tarama import fetch_bulk_zip, ingest_zip
from sec_sirket_profili import (SUBMISSIONS_URL, import_profiles, is_financial, load_profiles, parse_profile,
                                sic_division)
from test_kapsam_raporu import BulkCoverageTests

RATE = 0.045
GOOD = {"roe": 0.25, "roic": 0.20, "net_debt_to_ebitda": 0.5, "cash_conversion_3y": 1.2, "fcf_3y": 300.0}


def issuer(cik, **values):
    row = {"cik": f"{cik:010d}", "ticker": f"T{cik}", "company": f"CO {cik}", "as_of": "2026-10-25",
           "fiscal_year": "2025-12-31", "revenue": 1e9, **GOOD}
    row.update(values)
    return row


def profile(cik, sic, description="Services-Prepackaged Software"):
    return {"cik": f"{cik:010d}", "sic": sic, "sic_description": description, "division": sic_division(sic),
            "financial": is_financial(sic), "exchanges": "Nasdaq"}


class ProfileTests(unittest.TestCase):
    def test_sic_divisions_and_financial_boundary(self):
        self.assertEqual(sic_division(7372), "Hizmetler")
        self.assertEqual(sic_division(3674), "İmalat")
        self.assertEqual(sic_division(None), "Bilinmiyor")
        self.assertEqual([is_financial(s) for s in (5999, 6000, 6798, 6799, 6800, None)],
                         [False, True, True, True, False, False])

    def test_parse_submissions_profile(self):
        p = parse_profile({"cik": "320193", "name": "Apple Inc.", "sic": "3571",
                           "sicDescription": "Electronic Computers", "entityType": "operating",
                           "exchanges": ["Nasdaq"], "tickers": ["AAPL"], "fiscalYearEnd": "0926",
                           "category": "Large Accelerated Filer"})
        self.assertEqual((p["cik"], p["sic"], p["division"], p["financial"]), ("0000320193", 3571, "İmalat", False))
        self.assertEqual((p["exchanges"], p["tickers"], p["fiscal_year_end"]), ("Nasdaq", "AAPL", "0926"))
        self.assertIsNone(parse_profile({"cik": "x"}))
        self.assertIsNone(parse_profile({"cik": 1, "sic": ""})["sic"])

    def test_import_profiles_reads_only_screened_issuers(self):
        with tempfile.TemporaryDirectory() as root:
            ingest_zip(root, archive_path=BulkCoverageTests().fixture(root), as_of="2025-03-01")
            archive = Path(root) / "veri" / "submissions.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("CIK0000000055.json", json.dumps({"cik": "55", "sic": "7372",
                                                             "sicDescription": "Prepackaged Software"}))
                z.writestr("CIK0000000055-submissions-001.json", json.dumps({"filings": []}))
                z.writestr("CIK0000000077.json", json.dumps({"cik": "99", "sic": "6022"}))  # wrong issuer
                z.writestr("CIK0000000123.json", json.dumps({"cik": "123", "sic": "1000"}))  # not screened
            result = import_profiles(root)
            self.assertEqual((result["issuers"], result["profiles"], result["not_in_zip"]), (3, 1, 1))
            self.assertEqual(result["skipped"], {"CIK_MISMATCH_OR_INVALID": 1})
            profiles = load_profiles(root)
            self.assertEqual(list(profiles), ["0000000055"])
            self.assertEqual((profiles["0000000055"]["sic"], profiles["0000000055"]["financial"]), (7372, False))
            self.assertEqual(load_profiles(Path(root) / "none"), {})

    def test_submissions_download_uses_its_own_url(self):
        seen = []

        class Done(Exception):
            pass

        def opener(request, timeout):
            seen.append(request.full_url)
            raise Done
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(Done), \
                mock.patch("sec_piyasa_toplu_tarama.shutil.disk_usage",
                                    return_value=type("U", (), {"free": 10**10})()):
            fetch_bulk_zip(Path(folder) / "s.zip", user_agent="INVEST_AI Research a@b.co", opener=opener,
                           url=SUBMISSIONS_URL)
        self.assertEqual(seen, [SUBMISSIONS_URL])


class ScreenTests(unittest.TestCase):
    def test_conditions_pass_fail_and_pending(self):
        self.assertEqual(judge(issuer(1), RATE)[1], "PASS")
        checks, overall = judge(issuer(2, net_debt_to_ebitda=2.5, fcf_3y=None), RATE)
        self.assertEqual((checks["net_debt_to_ebitda"], checks["fcf_3y"], overall), ("FAIL", "PENDING", "FAIL"))
        checks, overall = judge(issuer(3), None)          # no reference rate: ROE / ROIC wait
        self.assertEqual((checks["roe"], checks["roic"], overall), ("PENDING", "PENDING", "PENDING"))
        self.assertEqual(judge(issuer(4, net_debt_to_ebitda=-3.0), RATE)[1], "PASS")   # net cash
        self.assertEqual(judge(issuer(5, cash_conversion_3y=1.0, net_debt_to_ebitda=2.0), RATE)[1], "PASS")
        self.assertEqual(judge(issuer(6, roe=0.045), RATE)[0]["roe"], "FAIL")          # must exceed the rate

    def test_funnel_sector_size_and_staleness(self):
        rows = [issuer(1), issuer(2, fiscal_year="2024-06-30"), issuer(3), issuer(4, revenue=10e6),
                issuer(5, roic=0.9, roic_warning=True), issuer(6, cash_conversion_3y=0.7), issuer(7)]
        profiles = {p["cik"]: p for p in (profile(1, 7372), profile(2, 7372), profile(3, 6022, "National Banks"),
                                          profile(4, 2834), profile(5, 3571, "Electronic Computers"),
                                          profile(6, 2834))}
        result = screen(rows, profiles, rate=RATE)
        self.assertEqual([s["count"] for s in result["funnel"]], [7, 6, 5, 4, 3])
        self.assertIn("1 şirketin SEC profili yok", result["funnel"][2]["note"])
        self.assertEqual(result["overall"], {"PASS": 3, "FAIL": 1, "PENDING": 0})
        self.assertEqual([r["ticker"] for r in result["passed"]], ["T5", "T1", "T7"])   # by ROIC
        self.assertEqual(result["passed"][2]["sector"], "Sektör bilinmiyor")
        self.assertEqual(result["by_division"], {"Hizmetler": 1, "İmalat": 1, "Bilinmiyor": 1})
        self.assertEqual(result["roic_cautions_among_passed"], 1)
        top = result["highlights"]["En yüksek ROIC (uyarısız)"]
        self.assertNotIn("T5", [r["ticker"] for r in top])
        cash = next(c for c in result["conditions"] if c["key"] == "cash_conversion_3y")
        self.assertEqual((cash["PASS"], cash["FAIL"]), (3, 1))

    def test_quality_growth_highlight(self):
        rows = [issuer(1, revenue_cagr_3y=0.12, shares_change_3y=-0.02),
                issuer(2, revenue_cagr_3y=0.12, shares_change_3y=0.20),      # heavy dilution
                issuer(3, revenue_cagr_3y=0.05),                             # slow growth
                issuer(4, revenue_cagr_3y=0.30, roic=0.10)]                  # low ROIC
        result = screen(rows, {}, rate=RATE)
        title = next(t for t in result["highlights"] if t.startswith("Kalite + büyüme"))
        self.assertEqual([r["ticker"] for r in result["highlights"][title]], ["T1"])

    def test_html_and_csv_are_escaped(self):
        result = screen([issuer(1, company="<script>x</script>", ticker="=EVIL")], {}, rate=RATE)
        page = render_html(result, as_of="2026-10-25")
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>x", page)
        self.assertIn("referans faiz %4.50", page.replace(",", "."))
        text = passed_csv(result)
        self.assertIn("'=EVIL", text)
        self.assertIn(";25,0;20,0;", text)   # ROE and ROIC as percentages with a decimal comma

    def test_cli_writes_report_files(self):
        with tempfile.TemporaryDirectory() as root:
            ingest_zip(root, archive_path=BulkCoverageTests().fixture(root), as_of="2025-03-01")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(["--root", root, "--rate", "4.5", "--min-revenue", "0", "--out", str(Path(root) / "r" / "eleme")])
            self.assertIn("SEC finansalları işlenmiş şirketler (OK)", out.getvalue())
            data = json.loads((Path(root) / "r" / "eleme.json").read_text(encoding="utf-8"))
            self.assertEqual((data["rate"], data["as_of"]), (0.045, "2025-03-01"))
            self.assertTrue((Path(root) / "r" / "eleme.html").is_file())
            self.assertTrue((Path(root) / "r" / "eleme.csv").read_text(encoding="utf-8").startswith("﻿Hisse"))


if __name__ == "__main__":
    unittest.main()
