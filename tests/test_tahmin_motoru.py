"""Offline synthetic tests for the scenario projection engine and its ledger records."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from finansal_oranlar import compute_ratios
from finansal_tablolar import build_annual_statements
from sirket_arastirma_akisi import build_company_research, render_company_research
from tahmin_defteri import TahminDefteri
from tahmin_motoru import historical_baseline, main, project_scenarios, record_projection
from test_finansal_tablolar import AS_OF, company, fact

YEARS = (2020, 2021, 2022, 2023, 2024)
FLOWS = {
    "RevenueFromContractWithCustomerExcludingAssessedTax": (700, 800, 1000, 1100, 1200),
    "OperatingIncomeLoss": (70, 96, 130, 154, 180),  # margins 10%, 12%, 13%, 14%, 15%
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest":
        (60, 86, 120, 144, 170),
    "IncomeTaxExpenseBenefit": (12, 17.2, 24, 28.8, 34),
    "NetIncomeLoss": (48, 68.8, 96, 115.2, 136),
    "NetCashProvidedByUsedInOperatingActivities": (80, 100, 130, 150, 170),
    "PaymentsToAcquirePropertyPlantAndEquipment": (20, 25, 30, 35, 40),
}
INSTANTS = {
    "StockholdersEquity": (400, 450, 520, 580, 640),
    "LongTermDebtNoncurrent": (200, 210, 230, 240, 250),
    "CashAndCashEquivalentsAtCarryingValue": (50, 60, 70, 80, 90),
    "Assets": (900, 1000, 1150, 1250, 1350),
}
LONG_RUN = dict(long_run_growth=0.03, long_run_growth_source="Synthetic long-run growth source")


def five_year_company():
    gaap = {}
    for tag, values in FLOWS.items():
        gaap[tag] = {"units": {"USD": [fact(v, y) for y, v in zip(YEARS, values)]}}
    for tag, values in INSTANTS.items():
        gaap[tag] = {"units": {"USD": [fact(v, y, instant=True) for y, v in zip(YEARS, values)]}}
    return {"cik": 55, "entityName": "SYNTHETIC FORECAST CO", "facts": {"us-gaap": gaap}}


def baseline_of(data):
    statements = build_annual_statements(data, as_of=AS_OF)
    return historical_baseline(statements, compute_ratios(statements))


GROWTH = sorted([800 / 700 - 1, 1000 / 800 - 1, 1100 / 1000 - 1, 1200 / 1100 - 1])


class BaselineTests(unittest.TestCase):
    def test_statistics_come_from_own_history(self):
        b = baseline_of(five_year_company())
        self.assertEqual(b["status"], "OK")
        self.assertEqual(b["base_fiscal_year_end"], "2024-12-31")
        self.assertEqual(b["revenue_growth"]["n"], 4)
        self.assertAlmostEqual(b["revenue_growth"]["median"], (GROWTH[1] + GROWTH[2]) / 2)
        self.assertAlmostEqual(b["revenue_growth"]["q1"], GROWTH[0] + (GROWTH[1] - GROWTH[0]) * 0.75)
        self.assertAlmostEqual(b["revenue_cagr"]["value"], (1200 / 700) ** 0.25 - 1)
        self.assertEqual((b["revenue_cagr"]["from"], b["revenue_cagr"]["years"]), ("2020-12-31", 4))
        self.assertAlmostEqual(b["operating_margin"]["median"], 0.13)
        self.assertAlmostEqual(b["effective_tax_rate"]["median"], 0.2)
        self.assertEqual([r["fiscal_year_end"][:4] for r in b["series"]], ["2020", "2021", "2022", "2023", "2024"])
        self.assertIn("a2024", b["sources"])

    def test_sales_to_capital_only_when_revenue_and_capital_grow(self):
        b = baseline_of(five_year_company())
        # 2021: +100 revenue / +50 invested capital (650 -> 700) = 2.0
        self.assertAlmostEqual(b["series"][1]["sales_to_capital"], 2.0)
        self.assertEqual(b["sales_to_capital"]["n"], 4)

    def test_shrinking_invested_capital_gives_no_sales_to_capital(self):
        data = five_year_company()
        data["facts"]["us-gaap"]["StockholdersEquity"]["units"]["USD"][3]["val"] = 400  # 2023 capital falls
        b = baseline_of(data)
        self.assertNotIn("sales_to_capital", b["series"][3])
        self.assertEqual(b["sales_to_capital"]["n"], 3)

    def test_one_year_of_history_is_insufficient(self):
        single = build_annual_statements(five_year_company(), as_of=AS_OF, years=1)
        b = historical_baseline(single, compute_ratios(single))
        self.assertEqual(b["status"], "INSUFFICIENT_HISTORY")
        self.assertIn("FEWER_THAN_2_REVENUE_GROWTH_OBSERVATIONS", b["reasons"])
        projection = project_scenarios(b, **LONG_RUN)
        self.assertEqual((projection["status"], projection["scenarios"]), ("INSUFFICIENT_HISTORY", {}))

    def test_baseline_rejects_foreign_ratios(self):
        statements = build_annual_statements(five_year_company(), as_of=AS_OF)
        other = build_annual_statements(company(), as_of=AS_OF)
        with self.assertRaises(ValueError):
            historical_baseline(statements, compute_ratios(other))


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.baseline = baseline_of(five_year_company())

    def test_three_scenarios_from_quartiles_fade_to_long_run(self):
        p = project_scenarios(self.baseline, years=5, **LONG_RUN)
        self.assertEqual(list(p["scenarios"]), ["temkinli", "baz", "iyimser"])
        starts = [p["scenarios"][s]["starting_growth"] for s in ("temkinli", "baz", "iyimser")]
        self.assertEqual(starts, sorted(starts))
        for scenario in p["scenarios"].values():
            last = scenario["rows"][-1]
            self.assertAlmostEqual(last["revenue_growth"], 0.03)
            self.assertAlmostEqual(last["operating_margin"], scenario["target_operating_margin"])
        self.assertAlmostEqual(p["scenarios"]["temkinli"]["target_operating_margin"], 0.12)
        self.assertAlmostEqual(p["scenarios"]["iyimser"]["target_operating_margin"], 0.14)

    def test_base_path_arithmetic(self):
        p = project_scenarios(self.baseline, years=4, **LONG_RUN)
        base = p["scenarios"]["baz"]
        g0 = self.baseline["revenue_growth"]["median"]
        g1 = g0 + (0.03 - g0) / 4
        first = base["rows"][0]
        self.assertAlmostEqual(first["revenue_growth"], g1)
        self.assertAlmostEqual(first["revenue"], 1200 * (1 + g1))
        self.assertAlmostEqual(first["operating_margin"], 0.15 + (0.13 - 0.15) / 4)
        self.assertAlmostEqual(first["operating_income"], first["revenue"] * first["operating_margin"])
        self.assertEqual(first["target_period"], "FY+1_AFTER_2024-12-31")
        self.assertEqual(p["method"]["name"], "HISTORICAL_QUANTILE_LINEAR_FADE")

    def test_short_history_gives_only_base_scenario(self):
        p = project_scenarios(baseline_of(company()), **LONG_RUN)
        self.assertEqual(list(p["scenarios"]), ["baz"])
        self.assertIn("SHORT_HISTORY_ONLY_BASE_SCENARIO", p["warnings"])

    def test_warnings_for_high_growth_and_high_long_run_rate(self):
        p = project_scenarios(baseline_of(company()), long_run_growth=0.06,
                              long_run_growth_source="Synthetic optimistic source")
        self.assertIn("LONG_RUN_GROWTH_ABOVE_TYPICAL_NOMINAL_ECONOMY", p["warnings"])
        data = five_year_company()
        data["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"] = [
            fact(v, y) for y, v in zip(YEARS, (100, 150, 220, 300, 420))]
        self.assertIn("HIGH_HISTORICAL_GROWTH_RARELY_PERSISTS",
                      project_scenarios(baseline_of(data), **LONG_RUN)["warnings"])

    def test_analyst_input_is_validated(self):
        bad = (dict(long_run_growth=0.2, long_run_growth_source="Synthetic source"),
               dict(long_run_growth=True, long_run_growth_source="Synthetic source"),
               dict(long_run_growth=float("nan"), long_run_growth_source="Synthetic source"),
               dict(long_run_growth=0.03, long_run_growth_source="short"),
               dict(long_run_growth=0.03, long_run_growth_source=None))
        for kwargs in bad:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                project_scenarios(self.baseline, **kwargs)
        for years in (0, 11, True):
            with self.subTest(years=years), self.assertRaises(ValueError):
                project_scenarios(self.baseline, years=years, **LONG_RUN)

    def test_retrospective_flag(self):
        after = project_scenarios(self.baseline, today=dt.date(2026, 1, 1), **LONG_RUN)
        same_day = project_scenarios(self.baseline, today=dt.date.fromisoformat(AS_OF), **LONG_RUN)
        self.assertEqual((after["retrospective"], same_day["retrospective"]), (True, False))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / "ledger.sqlite"
        self.projection = project_scenarios(baseline_of(five_year_company()), years=3, **LONG_RUN)

    def tearDown(self):
        self.folder.cleanup()

    def rows(self):
        with TahminDefteri(self.db) as ledger:
            return ledger.tahminleri_listele()

    def test_records_revenue_and_operating_income_per_year(self):
        ids = record_projection(self.projection, db_path=self.db, scenarios=("temkinli", "baz"))
        self.assertEqual(len(ids), 2 * 3 * 2)
        rows = self.rows()
        self.assertEqual({r["metric"] for r in rows}, {"revenue", "operating_income"})
        self.assertEqual({r["company"] for r in rows}, {"CIK:0000000055"})
        self.assertIn("FY+3_AFTER_2024-12-31", {r["target_period"] for r in rows})
        with TahminDefteri(self.db) as ledger:
            assumptions, sources = ledger.db.execute(
                "SELECT assumptions_json, sources_json FROM forecasts LIMIT 1").fetchone()
        self.assertEqual(json.loads(assumptions)["scenario"], "temkinli")
        self.assertIn("Long-run growth: Synthetic long-run growth source", json.loads(sources))

    def test_identical_projection_cannot_be_recorded_twice(self):
        record_projection(self.projection, db_path=self.db)
        with self.assertRaisesRegex(ValueError, "already recorded"):
            record_projection(self.projection, db_path=self.db)
        self.assertEqual(len(self.rows()), 6)

    def test_unknown_scenario_writes_nothing(self):
        with self.assertRaises(ValueError):
            record_projection(self.projection, db_path=self.db, scenarios=("baz", "missing"))
        self.assertFalse(self.db.exists() and self.rows())

    def test_failure_midway_leaves_no_partial_projection(self):
        original = TahminDefteri.tahmin_kaydet
        calls = []

        def failing(ledger, **kwargs):
            calls.append(1)
            if len(calls) == 4:
                raise RuntimeError("disk full")
            return original(ledger, **kwargs)
        with mock.patch.object(TahminDefteri, "tahmin_kaydet", failing):
            with self.assertRaises(RuntimeError):
                record_projection(self.projection, db_path=self.db)
        self.assertEqual(self.rows(), [])

    def test_insufficient_projection_is_not_recorded(self):
        single = build_annual_statements(five_year_company(), as_of=AS_OF, years=1)
        projection = project_scenarios(historical_baseline(single, compute_ratios(single)), **LONG_RUN)
        with self.assertRaises(ValueError):
            record_projection(projection, db_path=self.db)

    def test_cli_writes_report_and_ledger(self):
        source, out = Path(self.folder.name) / "facts.json", Path(self.folder.name) / "out.json"
        source.write_text(json.dumps(five_year_company()), encoding="utf-8")
        main(["--companyfacts", str(source), "--as-of", AS_OF, "--years", "2", "--long-run-growth", "0.03",
              "--long-run-source", "Synthetic CLI source", "--ledger", str(self.db),
              "--record-scenarios", "baz,iyimser", "--out", str(out)])
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(len(report["ledger_ids"]), 2 * 2 * 2)
        self.assertEqual(report["baseline"]["revenue_growth"]["n"], 4)


class ResearchReportTests(unittest.TestCase):
    def research(self, **kwargs):
        return build_company_research(five_year_company(), as_of=AS_OF, expected_cik=55,
                                      sector="non_financial", **kwargs)

    def test_baseline_always_shown_projection_needs_analyst_rate(self):
        report = self.research()
        self.assertIsNone(report["projection"])
        page = render_company_research(report)
        self.assertIn("Tarihsel baz ve senaryolar", page)
        self.assertIn("Sistem bu oranı kendisi seçmez", page)

    def test_projection_rendered_with_escaped_source(self):
        report = self.research(long_run_growth=0.03, long_run_growth_source="<b>IMF WEO</b> 2026")
        self.assertEqual(list(report["projection"]["scenarios"]), ["temkinli", "baz", "iyimser"])
        page = render_company_research(report)
        self.assertIn("İyimser", page)
        self.assertIn("&lt;b&gt;IMF WEO&lt;/b&gt; 2026", page)
        self.assertFalse(report["forecast_created"])

    def test_rate_and_source_must_come_together(self):
        with self.assertRaises(ValueError):
            self.research(long_run_growth=0.03)


if __name__ == "__main__":
    unittest.main()
