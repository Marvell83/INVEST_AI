import os
import sqlite3
import tempfile
import unittest

from degerleme_kaydi import degerle_ve_kaydet
from tahmin_defteri import TahminDefteri

INPUTS = {
    "yillar": 3, "gelir_0": 100, "buyume": 0.1,
    "faaliyet_marji": 0.2, "satis_sermaye": 2,
    "vergi_orani": 0.2, "iskonto": 0.1,
    "uc_buyume": 0.02, "uc_roic": 0.12,
    "net_borc": 0, "hisse": 10, "sbc_yontemi": "gider"
}

class DcfLedgerIntegration(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.folder.name, "records.sqlite")
        self.kwargs = dict(db_path=self.db, company="DEMO",
                           currency="USD", base_year=2026,
                           inputs=INPUTS, sources=["synthetic test"])
    def tearDown(self):
        self.folder.cleanup()

    def test_persists_all_years_and_metrics(self):
        output = degerle_ve_kaydet(**self.kwargs)
        self.assertEqual(output["durum"], "gecerli")
        self.assertEqual(len(output["tahmin_kimlikleri"]), 6)
        with TahminDefteri(self.db) as ledger:
            rows = ledger.tahminleri_listele()
            self.assertEqual(len(rows), 6)
            self.assertEqual({r["metric"] for r in rows}, {"revenue", "fcff"})
            self.assertEqual({r["target_period"] for r in rows},
                             {"2027-FY", "2028-FY", "2029-FY"})

    def test_invalid_valuation_does_not_create_database(self):
        kw = dict(self.kwargs, inputs=dict(INPUTS, uc_buyume=0.2))
        result = degerle_ve_kaydet(**kw)
        self.assertEqual(result["durum"], "gecersiz")
        self.assertFalse(os.path.exists(self.db))

    def test_duplicate_batch_preserves_original_records(self):
        degerle_ve_kaydet(**self.kwargs)
        with self.assertRaises(sqlite3.IntegrityError):
            degerle_ve_kaydet(**self.kwargs)
        with TahminDefteri(self.db) as ledger:
            self.assertEqual(len(ledger.tahminleri_listele()), 6)

    def test_missing_sources_rejected(self):
        with self.assertRaises(ValueError):
            degerle_ve_kaydet(**dict(self.kwargs, sources=[]))

    def test_transaction_rollback_when_second_record_fails(self):
        with TahminDefteri(self.db) as ledger:
            ledger.tahmin_kaydet(company="DEMO", metric="fcff",
                target_period="2027-FY", currency="USD", predicted=999,
                model_version="uretim-0.1.0", assumptions={
                    "inputs": INPUTS, "scenario": "base", "base_year": 2026,
                    "valuation_metric": "fcff", "valuation_result": {
                        "firma_degeri": 0, "ozsermaye_degeri": 0,
                        "hisse_basi_deger": 0, "uc_deger_payi": 0}},
                sources=["synthetic test"])
        # A conflict in an existing row should never leave earlier inserts.
        with self.assertRaises(sqlite3.IntegrityError):
            degerle_ve_kaydet(**self.kwargs)
        with TahminDefteri(self.db) as ledger:
            self.assertEqual(len(ledger.tahminleri_listele()), 1)

if __name__ == "__main__":
    unittest.main()
