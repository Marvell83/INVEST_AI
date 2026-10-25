"""Offline synthetic tests: TTM from the shared quarterly layer for any latest fiscal quarter."""
from __future__ import annotations

import copy
import unittest

from finansal_tablolar import build_quarterly_statements, trailing_twelve_months
from katman_mutabakati import layer_health, reconcile_ttm
from sec_ttm_crosscheck import audit_ttm
from sirket_analiz_paneli import render_ttm_section
from sirket_arastirma_akisi import build_company_research, render_company_research
from test_katman_mutabakati import REVENUE, TTM_AS_OF, ttm_company

# 10-Q filing dates of ttm_company(): Q1 05-01, Q2 08-01, Q3 11-01; FY2024 10-K 2025-02-15.
AFTER_Q1 = "2025-06-15"
AFTER_10K = "2025-03-01"


def shared(as_of, data=None, **kwargs):
    return build_quarterly_statements(data or ttm_company(), as_of=as_of)["ttm"]


def research(as_of, data=None):
    return build_company_research(data or ttm_company(), as_of=as_of, expected_cik=99, sector="unknown")


class SharedTTMTests(unittest.TestCase):
    def test_latest_first_quarter_sums_the_four_latest_quarters(self):
        ttm = shared(AFTER_Q1)
        self.assertEqual((ttm["status"], ttm["fiscal_year_label"], ttm["fiscal_quarter"]), ("OK", "MY2025", 1))
        self.assertEqual(ttm["quarters"], ["2025-03-31", "2024-12-31", "2024-09-30", "2024-06-30"])
        self.assertEqual((ttm["start"], ttm["end"]), ("2024-04-01", "2025-03-31"))
        items = ttm["items"]
        self.assertEqual(items["revenue"]["value"], 280 + 330 + 320 + 300)
        self.assertEqual(items["operating_income"]["value"], 56 + 70 + 64 + 60)
        self.assertEqual(items["cfo"]["value"], 50 + 80 + 60 + 50)
        self.assertEqual(items["free_cash_flow"]["value"], 240 - (12 + 15 + 10 + 15))
        self.assertEqual(items["revenue"]["method"], "SUM_OF_FOUR_QUARTERS")
        # Q2 and Q3 revenue are reported 3-month values; Q4 is the 10-K minus the Q3 10-Q.
        self.assertEqual(items["revenue"]["sources"], ["k2024", "q2024-2", "q2024-3", "q2025-1"])
        self.assertEqual(items["revenue"]["filed"], "2025-05-01")

    def test_latest_fourth_quarter_equals_the_annual_10k(self):
        ttm = shared(AFTER_10K)
        self.assertEqual((ttm["status"], ttm["fiscal_quarter"], ttm["end"]), ("OK", 4, "2024-12-31"))
        self.assertEqual(ttm["items"]["revenue"]["value"], 1200)

    def test_latest_third_quarter_matches_the_older_engines(self):
        ttm = shared(TTM_AS_OF)
        self.assertEqual((ttm["fiscal_quarter"], ttm["items"]["revenue"]["value"]), (3, 1250))

    def test_an_older_window_can_be_requested(self):
        quarterly = build_quarterly_statements(ttm_company(), as_of=TTM_AS_OF)
        ttm = trailing_twelve_months(quarterly, end="2025-03-31")
        self.assertEqual((ttm["end"], ttm["items"]["revenue"]["value"]), ("2025-03-31", 1230))
        self.assertEqual(trailing_twelve_months(quarterly, end="2023-12-31")["status"], "INSUFFICIENT_QUARTERS")

    def test_fewer_than_four_consecutive_quarters(self):
        quarterly = build_quarterly_statements(ttm_company(), as_of=TTM_AS_OF)
        short = dict(quarterly, quarters=quarterly["quarters"][:3])
        broken = dict(quarterly, quarters=[q for q in quarterly["quarters"] if q["end"] != "2025-03-31"])
        for case in (short, broken):
            ttm = trailing_twelve_months(case)
            self.assertEqual((ttm["status"], ttm["items"]), ("INSUFFICIENT_QUARTERS", {}))
            self.assertEqual(ttm["end"], "2025-09-30")
        self.assertIsNone(trailing_twelve_months({"quarters": []})["end"])

    def test_a_missing_quarter_leaves_the_item_unavailable(self):
        data = ttm_company()
        rows = data["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"]
        rows[:] = [r for r in rows if r["end"] != "2024-12-31"]
        ttm = shared(AFTER_Q1, data)
        self.assertEqual(ttm["status"], "PARTIAL")
        self.assertEqual(ttm["core_unavailable"], ["cfo"])
        self.assertEqual(ttm["items"]["cfo"]["value"], None)
        self.assertEqual(ttm["items"]["cfo"]["reason"], "QUARTER_UNAVAILABLE")
        self.assertEqual(ttm["items"]["cfo"]["quarters_unavailable"], ["2024-12-31"])
        self.assertEqual(ttm["items"]["free_cash_flow"]["status"], "MISSING")
        self.assertEqual(ttm["items"]["revenue"]["status"], "DERIVED")

    def test_a_conflicting_quarter_is_a_conflict(self):
        quarterly = build_quarterly_statements(ttm_company(), as_of=AFTER_Q1)
        quarterly["quarters"][2]["income"]["revenue"] = {"status": "CONFLICT", "value": None, "unit": "USD"}
        cell = trailing_twelve_months(quarterly)["items"]["revenue"]
        self.assertEqual((cell["status"], cell["reason"]), ("CONFLICT", "QUARTER_CONFLICT"))
        self.assertEqual(cell["quarters_unavailable"], ["2024-09-30"])

    def test_non_additive_share_counts_are_not_summed(self):
        self.assertNotIn("diluted_shares", shared(AFTER_Q1)["items"])

    def test_approximate_quarter_marks_the_sum_approximate(self):
        quarterly = build_quarterly_statements(ttm_company(), as_of=AFTER_Q1)
        quarterly["quarters"][1]["income"]["operating_income"]["approximate"] = True
        items = trailing_twelve_months(quarterly)["items"]
        self.assertTrue(items["operating_income"]["approximate"])
        self.assertNotIn("approximate", items["revenue"])


class ReconciliationWithSharedTTMTests(unittest.TestCase):
    def test_older_engines_compare_against_the_shared_ttm(self):
        data = ttm_company()
        result = reconcile_ttm(audit_ttm(data, as_of=TTM_AS_OF), build_quarterly_statements(data, as_of=TTM_AS_OF))
        self.assertEqual(result["status"], "MATCHED")
        self.assertEqual(result["checks"][0]["quarters"], ["2025-09-30", "2025-06-30", "2025-03-31", "2024-12-31"])

    def test_approximate_shared_value_is_a_note_not_a_difference(self):
        data = ttm_company()
        quarterly = build_quarterly_statements(data, as_of=TTM_AS_OF)
        quarterly = copy.deepcopy(quarterly)
        quarterly["quarters"][1]["income"]["operating_income"].update(approximate=True, value=999)
        result = reconcile_ttm(audit_ttm(data, as_of=TTM_AS_OF), quarterly)
        ebit = next(c for c in result["checks"] if c["metric"] == "ebit")
        self.assertEqual((result["status"], ebit["status"]), ("MATCHED_WITH_NOTES", "SHARED_APPROXIMATE"))
        self.assertEqual(result["attention"], [])


class ResearchReportTests(unittest.TestCase):
    def test_first_quarter_ttm_is_reported_without_the_older_engines(self):
        report = research(AFTER_Q1)
        self.assertNotEqual(report["ttm_crosscheck"]["status"], "RECONCILED_CALCULATIONS")
        self.assertEqual(report["quarterly_statements"]["ttm"]["status"], "OK")
        gap = [g for g in report["research_gaps"] if g.startswith("TTM_")]
        self.assertEqual(gap, ["TTM_SINGLE_METHOD_ONLY:" + report["ttm_crosscheck"]["status"]])
        health = layer_health(report)
        self.assertEqual((health["shared_ttm_status"], health["shared_ttm_end"]), ("OK", "2025-03-31"))
        self.assertEqual(health["ttm_reconciliation"], "NOT_APPLICABLE")
        page = render_company_research(report)
        self.assertIn("Son 12 ay (TTM) — ortak çeyreklerden", page)
        self.assertIn("son çeyrek <strong>MY2025 Ç1</strong>", page)
        self.assertIn("<td class='num' title='SUM_OF_FOUR_QUARTERS", page)

    def test_incomplete_shared_ttm_keeps_the_original_gap(self):
        data = ttm_company()
        del data["facts"]["us-gaap"][REVENUE]
        report = research(AFTER_Q1, data)
        self.assertIn("TTM_NOT_RECONCILED:", " ".join(report["research_gaps"]))
        self.assertNotIn("TTM_SINGLE_METHOD_ONLY:", " ".join(report["research_gaps"]))

    def test_reconciled_engines_add_no_ttm_gap(self):
        report = research(TTM_AS_OF)
        self.assertFalse([g for g in report["research_gaps"] if g.startswith("TTM_")])


class RenderTests(unittest.TestCase):
    def test_section_values_and_missing_cells(self):
        page = render_ttm_section(shared(AFTER_Q1))
        self.assertIn("2024-04-01 – 2025-03-31", page)
        self.assertIn("Gelir</td><td class='num'", page)
        self.assertIn(">0†<", page)  # synthetic values are below one million

    def test_insufficient_and_absent(self):
        self.assertIn("Art arda dört çeyrek bulunamadı", render_ttm_section({"status": "INSUFFICIENT_QUARTERS"}))
        self.assertEqual(render_ttm_section(None), "")


if __name__ == "__main__":
    unittest.main()
