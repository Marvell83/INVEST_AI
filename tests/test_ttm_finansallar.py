"""Offline SEC-transcription and synthetic point-in-time regression tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from ttm_finansallar import calculate_ttm, main

SAMPLE = Path(__file__).resolve().parent.parent / "ornekler/apple_ttm_evidence_2026-10-21.json"
AS_OF = "2026-10-21"


def fixture():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def series(data, tag):
    return data["facts"]["us-gaap"][tag]["units"]["USD"]


class TTMTests(unittest.TestCase):
    def test_apple_totals(self):
        r = calculate_ttm(fixture(), as_of=AS_OF)
        self.assertEqual(r["status"], "complete_core")
        values = {name: row["value_usd"] for name, row in r["metrics"].items()}
        self.assertEqual(values, dict(revenue=466_823_000_000, ebit=154_859_000_000,
            net_income=128_930_000_000, gross_profit=227_123_000_000,
            cfo=146_724_000_000, capex=10_041_000_000))
        self.assertFalse(r["cfo_less_capex_is_fcff"])
        self.assertEqual(r["cfo_less_capex_usd"], 136_683_000_000)

    def test_auditable_period_and_accessions(self):
        r=calculate_ttm(fixture(),as_of=AS_OF)
        self.assertEqual(r["periods"]["annual_end"],"2025-09-27")
        self.assertEqual(r["periods"]["current_9m_end"],"2026-06-27")
        self.assertEqual(r["periods"]["prior_9m_end"],"2025-06-28")
        self.assertEqual(r["metrics"]["revenue"]["annual"]["accession"],"0000320193-25-000079")
        self.assertIn("MANUAL_TRANSCRIPTION",r["input_disclosure"]["status"])

    def test_asof_before_10q_prohibits_lookahead(self):
        r=calculate_ttm(fixture(),as_of="2026-07-30")
        self.assertEqual(r["status"],"unavailable")
        self.assertIsNone(r["metrics"]["revenue"]["value_usd"])

    def test_asof_before_annual_filing_no_baseline(self):
        with self.assertRaisesRegex(ValueError,"no eligible"):
            calculate_ttm(fixture(),as_of="2025-10-30")

    def test_three_month_not_nine_month(self):
        d=fixture()
        series(d,"OperatingIncomeLoss")[1]["start"]="2026-03-29"
        self.assertIsNone(calculate_ttm(d,as_of=AS_OF)["metrics"]["ebit"]["value_usd"])

    def test_prior_period_wrong_start_rejected(self):
        d=fixture()
        series(d,"NetCashProvidedByUsedInOperatingActivities")[2]["start"]="2024-10-07"
        self.assertIsNone(calculate_ttm(d,as_of=AS_OF)["metrics"]["cfo"]["value_usd"])

    def test_missing_capex_not_zero(self):
        d=fixture()
        del d["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]
        r=calculate_ttm(d,as_of=AS_OF)
        self.assertEqual(r["status"],"partial")
        self.assertIsNone(r["cfo_less_capex_usd"])

    def test_revenue_alias_disagreement(self):
        d=fixture()
        alternative=copy.deepcopy(series(d,"RevenueFromContractWithCustomerExcludingAssessedTax"))
        alternative[1]["val"] += 40_000_000_000
        d["facts"]["us-gaap"]["Revenues"]={"units":{"USD":alternative}}
        item=calculate_ttm(d,as_of=AS_OF)["metrics"]["revenue"]
        self.assertEqual(item["issues"]["current_ytd9"],"CONFLICTING_ALIASES")

    def test_changed_revenue_tag_blocks(self):
        d=fixture()
        current=series(d,"RevenueFromContractWithCustomerExcludingAssessedTax").pop(1)
        d["facts"]["us-gaap"]["Revenues"]={"units":{"USD":[current]}}
        self.assertEqual(calculate_ttm(d,as_of=AS_OF)["metrics"]["revenue"]["status"],"REVENUE_CONCEPT_CHANGED")

    def test_late_amendment_visibility(self):
        d=fixture()
        rows=series(d,"NetIncomeLoss")
        rows.append(dict(rows[0],val=118_000_000_000,filed="2026-10-22",
                         form="10-K/A",accn="0000320193-26-000999"))
        self.assertEqual(calculate_ttm(d,as_of=AS_OF)["metrics"]["net_income"]["value_usd"],128_930_000_000)
        self.assertEqual(calculate_ttm(d,as_of="2026-10-23")["metrics"]["net_income"]["value_usd"],134_920_000_000)

    def test_negative_capex_rejected(self):
        d=fixture()
        series(d,"PaymentsToAcquirePropertyPlantAndEquipment")[1]["val"] *= -1
        self.assertEqual(calculate_ttm(d,as_of=AS_OF)["metrics"]["capex"]["status"],"CAPEX_SIGN_NOT_NORMALIZED")

    def test_wrong_currency_rejected(self):
        d=fixture()
        d["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]={"EUR":series(d,"OperatingIncomeLoss")}
        self.assertIsNone(calculate_ttm(d,as_of=AS_OF)["metrics"]["ebit"]["value_usd"])

    def test_invalid_cik_rejected(self):
        d=fixture();d["cik"]=True
        with self.assertRaisesRegex(ValueError,"invalid CIK"):
            calculate_ttm(d,as_of=AS_OF)

    def test_wrong_quarter_label_rejected(self):
        d=fixture()
        series(d,"OperatingIncomeLoss")[1]["fp"]="Q2"
        self.assertIsNone(calculate_ttm(d,as_of=AS_OF)["metrics"]["ebit"]["value_usd"])

    def test_8k_not_10q_rejected(self):
        d=fixture()
        series(d,"OperatingIncomeLoss")[1]["form"]="8-K"
        self.assertIsNone(calculate_ttm(d,as_of=AS_OF)["metrics"]["ebit"]["value_usd"])

    def test_negative_cfo_can_be_reported(self):
        d=fixture()
        series(d,"NetCashProvidedByUsedInOperatingActivities")[1]["val"]=-100_000_000_000
        self.assertLess(calculate_ttm(d,as_of=AS_OF)["metrics"]["cfo"]["value_usd"],0)

    def test_future_quarter_end_rejected(self):
        d=fixture()
        for tag in d["facts"]["us-gaap"].values():
            tag["units"]["USD"][1]["end"]="2026-11-01"
        self.assertEqual(calculate_ttm(d,as_of=AS_OF)["status"],"unavailable")

    def test_cli_offline(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/"result.json"
            main(["--companyfacts",str(SAMPLE),"--as-of",AS_OF,"--out",str(target)])
            self.assertEqual(json.loads(target.read_text())["metrics"]["revenue"]["value_usd"],466_823_000_000)

if __name__ == "__main__":
    unittest.main()
