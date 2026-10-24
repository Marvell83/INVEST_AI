"""Offline synthetic tests for discrete fiscal quarters and cover-page shares."""
from __future__ import annotations

import unittest

from finansal_tablolar import build_annual_statements, build_quarterly_statements, shares_outstanding
from sec_ttm import compute_ttm
from sirket_analiz_paneli import render_quarterly_section
from sirket_arastirma_akisi import build_company_research, render_company_research

AS_OF = "2025-09-01"
REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"
CFO = "NetCashProvidedByUsedInOperatingActivities"
CAPEX = "PaymentsToAcquirePropertyPlantAndEquipment"
COST = "CostOfRevenue"
# Filing accession and filed date per period end (10-Q per quarter, 10-K per year).
FILINGS = {
    "2024-03-31": ("q2024-1", "2024-05-01", "10-Q"), "2024-06-30": ("q2024-2", "2024-08-01", "10-Q"),
    "2024-09-30": ("q2024-3", "2024-11-01", "10-Q"), "2024-12-31": ("k2024", "2025-02-15", "10-K"),
    "2025-03-31": ("q2025-1", "2025-05-01", "10-Q"), "2025-06-30": ("q2025-2", "2025-08-01", "10-Q"),
}


def fact(val, start, end, filing_end=None):
    accn, filed, form = FILINGS[filing_end or end]
    row = {"val": val, "end": end, "form": form, "fp": "Q9", "fy": 1999, "accn": accn, "filed": filed}
    if start:
        row["start"] = start
    return row


def flows(*items):
    return {"units": {"USD": [fact(*item) for item in items]}}


def company():
    gaap = {
        # Direct 3-month revenue for Q1-Q3, YTD totals, the annual 10-K value and
        # the prior-year comparatives that the 2025 10-Qs repeat.
        REVENUE: flows((250, "2024-01-01", "2024-03-31"), (300, "2024-04-01", "2024-06-30"),
                       (550, "2024-01-01", "2024-06-30"), (320, "2024-07-01", "2024-09-30"),
                       (870, "2024-01-01", "2024-09-30"), (1200, "2024-01-01", "2024-12-31"),
                       (280, "2025-01-01", "2025-03-31"), (310, "2025-04-01", "2025-06-30"),
                       (590, "2025-01-01", "2025-06-30"),
                       (550, "2024-01-01", "2024-06-30", "2025-06-30")),
        # Cash flow is reported only year-to-date, as in real 10-Q filings.
        CFO: flows((40, "2024-01-01", "2024-03-31"), (90, "2024-01-01", "2024-06-30"),
                   (150, "2024-01-01", "2024-09-30"), (230, "2024-01-01", "2024-12-31"),
                   (50, "2025-01-01", "2025-03-31"), (110, "2025-01-01", "2025-06-30"),
                   (90, "2024-01-01", "2024-06-30", "2025-06-30")),
        CAPEX: flows((10, "2024-01-01", "2024-03-31"), (25, "2024-01-01", "2024-06-30"),
                     (35, "2024-01-01", "2024-09-30"), (50, "2024-01-01", "2024-12-31"),
                     (12, "2025-01-01", "2025-03-31"), (26, "2025-01-01", "2025-06-30"),
                     (25, "2024-01-01", "2024-06-30", "2025-06-30")),
        COST: flows((180, "2025-04-01", "2025-06-30")),
        "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
            fact(v, None, end) for end, v in (("2024-03-31", 60), ("2024-06-30", 65), ("2024-09-30", 70),
                                              ("2024-12-31", 80), ("2025-03-31", 85), ("2025-06-30", 90))]}},
        "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
            fact(100, "2025-01-01", "2025-03-31"), fact(99, "2025-01-01", "2025-06-30")]}},
    }
    dei = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"val": 101, "end": "2025-01-31", "form": "10-K", "accn": "k2024", "filed": "2025-02-15"},
        {"val": 98, "end": "2025-07-25", "form": "10-Q", "accn": "q2025-2", "filed": "2025-08-01"}]}}}
    return {"cik": 88, "entityName": "SYNTHETIC QUARTERS CO", "facts": {"us-gaap": gaap, "dei": dei}}


def build(data=None, as_of=AS_OF, **kwargs):
    return build_quarterly_statements(data or company(), as_of=as_of, **kwargs)


def quarter(result, label, number):
    return next(q for q in result["quarters"]
                if q["fiscal_year_label"] == label and q["fiscal_quarter"] == number)


class QuarterlyStatementsTests(unittest.TestCase):
    def test_calendar_newest_first_including_year_in_progress(self):
        result = build()
        self.assertEqual(result["status"], "OK")
        self.assertEqual([(q["fiscal_year_label"], q["fiscal_quarter"], q["end"]) for q in result["quarters"]], [
            ("MY2025", 2, "2025-06-30"), ("MY2025", 1, "2025-03-31"), ("MY2024", 4, "2024-12-31"),
            ("MY2024", 3, "2024-09-30"), ("MY2024", 2, "2024-06-30"), ("MY2024", 1, "2024-03-31")])
        current = quarter(result, "MY2025", 2)
        self.assertIsNone(current["fiscal_year_end"])
        self.assertEqual((current["start"], current["fiscal_year_start"]), ("2025-04-01", "2025-01-01"))
        self.assertEqual(len(build(quarters=2)["quarters"]), 2)

    def test_reported_three_month_value_is_used_first(self):
        cell = quarter(build(), "MY2025", 2)["income"]["revenue"]
        self.assertEqual((cell["status"], cell["value"], cell["accession"]), ("REPORTED", 310, "q2025-2"))

    def test_ytd_difference_when_only_year_to_date_is_reported(self):
        cell = quarter(build(), "MY2025", 2)["cash_flow"]["cfo"]
        self.assertEqual((cell["status"], cell["value"], cell["method"]), ("DERIVED", 60, "YTD_DIFFERENCE"))
        self.assertEqual(cell["sources"], ["q2025-2", "q2025-1"])
        self.assertEqual(cell["derivation"]["ytd_previous"]["end"], "2025-03-31")

    def test_fourth_quarter_is_annual_minus_nine_months(self):
        q4 = quarter(build(), "MY2024", 4)
        self.assertEqual((q4["start"], q4["end"]), ("2024-10-01", "2024-12-31"))
        revenue, cfo = q4["income"]["revenue"], q4["cash_flow"]["cfo"]
        self.assertEqual((revenue["value"], revenue["method"]), (330, "ANNUAL_MINUS_NINE_MONTHS"))
        self.assertEqual((cfo["value"], cfo["sources"]), (80, ["k2024", "q2024-3"]))

    def test_free_cash_flow_needs_matching_filings(self):
        cell = quarter(build(), "MY2025", 2)["cash_flow"]["free_cash_flow"]
        self.assertEqual((cell["status"], cell["value"]), ("DERIVED", 60 - 14))
        data = company()
        data["facts"]["us-gaap"][CAPEX]["units"]["USD"][5]["accn"] = "other"
        cell = quarter(build(data), "MY2025", 2)["cash_flow"]["free_cash_flow"]
        self.assertEqual(cell["reason"], "CFO_AND_CAPEX_FROM_DIFFERENT_FILINGS")

    def test_gross_profit_from_same_quarterly_filing(self):
        cell = quarter(build(), "MY2025", 2)["income"]["gross_profit"]
        self.assertEqual((cell["status"], cell["value"]), ("DERIVED", 130))

    def test_fourth_quarter_reported_in_10k_does_not_shift_fiscal_year(self):
        data = company()
        gaap = data["facts"]["us-gaap"]
        for tag, value in ((REVENUE, 333), (CFO, 81), ("NetIncomeLoss", 40)):
            gaap.setdefault(tag, {"units": {"USD": []}})["units"]["USD"].append(
                fact(value, "2024-10-01", "2024-12-31"))
        q4 = quarter(build(data), "MY2024", 4)
        self.assertEqual((q4["fiscal_year_start"], q4["start"]), ("2024-01-01", "2024-10-01"))
        self.assertEqual((q4["income"]["revenue"]["status"], q4["income"]["revenue"]["value"]), ("REPORTED", 333))

    def test_balance_items_are_quarter_end_values(self):
        result = build()
        self.assertEqual(quarter(result, "MY2025", 2)["balance"]["cash"]["value"], 90)
        self.assertEqual(quarter(result, "MY2024", 4)["balance"]["cash"]["accession"], "k2024")

    def test_weighted_average_shares_are_never_differenced(self):
        cell = quarter(build(), "MY2025", 2)["income"]["diluted_shares"]
        self.assertEqual((cell["value"], cell["reason"]), (None, "NON_ADDITIVE_NOT_DERIVED"))
        self.assertEqual(quarter(build(), "MY2025", 1)["income"]["diluted_shares"]["value"], 100)

    def test_later_filing_is_invisible(self):
        result = build(as_of="2025-07-31")
        self.assertEqual(result["quarters"][0]["end"], "2025-03-31")

    def test_ytd_values_of_different_concepts_are_not_mixed(self):
        data = company()
        revenue = data["facts"]["us-gaap"][REVENUE]["units"]["USD"]
        moved = [r for r in revenue if (r["start"], r["end"]) == ("2025-01-01", "2025-06-30")]
        revenue.remove(moved[0])
        revenue.remove(next(r for r in revenue if r["start"] == "2025-04-01"))
        data["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": moved}}
        cell = quarter(build(data), "MY2025", 2)["income"]["revenue"]
        self.assertEqual((cell["value"], cell["reason"]), (None, "YTD_CONCEPTS_DIFFER"))

    def test_quarter_without_known_start_is_not_listed(self):
        data = company()
        for concept in data["facts"]["us-gaap"].values():
            for rows in concept["units"].values():
                rows[:] = [r for r in rows if r["end"] != "2024-06-30"]
        ends = [q["end"] for q in build(data)["quarters"] if q["fiscal_year_label"] == "MY2024"]
        self.assertEqual(ends, ["2024-12-31", "2024-03-31"])

    def test_annual_only_issuer_has_no_quarters(self):
        data = company()
        for concept in data["facts"]["us-gaap"].values():
            for rows in concept["units"].values():
                rows[:] = [r for r in rows if r["form"] == "10-K"]
        self.assertEqual(build(data)["status"], "NO_QUARTERLY_PERIODS")

    def test_last_four_quarters_match_existing_ttm_engine(self):
        result = build()
        latest = result["quarters"][:4]
        ttm = compute_ttm(company(), as_of=AS_OF, current_ytd_end="2025-06-30",
                          metrics=("revenue", "cfo", "capex"))
        for key, statement in (("revenue", "income"), ("cfo", "cash_flow"), ("capex", "cash_flow")):
            with self.subTest(key=key):
                self.assertEqual(sum(q[statement][key]["value"] for q in latest), ttm["metrics"][key]["value_usd"])

    def test_invalid_quarter_count_rejected(self):
        for bad in (0, 41, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build(quarters=bad)


class QuarterlyReportTests(unittest.TestCase):
    def research(self, data=None):
        return build_company_research(data or company(), as_of=AS_OF, expected_cik=88, sector="unknown")

    def test_research_report_shows_quarters_and_shares(self):
        report = self.research()
        self.assertEqual(report["quarterly_statements"]["quarters"][0]["end"], "2025-06-30")
        page = render_company_research(report)
        self.assertIn("Çeyreklik tablolar — 10-Q / 10-K (milyon USD)", page)
        self.assertIn("MY2025 Ç2", page)
        self.assertIn("Dolaşımdaki hisse (kapak sayfası, 2025-07-25)", page)
        self.assertIn("YTD_DIFFERENCE · q2025-2, q2025-1", page)

    def test_untrusted_accession_is_escaped_in_quarter_table(self):
        data = company()
        data["facts"]["us-gaap"][REVENUE]["units"]["USD"][7]["accn"] = "<img src=x onerror=alert(1)>"
        page = render_company_research(self.research(data))
        self.assertNotIn("<img src=x", page)

    def test_report_without_quarters_still_renders(self):
        report = self.research()
        del report["quarterly_statements"]
        self.assertNotIn("Çeyreklik tablolar", render_company_research(report))

    def test_no_quarters_section(self):
        empty = build_quarterly_statements({"cik": 88, "facts": {"us-gaap": {}}}, as_of=AS_OF)
        self.assertIn("10-Q verisi bulunamadı", render_quarterly_section(empty))


class SharesOutstandingTests(unittest.TestCase):
    def test_latest_cover_page_count_by_filing_date(self):
        shares = shares_outstanding(company(), as_of=AS_OF)
        self.assertEqual((shares["status"], shares["value"], shares["date"]), ("REPORTED", 98, "2025-07-25"))
        self.assertEqual(shares["concept"], "dei:EntityCommonStockSharesOutstanding")
        self.assertEqual(shares_outstanding(company(), as_of="2025-07-31")["value"], 101)

    def test_multiple_share_classes_are_not_summed(self):
        data = company()
        data["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"].append(
            {"val": 7, "end": "2025-07-25", "form": "10-Q", "accn": "q2025-2", "filed": "2025-08-01"})
        shares = shares_outstanding(data, as_of=AS_OF)
        self.assertEqual((shares["status"], shares["reason"]),
                         ("CONFLICT", "MULTIPLE_VALUES_POSSIBLY_SHARE_CLASSES"))

    def test_missing_dei_namespace(self):
        data = company()
        del data["facts"]["dei"]
        self.assertEqual(shares_outstanding(data, as_of=AS_OF)["status"], "MISSING")

    def test_annual_statements_carry_shares_outstanding(self):
        self.assertEqual(build_annual_statements(company(), as_of=AS_OF)["shares_outstanding"]["value"], 98)


if __name__ == "__main__":
    unittest.main()
