"""Offline synthetic tests: reverse DCF on the valued base scenario."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from degerleme_v02 import degerle_v02
from invest_ai_web import RequestError
from senaryo_degerleme import _engine_inputs, _history_position, implied_growth, main
from sirket_arastirma_akisi import build_company_research, render_company_research
from test_finansal_tablolar import AS_OF
from test_senaryo_degerleme import value, with_shares
from test_tahmin_motoru import five_year_company
from test_web_senaryo import DISCOUNT, GROWTH, REQUEST, five_service

PRICE = dict(price_source="Synthetic closing price source", price_date=AS_OF)


def reverse(price, **kwargs):
    valuation, projection, baseline = value()
    result = implied_growth(projection, baseline, valuation, price=price, **dict(PRICE, **kwargs))
    return result, valuation, projection, baseline


class ImpliedGrowthTests(unittest.TestCase):
    def test_implied_growth_reproduces_the_price(self):
        result, valuation, projection, _ = reverse(20.0)
        self.assertEqual(result["status"], "OK")
        engine = _engine_inputs(projection, "baz", valuation["inputs"])
        repriced = degerle_v02(dict(engine, buyume=result["implied_growth"]))["hisse_basi_deger"]
        self.assertAlmostEqual(repriced, 20.0, places=5)
        self.assertEqual((result["scenario"], result["years"]), ("baz", 5))
        self.assertFalse(result["search"]["all_roots_guaranteed"])

    def test_higher_price_implies_higher_growth(self):
        low, high = reverse(12.0)[0], reverse(25.0)[0]
        self.assertLess(low["implied_growth"], high["implied_growth"])

    def test_position_against_company_history(self):
        result = reverse(30.0)[0]
        self.assertEqual(result["history_position"]["band"], "ABOVE_HISTORY")
        self.assertEqual(result["history_position"]["n"], 4)
        self.assertEqual(result["history_position"]["share_of_years_below"], 1.0)

    def test_unreachable_price_has_no_unique_solution(self):
        result = reverse(0.01)[0]
        self.assertEqual(result["status"], "NO_UNIQUE_SOLUTION")
        self.assertNotIn("implied_growth", result)

    def test_needs_a_valuation(self):
        valuation, projection, baseline = value(five_year_company())   # shares missing
        self.assertEqual(implied_growth(projection, baseline, valuation, price=10.0, **PRICE)["status"],
                         "VALUATION_UNAVAILABLE")

    def test_price_inputs_validated(self):
        for kwargs in (dict(price=0), dict(price=-1), dict(price=True), dict(price=float("nan")),
                       dict(price=10, price_source="short"), dict(price=10, price_date="01.03.2025")):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                reverse(**kwargs)

    def test_nonpositive_price_rejected_with_clear_message(self):
        for price in (0, -5):
            with self.subTest(price=price), self.assertRaisesRegex(ValueError, "positive per-share"):
                reverse(price)

    def test_price_date_warnings(self):
        self.assertEqual(reverse(20.0, price_date=AS_OF)[0]["warnings"], [])
        self.assertEqual(reverse(20.0, price_date="2025-03-02")[0]["warnings"], ["PRICE_AFTER_SEC_AS_OF"])
        self.assertEqual(reverse(20.0, price_date="2025-03-05")[0]["warnings"], ["PRICE_AFTER_SEC_AS_OF"])
        self.assertEqual(reverse(20.0, price_date="2025-04-15")[0]["warnings"],
                         ["PRICE_AFTER_SEC_AS_OF", "PRICE_DATE_FAR_FROM_SEC_AS_OF"])
        self.assertEqual(reverse(20.0, price_date="2025-01-01")[0]["warnings"], ["PRICE_DATE_FAR_FROM_SEC_AS_OF"])


class HistoryPositionTests(unittest.TestCase):
    def test_bands(self):
        history = [0.0, 0.1, 0.2, 0.3, 0.4]      # q1 = 0.1, q3 = 0.3
        for growth, band in ((-0.1, "BELOW_HISTORY"), (0.05, "BELOW_Q1"), (0.2, "WITHIN_Q1_Q3"),
                             (0.35, "ABOVE_Q3"), (0.5, "ABOVE_HISTORY")):
            with self.subTest(growth=growth):
                self.assertEqual(_history_position(growth, history)["band"], band)
        self.assertEqual(_history_position(0.25, history)["share_of_years_below"], 0.6)
        self.assertEqual(_history_position(0.1, [])["band"], "NO_HISTORY")


class ReportAndInterfaceTests(unittest.TestCase):
    INPUTS = dict(long_run_growth=0.03, long_run_growth_source="Synthetic long run",
                  discount_rate=0.09, discount_rate_source="Synthetic WACC source")

    def research(self, **kwargs):
        return build_company_research(with_shares(), as_of=AS_OF, expected_cik=55, sector="non_financial",
                                      **dict(self.INPUTS, **kwargs))

    def test_report_section(self):
        report = self.research(market_price=30.0, market_price_source="<b>Synthetic</b> close",
                               market_price_date=AS_OF)
        self.assertEqual(report["implied_growth"]["status"], "OK")
        page = render_company_research(report)
        self.assertIn("Ters DCF — fiyatın ima ettiği büyüme", page)
        self.assertIn("4 yıllık büyüme gözleminin en yükseğinin", page)
        self.assertIn("&lt;b&gt;Synthetic&lt;/b&gt; close", page)

    def test_report_requires_all_price_inputs_and_a_valuation(self):
        with self.assertRaises(ValueError):
            self.research(market_price=30.0)
        with self.assertRaises(ValueError):
            build_company_research(with_shares(), as_of=AS_OF, expected_cik=55, sector="non_financial",
                                   long_run_growth=0.03, long_run_growth_source="Synthetic long run",
                                   market_price=30.0, market_price_source="Synthetic close", market_price_date=AS_OF)
        self.assertIsNone(self.research()["implied_growth"])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            source, out = Path(folder) / "facts.json", Path(folder) / "out.json"
            source.write_text(json.dumps(with_shares()), encoding="utf-8")
            main(["--companyfacts", str(source), "--as-of", AS_OF, "--long-run-growth", "0.03",
                  "--long-run-source", "Synthetic long run", "--discount-rate", "0.09",
                  "--discount-source", "Synthetic WACC source", "--price", "20", "--price-date", AS_OF,
                  "--price-source", "Synthetic close price", "--out", str(out)])
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["implied_growth"]["status"], "OK")

    def test_web_request(self):
        price = {"market_price": 30.0, "market_price_date": "2025-10-24",
                 "market_price_source": "Sentetik kapanış fiyatı kaynağı"}
        with tempfile.TemporaryDirectory() as folder:
            s = five_service(folder)
            answer = s.analyze({**REQUEST, **GROWTH, **DISCOUNT, **price})
            self.assertEqual(answer["implied_growth_status"], "OK")
            self.assertIsInstance(answer["implied_growth"], float)
            bad = ({"market_price": 30.0},
                   {**price, "market_price_date": "2025-10-26"},            # after the server's today
                   {**price, "market_price_date": "24.10.2025"},
                   {**price, "market_price_date": "2025-02-30"},
                   {**price, "market_price": 0},
                   {**price, "market_price_source": "kısa"})
            for extra in bad:
                with self.subTest(extra=extra), self.assertRaises(RequestError):
                    s.analyze({**REQUEST, **GROWTH, **DISCOUNT, **extra})
            with self.assertRaisesRegex(RequestError, "iskonto"):
                s.analyze({**REQUEST, **GROWTH, **price})

    def test_form_fields(self):
        page = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
        for element in ("analysis-price", "analysis-price-date", "analysis-price-source"):
            self.assertIn(f'id="{element}"', page)
        self.assertIn("body.market_price_date = priceDate", page)
        self.assertIn("Sistem fiyat indirmez", page)


if __name__ == "__main__":
    unittest.main()
