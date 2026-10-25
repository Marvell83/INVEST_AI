"""Offline synthetic tests: per-issuer layer health and the multi-company summary."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from katman_mutabakati import layer_health
from sec_toplu_tarama import _export, health_summary_lines, resolve_universe
from sirket_arastirma_akisi import build_company_research
from test_finansal_tablolar import AS_OF, company, fact
from test_sec_toplu_tarama import scan

ROOT = Path(__file__).resolve().parents[1]


def with_revenue_alias(value, year=2024):
    data = company()
    data["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [fact(value, year)]}}
    return data


def health(data, cik=77):
    return layer_health(build_company_research(data, as_of=AS_OF, expected_cik=cik, sector="non_financial"))


class LayerHealthTests(unittest.TestCase):
    def test_clean_issuer(self):
        h = health(company())
        self.assertEqual((h["statement_years"], h["latest_fiscal_year_end"]), (3, "2024-12-31"))
        self.assertEqual((h["statement_conflicts"], h["revenue_alias_bucket"]), ([], "NO_REVENUE_CONFLICT"))
        self.assertEqual((h["piotroski_reconciliation"], h["shares_status"]), ("MATCHED", "MISSING"))
        self.assertEqual(h["latest_ratios_total"], 18)

    def test_gap_between_half_and_five_percent_is_the_threshold_case(self):
        h = health(with_revenue_alias(1224))           # 1200 vs 1224: 1.96 %
        self.assertEqual(h["revenue_alias_bucket"], "HALF_TO_FIVE_PERCENT")
        self.assertAlmostEqual(h["revenue_alias_gap"], 24 / 1224)
        self.assertEqual((h["statement_conflicts"], h["piotroski_attention"]), (["revenue"], ["rev_t"]))

    def test_gap_above_five_percent(self):
        h = health(with_revenue_alias(1320))            # 10 %: Piotroski rejects it too
        self.assertEqual(h["revenue_alias_bucket"], "ABOVE_FIVE_PERCENT")
        self.assertNotIn("rev_t", h["piotroski_attention"])

    def test_only_latest_two_years_count_for_the_threshold(self):
        h = health(with_revenue_alias(820, year=2022))  # conflict three years back
        self.assertEqual(h["statement_conflicts"], ["revenue"])
        self.assertEqual(h["revenue_alias_bucket"], "NO_REVENUE_CONFLICT")


class ScanSummaryTests(unittest.TestCase):
    def test_counts_csv_and_turkish_lines(self):
        def fetch(cik, *, user_agent):
            data = with_revenue_alias(1224) if cik == 42 else company()
            return dict(data, cik=cik)
        with tempfile.TemporaryDirectory() as folder:
            summary = scan(folder, fetch=fetch, as_of=AS_OF)
            counts = summary["layer_health_counts"]
            self.assertEqual(counts["issuers"], 2)
            self.assertEqual(counts["revenue_alias_bucket"],
                             {"HALF_TO_FIVE_PERCENT": 1, "NO_REVENUE_CONFLICT": 1})
            self.assertEqual(counts["statement_conflict_items"], {"revenue": 1})
            out_json, out_csv = Path(folder) / "s.json", Path(folder) / "s.csv"
            _export(summary, out_json, out_csv)
            with out_csv.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["revenue_alias_bucket"], "HALF_TO_FIVE_PERCENT")
            self.assertEqual(rows[0]["piotroski_attention"], "rev_t")
            self.assertEqual(json.loads(out_json.read_text(encoding="utf-8"))["layer_health_counts"], counts)
            text = "\n".join(health_summary_lines(summary))
            self.assertIn("%0,5–%5 arası 1 (Piotroski eşik kararını etkiler)", text)
            self.assertIn("revenue (1)", text)

    def test_empty_summary_line(self):
        self.assertEqual(health_summary_lines({}), ["Katman sağlığı: analiz edilen şirket yok."])

    def test_real_data_universe_file_is_valid(self):
        entries = json.loads((ROOT / "ornekler/gercek_veri_kontrol_evreni.json").read_text(encoding="utf-8"))
        resolved = resolve_universe(entries)
        self.assertEqual(len(resolved), 11)
        self.assertEqual({r["sector"] for r in resolved}, {"non_financial", "financial"})


if __name__ == "__main__":
    unittest.main()
