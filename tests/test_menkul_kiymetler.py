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


def restated_securities():
    """Current securities restated in a later filing, noncurrent only in the original one."""
    data = with_instants(company(), {CURRENT: 40, NONCURRENT: 100})
    data["facts"]["us-gaap"][CURRENT]["units"]["USD"].append(
        fact(45, 2024, instant=True, accn="restated", filed="2025-02-20"))
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
        self.assertEqual(liquid["components_not_reported"], ["short_term_investments", "other_short_term_investments"])
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
        cells = balance(restated_securities())
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
        self.assertEqual(basis(restated_securities()), "NET_DEBT_UNAVAILABLE")
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


OTHER_SHORT_TERM, UNCLASSIFIED = "OtherShortTermInvestments", "MarketableSecurities"


class IssuerTaggingTests(unittest.TestCase):
    """Tag variants seen in the real SEC data check (Coca-Cola, P&G, J&J, Apple)."""

    def test_other_short_term_investments_and_unsplit_securities_are_added(self):
        # Coca-Cola: "OtherShortTermInvestments" 3.6 and "MarketableSecurities" 1.93, no maturity split.
        cells = balance(with_instants(company(), {OTHER_SHORT_TERM: 36, UNCLASSIFIED: 19}))
        liquid = cells["liquid_investments"]
        self.assertEqual((liquid["value"], liquid["components"]),
                         (55, ["other_short_term_investments", "marketable_securities_unclassified"]))
        self.assertNotIn("overlap", liquid)
        self.assertEqual(cells["net_debt"]["value"], 300 - 150 - 55)

    def test_unsplit_total_is_ignored_when_a_maturity_split_is_reported(self):
        cells = balance(with_instants(company(), {UNCLASSIFIED: 140, CURRENT: 40, NONCURRENT: 100}))
        self.assertEqual(cells["liquid_investments"]["value"], 140)
        self.assertNotIn("marketable_securities_unclassified", cells["liquid_investments"]["components_not_reported"])

    def test_short_term_investments_and_unsplit_total_may_overlap(self):
        liquid = balance(with_instants(company(), {SHORT_TERM: 30, UNCLASSIFIED: 50}))["liquid_investments"]
        self.assertEqual((liquid["value"], liquid["overlap"]["not_added"]), (50, SHORT_TERM))

    def test_cash_fallback_includes_restricted_cash(self):
        # P&G tags its balance-sheet cash only with the restricted-cash-inclusive concept.
        data = company()
        gaap = data["facts"]["us-gaap"]
        gaap["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"] = gaap.pop(
            "CashAndCashEquivalentsAtCarryingValue")
        statements = build_annual_statements(data, as_of=AS_OF)
        cash = row(statements)["balance"]["cash"]
        self.assertEqual((cash["status"], cash["value"], cash["fallback_concept"]), ("REPORTED", 150, True))
        self.assertEqual(row(statements)["balance"]["net_debt"]["value"], 150)
        page = render_financial_sections(statements, compute_ratios(statements))
        self.assertIn("Nakde kısıtlı nakit de dahil olabilir.", page)

    def test_primary_cash_wins_over_the_fallback(self):
        data = with_instants(company(), {"CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": 170})
        cash = balance(data)["cash"]
        self.assertEqual((cash["value"], cash["concept"]), (150, "CashAndCashEquivalentsAtCarryingValue"))
        self.assertNotIn("fallback_concept", cash)

    def test_equity_fallback_includes_noncontrolling_interest(self):
        data = company()
        gaap = data["facts"]["us-gaap"]
        gaap["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"] = gaap.pop("StockholdersEquity")
        statements = build_annual_statements(data, as_of=AS_OF)
        equity = row(statements)["balance"]["stockholders_equity"]
        self.assertEqual((equity["value"], equity["fallback_concept"]), (700, True))
        self.assertIsNotNone(compute_ratios(statements)["years"][0]["ratios"]["roic"]["value"])
        page = render_financial_sections(statements, compute_ratios(statements))
        self.assertIn("Özkaynağa azınlık payları da dahildir.", page)

    def test_very_high_roic_carries_a_caution(self):
        # Securities larger than debt minus cash shrink invested capital, as for Apple:
        # 208 NOPAT / average of (700 + 300 - 150 - 690) and (580 + 210 - 120 - 600) = 1.81.
        data = company()
        data["facts"]["us-gaap"][NONCURRENT] = {"units": {"USD": [fact(690, 2024, instant=True),
                                                                   fact(600, 2023, instant=True)]}}
        statements = build_annual_statements(data, as_of=AS_OF)
        roic = compute_ratios(statements)["years"][0]["ratios"]["roic"]
        self.assertAlmostEqual(roic["value"], 208 / 115)
        self.assertEqual(roic["caution"], "VERY_SMALL_INVESTED_CAPITAL")
        page = render_financial_sections(statements, compute_ratios(statements))
        self.assertIn("title='yatırılan sermaye çok küçük; oranı dikkatle yorumlayın'", page)
        self.assertIn("!</td>", page)
        # 50% is high but readable: no caution below 100%.
        high = build_annual_statements(with_instants(company(), {NONCURRENT: 690}), as_of=AS_OF)
        high_roic = compute_ratios(high)["years"][0]["ratios"]["roic"]
        self.assertAlmostEqual(high_roic["value"], 208 / 415)
        self.assertNotIn("caution", high_roic)


if __name__ == "__main__":
    unittest.main()
