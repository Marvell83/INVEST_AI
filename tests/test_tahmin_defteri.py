"""Run: python -m unittest discover -s tests -v"""
import os
import sqlite3
import tempfile
import unittest

from tahmin_defteri import TahminDefteri

class TahminDefteriTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = TahminDefteri(os.path.join(self.temp.name, "ledger.sqlite"))
        self.data = dict(company="DEMO", metric="revenue", target_period="2027-FY",
                         currency="USD", predicted=120.0, model_version="v0.1",
                         assumptions={"growth": 0.2}, sources=["synthetic test"])
    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()
    def test_forecast_outcome_and_scoring(self):
        fid = self.ledger.tahmin_kaydet(**self.data)
        oid = self.ledger.gerceklesen_kaydet(company="DEMO", metric="revenue",
             target_period="2027-FY", currency="USD", actual=100, source="synthetic test")
        self.assertEqual(self.ledger.puanla(fid, oid)["absolute_error"], 20)
        self.assertEqual(len(self.ledger.tahminleri_listele()), 1)
    def test_forecasts_immutable(self):
        fid = self.ledger.tahmin_kaydet(**self.data)
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.db.execute("UPDATE forecasts SET predicted=1 WHERE id=?", (fid,))
        self.ledger.db.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.db.execute("DELETE FROM forecasts WHERE id=?", (fid,))
        self.ledger.db.rollback()
    def test_mismatched_outcome_rejected(self):
        fid = self.ledger.tahmin_kaydet(**self.data)
        oid = self.ledger.gerceklesen_kaydet(company="OTHER", metric="revenue",
             target_period="2027-FY", currency="USD", actual=100, source="synthetic test")
        with self.assertRaises(ValueError):
            self.ledger.puanla(fid, oid)
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            self.ledger.tahmin_kaydet(**{**self.data, "predicted": float("nan")})
    def test_duplicate_forecast_rejected(self):
        self.ledger.tahmin_kaydet(**self.data)
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.tahmin_kaydet(**self.data)

if __name__ == "__main__":
    unittest.main()
