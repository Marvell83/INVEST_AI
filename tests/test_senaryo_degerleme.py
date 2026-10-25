"""Offline synthetic tests: forecast scenarios valued with the v0.2 DCF."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from degerleme_v02 import degerle_v02
from finansal_oranlar import compute_ratios
from finansal_tablolar import build_annual_statements
from senaryo_degerleme import main, value_scenarios
from sirket_arastirma_akisi import build_company_research, render_company_research
from tahmin_motoru import historical_baseline, project_scenarios
from test_finansal_tablolar import AS_OF
from test_tahmin_motoru import LONG_RUN, five_year_company

DISCOUNT = dict(discount_rate=0.09, discount_source="Synthetic cost of capital source")


def with_shares(data=None):
    data = data or five_year_company()
    data["facts"]["dei"] = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"val": 100, "end": "2025-01-31", "form": "10-K", "accn": "a2024", "filed": "2025-02-15"}]}}}
    return data


def setup(data=None, **projection_kwargs):
    statements = build_annual_statements(data or with_shares(), as_of=AS_OF)
    baseline = historical_baseline(statements, compute_ratios(statements))
    kwargs = dict(LONG_RUN, **projection_kwargs)
    return statements, baseline, project_scenarios(baseline, **kwargs)


def value(data=None, projection_kwargs=None, **kwargs):
    statements, baseline, projection = setup(data, **(projection_kwargs or {}))
    return value_scenarios(projection, baseline, statements, **dict(DISCOUNT, **kwargs)), projection, baseline


def engine_inputs(projection, baseline, scenario="baz", discount=0.09, growth=0.03, roic=None):
    rows = projection["scenarios"][scenario]["rows"]
    return dict(yillar=len(rows), gelir_0=1200, buyume=[r["revenue_growth"] for r in rows],
                marj_0=0.15, marj_hedef=rows[-1]["operating_margin"], yakinlasma=1.0,
                marj_yolu=[r["operating_margin"] for r in rows],
                satis_sermaye=baseline["sales_to_capital"]["median"], vergi_orani=0.2, iskonto=discount,
                uc_buyume=growth, uc_roic=discount if roic is None else roic, hisse=100, net_borc=160)


class InputTests(unittest.TestCase):
    def test_every_input_keeps_its_origin(self):
        result, _, baseline = value()
        origins = {k: (v["value"], v["origin"]) for k, v in result["inputs"].items()}
        self.assertEqual(origins["discount_rate"], (0.09, "ANALYST"))
        self.assertEqual(origins["terminal_growth"], (0.03, "ANALYST"))
        self.assertEqual(origins["tax_rate"][1], "SEC_HISTORY")
        self.assertAlmostEqual(origins["tax_rate"][0], 0.2)
        self.assertEqual(origins["sales_to_capital"], (baseline["sales_to_capital"]["median"], "SEC_HISTORY"))
        self.assertEqual(origins["net_debt"], (160, "SEC_FILING"))   # 250 debt - 90 cash at FY2024
        self.assertEqual(origins["shares"], (100, "SEC_FILING"))
        self.assertEqual(origins["terminal_roic"], (0.09, "METHOD_DEFAULT"))
        self.assertIn("a2024", result["inputs"]["shares"]["source"])

    def test_missing_share_count_is_reported_not_guessed(self):
        result, _, _ = value(five_year_company())
        self.assertEqual((result["status"], result["missing"]), ("INPUTS_MISSING", ["shares"]))
        self.assertEqual(result["scenarios"], {})
        fixed, _, _ = value(five_year_company(), overrides={"shares": {"value": 100, "source": "Synthetic count"}})
        self.assertEqual((fixed["status"], fixed["inputs"]["shares"]["origin"]), ("OK", "ANALYST"))

    def test_analyst_inputs_are_validated(self):
        bad = (dict(discount_rate=0.02), dict(discount_rate=0.25), dict(discount_rate=True),
               dict(discount_source="short"), dict(overrides={"beta": {"value": 1, "source": "Synthetic source"}}),
               dict(overrides={"shares": {"value": 100}}), dict(overrides={"shares": 100}))
        for kwargs in bad:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                value(**kwargs)

    def test_terminal_growth_above_perpetual_cap_needs_override(self):
        with self.assertRaisesRegex(ValueError, "perpetual cap"):
            value(projection_kwargs=dict(long_run_growth=0.05))
        result, _, _ = value(projection_kwargs=dict(long_run_growth=0.05),
                             overrides={"terminal_growth": {"value": 0.03, "source": "Synthetic terminal source"}})
        self.assertEqual(result["status"], "OK")

    def test_unavailable_projection_and_foreign_issuer(self):
        statements = build_annual_statements(with_shares(), as_of=AS_OF, years=1)
        baseline = historical_baseline(statements, compute_ratios(statements))
        projection = project_scenarios(baseline, **LONG_RUN)
        self.assertEqual(value_scenarios(projection, baseline, statements, **DISCOUNT)["status"],
                         "PROJECTION_UNAVAILABLE")
        _, baseline, projection = setup()
        other = dict(statements, cik="0000000001")
        with self.assertRaises(ValueError):
            value_scenarios(projection, baseline, other, **DISCOUNT)


class ValuationTests(unittest.TestCase):
    def test_each_scenario_equals_direct_engine_run(self):
        result, projection, baseline = value()
        self.assertEqual(list(result["scenarios"]), ["temkinli", "baz", "iyimser"])
        for name in result["scenarios"]:
            expected = degerle_v02(engine_inputs(projection, baseline, name))
            self.assertAlmostEqual(result["scenarios"][name]["per_share"], expected["hisse_basi_deger"])
            self.assertAlmostEqual(result["scenarios"][name]["equity_value"], expected["ozsermaye_degeri"])

    def test_dcf_operating_income_matches_projection(self):
        _, projection, baseline = value()
        table = degerle_v02(engine_inputs(projection, baseline))["tablo"]
        for row, projected in zip(table, projection["scenarios"]["baz"]["rows"]):
            self.assertAlmostEqual(row["ebit"], projected["operating_income"])

    def test_sensitivity_grid(self):
        result, projection, baseline = value()
        grid = result["sensitivity"]
        self.assertEqual(grid["discount_rates"], [0.08, 0.085, 0.09, 0.095, 0.1])
        self.assertEqual(grid["terminal_growths"], [0.02, 0.025, 0.03, 0.035, 0.04])
        self.assertAlmostEqual(grid["per_share"][2][2], result["scenarios"]["baz"]["per_share"])
        # A neutral terminal RONIC follows the discount rate in every cell.
        corner = degerle_v02(engine_inputs(projection, baseline, discount=0.1, growth=0.02))["hisse_basi_deger"]
        self.assertAlmostEqual(grid["per_share"][4][0], corner)

    def test_invalid_grid_cells_are_empty(self):
        result, _, _ = value(discount_rate=0.05, projection_kwargs=dict(long_run_growth=0.035))
        grid = result["sensitivity"]
        self.assertIsNone(grid["per_share"][0][4])   # growth 4.5% > 4% cap
        self.assertIsNone(grid["per_share"][0][3])   # growth 4.0% >= discount 4.0%
        self.assertIsNotNone(grid["per_share"][2][2])

    def test_analyst_ronic_stays_fixed(self):
        result, projection, baseline = value(
            overrides={"terminal_roic": {"value": 0.15, "source": "Synthetic moat evidence"}})
        corner = degerle_v02(engine_inputs(projection, baseline, discount=0.1, growth=0.02, roic=0.15))
        self.assertAlmostEqual(result["sensitivity"]["per_share"][4][0], corner["hisse_basi_deger"])
        self.assertNotIn("TERMINAL_RONIC_NEUTRAL_DEFAULT", result["warnings"])

    def test_warnings(self):
        result, _, _ = value()
        self.assertIn("NET_DEBT_EXCLUDES_LEASES", result["warnings"])
        self.assertIn("NET_DEBT_NO_SECURITIES_REPORTED", result["warnings"])  # the fixture has no securities
        self.assertIn("TERMINAL_RONIC_NEUTRAL_DEFAULT", result["warnings"])
        self.assertIn("RETROSPECTIVE_PROJECTION", result["warnings"])


class ReportTests(unittest.TestCase):
    def research(self, data=None, **kwargs):
        return build_company_research(data or with_shares(), as_of=AS_OF, expected_cik=55,
                                      sector="non_financial", **kwargs)

    def test_valuation_section_with_origins_and_grid(self):
        report = self.research(long_run_growth=0.03, long_run_growth_source="<i>Synthetic</i> long run",
                               discount_rate=0.09, discount_rate_source="Synthetic WACC <b>note</b>")
        self.assertEqual(report["scenario_valuation"]["status"], "OK")
        page = render_company_research(report)
        self.assertIn("Senaryo değerlemesi (deneysel DCF)", page)
        self.assertIn("Hisse başı (USD)", page)
        self.assertIn("SEC dosyası", page)
        self.assertIn("Synthetic WACC &lt;b&gt;note&lt;/b&gt;", page)
        self.assertIn("iskonto 9.0%", page)

    def test_missing_input_is_explained(self):
        report = self.research(five_year_company(), long_run_growth=0.03,
                               long_run_growth_source="Synthetic long run", discount_rate=0.09,
                               discount_rate_source="Synthetic WACC source")
        self.assertIn("kapak sayfası hisse sayısı yok", render_company_research(report))

    def test_discount_needs_projection_inputs(self):
        with self.assertRaises(ValueError):
            self.research(discount_rate=0.09, discount_rate_source="Synthetic WACC source")
        self.assertIsNone(self.research()["scenario_valuation"])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            source, out = Path(folder) / "facts.json", Path(folder) / "out.json"
            source.write_text(json.dumps(five_year_company()), encoding="utf-8")
            args = ["--companyfacts", str(source), "--as-of", AS_OF, "--long-run-growth", "0.03",
                    "--long-run-source", "Synthetic long run", "--discount-rate", "0.09",
                    "--discount-source", "Synthetic WACC source", "--out", str(out)]
            main(args + ["--shares", "100", "--shares-source", "Synthetic share count"])
            report = json.loads(out.read_text(encoding="utf-8"))["valuation"]
            self.assertEqual((report["status"], report["inputs"]["shares"]["origin"]), ("OK", "ANALYST"))
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(args + ["--shares", "100"])


if __name__ == "__main__":
    unittest.main()
