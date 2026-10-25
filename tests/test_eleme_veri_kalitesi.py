"""Synthetic tests for the fixes after the first full SEC-only screen (2,122 issuers).

Primary tickers, debt and D&A tag variants, ROE caution, split / unusual share counts
and the "why is it pending" breakdown.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from finansal_oranlar import compute_ratios
from finansal_tablolar import build_annual_statements
from hisse_tarama_tablosu import _lineup
from sec_arsiv import ticker_mapping
from sec_eleme_raporu import render_html, screen
from sec_piyasa_toplu_tarama import DB_REL, _check_stock_split, _placeholders, ingest_zip
from sec_sirket_profili import DB_REL as PROFILE_DB, import_profiles, load_profiles, parse_profile, primary_ticker
from sirket_arastirma_akisi import build_company_research
from test_finansal_tablolar import AS_OF, company, fact, row
from test_kapsam_raporu import four_year_company
from test_sec_eleme_raporu import GOOD, RATE, issuer

GAAP = "us-gaap"


def statements(data):
    return build_annual_statements(data, as_of=AS_OF)


def lineup(data):
    report = build_company_research(data, as_of=AS_OF, expected_cik=data["cik"], sector="non_financial",
                                    include_piotroski=False)
    return _lineup(report, ticker="SYN")


def rename(data, old, new):
    data["facts"][GAAP][new] = data["facts"][GAAP].pop(old)
    return data


class PrimaryTickerTests(unittest.TestCase):
    def test_sec_file_order_not_alphabetical(self):
        mapping = ticker_mapping({"0": {"ticker": "AMCR", "cik_str": 1748790, "title": "AMCOR"},
                                  "1": {"ticker": "AMCCF", "cik_str": 1748790, "title": "AMCOR"}})
        self.assertEqual(_placeholders(mapping), {"0001748790": "AMCR"})

    def test_listed_exchange_preferred_and_pairs_stay_aligned(self):
        amcor = parse_profile({"cik": 1748790, "tickers": ["AMCCF", "AMCR"], "exchanges": ["OTC", "NYSE"]})
        self.assertEqual((amcor["listings"], primary_ticker(amcor)), ("AMCCF:OTC,AMCR:NYSE", "AMCR"))
        gap = parse_profile({"cik": 2, "tickers": ["X", "Y"], "exchanges": [None, "Nasdaq"]})
        self.assertEqual((gap["listings"], gap["exchanges"], primary_ticker(gap)), ("X:,Y:Nasdaq", "Nasdaq", "Y"))
        otc = parse_profile({"cik": 3, "tickers": ["OTCA"], "exchanges": ["OTC"]})
        self.assertEqual(primary_ticker(otc), "OTCA")
        self.assertEqual(primary_ticker(None, "FALLBACK"), "FALLBACK")
        self.assertEqual(primary_ticker({"listings": None}, "FALLBACK"), "FALLBACK")

    def test_profile_import_replaces_an_older_table_layout(self):
        with tempfile.TemporaryDirectory() as root:
            ingest_zip(root, archive_path=_fixture(root), as_of=AS_OF)
            with sqlite3.connect(Path(root) / PROFILE_DB) as conn:
                conn.execute("CREATE TABLE profiles (cik TEXT PRIMARY KEY, name TEXT)")
            with zipfile.ZipFile(Path(root) / "veri" / "submissions.zip", "w") as z:
                z.writestr("CIK0000000055.json", json.dumps({"cik": "55", "sic": "3571", "tickers": ["SYN"],
                                                             "exchanges": ["Nasdaq"]}))
            import_profiles(root)
            self.assertEqual(load_profiles(root)["0000000055"]["listings"], "SYN:Nasdaq")

    def test_report_shows_the_listed_ticker(self):
        profile = {"cik": "0000000001", "sic": 2650, "sic_description": "Packaging", "division": "İmalat",
                   "financial": False, "exchanges": "OTC,NYSE", "listings": "AMCCF:OTC,AMCR:NYSE"}
        result = screen([issuer(1, ticker="AMCCF")], {"0000000001": profile}, rate=RATE)
        self.assertEqual(result["passed"][0]["ticker"], "AMCR")


def _fixture(root):
    folder = Path(root) / "veri"
    folder.mkdir(exist_ok=True)
    (folder / "sec_ticker_esleme.json").write_text(json.dumps(
        {"0": {"ticker": "SYN", "cik_str": 55, "title": "SYNTHETIC CO"}}), encoding="utf-8")
    data = four_year_company()
    data["facts"][GAAP]["StockholdersEquityNoteStockSplitConversionRatio1"] = {"units": {"pure": [
        {"val": 2, "end": "2023-06-15", "form": "10-K", "accn": "a2023", "filed": "2024-02-15"}]}}
    with zipfile.ZipFile(folder / "companyfacts.zip", "w") as archive:
        archive.writestr("CIK0000000055.json", json.dumps(data))
    return folder / "companyfacts.zip"


class DebtAndDepreciationTagTests(unittest.TestCase):
    # company(), FY2024: noncurrent 250, current maturities 30, commercial paper 20.
    def test_debt_with_finance_lease_tag_is_read(self):
        debt = row(statements(rename(company(), "LongTermDebtNoncurrent",
                                     "LongTermDebtAndCapitalLeaseObligations")))["balance"]
        self.assertEqual(debt["total_debt"]["value"], 300)
        self.assertTrue(debt["long_term_debt_noncurrent"]["fallback_concept"])

    def test_total_including_current_maturities_when_no_noncurrent_line(self):
        data = company()
        del data["facts"][GAAP]["LongTermDebtNoncurrent"]
        data["facts"][GAAP]["LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"] = {
            "units": {"USD": [fact(280, 2024, instant=True)]}}
        debt = row(statements(data))["balance"]["total_debt"]
        self.assertEqual((debt["value"], debt["components"]), (300, ["long_term_debt", "commercial_paper"]))

    def test_debt_current_replaces_its_parts(self):
        data = company()
        data["facts"][GAAP]["DebtCurrent"] = {"units": {"USD": [fact(70, 2024, instant=True)]}}
        debt = row(statements(data))["balance"]["total_debt"]
        self.assertEqual((debt["value"], debt["components"]), (320, ["long_term_debt_noncurrent", "debt_current"]))
        earlier = row(statements(data), "2023-12-31")["balance"]["total_debt"]   # no DebtCurrent that year
        self.assertEqual(earlier["components"], ["long_term_debt_noncurrent", "long_term_debt_current"])

    def test_depreciation_and_other_gives_ebitda(self):
        data = rename(company(), "DepreciationDepletionAndAmortization", "DepreciationAmortizationAndOther")
        cell = row(statements(data))["cash_flow"]["depreciation_amortization"]
        self.assertEqual((cell["value"], cell["fallback_concept"]), (30, True))
        self.assertEqual(lineup(data)["ebitda"], 260 + 30)


class CautionTests(unittest.TestCase):
    def test_roe_above_one_hundred_percent_is_flagged(self):
        data = company()
        for r in data["facts"][GAAP]["StockholdersEquity"]["units"]["USD"]:
            r["val"] = 10                                        # buybacks left almost no equity
        ratios = compute_ratios(statements(data))["years"][0]["ratios"]
        self.assertEqual(ratios["roe"]["caution"], "VERY_SMALL_EQUITY")
        self.assertTrue(lineup(data)["roe_warning"])
        normal = compute_ratios(statements(company()))["years"][0]["ratios"]["roe"]
        self.assertNotIn("caution", normal)
        self.assertFalse(lineup(company())["roe_warning"])

    def test_unusual_three_year_share_change_is_flagged(self):
        data = four_year_company()
        shares = data["facts"][GAAP]["WeightedAverageNumberOfDilutedSharesOutstanding"]["units"]["shares"]
        next(r for r in shares if r["fy"] == 2021)["val"] = 50  # 100 / 50: doubled, likely a split
        self.assertTrue(lineup(data)["shares_change_unusual"])
        self.assertNotIn("shares_change_unusual", lineup(four_year_company()))

    def test_reported_split_withholds_share_change_and_eps_growth(self):
        new = {"fiscal_year": "2024-12-31", "shares_change_3y": 1.0, "eps_cagr_3y": 0.5, "pending_reasons": {}}
        raw = {"facts": {GAAP: {"StockholdersEquityNoteStockSplitConversionRatio1": {"units": {"pure": [
            {"val": 2, "end": "2023-06-15"}]}}}}}
        _check_stock_split(new, raw)
        self.assertEqual((new["shares_change_3y"], new["eps_cagr_3y"]), (None, None))
        self.assertEqual(new["stock_split"], {"ratio": 2.0, "date": "2023-06-15"})
        self.assertEqual(new["pending_reasons"]["shares_change_3y"], "STOCK_SPLIT_IN_WINDOW")
        old = dict(new, shares_change_3y=1.0, eps_cagr_3y=0.5)
        old.pop("stock_split")
        raw["facts"][GAAP]["StockholdersEquityNoteStockSplitConversionRatio1"]["units"]["pure"][0]["end"] = "2021-06-15"
        _check_stock_split(old, raw)                           # before the 3-year window
        self.assertEqual((old["shares_change_3y"], old.get("stock_split")), (1.0, None))

    def test_ingest_applies_the_split_check(self):
        with tempfile.TemporaryDirectory() as root:
            ingest_zip(root, archive_path=_fixture(root), as_of=AS_OF)
            with sqlite3.connect(Path(root) / DB_REL) as conn:
                payload = json.loads(conn.execute("SELECT payload FROM companies").fetchone()[0])
            self.assertEqual(payload["stock_split"]["ratio"], 2.0)
            self.assertIsNone(payload["eps_cagr_3y"])


class PendingReasonTests(unittest.TestCase):
    def test_reasons_for_missing_screen_inputs(self):
        self.assertEqual(lineup(company())["pending_reasons"], {})
        no_da = lineup(rename(company(), "DepreciationDepletionAndAmortization", "UnusedConcept"))
        self.assertEqual(no_da["pending_reasons"]["net_debt_to_ebitda"], "EBITDA:DEPRECIATION_AMORTIZATION_MISSING")
        data = company()
        for tag in ("LongTermDebtNoncurrent", "LongTermDebtCurrent", "CommercialPaper"):
            del data["facts"][GAAP][tag]
        reasons = lineup(data)["pending_reasons"]
        self.assertEqual(reasons["net_debt_to_ebitda"], "NET_DEBT:TOTAL_DEBT:NO_DEBT_COMPONENT_REPORTED")
        self.assertEqual(reasons["roic"], "INPUT_UNAVAILABLE:average_invested_capital")
        no_cash = company()
        del no_cash["facts"][GAAP]["CashAndCashEquivalentsAtCarryingValue"]
        self.assertEqual(lineup(no_cash)["pending_reasons"]["net_debt_to_ebitda"], "NET_DEBT:CASH:NOT_REPORTED")

    def test_three_year_reasons(self):
        short = lineup(company(years=(2023, 2024)))["pending_reasons"]
        self.assertEqual((short["cash_conversion_3y"], short["fcf_3y"]),
                         ("FEWER_THAN_3_CONSECUTIVE_FISCAL_YEARS", "FEWER_THAN_3_CONSECUTIVE_FISCAL_YEARS"))
        losses = company()
        for r in losses["facts"][GAAP]["NetIncomeLoss"]["units"]["USD"]:
            r["val"] = -r["val"]
        self.assertEqual(lineup(losses)["pending_reasons"]["cash_conversion_3y"], "NET_INCOME_3Y_NOT_POSITIVE")
        gap = company()
        capex = gap["facts"][GAAP]["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"]
        capex[:] = [r for r in capex if r["fy"] != 2023]
        self.assertEqual(lineup(gap)["pending_reasons"]["fcf_3y"], "FCF_MISSING_IN_A_YEAR")
        single = lineup(company(years=(2024,)))["pending_reasons"]
        self.assertEqual(single["roe"], "PRIOR_FISCAL_YEAR_REQUIRED")

    def test_report_counts_reasons_and_marks_suspect_values(self):
        rows = [issuer(1, roe=15.0, roe_warning=True, shares_change_3y=1.0, shares_change_unusual=True,
                       eps_cagr_3y=3.0, cash_conversion_3y=9.0),
                issuer(2, net_debt_to_ebitda=None,
                       pending_reasons={"net_debt_to_ebitda": "EBITDA:DEPRECIATION_AMORTIZATION_MISSING"}),
                issuer(3, net_debt_to_ebitda=None)]            # saved by an older version
        result = screen(rows, {}, rate=RATE)
        leverage = next(c for c in result["conditions"] if c["key"] == "net_debt_to_ebitda")
        self.assertEqual(leverage["pending_reasons"],
                         {"EBITDA:DEPRECIATION_AMORTIZATION_MISSING": 1, "OLD_ROW_REBUILD_NEEDED": 1})
        self.assertEqual(result["roe_cautions_among_passed"], 1)
        page = render_html(result, as_of=AS_OF)
        self.assertIn("amortisman bildirilmemiş (FAVÖK yok)", page)
        self.assertIn("%1500,0 !", page)
        self.assertIn("%100,0 ?", page)                         # unusual share change
        self.assertIn("%300,0 ?", page)                         # EPS CAGR above 100%
        self.assertIn("9,00x ?", page)                          # CFO / net income above 5
        no_rate = screen([issuer(4, roe=None)], {}, rate=None)
        roe = next(c for c in no_rate["conditions"] if c["key"] == "roe")
        self.assertEqual(roe["pending_reasons"], {})            # waiting on the rate, not on data
        self.assertEqual(GOOD["roe"], 0.25)


if __name__ == "__main__":
    unittest.main()
