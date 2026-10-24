"""Offline synthetic tests for ratios and their research-report integration."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from finansal_oranlar import compute_ratios, main
from finansal_tablolar import build_annual_statements
from sirket_analiz_paneli import render_financial_sections
from sirket_arastirma_akisi import build_company_research, render_company_research
from test_finansal_tablolar import AS_OF, company, fact

ROOT = Path(__file__).resolve().parents[1]


def ratios(data=None, end="2024-12-31"):
    statements = build_annual_statements(data or company(), as_of=AS_OF)
    result = compute_ratios(statements)
    return next(y["ratios"] for y in result["years"] if y["fiscal_year_end"] == end)


def values(result, *keys):
    return [result[k]["value"] for k in keys]


class RatioTests(unittest.TestCase):
    def test_profitability_and_growth(self):
        r = ratios()
        for key, expected in (("gross_margin", 500 / 1200), ("operating_margin", 260 / 1200),
                              ("net_margin", 200 / 1200), ("revenue_growth", 0.2),
                              ("operating_income_growth", 0.3)):
            self.assertAlmostEqual(r[key]["value"], expected, msg=key)
        self.assertEqual(r["gross_margin"]["inputs"], {"gross_profit": 500, "revenue": 1200})

    def test_cash_flow_ratios(self):
        r = ratios()
        for key, expected in (("fcf_margin", 180 / 1200), ("cash_conversion", 230 / 200),
                              ("capex_intensity", 50 / 1200), ("sbc_to_revenue", 8 / 1200),
                              ("shareholder_payout", 90 / 200)):
            self.assertAlmostEqual(r[key]["value"], expected, msg=key)

    def test_returns_use_average_balances_and_effective_tax(self):
        r = ratios()
        self.assertAlmostEqual(r["roa"]["value"], 200 / 1200)
        self.assertAlmostEqual(r["roe"]["value"], 200 / 640)
        self.assertAlmostEqual(r["effective_tax_rate"]["value"], 0.2)
        # invested capital: 700 + 300 - 150 = 850 and 580 + 210 - 120 = 670
        self.assertAlmostEqual(r["roic"]["value"], 260 * 0.8 / 760)

    def test_balance_sheet_ratios(self):
        r = ratios()
        self.assertAlmostEqual(r["current_ratio"]["value"], 2.0)
        self.assertAlmostEqual(r["debt_to_equity"]["value"], 300 / 700)
        self.assertEqual(r["net_debt"]["value"], 150)
        self.assertAlmostEqual(r["interest_coverage"]["value"], 260 / 12)

    def test_first_year_needs_prior_fiscal_year(self):
        r = ratios(end="2022-12-31")
        for key in ("revenue_growth", "roa", "roe", "roic"):
            self.assertEqual((r[key]["value"], r[key]["reason"]), (None, "PRIOR_FISCAL_YEAR_REQUIRED"), key)
        self.assertIsNotNone(r["gross_margin"]["value"])

    def test_gap_between_fiscal_years_blocks_comparisons(self):
        r = ratios(company(years=(2022, 2024)))
        self.assertEqual(values(r, "revenue_growth", "roe"), [None, None])
        self.assertEqual(r["revenue_growth"]["reason"], "PRIOR_FISCAL_YEAR_REQUIRED")

    def test_negative_equity_blocks_equity_ratios(self):
        data = company()
        equity = data["facts"]["us-gaap"]["StockholdersEquity"]["units"]["USD"]
        equity[1]["val"], equity[2]["val"] = -20, -50
        r = ratios(data)
        self.assertEqual(values(r, "roe", "debt_to_equity"), [None, None])
        self.assertEqual(r["roe"]["reason"], "NONPOSITIVE_DENOMINATOR:average_equity")

    def test_implausible_tax_rate_blocks_roic(self):
        data = company()
        data["facts"]["us-gaap"]["IncomeTaxExpenseBenefit"]["units"]["USD"][2]["val"] = 200
        r = ratios(data)
        self.assertEqual(r["effective_tax_rate"]["reason"], "TAX_RATE_OUTSIDE_0%_50%")
        self.assertEqual(r["roic"]["reason"], "INPUT_UNAVAILABLE:effective_tax_rate")

    def test_missing_input_named_in_reason(self):
        data = company()
        del data["facts"]["us-gaap"]["InterestExpense"]
        self.assertEqual(ratios(data)["interest_coverage"]["reason"], "INPUT_UNAVAILABLE:interest_expense")

    def test_unsupported_statements_rejected(self):
        with self.assertRaises(ValueError):
            compute_ratios({"version": "other"})


class ResearchIntegrationTests(unittest.TestCase):
    def research(self, data=None):
        return build_company_research(data or company(), as_of=AS_OF, expected_cik=77,
                                      sector="non_financial")

    def test_research_report_includes_statements_and_ratios(self):
        report = self.research()
        self.assertEqual(report["financial_statements"]["years"][0]["fiscal_year_end"], "2024-12-31")
        self.assertEqual(report["financial_ratios"]["cik"], report["cik"])
        page = render_company_research(report)
        self.assertIn("Finansal tablolar — yıllık 10-K (milyon USD)", page)
        self.assertIn("Finansal oranlar", page)
        self.assertIn("20.0%", page)  # revenue growth 2024

    def test_untrusted_sec_strings_are_escaped(self):
        data = company()
        data["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][2]["accn"] = "<script>x</script>"
        page = render_company_research(self.research(data))
        self.assertNotIn("<script>x", page)
        self.assertIn("&lt;script&gt;x", page)

    def test_alias_conflict_is_flagged_in_html(self):
        data = company()
        data["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [fact(1300, 2024)]}}
        page = render_company_research(self.research(data))
        self.assertIn("XBRL etiketleri birbirini tutmuyor", page)
        self.assertIn("çelişki", page)

    def test_report_without_statements_still_renders(self):
        report = self.research()
        del report["financial_statements"], report["financial_ratios"]
        self.assertNotIn("Finansal oranlar", render_company_research(report))

    def test_no_annual_data_section(self):
        statements = build_annual_statements({"cik": 77, "facts": {"us-gaap": {}}}, as_of=AS_OF)
        html = render_financial_sections(statements, compute_ratios(statements))
        self.assertIn("uygun yıllık 10-K verisi bulunamadı", html)

    def test_apple_demo_fy2025_values(self):
        raw = json.loads((ROOT / "ornekler/apple_ttm_evidence_2026-10-21.json").read_text(encoding="utf-8"))
        statements = build_annual_statements(raw, as_of="2026-10-21")
        year = statements["years"][0]
        self.assertEqual(year["fiscal_year_end"], "2025-09-27")
        self.assertEqual(year["income"]["revenue"]["value"], 416161000000)
        self.assertEqual(year["cash_flow"]["free_cash_flow"]["value"], 111482000000 - 12715000000)
        r = compute_ratios(statements)["years"][0]["ratios"]
        self.assertAlmostEqual(r["operating_margin"]["value"], 133050 / 416161)
        self.assertEqual(r["current_ratio"]["reason"], "INPUT_UNAVAILABLE:current_assets,current_liabilities")

    def test_cli_writes_statements_and_ratios(self):
        with tempfile.TemporaryDirectory() as folder:
            source, out = Path(folder) / "facts.json", Path(folder) / "out.json"
            source.write_text(json.dumps(company()), encoding="utf-8")
            main(["--companyfacts", str(source), "--as-of", AS_OF, "--years", "2", "--out", str(out)])
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(report["statements"]["years"]), 2)
            self.assertEqual(len(report["ratios"]["years"]), 2)


if __name__ == "__main__":
    unittest.main()
