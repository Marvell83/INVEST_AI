"""Offline synthetic tests for the rules added after the first real SEC data check.

- share-based compensation reads only the cash-flow add-back concept,
- revenue aliases up to 5% apart use the priority alias with a visible note,
- without a reported operating income an approximate EBIT (pretax + interest) is derived.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from finansal_oranlar import OPERATING_INCOME_RATIOS, compute_ratios
from finansal_tablolar import build_annual_statements, build_quarterly_statements
from katman_mutabakati import layer_health
from sirket_arastirma_akisi import build_company_research
from sirket_analiz_paneli import render_financial_sections, render_forecast_section, render_quarterly_section
from tahmin_defteri import TahminDefteri
from tahmin_motoru import historical_baseline, project_scenarios, record_projection
from test_finansal_ceyrekler import company as quarterly_company, flows as quarterly_flows
from test_finansal_tablolar import AS_OF, company, fact, row
from test_senaryo_degerleme import value, with_shares
from test_tahmin_motoru import LONG_RUN, five_year_company

PRETAX = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"


def build(data):
    return build_annual_statements(data, as_of=AS_OF)


def with_revenues(value, year=2024):
    data = company()
    data["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [fact(value, year)]}}
    return data


def without_operating_income(data=None, years=None):
    data = data or company()
    rows = data["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"]
    rows[:] = [r for r in rows if years is not None and r["fy"] not in years]
    return data


class ShareBasedCompensationTests(unittest.TestCase):
    def test_allocated_expense_is_not_an_alias(self):
        data = company()
        data["facts"]["us-gaap"]["AllocatedShareBasedCompensationExpense"] = {"units": {"USD": [fact(12, 2024)]}}
        cell = row(build(data))["cash_flow"]["share_based_compensation"]
        self.assertEqual((cell["status"], cell["value"], cell["concept"]), ("REPORTED", 8, "ShareBasedCompensation"))
        self.assertNotIn("agreeing_aliases", cell)
        del data["facts"]["us-gaap"]["ShareBasedCompensation"]
        self.assertEqual(row(build(data))["cash_flow"]["share_based_compensation"]["status"], "MISSING")


class RevenueAliasTests(unittest.TestCase):
    def test_gap_up_to_five_percent_uses_priority_alias_and_stays_visible(self):
        result = build(with_revenues(1224))
        cell = row(result)["income"]["revenue"]
        self.assertEqual((cell["status"], cell["value"]), ("REPORTED", 1200))
        self.assertEqual(cell["concept"], "RevenueFromContractWithCustomerExcludingAssessedTax")
        self.assertAlmostEqual(cell["alias_gap"]["spread"], 24 / 1224)
        self.assertEqual(cell["alias_gap"]["other_aliases"],
                         [{"concept": "Revenues", "value": 1224, "accession": "a2024"}])
        self.assertNotIn("agreeing_aliases", cell)
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(result["alias_gaps"], [{
            "start": "2024-01-01", "end": "2024-12-31", "item": "revenue", "spread": 24 / 1224,
            "used": "RevenueFromContractWithCustomerExcludingAssessedTax", "others": ["Revenues"]}])
        self.assertEqual(row(result)["income"]["gross_profit"]["value"], 500)

    def test_five_percent_boundary(self):
        noted = row(build(with_revenues(1263)))["income"]["revenue"]   # 4.99 %
        self.assertEqual(noted["status"], "REPORTED")
        conflict = row(build(with_revenues(1264)))["income"]["revenue"]  # 5.06 %
        self.assertEqual(conflict["status"], "CONFLICT")

    def test_agreeing_aliases_carry_no_gap(self):
        cell = row(build(with_revenues(1205)))["income"]["revenue"]   # 0.41 %
        self.assertEqual(cell["agreeing_aliases"], ["Revenues"])
        self.assertNotIn("alias_gap", cell)

    def test_other_items_keep_the_half_percent_rule(self):
        data = company()
        data["facts"]["us-gaap"]["CostOfGoodsAndServicesSold"] = {"units": {"USD": [fact(710, 2024)]}}
        self.assertEqual(row(build(data))["income"]["cost_of_revenue"]["status"], "CONFLICT")

    def test_ytd_derived_quarter_keeps_the_gap(self):
        data = quarterly_company()
        data["facts"]["us-gaap"]["Revenues"] = quarterly_flows((1210, "2024-01-01", "2024-12-31"))
        quarterly = build_quarterly_statements(data, as_of="2025-09-01")
        q4 = next(q for q in quarterly["quarters"] if q["end"] == "2024-12-31")
        cell = q4["income"]["revenue"]
        self.assertEqual((cell["status"], cell["value"]), ("DERIVED", 330))
        self.assertEqual(cell["alias_gap"]["other_aliases"][0]["concept"], "Revenues")
        self.assertEqual([g["end"] for g in quarterly["alias_gaps"]], ["2024-12-31"])
        page = render_quarterly_section(quarterly)
        self.assertIn("‡ 1 dönemde gelir etiketleri", page)

    def test_html_marks_the_cell_and_explains_the_rule(self):
        statements = build(with_revenues(1224))
        page = render_financial_sections(statements, compute_ratios(statements))
        self.assertIn("0‡</td>", page)
        self.assertIn("diğer etiket Revenues = 0 (fark %1,96)", page)
        self.assertIn("‡ 1 dönemde gelir etiketleri en çok %1,96 ayrışıyor", page)
        self.assertNotIn("XBRL etiketleri birbirini tutmuyor", page)


class OperatingIncomeProxyTests(unittest.TestCase):
    def test_pretax_plus_interest_when_operating_income_is_not_reported(self):
        result = build(without_operating_income())
        cell = row(result)["income"]["operating_income"]
        self.assertEqual((cell["status"], cell["value"], cell["approximate"]), ("DERIVED", 262, True))
        self.assertEqual(cell["method"], "EBIT_PROXY_PRETAX_PLUS_INTEREST")
        self.assertEqual((cell["accession"], cell["filed"], cell["sources"]), ("a2024", "2025-02-15", ["a2024"]))
        self.assertEqual(cell["derivation"], {"pretax_income": PRETAX, "interest_expense": "InterestExpense"})
        self.assertIn("non-operating", cell["includes"])
        self.assertEqual([a["end"] for a in result["approximations"]],
                         ["2024-12-31", "2023-12-31", "2022-12-31"])
        self.assertEqual(result["coverage"]["operating_income"], {"available": 3, "conflicts": 0})

    def test_layer_health_shows_the_latest_operating_income_basis(self):
        def basis(data):
            research = build_company_research(data, as_of=AS_OF, expected_cik=77, sector="non_financial")
            return layer_health(research)["latest_operating_income"]
        self.assertEqual(basis(without_operating_income()), "APPROXIMATE")
        self.assertEqual(basis(company()), "REPORTED")

    def test_reported_operating_income_is_never_replaced(self):
        result = build(company())
        cell = row(result)["income"]["operating_income"]
        self.assertEqual((cell["status"], cell["value"]), ("REPORTED", 260))
        self.assertNotIn("approximate", cell)
        self.assertEqual(result["approximations"], [])

    def test_inputs_from_different_filings_or_missing_give_no_proxy(self):
        data = without_operating_income()
        data["facts"]["us-gaap"]["InterestExpense"]["units"]["USD"][2]["accn"] = "elsewhere"
        cell = row(build(data))["income"]["operating_income"]
        self.assertEqual((cell["status"], cell["value"]), ("MISSING", None))
        self.assertEqual(cell["proxy_unavailable"], "PRETAX_AND_INTEREST_FROM_DIFFERENT_FILINGS")
        del data["facts"]["us-gaap"]["InterestExpense"]
        cell = row(build(data))["income"]["operating_income"]
        self.assertEqual(cell["proxy_unavailable"], "PRETAX_OR_INTEREST_UNAVAILABLE")

    def test_ratios_using_the_proxy_are_flagged(self):
        statements = build(without_operating_income())
        ratios = compute_ratios(statements)["years"][0]["ratios"]
        self.assertAlmostEqual(ratios["operating_margin"]["value"], 262 / 1200)
        for key in OPERATING_INCOME_RATIOS:
            self.assertEqual(ratios[key]["approximate"], "OPERATING_INCOME_PROXY", key)
        self.assertNotIn("approximate", ratios["net_margin"])

    def test_growth_is_flagged_when_only_the_prior_year_is_a_proxy(self):
        statements = build(without_operating_income(years={2023}))
        latest, middle = (y["ratios"] for y in compute_ratios(statements)["years"][:2])
        self.assertNotIn("approximate", latest["operating_margin"])
        self.assertEqual(latest["operating_income_growth"]["approximate"], "OPERATING_INCOME_PROXY")
        self.assertEqual(middle["operating_margin"]["approximate"], "OPERATING_INCOME_PROXY")
        # No prior year for the oldest row: an unavailable ratio is never flagged.
        oldest = compute_ratios(build(without_operating_income()))["years"][-1]["ratios"]
        self.assertIsNone(oldest["operating_income_growth"]["value"])
        self.assertNotIn("approximate", oldest["operating_income_growth"])

    def test_html_marks_values_and_ratios_as_approximate(self):
        statements = build(without_operating_income())
        page = render_financial_sections(statements, compute_ratios(statements))
        self.assertIn("title='yaklaşık: EBIT_PROXY_PRETAX_PLUS_INTEREST · a2024 · faaliyet dışı kalemleri içerir'",
                      page.replace("&#x27;", "'"))
        self.assertIn(">≈0†</td>", page)
        self.assertIn(">≈21.8%</td>", page)
        self.assertIn("≈ 3 dönemde şirket faaliyet kârı bildirmedi", page)


def proxy_five_year_company():
    data = with_shares(five_year_company())
    gaap = data["facts"]["us-gaap"]
    del gaap["OperatingIncomeLoss"]
    gaap["InterestExpense"] = {"units": {"USD": [fact(10, y) for y in range(2020, 2025)]}}
    return data


class ForecastWithProxyTests(unittest.TestCase):
    def setUp(self):
        statements = build_annual_statements(proxy_five_year_company(), as_of=AS_OF)
        self.baseline = historical_baseline(statements, compute_ratios(statements))

    def test_baseline_lists_approximate_years_and_projection_warns(self):
        self.assertEqual(self.baseline["status"], "OK")
        self.assertEqual(len(self.baseline["approximate_operating_income_years"]), 5)
        self.assertIn("a2024", self.baseline["sources"])
        projection = project_scenarios(self.baseline, **LONG_RUN)
        self.assertIn("OPERATING_MARGIN_FROM_APPROXIMATE_EBIT", projection["warnings"])
        page = render_forecast_section(self.baseline, projection)
        self.assertIn("marjlar yaklaşık faaliyet kârıyla", page)
        self.assertIn("Faaliyet marjı yaklaşık faaliyet kârından", page)

    def test_baseline_sources_include_the_proxy_filing(self):
        data = proxy_five_year_company()
        for tag in (PRETAX, "InterestExpense"):
            data["facts"]["us-gaap"][tag]["units"]["USD"][-1]["accn"] = "p2024"
        statements = build_annual_statements(data, as_of=AS_OF)
        baseline = historical_baseline(statements, compute_ratios(statements))
        self.assertIn("p2024", baseline["sources"])

    def test_reported_history_has_no_proxy_warning(self):
        statements = build_annual_statements(five_year_company(), as_of=AS_OF)
        baseline = historical_baseline(statements, compute_ratios(statements))
        self.assertEqual(baseline["approximate_operating_income_years"], [])
        self.assertNotIn("OPERATING_MARGIN_FROM_APPROXIMATE_EBIT",
                         project_scenarios(baseline, **LONG_RUN)["warnings"])

    def test_ledger_records_the_operating_income_basis(self):
        projection = project_scenarios(self.baseline, years=2, **LONG_RUN)
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "ledger.sqlite"
            record_projection(projection, db_path=db)
            with TahminDefteri(db) as ledger:
                stored = [json.loads(a) for (a,) in ledger.db.execute("SELECT assumptions_json FROM forecasts")]
        self.assertEqual({a["operating_income_basis"] for a in stored}, {"APPROXIMATE_PRETAX_PLUS_INTEREST"})

    def test_valuation_carries_the_warning(self):
        result, _, _ = value(proxy_five_year_company())
        self.assertEqual(result["status"], "OK")
        self.assertIn("OPERATING_MARGIN_FROM_APPROXIMATE_EBIT", result["warnings"])
        reported, _, _ = value()
        self.assertNotIn("OPERATING_MARGIN_FROM_APPROXIMATE_EBIT", reported["warnings"])


if __name__ == "__main__":
    unittest.main()
