"""Synthetic only: no real-company or investment-outcome claims."""
import copy
import json
import pathlib
import sqlite3
import tempfile
import unittest
from piotroski_fscore import compute_piotroski
from kredi_notlari import CreditRatingLedger,company_quality_snapshot
from sirket_kalite_cli import main

def annual(v, year, instant=False, filed=None, form="10-K"):
    row={"end":f"{year}-12-31","filed":filed or f"{year+1}-02-15",
         "form":form,"fp":"FY","accn":f"000042-{year+1}-001","val":v}
    if not instant:row["start"]=f"{year}-01-01"
    return row

def fixture():
    out={"cik":42,"entityName":"SYNTHETIC CO","facts":{"us-gaap":{}}}
    data={
      "NetIncomeLoss":{2023:70,2024:100},
      "NetCashProvidedByUsedInOperatingActivities":{2023:90,2024:140},
      "RevenueFromContractWithCustomerExcludingAssessedTax":{2023:1200,2024:1500},
      "GrossProfit":{2023:420,2024:600},
      "Assets":{2022:900,2023:1000,2024:1100},
      "AssetsCurrent":{2023:400,2024:500},
      "LiabilitiesCurrent":{2023:250,2024:250},
      "LongTermDebtNoncurrent":{2023:130,2024:100},
    }
    for concept,years in data.items():
        instant=concept in ("Assets","AssetsCurrent","LiabilitiesCurrent","LongTermDebtNoncurrent")
        out["facts"]["us-gaap"][concept]={"units":{"USD":[annual(value,year,instant)
                                                        for year,value in years.items()]}}
    return out

def issuance(issued=False):
    return {"issued":issued,"fiscal_start":"2024-01-01","fiscal_end":"2024-12-31",
            "reviewed_at":"2025-02-18",
            "source_url":"https://www.sec.gov/Archives/example/10k",
            "review_note":"Manual synthetic equity financing footnote review"}

class PiotroskiTests(unittest.TestCase):
    def score(self,data=None,**opts):
        return compute_piotroski(data or fixture(),as_of="2025-03-01",
                                 sector="non_financial",**opts)
    def test_nine_out_of_nine(self):
        result=self.score(equity_offering_evidence=issuance())
        self.assertEqual(result["score"],9)
        self.assertEqual(result["known_count"],9)
        self.assertEqual(result["periods"]["opening_assets_end"],"2022-12-31")
    def test_no_issuance_evidence_not_zero(self):
        result=self.score()
        self.assertIsNone(result["score"])
        self.assertEqual(result["score_range"],[8,9])
        self.assertIn("NO_EQUITY_OFFERING",result["missing_reasons"])
    def test_equity_offering_lowers_score(self):
        result=self.score(equity_offering_evidence=issuance(True))
        self.assertEqual(result["score"],8)
    def test_no_lookahead(self):
        data=fixture()
        before=compute_piotroski(data,as_of="2025-01-01",sector="non_financial")
        self.assertIsNone(before["score"])
        self.assertEqual(before["known_count"],0)
    def test_amendment_applies_only_after_filing(self):
        data=fixture()
        data["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"].append(
            annual(-10,2024,filed="2025-04-01",form="10-K/A"))
        self.assertEqual(self.score(data)["signals"]["ROA_POSITIVE"],1)
        later=compute_piotroski(data,as_of="2025-04-03",sector="non_financial")
        self.assertEqual(later["signals"]["ROA_POSITIVE"],0)
    def test_conflicting_revenue_needs_review(self):
        data=fixture()
        data["facts"]["us-gaap"]["Revenues"]={"units":{"USD":[annual(2500,2024)]}}
        result=self.score(data,equity_offering_evidence=issuance())
        self.assertIsNone(result["score"])
        self.assertIsNone(result["signals"]["DELTA_GROSS_MARGIN"])
        self.assertIsNone(result["signals"]["DELTA_ASSET_TURNOVER"])
        self.assertIn("CONFLICTING_ALIASES",result["missing_reasons"]["DELTA_ASSET_TURNOVER"])
    def test_missing_assets_not_zero(self):
        data=fixture()
        arr=data["facts"]["us-gaap"]["Assets"]["units"]["USD"]
        arr[:]=[f for f in arr if f["end"]!="2022-12-31"]
        result=self.score(data)
        for name in ("DELTA_ROA","DELTA_LEVERAGE","DELTA_ASSET_TURNOVER"):
            self.assertIsNone(result["signals"][name])
    def test_wrong_currency(self):
        data=fixture()
        data["facts"]["us-gaap"]["GrossProfit"]["units"]={"EUR":[annual(999,2024)]}
        self.assertIsNone(self.score(data)["signals"]["DELTA_GROSS_MARGIN"])
    def test_fiscal_start_mismatch(self):
        data=fixture()
        data["facts"]["us-gaap"]["GrossProfit"]["units"]["USD"][1]["start"]="2024-01-02"
        self.assertIsNone(self.score(data)["signals"]["DELTA_GROSS_MARGIN"])
    def test_future_manual_evidence_ignored(self):
        item=issuance()
        item["reviewed_at"]="2025-04-01"
        self.assertIsNone(self.score(equity_offering_evidence=item)["score"])
    def test_financial_sector_not_ranked(self):
        result=compute_piotroski(fixture(),as_of="2025-03-01",sector="financial")
        self.assertEqual(result["status"],"not_applicable_financial_sector")
        self.assertIsNone(result["score"])
    def test_unconfirmed_sector_not_ranked(self):
        self.assertEqual(compute_piotroski(fixture(),as_of="2025-03-01")["status"],
                         "sector_unconfirmed")
    def test_leverage_unchanged_not_a_point(self):
        data=fixture()
        data["facts"]["us-gaap"]["LongTermDebtNoncurrent"]["units"]["USD"][1]["val"]=130*1050/950
        self.assertEqual(self.score(data)["signals"]["DELTA_LEVERAGE"],0)

class CreditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=pathlib.Path(self.tmp.name)/"ratings.sqlite"
        self.record=dict(cik=42,issuer_name="SYNTHETIC CO",agency="MOODYS",
           rating="Aa3",outlook="positive",effective_date="2024-10-01",
           published_date="2024-10-01",
           source_url="https://ratings.moodys.com/example",
           review_note="Manually checked synthetic release details")
    def tearDown(self):self.tmp.cleanup()
    def test_rating_upgrade_and_vintage(self):
        with CreditRatingLedger(self.path) as db:
            db.add(**self.record)
            db.add(**dict(self.record,rating="Aa2",outlook="stable",
                          effective_date="2025-04-01",published_date="2025-04-02"))
            self.assertEqual(db.as_of(42,"2025-03-01")["agency_ratings"]["MOODYS"]["rating"],"Aa3")
            self.assertEqual(db.as_of(42,"2025-04-03")["agency_ratings"]["MOODYS"]["rating"],"Aa2")
    def test_separate_issuer_and_bond_ratings(self):
        with CreditRatingLedger(self.path) as db:
            with self.assertRaises(ValueError):
                db.add(**dict(self.record,rating_scope="senior_unsecured"))
    def test_investment_grade_thresholds(self):
        with CreditRatingLedger(self.path) as db:
            db.add(**dict(self.record,rating="Baa3"))
            db.add(**dict(self.record,agency="S&P",rating="BB+"))
            result=db.as_of(42,"2025-03-01")["agency_ratings"]
            self.assertTrue(result["MOODYS"]["investment_grade"])
            self.assertFalse(result["S&P"]["investment_grade"])
    def test_withdrawn_not_stale(self):
        with CreditRatingLedger(self.path) as db:
            db.add(**self.record)
            db.add(**dict(self.record,rating="WR",
                          effective_date="2025-02-01",published_date="2025-02-01"))
            entry=db.as_of(42,"2025-03-01")["agency_ratings"]["MOODYS"]
            self.assertTrue(entry["withdrawn_or_unrated"])
            self.assertIsNone(entry["investment_grade"])
    def test_never_map_to_single_score(self):
        with CreditRatingLedger(self.path) as db: db.add(**self.record)
        result=company_quality_snapshot(fixture(),as_of="2025-03-01",
           sector="non_financial",equity_offering_evidence=issuance(),credit_db=self.path)
        self.assertEqual(result["piotroski"]["score"],9)
        self.assertIsNone(result["combined_score"])
    def test_immutable_rating_events(self):
        with CreditRatingLedger(self.path) as db:
            ident=db.add(**self.record)
            with self.assertRaises(sqlite3.IntegrityError):
                db.db.execute("DELETE FROM rating_events WHERE id=?",(ident,))
            db.db.rollback()
    def test_wrong_grade_system_rejected(self):
        with CreditRatingLedger(self.path) as db:
            with self.assertRaises(ValueError):
                db.add(**dict(self.record,rating="AA"))
    def test_no_future_published_info(self):
        with CreditRatingLedger(self.path) as db:
            db.add(**dict(self.record,published_date="2024-10-04"))
            self.assertEqual(db.as_of(42,"2024-10-02")["status"],"not_available")

class CliTests(unittest.TestCase):
    def test_offline_report(self):
        with tempfile.TemporaryDirectory() as d:
            folder=pathlib.Path(d)
            source=folder/"facts.json";out=folder/"report.json"
            source.write_text(json.dumps(fixture()),encoding="utf-8")
            main(["report","--companyfacts",str(source),"--as-of","2025-03-01",
                  "--sector","non_financial","--out",str(out)])
            obj=json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(obj["piotroski"]["score_range"],[8,9])
            self.assertIsNone(obj["credit"])
