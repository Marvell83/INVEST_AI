"""Offline synthetic tests: ledger forecasts scored against later SEC actuals."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from finansal_oranlar import compute_ratios
from finansal_tablolar import build_annual_statements
from sapma_analizi import analyze_variance, main
from tahmin_defteri import TahminDefteri
from tahmin_motoru import historical_baseline, project_scenarios, record_projection
from test_finansal_tablolar import fact
from test_tahmin_motoru import LONG_RUN, five_year_company

FORECAST_AS_OF = "2024-03-01"   # FY2020-FY2023 known when the projection is made
ACTUAL_AS_OF = "2025-03-01"     # FY2024 10-K (filed 2025-02-15) is now public
REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"
COMPANY = "CIK:0000000055"


class VarianceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / "ledger.sqlite"
        statements = build_annual_statements(five_year_company(), as_of=FORECAST_AS_OF)
        self.projection = project_scenarios(historical_baseline(statements, compute_ratios(statements)),
                                            years=3, **LONG_RUN)
        record_projection(self.projection, db_path=self.db, scenarios=("temkinli", "baz", "iyimser"))

    def tearDown(self):
        self.folder.cleanup()

    def analyze(self, data=None, as_of=ACTUAL_AS_OF, record=False):
        return analyze_variance(db_path=self.db, raw=data or five_year_company(), as_of=as_of, record=record)

    def ledger(self):
        with TahminDefteri(self.db) as ledger:
            return ledger.gerceklesenleri_listele(), ledger.puanlari_listele()

    def row(self, report, metric, scenario, target="FY+1_AFTER_2023-12-31"):
        return next(r for r in report["rows"]
                    if (r["metric"], r["scenario"], r["target_period"]) == (metric, scenario, target))

    def add(self, metric, target, predicted, assumptions=None, company=COMPANY):
        with TahminDefteri(self.db) as ledger:
            return ledger.tahmin_kaydet(company=company, metric=metric, target_period=target, currency="USD",
                                        predicted=predicted, model_version="sec-reviewed-test",
                                        assumptions=assumptions or {"historic_as_of": FORECAST_AS_OF},
                                        sources=["synthetic"])

    def test_first_year_scored_later_years_wait(self):
        report = self.analyze()
        self.assertEqual(report["summary"]["by_status"], {"SCORED": 6, "NOT_YET_REPORTED": 12})
        row = self.row(report, "revenue", "baz")
        predicted = self.projection["scenarios"]["baz"]["rows"][0]["revenue"]
        self.assertEqual((row["fiscal_year_end"], row["actual"], row["actual_accession"]),
                         ("2024-12-31", 1200, "a2024"))
        self.assertAlmostEqual(row["signed_error"], predicted - 1200)
        self.assertAlmostEqual(row["percentage_error"], (predicted - 1200) / 1200)
        self.assertEqual(self.row(report, "operating_income", "temkinli")["actual"], 180)
        self.assertEqual(self.row(report, "revenue", "baz", "FY+2_AFTER_2023-12-31")["status"], "NOT_YET_REPORTED")

    def test_dry_run_writes_nothing(self):
        self.analyze()
        self.assertEqual(self.ledger(), ([], []))

    def test_recording_is_one_outcome_per_target_and_idempotent(self):
        first = self.analyze(record=True)
        outcomes, scores = self.ledger()
        self.assertEqual((len(outcomes), len(scores)), (2, 6))
        self.assertEqual({o["target_period"] for o in outcomes}, {"FY+1_AFTER_2023-12-31"})
        self.assertIn("first reported value", outcomes[0]["source"])
        self.assertTrue(all("evaluation_id" in r for r in first["rows"] if r["status"] == "SCORED"))
        second = self.analyze(record=True)
        self.assertEqual(self.ledger(), (outcomes, scores))
        self.assertTrue(all(r["already_recorded"] for r in second["rows"] if r["status"] == "SCORED"))

    def test_first_reported_actual_is_used_after_restatement(self):
        data = five_year_company()
        data["facts"]["us-gaap"][REVENUE]["units"]["USD"].append(
            fact(1250, 2024, accn="a2025", filed="2026-02-15"))
        row = self.row(self.analyze(data, as_of="2026-03-01"), "revenue", "baz")
        self.assertEqual((row["actual"], row["latest_actual"], row["restated"]), (1200, 1250, True))
        self.assertEqual(row["actual_accession"], "a2024")

    def test_actual_invisible_before_its_filing_date(self):
        report = self.analyze(as_of="2025-02-14")
        self.assertEqual(report["summary"]["by_status"], {"NOT_YET_REPORTED": 18})

    def test_sec_reviewed_targets_and_unobservable_fcff(self):
        self.add("ebit", "FY_END:2024-12-28", 170)        # 52/53-week calendars: within 7 days
        self.add("fcff", "FY_END:2024-12-31", 90)
        self.add("revenue", "FY_END:2026-12-31", 1300)
        report = self.analyze()
        by_metric = {(r["metric"], r["target_period"]): r for r in report["rows"]}
        ebit = by_metric[("ebit", "FY_END:2024-12-28")]
        self.assertEqual((ebit["status"], ebit["actual"], ebit["signed_error"]), ("SCORED", 180, -10))
        self.assertEqual(by_metric[("fcff", "FY_END:2024-12-31")]["status"], "NOT_OBSERVABLE")
        self.assertEqual(by_metric[("revenue", "FY_END:2026-12-31")]["status"], "NOT_YET_REPORTED")

    def test_missing_fiscal_year_is_not_skipped_over(self):
        data = five_year_company()
        for concept in data["facts"]["us-gaap"].values():
            concept["units"]["USD"][:] = [r for r in concept["units"]["USD"] if r["end"] != "2023-12-31"]
        self.add("revenue", "FY+1_AFTER_2022-12-31", 1100)  # FY2023 is absent; FY2024 is not "FY+1"
        row = next(r for r in self.analyze(data)["rows"] if r["target_period"] == "FY+1_AFTER_2022-12-31")
        self.assertEqual(row["status"], "FISCAL_YEAR_CHAIN_BROKEN")

    def test_unsupported_period_and_other_issuers(self):
        self.add("revenue", "2027-FY", 1)
        self.add("revenue", "FY+1_AFTER_2023-12-31", 1, company="CIK:0000000099")
        report = self.analyze()
        self.assertEqual(report["summary"]["by_status"]["UNSUPPORTED_TARGET_PERIOD"], 1)
        self.assertEqual(report["summary"]["forecasts"], 19)

    def test_summary_accuracy_and_scenario_range(self):
        summary = self.analyze()["summary"]
        revenue_base = next(a for a in summary["accuracy"] if (a["metric"], a["scenario"]) == ("revenue", "baz"))
        predicted = self.projection["scenarios"]["baz"]["rows"][0]["revenue"]
        self.assertEqual(revenue_base["n"], 1)
        self.assertAlmostEqual(revenue_base["mean_absolute_percentage_error"], abs(predicted - 1200) / 1200)
        expected = 0
        for metric, actual in (("revenue", 1200), ("operating_income", 180)):
            low = self.projection["scenarios"]["temkinli"]["rows"][0][metric]
            high = self.projection["scenarios"]["iyimser"]["rows"][0][metric]
            expected += min(low, high) <= actual <= max(low, high)
        self.assertEqual(summary["scenario_range"], {"ranges": 2, "actual_inside": expected})

    def test_failure_midway_leaves_ledger_unchanged(self):
        original = TahminDefteri.puanla
        calls = []

        def failing(ledger, forecast_id, outcome_id):
            calls.append(1)
            if len(calls) == 3:
                raise RuntimeError("disk full")
            return original(ledger, forecast_id, outcome_id)
        with mock.patch.object(TahminDefteri, "puanla", failing):
            with self.assertRaises(RuntimeError):
                self.analyze(record=True)
        self.assertEqual(self.ledger(), ([], []))

    def test_cli_writes_json_and_escaped_html(self):
        data = five_year_company()
        data["entityName"] = "<script>alert(1)</script>"
        source = Path(self.folder.name) / "facts.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        out, page = Path(self.folder.name) / "v.json", Path(self.folder.name) / "v.html"
        main(["--ledger", str(self.db), "--companyfacts", str(source), "--as-of", ACTUAL_AS_OF,
              "--record", "--out", str(out), "--out-html", str(page)])
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["summary"]["scored"], 6)
        text = page.read_text(encoding="utf-8")
        self.assertIn("SAPMA ANALİZİ", text)
        self.assertIn("puanlandı", text)
        self.assertNotIn("<script>alert", text)
        self.assertEqual(len(self.ledger()[1]), 6)


class LedgerReadTests(unittest.TestCase):
    def test_detailed_listing_and_outer_transaction(self):
        with tempfile.TemporaryDirectory() as folder, TahminDefteri(Path(folder) / "l.sqlite") as ledger:
            ledger.tahmin_kaydet(company="X", metric="revenue", target_period="P", currency="USD",
                                 predicted=1.0, model_version="m", assumptions={"scenario": "baz"},
                                 sources=["s"])
            self.assertEqual(ledger.tahminleri_listele(ayrintili=True)[0]["assumptions"], {"scenario": "baz"})
            self.assertNotIn("assumptions", ledger.tahminleri_listele()[0])
            ledger.db.execute("BEGIN IMMEDIATE")
            ledger.gerceklesen_kaydet(company="X", metric="revenue", target_period="P", currency="USD",
                                      actual=1.0, source="s")
            ledger.db.rollback()
            self.assertEqual(ledger.gerceklesenleri_listele(), [])


if __name__ == "__main__":
    unittest.main()
