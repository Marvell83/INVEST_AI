"""Offline synthetic tests for the shared annual statements layer; no real issuer."""
from __future__ import annotations

import unittest

from finansal_tablolar import build_annual_statements

YEARS = (2022, 2023, 2024)
FLOWS = {
    "RevenueFromContractWithCustomerExcludingAssessedTax": (800, 1000, 1200),
    "CostOfRevenue": (500, 600, 700),
    "OperatingIncomeLoss": (150, 200, 260),
    "InterestExpense": (10, 10, 12),
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": (140, 190, 250),
    "IncomeTaxExpenseBenefit": (28, 38, 50),
    "NetIncomeLoss": (112, 152, 200),
    "NetCashProvidedByUsedInOperatingActivities": (130, 180, 230),
    "PaymentsToAcquirePropertyPlantAndEquipment": (30, 40, 50),
    "DepreciationDepletionAndAmortization": (20, 25, 30),
    "ShareBasedCompensation": (5, 6, 8),
    "PaymentsOfDividends": (20, 25, 30),
    "PaymentsForRepurchaseOfCommonStock": (10, 40, 60),
}
INSTANTS = {
    "CashAndCashEquivalentsAtCarryingValue": (100, 120, 150),
    "AssetsCurrent": (300, 350, 400),
    "Assets": (1000, 1100, 1300),
    "LiabilitiesCurrent": (150, 175, 200),
    "Liabilities": (500, 520, 600),
    "LongTermDebtNoncurrent": (200, 190, 250),
    "LongTermDebtCurrent": (20, 20, 30),
    "StockholdersEquity": (500, 580, 700),
}
AS_OF = "2025-03-01"


def fact(val, year, *, instant=False, accn=None, filed=None, form="10-K", start=None, end=None):
    row = {"val": val, "end": end or f"{year}-12-31", "form": form, "fy": year, "fp": "FY",
           "accn": accn or f"a{year}", "filed": filed or f"{year + 1}-02-15"}
    if not instant:
        row["start"] = start or f"{year}-01-01"
    return row


def company(years=YEARS):
    data = {"cik": 77, "entityName": "SYNTHETIC STATEMENTS CO", "facts": {"us-gaap": {}}}
    gaap = data["facts"]["us-gaap"]
    for tag, values in FLOWS.items():
        gaap[tag] = {"units": {"USD": [fact(v, y) for y, v in zip(YEARS, values) if y in years]}}
    for tag, values in INSTANTS.items():
        gaap[tag] = {"units": {"USD": [fact(v, y, instant=True) for y, v in zip(YEARS, values) if y in years]}}
    gaap["CommercialPaper"] = {"units": {"USD": [fact(20, 2024, instant=True)]}}
    gaap["WeightedAverageNumberOfDilutedSharesOutstanding"] = {
        "units": {"shares": [fact(v, y) for y, v in zip(YEARS, (100, 100, 98)) if y in years]}}
    return data


def build(data=None, as_of=AS_OF, **kwargs):
    return build_annual_statements(data or company(), as_of=as_of, **kwargs)


def row(statements, end="2024-12-31"):
    return next(y for y in statements["years"] if y["fiscal_year_end"] == end)


class AnnualStatementsTests(unittest.TestCase):
    def test_years_are_most_recent_first_and_limited(self):
        result = build(years=2)
        self.assertEqual(result["status"], "OK")
        self.assertEqual([y["fiscal_year_end"] for y in result["years"]], ["2024-12-31", "2023-12-31"])
        self.assertEqual(result["cik"], "0000000077")

    def test_reported_cell_keeps_sec_provenance(self):
        cell = row(build())["income"]["revenue"]
        self.assertEqual(cell["status"], "REPORTED")
        self.assertEqual(cell["value"], 1200)
        self.assertEqual(cell["concept"], "RevenueFromContractWithCustomerExcludingAssessedTax")
        self.assertEqual((cell["accession"], cell["filed"], cell["form"]), ("a2024", "2025-02-15", "10-K"))
        self.assertEqual((cell["start"], cell["end"]), ("2024-01-01", "2024-12-31"))
        self.assertFalse(cell["revised"])

    def test_later_filing_is_invisible_before_its_filed_date(self):
        result = build(as_of="2025-02-14")
        self.assertEqual(result["years"][0]["fiscal_year_end"], "2023-12-31")

    def test_restatement_wins_and_first_reported_value_is_kept(self):
        data = company()
        data["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"].append(fact(150, 2023, accn="a2024",
                                                                             filed="2025-02-15"))
        cell = row(build(data), "2023-12-31")["income"]["net_income"]
        self.assertEqual((cell["value"], cell["accession"]), (150, "a2024"))
        self.assertTrue(cell["revised"])
        self.assertEqual(cell["first_reported"], {"value": 152, "filed": "2024-02-15", "accession": "a2023"})
        before = row(build(data, as_of="2024-06-01"), "2023-12-31")["income"]["net_income"]
        self.assertEqual(before["value"], 152)
        self.assertFalse(before["revised"])

    def test_disagreeing_aliases_are_a_conflict_without_value(self):
        data = company()
        data["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [fact(1300, 2024)]}}
        result = build(data)
        cell = row(result)["income"]["revenue"]
        self.assertEqual((cell["status"], cell["value"]), ("CONFLICT", None))
        self.assertEqual({a["concept"] for a in cell["alternatives"]},
                         {"RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"})
        self.assertEqual(result["conflicts"][0]["item"], "revenue")
        self.assertEqual(row(result)["income"]["gross_profit"]["status"], "MISSING")
        self.assertEqual(result["coverage"]["revenue"], {"available": 2, "conflicts": 1})

    def test_agreeing_aliases_use_priority_concept(self):
        data = company()
        data["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [fact(1200.5, 2024)]}}
        cell = row(build(data))["income"]["revenue"]
        self.assertEqual(cell["status"], "REPORTED")
        self.assertEqual(cell["concept"], "RevenueFromContractWithCustomerExcludingAssessedTax")
        self.assertEqual(cell["agreeing_aliases"], ["Revenues"])

    def test_missing_item_is_null_never_zero(self):
        cell = row(build())["income"]["research_development"]
        self.assertEqual(cell, {"status": "MISSING", "value": None, "unit": "USD", "reason": "NOT_REPORTED"})

    def test_gross_profit_derived_only_within_one_filing(self):
        cell = row(build())["income"]["gross_profit"]
        self.assertEqual((cell["status"], cell["value"]), ("DERIVED", 500))
        self.assertEqual(cell["method"], "REVENUE_MINUS_COST_OF_REVENUE_SAME_FILING")
        data = company()
        data["facts"]["us-gaap"]["CostOfRevenue"]["units"]["USD"][2]["accn"] = "unrelated"
        self.assertEqual(row(build(data))["income"]["gross_profit"]["status"], "MISSING")

    def test_reported_gross_profit_is_not_overwritten(self):
        data = company()
        data["facts"]["us-gaap"]["GrossProfit"] = {"units": {"USD": [fact(510, 2024)]}}
        cell = row(build(data))["income"]["gross_profit"]
        self.assertEqual((cell["status"], cell["value"]), ("REPORTED", 510))

    def test_free_cash_flow_is_cfo_minus_capex_not_fcff(self):
        cell = row(build())["cash_flow"]["free_cash_flow"]
        self.assertEqual((cell["status"], cell["value"], cell["is_fcff"]), ("DERIVED", 180, False))
        data = company()
        data["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"][2]["accn"] = "x"
        cell = row(build(data))["cash_flow"]["free_cash_flow"]
        self.assertEqual((cell["value"], cell["reason"]), (None, "CFO_AND_CAPEX_FROM_DIFFERENT_FILINGS"))

    def test_total_debt_lists_summed_and_unreported_components(self):
        result = build()
        debt = row(result)["balance"]["total_debt"]
        self.assertEqual((debt["status"], debt["value"]), ("DERIVED", 300))
        self.assertEqual(debt["components"], ["long_term_debt_noncurrent", "long_term_debt_current",
                                              "commercial_paper"])
        self.assertEqual(debt["components_not_reported"], ["short_term_borrowings"])
        earlier = row(result, "2023-12-31")["balance"]["total_debt"]
        self.assertEqual(earlier["value"], 210)
        self.assertIn("commercial_paper", earlier["components_not_reported"])

    def test_unrevised_debt_components_from_different_filings_are_summed(self):
        # A later 10-K repeats only some prior-year lines; unchanged values may be combined.
        data = company()
        data["facts"]["us-gaap"]["CommercialPaper"]["units"]["USD"][0]["accn"] = "other"
        debt = row(build(data))["balance"]["total_debt"]
        self.assertEqual((debt["status"], debt["value"]), ("DERIVED", 300))
        self.assertEqual(debt["method"], "SUM_OF_REPORTED_DEBT_COMPONENTS_UNREVISED_ACROSS_FILINGS")
        self.assertEqual(debt["sources"], ["a2024", "other"])

    def test_restated_and_original_debt_components_are_not_summed(self):
        data = company()
        data["facts"]["us-gaap"]["LongTermDebtNoncurrent"]["units"]["USD"].append(
            fact(260, 2024, instant=True, accn="restated", filed="2025-02-20"))
        debt = row(build(data))["balance"]["total_debt"]
        self.assertEqual((debt["value"], debt["reason"]), (None, "DEBT_COMPONENTS_FROM_DIFFERENT_FILINGS"))
        self.assertEqual(debt["revised_components"], ["long_term_debt_noncurrent"])
        same_filing = company()
        same_filing["facts"]["us-gaap"]["LongTermDebtNoncurrent"]["units"]["USD"].append(
            fact(260, 2024, instant=True, accn="a2024", filed="2025-02-15"))
        self.assertEqual(row(build(same_filing))["balance"]["total_debt"]["status"], "DERIVED")

    def test_long_term_debt_total_is_fallback_without_double_counting(self):
        data = company()
        gaap = data["facts"]["us-gaap"]
        del gaap["LongTermDebtNoncurrent"]
        gaap["LongTermDebt"] = {"units": {"USD": [fact(280, 2024, instant=True)]}}
        debt = row(build(data))["balance"]["total_debt"]
        self.assertEqual(debt["value"], 300)
        self.assertEqual(debt["components"], ["long_term_debt", "commercial_paper"])

    def test_no_debt_component_is_missing_not_zero(self):
        data = company()
        for tag in ("LongTermDebtNoncurrent", "LongTermDebtCurrent", "CommercialPaper"):
            del data["facts"]["us-gaap"][tag]
        debt = row(build(data))["balance"]["total_debt"]
        self.assertEqual((debt["value"], debt["reason"]), (None, "NO_DEBT_COMPONENT_REPORTED"))

    def test_periods_come_from_fact_dates_not_filing_fields(self):
        data = company()
        revenue = data["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"]
        for item in revenue:
            item["fy"], item["fp"] = 2099, "Q1"
        revenue.append(fact(999, 2025, form="10-Q", start="2025-01-01", end="2025-01-31", filed="2025-02-20"))
        # Quarters disclosed inside a 10-K are not fiscal years.
        revenue.append(fact(333, 2024, start="2024-10-01"))
        revenue.append(fact(300, 2024, start="2024-07-01", end="2024-09-30"))
        result = build(data)
        self.assertEqual([y["fiscal_year_end"] for y in result["years"]],
                         ["2024-12-31", "2023-12-31", "2022-12-31"])
        self.assertFalse(row(result)["start_ambiguous"])
        self.assertEqual(row(result)["income"]["revenue"]["value"], 1200)

    def test_non_usd_units_are_not_used(self):
        data = company()
        cost = data["facts"]["us-gaap"]["CostOfRevenue"]["units"]
        cost["EUR"] = cost.pop("USD")
        self.assertEqual(row(build(data))["income"]["cost_of_revenue"]["status"], "MISSING")

    def test_share_counts_keep_share_unit(self):
        cell = row(build())["income"]["diluted_shares"]
        self.assertEqual((cell["value"], cell["unit"]), (98, "shares"))

    def test_company_without_annual_filings_reports_status(self):
        data = company()
        for concept in data["facts"]["us-gaap"].values():
            for unit in concept["units"].values():
                for item in unit:
                    item["form"] = "10-Q"
        result = build(data)
        self.assertEqual((result["status"], result["years"], result["conflicts"]), ("NO_ANNUAL_PERIODS", [], []))

    def test_invalid_inputs_rejected(self):
        for bad in ({"years": 0}, {"years": True}, {"years": 11}, {"as_of": "2025-13-01"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build(**bad)
        with self.assertRaises(ValueError):
            build_annual_statements({"cik": 77}, as_of=AS_OF)


if __name__ == "__main__":
    unittest.main()
