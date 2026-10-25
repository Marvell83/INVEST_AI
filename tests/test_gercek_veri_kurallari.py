"""Offline synthetic tests for the rules added after the first real SEC data check.

- share-based compensation reads only the cash-flow add-back concept,
- revenue aliases up to 5% apart use the priority alias with a visible note,
- without a reported operating income an approximate EBIT (pretax + interest) is derived.
"""
from __future__ import annotations

import copy
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
from test_katman_mutabakati import ttm_company
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


CAPEX = "PaymentsToAcquirePropertyPlantAndEquipment"
PRODUCTIVE = "PaymentsToAcquireProductiveAssets"


def productive_capex(data):
    """CapEx tagged as productive-asset payments, as NVIDIA and Amazon do."""
    data["facts"]["us-gaap"][PRODUCTIVE] = data["facts"]["us-gaap"].pop(CAPEX)
    return data


class CapexFallbackTests(unittest.TestCase):
    def test_productive_assets_are_read_when_no_capex_alias_is_reported(self):
        result = build(productive_capex(company()))
        cash_flow = row(result)["cash_flow"]
        self.assertEqual((cash_flow["capex"]["status"], cash_flow["capex"]["value"]), ("REPORTED", 50))
        self.assertEqual(cash_flow["capex"]["concept"], PRODUCTIVE)
        self.assertTrue(cash_flow["capex"]["fallback_concept"])
        self.assertEqual(cash_flow["free_cash_flow"]["value"], 180)
        self.assertEqual([f["end"] for f in result["fallback_concepts"]],
                         ["2024-12-31", "2023-12-31", "2022-12-31"])
        self.assertEqual(result["fallback_concepts"][0]["concept"], PRODUCTIVE)

    def test_primary_capex_wins_and_the_broader_concept_is_not_compared(self):
        data = company()
        data["facts"]["us-gaap"][PRODUCTIVE] = {"units": {"USD": [fact(70, 2024)]}}
        result = build(data)
        capex = row(result)["cash_flow"]["capex"]
        self.assertEqual((capex["status"], capex["value"], capex["concept"]), ("REPORTED", 50, CAPEX))
        self.assertNotIn("fallback_concept", capex)
        self.assertEqual((result["fallback_concepts"], result["conflicts"]), ([], []))

    def test_quarters_and_ttm_use_the_fallback(self):
        data = quarterly_company()
        data["facts"]["us-gaap"][PRODUCTIVE] = data["facts"]["us-gaap"].pop(CAPEX)
        quarterly = build_quarterly_statements(data, as_of="2025-09-01")
        q2 = next(q for q in quarterly["quarters"] if q["end"] == "2025-06-30")["cash_flow"]["capex"]
        self.assertEqual((q2["status"], q2["value"], q2["concept"]), ("DERIVED", 14, PRODUCTIVE))
        self.assertTrue(q2["fallback_concept"])
        self.assertIn("daha geniş kapsamlı yedek etiket okundu (PaymentsToAcquireProductiveAssets)",
                      render_quarterly_section(quarterly))
        ttm_data = ttm_company()
        ttm_data["facts"]["us-gaap"][PRODUCTIVE] = ttm_data["facts"]["us-gaap"].pop(CAPEX)
        ttm = build_quarterly_statements(ttm_data, as_of="2025-06-15")["ttm"]
        self.assertEqual((ttm["status"], ttm["items"]["capex"]["value"]), ("OK", 12 + 15 + 10 + 15))

    def test_html_title_marks_the_broader_concept(self):
        statements = build(productive_capex(company()))
        page = render_financial_sections(statements, compute_ratios(statements))
        self.assertIn("yedek XBRL etiketi; kapsamı daha geniş olabilir", page)


class SectorGuardTests(unittest.TestCase):
    def research(self, sector):
        return build_company_research(without_operating_income(), as_of=AS_OF, expected_cik=77, sector=sector)

    def test_no_ebit_proxy_for_financial_or_unconfirmed_sectors(self):
        for sector in ("financial", "unknown"):
            with self.subTest(sector):
                report = self.research(sector)
                statements = report["financial_statements"]
                cell = row(statements)["income"]["operating_income"]
                self.assertEqual((cell["status"], cell["proxy_unavailable"]),
                                 ("MISSING", "EBIT_PROXY_DISABLED_FOR_SECTOR"))
                self.assertEqual((statements["ebit_proxy"], report["quarterly_statements"]["ebit_proxy"]),
                                 (False, False))
                self.assertEqual(statements["approximations"], [])
                self.assertEqual(layer_health(report)["latest_operating_income"], "MISSING")

    def test_non_financial_research_keeps_the_proxy(self):
        report = self.research("non_financial")
        self.assertTrue(report["financial_statements"]["ebit_proxy"])
        self.assertEqual(layer_health(report)["latest_operating_income"], "APPROXIMATE")

    def test_quarterly_cells_follow_the_sector_rule(self):
        data = ttm_company()
        gaap = data["facts"]["us-gaap"]
        gaap[PRETAX] = gaap.pop("OperatingIncomeLoss")
        gaap["InterestExpense"] = copy.deepcopy(gaap[PRETAX])
        for r in gaap["InterestExpense"]["units"]["USD"]:
            r["val"] = r["val"] / 10
        for sector, expected in (("non_financial", "DERIVED"), ("financial", "MISSING")):
            with self.subTest(sector):
                report = build_company_research(data, as_of="2025-06-15", expected_cik=99, sector=sector)
                latest = report["quarterly_statements"]["quarters"][0]["income"]["operating_income"]
                self.assertEqual(latest["status"], expected)

    def test_builders_default_to_the_proxy_and_can_disable_it(self):
        self.assertTrue(row(build(without_operating_income()))["income"]["operating_income"]["approximate"])
        disabled = build_annual_statements(without_operating_income(), as_of=AS_OF, ebit_proxy=False)
        self.assertEqual(row(disabled)["income"]["operating_income"]["status"], "MISSING")
        quarterly = build_quarterly_statements(without_operating_income(), as_of=AS_OF, ebit_proxy=False)
        self.assertFalse(quarterly["ebit_proxy"])


if __name__ == "__main__":
    unittest.main()
