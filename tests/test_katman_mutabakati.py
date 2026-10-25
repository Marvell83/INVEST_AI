"""Offline synthetic tests: Piotroski / TTM inputs versus the shared statements layer."""
from __future__ import annotations

import copy
import unittest

from finansal_tablolar import build_annual_statements, build_quarterly_statements
from katman_mutabakati import reconcile_piotroski, reconcile_ttm
from piotroski_fscore import compute_piotroski
from sec_ttm_crosscheck import audit_ttm
from sirket_arastirma_akisi import build_company_research, render_company_research
from test_finansal_tablolar import AS_OF, company, fact
from test_piotroski_coverage_v02 import sample

REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"
TTM_AS_OF = "2025-12-01"
QUARTER_ENDS = {1: "03-31", 2: "06-30", 3: "09-30"}
QUARTER_STARTS = {2: "04-01", 3: "07-01"}
FILED = {1: "05-01", 2: "08-01", 3: "11-01"}
VALUES = {  # three or four discrete quarters per calendar fiscal year
    REVENUE: {2024: [250, 300, 320, 330], 2025: [280, 310, 330]},
    "OperatingIncomeLoss": {2024: [50, 60, 64, 70], 2025: [56, 62, 66]},
    "NetCashProvidedByUsedInOperatingActivities": {2024: [40, 50, 60, 80], 2025: [50, 60, 70]},
    "PaymentsToAcquirePropertyPlantAndEquipment": {2024: [10, 15, 10, 15], 2025: [12, 14, 14]},
}
DIRECT = (REVENUE, "OperatingIncomeLoss")  # income items also carry 3-month values in 10-Qs


def row(val, start, end, accn, filed, form, fp):
    return {"val": val, "start": start, "end": end, "accn": accn, "filed": filed, "form": form, "fp": fp}


def ttm_company():
    """Calendar-year issuer with 10-Qs for 2024-2025 Q1-Q3 and a 10-K for FY2024."""
    gaap = {}
    for tag, years in VALUES.items():
        rows = []
        for year, quarters in years.items():
            for q in (1, 2, 3):
                filing = (f"q{year}-{q}", f"{year}-{FILED[q]}", "10-Q", f"Q{q}")
                end = f"{year}-{QUARTER_ENDS[q]}"
                rows.append(row(sum(quarters[:q]), f"{year}-01-01", end, *filing))
                if tag in DIRECT and q > 1:
                    rows.append(row(quarters[q - 1], f"{year}-{QUARTER_STARTS[q]}", end, *filing))
                if year == 2025:  # prior-year comparative repeated in the 2025 10-Q
                    rows.append(row(sum(years[2024][:q]), "2024-01-01", f"2024-{QUARTER_ENDS[q]}", *filing))
            if len(quarters) == 4:
                rows.append(row(sum(quarters), f"{year}-01-01", f"{year}-12-31",
                                f"k{year}", f"{year + 1}-02-15", "10-K", "FY"))
        gaap[tag] = {"units": {"USD": rows}}
    return {"cik": 99, "entityName": "SYNTHETIC TTM CO", "facts": {"us-gaap": gaap}}


def ttm_layers(data):
    return reconcile_ttm(audit_ttm(data, as_of=TTM_AS_OF),
                         build_quarterly_statements(data, as_of=TTM_AS_OF))


def piotroski_layers(data, sector="non_financial"):
    return reconcile_piotroski(compute_piotroski(data, as_of=AS_OF, sector=sector),
                               build_annual_statements(data, as_of=AS_OF))


def statuses(result):
    return {c.get("piotroski_input", c.get("metric")): c["status"] for c in result["checks"]}


class PiotroskiReconciliationTests(unittest.TestCase):
    def test_same_facts_match_exactly(self):
        result = piotroski_layers(company())
        self.assertEqual(result["status"], "MATCHED")
        self.assertEqual(set(statuses(result).values()), {"MATCH"})
        self.assertIn("rev_t", statuses(result))

    def test_revenue_alias_gap_up_to_five_percent_uses_the_same_priority_alias(self):
        # Piotroski and the shared layer both use the priority revenue alias up to 5% apart.
        data = company()
        data["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [fact(1224, 2024)]}}
        result = piotroski_layers(data)
        self.assertEqual(result["status"], "MATCHED")
        self.assertEqual(statuses(result)["rev_t"], "MATCH")

    def test_revenue_alias_gap_above_five_percent_is_unknown_in_both(self):
        data = company()
        data["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [fact(1320, 2024)]}}
        result = piotroski_layers(data)
        self.assertNotIn("rev_t", statuses(result))
        self.assertEqual(result["attention"], [])

    def test_piotroski_only_derivation_is_a_note(self):
        result = piotroski_layers(sample())  # noncurrent debt derived as total minus current portion
        self.assertEqual(result["status"], "MATCHED_WITH_NOTES")
        self.assertEqual(statuses(result)["d_t"], "SHARED_MISSING")

    def test_value_and_filing_differences(self):
        piotroski = compute_piotroski(company(), as_of=AS_OF, sector="non_financial")
        statements = build_annual_statements(company(), as_of=AS_OF)
        changed = copy.deepcopy(piotroski)
        changed["provenance"]["ni_t"]["value_usd"] = 201
        changed["provenance"]["cfo_t"]["accession"] = "elsewhere"
        result = reconcile_piotroski(changed, statements)
        self.assertEqual((statuses(result)["ni_t"], statuses(result)["cfo_t"]),
                         ("VALUE_DIFFERS", "SAME_VALUE_OTHER_FILING"))
        self.assertEqual(result["status"], "DIFFERENCES")

    def test_unscored_sector_is_not_applicable(self):
        self.assertEqual(piotroski_layers(company(), sector="unknown")["status"], "NOT_APPLICABLE")


class TTMReconciliationTests(unittest.TestCase):
    def test_four_shared_quarters_equal_reconciled_ttm(self):
        result = ttm_layers(ttm_company())
        self.assertEqual((result["status"], result["ttm_end"]), ("MATCHED", "2025-09-30"))
        revenue = next(c for c in result["checks"] if c["metric"] == "revenue")
        self.assertEqual((revenue["ttm"], revenue["shared"]), (1250, 1250))
        self.assertEqual(revenue["quarters"], ["2025-09-30", "2025-06-30", "2025-03-31", "2024-12-31"])

    def test_small_three_month_rounding_is_a_note(self):
        data = ttm_company()
        direct = next(r for r in data["facts"]["us-gaap"][REVENUE]["units"]["USD"] if r["start"] == "2025-04-01")
        direct["val"] = 310.3
        result = ttm_layers(data)
        self.assertEqual((result["status"], statuses(result)["revenue"]), ("MATCHED_WITH_NOTES", "ROUNDING"))

    def test_material_quarter_difference_is_flagged(self):
        data = ttm_company()
        direct = next(r for r in data["facts"]["us-gaap"][REVENUE]["units"]["USD"] if r["start"] == "2025-04-01")
        direct["val"] = 360
        result = ttm_layers(data)
        self.assertEqual((result["status"], statuses(result)["revenue"]), ("DIFFERENCES", "VALUE_DIFFERS"))
        self.assertEqual(result["attention"][0]["difference"], 50)

    def test_missing_quarter_makes_comparison_unavailable(self):
        data = ttm_company()
        for concept in data["facts"]["us-gaap"].values():
            concept["units"]["USD"][:] = [r for r in concept["units"]["USD"] if r["end"] != "2025-06-30"]
        result = ttm_layers(data)
        self.assertEqual(result["status"], "NOT_COMPARABLE")

    def test_short_or_broken_quarter_window_is_not_compared(self):
        data = ttm_company()
        audit = audit_ttm(data, as_of=TTM_AS_OF)
        quarterly = build_quarterly_statements(data, as_of=TTM_AS_OF)
        short = dict(quarterly, quarters=quarterly["quarters"][:3])
        gap = dict(quarterly, quarters=[q for q in quarterly["quarters"] if q["end"] != "2025-03-31"])
        for name, case in (("three quarters", short), ("missing middle quarter", gap)):
            with self.subTest(name):
                self.assertEqual(reconcile_ttm(audit, case)["status"], "NOT_COMPARABLE")

    def test_unreconciled_ttm_is_not_applicable(self):
        result = reconcile_ttm({"status": "BLOCKED"}, {"quarters": []})
        self.assertEqual(result["status"], "NOT_APPLICABLE")


class ResearchReportTests(unittest.TestCase):
    def test_differences_become_research_gaps_and_html(self):
        data = ttm_company()
        direct = next(r for r in data["facts"]["us-gaap"][REVENUE]["units"]["USD"] if r["start"] == "2025-04-01")
        direct["val"] = 360
        report = build_company_research(data, as_of=TTM_AS_OF, expected_cik=99, sector="unknown")
        self.assertEqual(report["layer_reconciliation"]["ttm"]["status"], "DIFFERENCES")
        self.assertIn("SHARED_QUARTERS_DIFFER_FROM_TTM", report["research_gaps"])
        page = render_company_research(report)
        self.assertIn("Katman mutabakatı", page)
        self.assertIn("fark var — manuel inceleme gerekir", page)
        self.assertIn("TTM · revenue", page)

    def test_matching_layers_add_no_gap(self):
        report = build_company_research(ttm_company(), as_of=TTM_AS_OF, expected_cik=99, sector="unknown")
        self.assertEqual(report["layer_reconciliation"]["ttm"]["status"], "MATCHED")
        self.assertFalse([g for g in report["research_gaps"] if g.startswith("SHARED_")])

    def test_unavailable_checks_are_explained_in_turkish(self):
        page = render_company_research(
            build_company_research(company(), as_of=AS_OF, expected_cik=77, sector="non_financial"))
        self.assertIn("Piotroski girdileri ↔ yıllık tablolar: <span class='yes'>birebir eşleşti</span>", page)
        self.assertIn("iki TTM motoru mutabık değil", page)

    def test_old_report_without_reconciliation_renders(self):
        report = build_company_research(company(), as_of=AS_OF, expected_cik=77, sector="non_financial")
        del report["layer_reconciliation"]
        self.assertNotIn("Katman mutabakatı", render_company_research(report))


if __name__ == "__main__":
    unittest.main()
