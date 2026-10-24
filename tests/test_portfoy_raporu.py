"""Offline presentation regression tests; no browser or network required."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from portfoy_risk import analyze_portfolio
from portfoy_raporu import main, render_portfolio_html

SOURCE = (Path(__file__).resolve().parent.parent /
          "ornekler/portfoy_risk_SENTETIK_8_HISSE.json")


def report():
    return analyze_portfolio(json.loads(SOURCE.read_text(encoding="utf-8")))


class PortfolioHTMLTests(unittest.TestCase):
    def test_html_contains_values_without_claiming_live_prices(self):
        h = render_portfolio_html(report())
        self.assertIn("3.000,00", h)
        self.assertIn("2.370,00", h)
        self.assertIn("AI gibi", h)
        self.assertIn("INVEST_AI | Portföy Risk Analizi", h)
        self.assertIn("kullanıcı tarafından", h)
        self.assertNotIn("<script", h.lower())

    def test_html_escapes_untrusted_text_fields(self):
        d = report()
        d["warnings"].append('<script>alert("x")</script>')
        d["positions"][0]["price_source"] = '"><img src=x onerror=alert(1)>'
        d["sector_allocation"][0]["label"] = '<svg onload=alert(1)>'
        d["scenarios"][0]["name"] = "<script>evil()</script>"
        h = render_portfolio_html(d)
        self.assertNotIn("<script>", h)
        self.assertNotIn("<svg onload=", h)
        self.assertIn("&lt;script&gt;evil()&lt;/script&gt;", h)
        self.assertIn("&lt;svg onload=alert(1)&gt;", h)

    def test_reject_wrong_schema(self):
        d = report()
        d["schema_version"] = "other"
        with self.assertRaisesRegex(ValueError, "supported"):
            render_portfolio_html(d)

    def test_no_fx_or_scenario_still_valid(self):
        d = report()
        d["fx_usdtry"] = None
        d["scenarios"] = []
        h = render_portfolio_html(d)
        self.assertIn("Veri bulunmuyor", h)
        self.assertNotIn("Güncel TL karşılığı:", h)

    def test_nonfinite_number_rejected(self):
        d = report()
        d["total_market_value_usd"] = float("nan")
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            render_portfolio_html(d)

    def test_cli_writes_offline_html(self):
        with tempfile.TemporaryDirectory() as folder:
            source, destination = (Path(folder) / n for n in ("report.json", "portfolio.html"))
            source.write_text(json.dumps(report(), ensure_ascii=False), encoding="utf-8")
            main(["--report", str(source), "--out", str(destination)])
            h = destination.read_text(encoding="utf-8")
            self.assertTrue(h.startswith("<!doctype html>"))
            self.assertIn("NVDA", h)


if __name__ == "__main__":
    unittest.main()
