"""Synthetic, offline SEC TTM tests. No real-company valuation assertions."""
import json
import pathlib
import tempfile
import unittest
from sec_ttm import compute_ttm, main

TAGS={"revenue":"RevenueFromContractWithCustomerExcludingAssessedTax",
      "ebit":"OperatingIncomeLoss","cfo":"NetCashProvidedByUsedInOperatingActivities",
      "capex":"PaymentsToAcquirePropertyPlantAndEquipment"}

def fact(v,start,end,filed,form,accession):
    return {"val":v,"start":start,"end":end,"filed":filed,"form":form,
            "fp":"FY" if form.startswith("10-K") else "Q3","accn":accession}

def fixture():
    raw={"cik":320193,"entityName":"SYNTHETIC COMPANY","facts":{"us-gaap":{}}}
    for metric,tag in TAGS.items():
        fy,cy,py={"revenue":(400,330,295),"ebit":(120,99,87),
                  "cfo":(110,88,70),"capex":(20,18,15)}[metric]
        raw["facts"]["us-gaap"][tag]={"units":{"USD":[
            fact(fy,"2024-09-29","2025-09-27","2025-10-30","10-K","fy25"),
            fact(cy,"2025-09-28","2026-06-27","2026-07-30","10-Q","q26"),
            fact(py,"2024-09-29","2025-06-28","2025-07-31","10-Q","q25")]}}
    return raw

def calc(raw=None,**options):
    return compute_ttm(raw if raw is not None else fixture(),
        as_of=options.pop("as_of","2026-08-01"),
        current_ytd_end=options.pop("current_ytd_end","2026-06-27"),**options)

class SEC_TTM_Tests(unittest.TestCase):
    def test_ytd_bridge(self):
        x=calc()
        self.assertEqual([x["metrics"][k]["value_usd"] for k in TAGS], [435,132,128,23])
        self.assertEqual(x["ttm_start"],"2025-06-29")
        self.assertEqual(x["cfo_less_capex_usd"],105)
        self.assertFalse(x["cfo_less_capex_is_fcff"])
        self.assertEqual(x["metrics"]["revenue"]["components"]["prior_ytd"]["accession"],"q25")

    def test_late_filing_not_visible(self):
        with self.assertRaisesRegex(ValueError,"current_ytd"):
            calc(as_of="2026-07-01")

    def test_late_amendment_only_after_publication(self):
        raw=fixture()
        raw["facts"]["us-gaap"][TAGS["ebit"]]["units"]["USD"].append(
            fact(900,"2025-09-28","2026-06-27","2026-09-30","10-Q/A","amended"))
        self.assertEqual(calc(raw)["metrics"]["ebit"]["value_usd"],132)
        self.assertEqual(calc(raw,as_of="2026-10-01")["metrics"]["ebit"]["value_usd"],933)

    def test_missing_prior_ytd_rejected(self):
        raw=fixture();raw["facts"]["us-gaap"][TAGS["ebit"]]["units"]["USD"].pop()
        with self.assertRaisesRegex(ValueError,"ebit/prior_ytd"):
            calc(raw)

    def test_single_quarter_not_used_as_ytd(self):
        raw=fixture();raw["facts"]["us-gaap"][TAGS["ebit"]]["units"]["USD"][-1]["start"]="2025-03-30"
        with self.assertRaisesRegex(ValueError,"ebit/prior_ytd"):
            calc(raw)

    def test_conflicting_revenue_alias_rejected(self):
        raw=fixture();raw["facts"]["us-gaap"]["Revenues"]={"units":{"USD":[
            fact(500,"2024-09-29","2025-09-27","2025-10-30","10-K","fy25")]}}
        with self.assertRaisesRegex(ValueError,"inconsistent XBRL"):
            calc(raw)

    def test_wrong_currency_rejected(self):
        raw=fixture();raw["facts"]["us-gaap"][TAGS["cfo"]]["units"]={"EUR":[]}
        with self.assertRaisesRegex(ValueError,"cfo/previous_fy"):
            calc(raw)

    def test_8k_not_substituted(self):
        raw=fixture();raw["facts"]["us-gaap"][TAGS["capex"]]["units"]["USD"][1]["form"]="8-K"
        with self.assertRaisesRegex(ValueError,"capex/current_ytd"):
            calc(raw)

    def test_wrong_fiscal_start_rejected(self):
        raw=fixture();raw["facts"]["us-gaap"][TAGS["revenue"]]["units"]["USD"][1]["start"]="2025-10-01"
        with self.assertRaisesRegex(ValueError,"revenue/current_ytd"):
            calc(raw)

    def test_inconsistent_annual_start_rejected(self):
        raw=fixture();raw["facts"]["us-gaap"][TAGS["cfo"]]["units"]["USD"][0]["start"]="2024-10-01"
        with self.assertRaisesRegex(ValueError,"prior_ytd|different annual"):
            calc(raw)

    def test_invalid_period_and_repeated_metric(self):
        with self.assertRaises(ValueError):calc(current_ytd_end="2026-12-31")
        with self.assertRaises(ValueError):calc(metrics=["revenue","revenue"])

    def test_offline_cli(self):
        with tempfile.TemporaryDirectory() as td:
            source=pathlib.Path(td)/"company.json";dest=pathlib.Path(td)/"ttm.json"
            source.write_text(json.dumps(fixture()),encoding="utf-8")
            main(["--companyfacts",str(source),"--as-of","2026-08-01",
                  "--current-ytd-end","2026-06-27","--out",str(dest)])
            self.assertEqual(json.loads(dest.read_text())["metrics"]["revenue"]["value_usd"],435)

if __name__=="__main__":unittest.main()
