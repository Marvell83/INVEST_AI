"""Offline source-linked fundamentals grid: no SEC or market calls in tests."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from hisse_tarama_tablosu import COLUMNS, _lineup, load_screening
from sirket_arastirma_akisi import build_company_research
from test_finansal_tablolar import AS_OF, company
from test_senaryo_degerleme import with_shares


def research(data=None, sector="non_financial", price=None, as_of=AS_OF):
    payload = data or company()
    report = build_company_research(payload, as_of=as_of, expected_cik=payload["cik"],
                                    sector=sector, include_piotroski=False)
    if price is not None:
        report["implied_growth"] = {"status": "NO_UNIQUE_SOLUTION",
                                    "price": {"value": price, "date": as_of,
                                              "source": "Source cited synthetic closing price"}}
    return report


class FinancialScreenerTests(unittest.TestCase):
    def test_wide_ratio_columns_and_comparable_three_years(self):
        r = _lineup(research(), ticker="SYN")
        self.assertEqual(r["ticker"], "SYN")
        self.assertEqual(r["fiscal_year"], "2024-12-31")
        self.assertAlmostEqual(r["roe"], 200 / 640)
        self.assertAlmostEqual(r["operating_margin"], 260 / 1200)
        self.assertAlmostEqual(r["cash_conversion_3y"], (130+180+230)/(112+152+200))
        self.assertEqual(r["fcf_3y"], (130-30)+(180-40)+(230-50))
        self.assertIsNone(r["revenue_cagr_3y"])  # only 3 annual observations
        self.assertIsNone(r["market_cap"])
        self.assertIsNone(r["peg"])
        self.assertIsNone(r["shares_change_3y"])
        self.assertGreaterEqual(len(COLUMNS), 45)

    def test_price_multiples_missing_without_shares_and_forward_growth(self):
        r = _lineup(research(price=10), ticker="SYN")
        self.assertEqual(r["market_price"], 10)
        self.assertIsNone(r["market_cap"])
        for field in ("pe", "pb", "ps", "ev_ebit", "roe_10_pb", "peg", "fcf_yield"):
            self.assertIsNone(r[field])

    def test_dated_analyst_price_can_calculate_multiples_if_shares_available(self):
        data = with_shares()
        r = _lineup(research(data, price=25), ticker="SHR")
        self.assertEqual(r["market_price"], 25)
        self.assertIsNotNone(r["market_cap"])
        self.assertIsNotNone(r["pe"])
        self.assertIsNotNone(r["pb"])
        self.assertAlmostEqual(r["roe_10_pb"], r["roe"] * 10 / r["pb"])
        self.assertIsNone(r["peg"])  # never infer PEG from historical revenue growth
        self.assertEqual(r["price_source"], "Source cited synthetic closing price")

    def test_later_price_does_not_backfill_old_snapshot(self):
        r = research(with_shares(), price=25)
        r["implied_growth"]["price"]["date"] = "2026-12-31"
        out = _lineup(r, ticker="SHR")
        self.assertEqual(out["market_price"], 25)
        self.assertIsNone(out["market_cap"])
        self.assertIsNone(out["pe"])

    def test_latest_report_per_company_kept_and_missing_is_null(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dest = root / "reports" / "research"
            dest.mkdir(parents=True)
            a = research()
            b = research(price=11)
            (dest / "SYN_CACHE_2025-03-01_unknown_111_fundamentals.json").write_text(
                json.dumps(a), encoding="utf-8")
            (dest / "SYN_LIVE_2025-03-01_non_financial_222_fundamentals.json").write_text(
                json.dumps(b), encoding="utf-8")
            data = load_screening(root)
            self.assertEqual(data["available"], 1)
            self.assertEqual(data["rows"][0]["ticker"], "SYN")
            self.assertEqual(data["rows"][0]["market_price"], 11)
            self.assertEqual(data["rows"][0]["source_mode"], "offline_file")
            self.assertFalse(data["market_price_fetched"])


if __name__ == "__main__":
    unittest.main()
