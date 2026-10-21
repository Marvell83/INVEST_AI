"""Offline, synthetic regression tests for gross-profit and noncurrent debt mapping."""
import unittest
from piotroski_fscore import compute_piotroski

def fact(v, year, instant=False, accn=None, filed=None):
    row=dict(val=v,end=f"{year}-12-31",form="10-K",fp="FY",
             accn=accn or f"000042-{year+1}-001",
             filed=filed or f"{year+1}-02-15")
    if not instant: row["start"]=f"{year}-01-01"
    return row

def sample():
    data={"cik":42,"entityName":"SYNTHETIC","facts":{"us-gaap":{}}}
    def add(tag,values,instant=False):
        data["facts"]["us-gaap"][tag]={"units":{"USD":[fact(v,year,instant)
                                                      for year,v in values.items()]}}
    add("NetIncomeLoss",{2023:70,2024:100})
    add("NetCashProvidedByUsedInOperatingActivities",{2024:140})
    add("RevenueFromContractWithCustomerExcludingAssessedTax",{2023:1200,2024:1500})
    add("Assets",{2022:900,2023:1000,2024:1100},True)
    add("AssetsCurrent",{2023:400,2024:500},True)
    add("LiabilitiesCurrent",{2023:250,2024:250},True)
    add("CostOfGoodsAndServicesSold",{2023:780,2024:900})
    add("LongTermDebt",{2023:160,2024:130},True)
    add("LongTermDebtCurrent",{2023:30,2024:30},True)
    return data

def score(data):
    return compute_piotroski(data,as_of="2025-03-01",sector="non_financial")

class EvidenceTests(unittest.TestCase):
    def test_gross_profit_derived_from_same_filing(self):
        result=score(sample())
        self.assertEqual(result["signals"]["DELTA_GROSS_MARGIN"],1)
        self.assertEqual(result["provenance"]["gp_t"]["value_usd"],600)
        self.assertEqual(result["provenance"]["gp_t"]["method"],"REVENUE_MINUS_MATCHED_COST")
        self.assertEqual(result["provenance"]["gp_t"]["derivation"]["cost"]["concept"],
                         "CostOfGoodsAndServicesSold")

    def test_cross_filing_cost_not_mixed(self):
        data=sample()
        data["facts"]["us-gaap"]["CostOfGoodsAndServicesSold"]["units"]["USD"][1]["accn"]="unrelated"
        self.assertIsNone(score(data)["signals"]["DELTA_GROSS_MARGIN"])

    def test_later_cost_is_not_visible_in_past(self):
        data=sample()
        data["facts"]["us-gaap"]["CostOfGoodsAndServicesSold"]["units"]["USD"][1]["filed"]="2025-04-01"
        self.assertIsNone(score(data)["signals"]["DELTA_GROSS_MARGIN"])

    def test_conflicting_cost_alias_not_guessed(self):
        data=sample()
        data["facts"]["us-gaap"]["CostOfRevenue"]={"units":{"USD":[fact(1100,2024)]}}
        result=score(data)
        self.assertIsNone(result["signals"]["DELTA_GROSS_MARGIN"])
        self.assertIn("CONFLICTING_COST_OF_REVENUE_ALIASES",
                      result["missing_reasons"]["DELTA_GROSS_MARGIN"])

    def test_euro_is_not_usd(self):
        data=sample()
        original=data["facts"]["us-gaap"]["CostOfGoodsAndServicesSold"]["units"]["USD"]
        data["facts"]["us-gaap"]["CostOfGoodsAndServicesSold"]["units"]={"EUR":original}
        self.assertIsNone(score(data)["signals"]["DELTA_GROSS_MARGIN"])

    def test_long_term_debt_total_minus_current(self):
        result=score(sample())
        self.assertEqual(result["signals"]["DELTA_LEVERAGE"],1)
        self.assertEqual(result["provenance"]["d_t"]["value_usd"],100)
        self.assertEqual(result["provenance"]["d_t"]["method"],
                         "TOTAL_LONG_TERM_DEBT_MINUS_CURRENT_PORTION")

    def test_total_debt_alone_is_not_noncurrent(self):
        data=sample()
        del data["facts"]["us-gaap"]["LongTermDebtCurrent"]
        self.assertIsNone(score(data)["signals"]["DELTA_LEVERAGE"])

    def test_explicit_noncurrent_debt_preferred(self):
        data=sample()
        data["facts"]["us-gaap"]["LongTermDebtNoncurrent"]={
            "units":{"USD":[fact(130,2023,True),fact(100,2024,True)]}}
        result=score(data)
        self.assertEqual(result["provenance"]["d_t"]["concept"],"LongTermDebtNoncurrent")

    def test_debt_inconsistent_with_direct_value(self):
        data=sample()
        data["facts"]["us-gaap"]["LongTermDebtNoncurrent"]={
            "units":{"USD":[fact(130,2023,True),fact(5,2024,True)]}}
        self.assertIsNone(score(data)["signals"]["DELTA_LEVERAGE"])

    def test_current_exceeds_total(self):
        data=sample()
        data["facts"]["us-gaap"]["LongTermDebtCurrent"]["units"]["USD"][1]["val"]=500
        self.assertIsNone(score(data)["signals"]["DELTA_LEVERAGE"])

    def test_debt_must_be_same_filing(self):
        data=sample()
        data["facts"]["us-gaap"]["LongTermDebtCurrent"]["units"]["USD"][1]["accn"]="unrelated"
        self.assertIsNone(score(data)["signals"]["DELTA_LEVERAGE"])

    def test_small_cost_difference_blocks_ambiguous_aliases(self):
        data=sample()
        data["facts"]["us-gaap"]["CostOfRevenue"]={"units":{"USD":[fact(906,2024)]}}
        self.assertIsNone(score(data)["signals"]["DELTA_GROSS_MARGIN"])

    def test_one_percent_noncurrent_debt_disagreement_blocks(self):
        data=sample()
        data["facts"]["us-gaap"]["LongTermDebtNoncurrent"]={
            "units":{"USD":[fact(130,2023,True),fact(101,2024,True)]}}
        self.assertIsNone(score(data)["signals"]["DELTA_LEVERAGE"])

    def test_no_equity_offering_evidence_stays_unknown(self):
        result=score(sample())
        self.assertIsNone(result["signals"]["NO_EQUITY_OFFERING"])
        self.assertIsNone(result["score"])

if __name__=="__main__": unittest.main()
