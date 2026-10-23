"""Deterministic, offline TTM-DCF safety tests; no live prediction validation."""
import json
from pathlib import Path
import unittest
from ttm_finansallar import calculate_ttm
from ttm_dcf_bridge import run_ttm_scenarios

ROOT=Path(__file__).resolve().parent.parent
FACTS=ROOT/"ornekler/apple_ttm_evidence_2026-10-21.json"
CASE=ROOT/"ornekler/apple_ttm_dcf_assumptions_2026-10-21.json"

def inputs():
    source=json.loads(FACTS.read_text(encoding="utf-8"))
    return calculate_ttm(source,as_of="2026-10-21"),json.loads(CASE.read_text(encoding="utf-8"))

class TTMBridgeTests(unittest.TestCase):
    def test_scenarios_with_ttm_baseline(self):
        t,c=inputs();r=run_ttm_scenarios(t,c)
        self.assertEqual(r["ttm_gelir_0_usd"],466_823_000_000)
        self.assertFalse(r["cfo_minus_capex_is_fcff"])
        self.assertAlmostEqual(r["scenarios"]["baz"]["valuation"]["hisse_basi_deger"],149.46029490248156,places=5)

    def test_reverse_is_not_guaranteed_exhaustive(self):
        t,c=inputs();r=run_ttm_scenarios(t,c)
        self.assertAlmostEqual(r["reverse_dcf"]["ima_edilen_buyume"],0.309383628139,places=6)
        self.assertFalse(r["reverse_dcf"]["tum_kokler_bulundu_garantisi"])

    def test_mismatched_company_rejected(self):
        t,c=inputs();c["issuer"]["cik"]="0000000001"
        with self.assertRaisesRegex(ValueError,"CIK differs"):
            run_ttm_scenarios(t,c)

    def test_stale_annual_baseline_rejected(self):
        t,c=inputs();c["historical"]["revenue_usd"]=1
        with self.assertRaisesRegex(ValueError,"does not reconcile"):
            run_ttm_scenarios(t,c)

    def test_wrong_interim_period(self):
        t,c=inputs();c["most_recent_interim_known"]["fiscal_end"]="2025-06-28"
        with self.assertRaisesRegex(ValueError,"periods differ"):
            run_ttm_scenarios(t,c)

    def test_missing_ttm_blocked(self):
        t,c=inputs();t["status"]="partial"
        with self.assertRaisesRegex(ValueError,"complete USD TTM"):
            run_ttm_scenarios(t,c)

    def test_future_price_rejected(self):
        t,c=inputs();c["market_price"]["date"]="2026-10-22"
        with self.assertRaisesRegex(ValueError,"future quote date"):
            run_ttm_scenarios(t,c)

    def test_no_same_day_quote(self):
        t,c=inputs();c["market_price"]["date"]="2026-10-21"
        with self.assertRaisesRegex(ValueError,"previous-session"):
            run_ttm_scenarios(t,c)

    def test_future_filing_rejected(self):
        t,c=inputs();c["most_recent_interim_known"]["filed_at"]="2026-10-22"
        with self.assertRaisesRegex(ValueError,"future filing"):
            run_ttm_scenarios(t,c)

    def test_annual_source_accession(self):
        t,c=inputs();c["historical"]["accession"]="fake"
        with self.assertRaisesRegex(ValueError,"provenance mismatch"):
            run_ttm_scenarios(t,c)

    def test_interim_source_accession(self):
        t,c=inputs();c["most_recent_interim_known"]["accession"]="fake"
        with self.assertRaisesRegex(ValueError,"provenance mismatch"):
            run_ttm_scenarios(t,c)

    def test_excess_cash_not_guessed(self):
        t,c=inputs();c["balance_sheet"]["treat_all_marketable_securities_as_excess_cash"]=False
        with self.assertRaisesRegex(ValueError,"excess cash"):
            run_ttm_scenarios(t,c)

    def test_research_vintage_same(self):
        t,c=inputs();c["research_as_of"]="2026-10-23"
        with self.assertRaisesRegex(ValueError,"cutoffs must match"):
            run_ttm_scenarios(t,c)

    def test_share_count_not_guessed(self):
        t,c=inputs();del c["share_count"]["shares"]
        with self.assertRaisesRegex(ValueError,"share count"):
            run_ttm_scenarios(t,c)

    def test_missing_scenario_rationale_rejected(self):
        t,c=inputs();del c["scenarios"]["baz"]["rationale"]
        with self.assertRaisesRegex(ValueError,"lacks cited explanation"):
            run_ttm_scenarios(t,c)

if __name__=="__main__": unittest.main()
