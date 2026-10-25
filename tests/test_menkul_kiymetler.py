"""Offline synthetic tests: marketable securities, lease liabilities and net debt in the shared layer."""
from __future__ import annotations

import unittest

from finansal_oranlar import compute_ratios
from finansal_tablolar import build_annual_statements
from katman_mutabakati import layer_health
from sec_toplu_tarama import health_summary_lines
from sirket_analiz_paneli import render_financial_sections, render_valuation_section
from sirket_arastirma_akisi import build_company_research
from tahmin_motoru import historical_baseline
from test_finansal_tablolar import AS_OF, company, fact, row
from test_senaryo_degerleme import value, with_shares
from test_tahmin_motoru import five_year_company

CURRENT, NONCURRENT, SHORT_TERM = "MarketableSecuritiesCurrent", "MarketableSecuritiesNoncurrent", "ShortTermInvestments"


def with_instants(data, values, year=2024, accn=None):
    for tag, val in values.items():
        data["facts"]["us-gaap"][tag] = {"units": {"USD": [fact(val, year, instant=True, accn=accn)]}}
    return data


def balance(data):
    return row(build_annual_statements(data, as_of=AS_OF))["balance"]


class NetDebtTests(unittest.TestCase):
    # company(), FY2024: debt 250 + 30 current + 20 commercial paper = 300, cash 150, equity 700.
    def test_without_securities_only_cash_is_deducted(self):
        cells = balance(company())
        self.assertEqual((cells["liquid_investments"]["status"], cells["liquid_investments"]["reason"]),
                         ("MISSING", "NO_SECURITIES_COMPONENT_REPORTED"))
        net = cells["net_debt"]
        self.assertEqual((net["status"], net["value"], net["deducted"]), ("DERIVED", 150, ["cash"]))
        self.assertEqual(net["method"], "TOTAL_DEBT_MINUS_CASH_NO_SECURITIES_REPORTED")
        self.assertEqual((net["sources"], net["excludes"]), (["a2024"], "lease liabilities"))

    def test_current_and_noncurrent_securities_are_deducted(self):
        cells = balance(with_instants(company(), {CURRENT: 40, NONCURRENT: 100}))
        liquid = cells["liquid_investments"]
        self.assertEqual((liquid["status"], liquid["value"]), ("DERIVED", 140))
        self.assertEqual(liquid["components"], ["marketable_securities_current", "marketable_securities_noncurrent"])
        self.assertEqual(liquid["components_not_reported"], ["short_term_investments"])
        self.assertNotIn("overlap", liquid)
        net = cells["net_debt"]
        self.assertEqual((net["value"], net["method"]), (10, "TOTAL_DEBT_MINUS_CASH_AND_SECURITIES"))
        self.assertEqual((net["deducted"], net["securities_lower_bound"]), (["cash", "liquid_investments"], False))

    def test_possibly_overlapping_current_lines_are_never_both_added(self):
        cells = balance(with_instants(company(), {SHORT_TERM: 60, CURRENT: 40, NONCURRENT: 100}))
        liquid = cells["liquid_investments"]
        self.assertEqual(liquid["value"], 160)
        self.assertEqual(liquid["overlap"], {"rule": "LARGER_OF_POSSIBLY_OVERLAPPING_CURRENT_LINES",
                                             "lower_bound": True, "not_added": CURRENT, "not_added_value": 40})
        self.assertEqual((cells["net_debt"]["value"], cells["net_debt"]["securities_lower_bound"]), (-10, True))
        duplicate = balance(with_instants(company(), {SHORT_TERM: 40, CURRENT: 40}))["liquid_investments"]
        self.assertEqual(duplicate["value"], 40)

    def test_unresolved_securities_make_net_debt_unavailable(self):
        data = with_instants(company(), {CURRENT: 40})
        with_instants(data, {NONCURRENT: 100}, accn="other-filing")
        cells = balance(data)
        self.assertEqual(cells["liquid_investments"]["reason"], "SECURITIES_COMPONENTS_FROM_DIFFERENT_FILINGS")
        self.assertEqual((cells["net_debt"]["status"], cells["net_debt"]["reason"]),
                         ("MISSING", "DEBT_CASH_OR_SECURITIES_UNAVAILABLE"))

    def test_missing_debt_or_cash_makes_net_debt_unavailable(self):
        data = company()
        del data["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"]
        self.assertEqual(balance(data)["net_debt"]["status"], "MISSING")

    def test_lease_liabilities_are_shown_but_not_in_net_debt(self):
        cells = balance(with_instants(company(), {"OperatingLeaseLiabilityCurrent": 5,
                                                  "OperatingLeaseLiabilityNoncurrent": 45,
                                                  "FinanceLeaseLiabilityNoncurrent": 10}))
        leases = cells["lease_liabilities"]
        self.assertEqual((leases["status"], leases["value"]), ("DERIVED", 60))
        self.assertEqual(leases["components_not_reported"], ["finance_lease_liability_current"])
        self.assertEqual(cells["net_debt"]["value"], 150)
        self.assertEqual(balance(company())["lease_liabilities"]["reason"], "NO_LEASE_COMPONENT_REPORTED")


class ConsumerTests(unittest.TestCase):
    def test_ratios_use_net_debt_for_net_debt_and_roic(self):
        statements = build_annual_statements(with_instants(company(), {CURRENT: 40, NONCURRENT: 100}), as_of=AS_OF)
        ratios = compute_ratios(statements)["years"][0]["ratios"]
        self.assertEqual(ratios["net_debt"]["value"], 10)
        # Invested capital: 2024 equity 700 + net debt 10; 2023 equity 580 + (210 debt - 120 cash).
        self.assertAlmostEqual(ratios["roic"]["value"], 260 * (1 - 50 / 250) / ((710 + 670) / 2))

    def test_sales_to_capital_uses_net_debt(self):
        data = with_instants(five_year_company(), {CURRENT: 50})
        statements = build_annual_statements(data, as_of=AS_OF)
        series = historical_baseline(statements, compute_ratios(statements))["series"]
        latest = next(r for r in series if r["fiscal_year_end"] == "2024-12-31")
        # Invested capital 640 + (250 - 90 - 50) = 750 against 580 + (240 - 80) = 740.
        self.assertAlmostEqual(latest["sales_to_capital"], 100 / 10)

    def test_valuation_input_and_warnings(self):
        result, _, _ = value(with_shares(with_instants(five_year_company(), {CURRENT: 50})))
        net_debt = result["inputs"]["net_debt"]
        self.assertEqual((net_debt["value"], net_debt["origin"]), (110, "SEC_FILING"))
        self.assertIn("toplam borç − nakit − menkul kıymetler", net_debt["source"])
        self.assertIn("NET_DEBT_EXCLUDES_LEASES", result["warnings"])
        self.assertNotIn("NET_DEBT_NO_SECURITIES_REPORTED", result["warnings"])
        self.assertNotIn("NET_DEBT_SECURITIES_LOWER_BOUND", result["warnings"])
        overlap, _, _ = value(with_shares(with_instants(five_year_company(), {CURRENT: 50, SHORT_TERM: 30})))
        self.assertEqual(overlap["inputs"]["net_debt"]["value"], 110)
        self.assertIn("NET_DEBT_SECURITIES_LOWER_BOUND", overlap["warnings"])
        self.assertIn("yalnız büyüğü düşüldü", render_valuation_section(overlap))

    def test_analyst_net_debt_carries_no_sec_warning(self):
        result, _, _ = value(overrides={"net_debt": {"value": 75, "source": "Analyst reconciliation note"}})
        self.assertEqual(result["inputs"]["net_debt"]["origin"], "ANALYST")
        self.assertFalse([w for w in result["warnings"] if w.startswith("NET_DEBT_")])

    def test_layer_health_reports_the_securities_basis(self):
        def basis(data):
            research = build_company_research(data, as_of=AS_OF, expected_cik=77, sector="non_financial")
            return layer_health(research)["net_debt_securities"]
        self.assertEqual(basis(company()), "NONE_REPORTED")
        self.assertEqual(basis(with_instants(company(), {CURRENT: 40})), "DEDUCTED")
        self.assertEqual(basis(with_instants(company(), {CURRENT: 40, SHORT_TERM: 60})), "LOWER_BOUND")
        unresolved = with_instants(with_instants(company(), {CURRENT: 40}), {NONCURRENT: 1}, accn="other")
        self.assertEqual(basis(unresolved), "NET_DEBT_UNAVAILABLE")
        lines = "\n".join(health_summary_lines({"layer_health_counts": {
            "issuers": 1, "net_debt_securities": {"DEDUCTED": 1}}}))
        self.assertIn("Net borçta menkul kıymetler: DEDUCTED 1", lines)

    def test_html_lists_the_new_balance_rows(self):
        statements = build_annual_statements(with_instants(company(), {CURRENT: 40}), as_of=AS_OF)
        page = render_financial_sections(statements, compute_ratios(statements))
        for label in ("Menkul kıymetler (kısa vadeli)", "Faaliyet kiralaması yükümlülüğü (uzun vadeli)",
                      "Net borç (toplam borç − nakit − menkul kıymetler)",
                      "Kira yükümlülükleri (faaliyet + finansal; net borca dahil değil)"):
            self.assertIn(label, page)


if __name__ == "__main__":
    unittest.main()
