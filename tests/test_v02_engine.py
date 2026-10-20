import math
import unittest
from degerleme_v02 import degerle_v02, ters_dcf_v02

BASE = dict(yillar=3, gelir_0=100, buyume=0.1,
    marj_0=.2, marj_hedef=.2, yakinlasma=.5,
    satis_sermaye=2, vergi_orani=.25,
    iskonto=.10, uc_buyume=.02, uc_roic=.12, hisse=10)

class TestV02Engine(unittest.TestCase):
    def test_simple_reconciliation(self):
        a=degerle_v02(BASE)
        self.assertEqual(len(a['tablo']),3)
        self.assertAlmostEqual(a['tablo'][0]['gelir'],110)
        self.assertAlmostEqual(a['tablo'][0]['nakit_vergi'],5.5)
        self.assertAlmostEqual(a['tablo'][0]['yeniden_yatirim'],5)
        self.assertAlmostEqual(a['tablo'][0]['fcff'],11.5)
        self.assertAlmostEqual(a['firma_degeri'],a['acik_donem_bd']+a['uc_deger_bd'])
    def test_loss_carryforwards(self):
        p=dict(BASE,yillar=3, buyume=0, marj_0=-.1,marj_hedef=.2,yakinlasma=1, baslangic_zarar=100)
        a=degerle_v02(p)
        self.assertEqual([r['nakit_vergi'] for r in a['tablo']], [0,0,0])
        self.assertIn('UC_VERGI_NORMALIZE_EDILDI',a['uyarilar'])
    def test_margin_convergence(self):
        p=dict(BASE, marj_0=.1, marj_hedef=.2,yakinlasma=.5)
        a=degerle_v02(p)
        self.assertAlmostEqual(a['tablo'][0]['faaliyet_marji'],.15)
        self.assertAlmostEqual(a['tablo'][1]['faaliyet_marji'],.175)
    def test_roiic_diagnostic(self):
        a=degerle_v02(BASE)
        self.assertIsNone(a['tablo'][0]['roiic'])
        self.assertAlmostEqual(a['tablo'][1]['roiic'],(a['tablo'][1]['nopat']-a['tablo'][0]['nopat'])/5)
    def test_negative_reinvestment_not_clamped(self):
        a=degerle_v02(dict(BASE,buyume=-.2))
        self.assertLess(a['tablo'][0]['yeniden_yatirim'],0)
        self.assertIn('NEGATIF_YATIRIM_SERMAYE_CIKISI_VARSAYIMI',a['uyarilar'])
    def test_sbc_double_count_rejected(self):
        with self.assertRaisesRegex(ValueError,'double counting'):
            degerle_v02(dict(BASE,sbc_ilave_gider_orani=.01))
    def test_reject_terminal_growth(self):
        with self.assertRaises(ValueError): degerle_v02(dict(BASE,uc_buyume=.11))
    def test_reject_nan(self):
        with self.assertRaises(ValueError): degerle_v02(dict(BASE,iskonto=float('nan')))
    def test_sbc_expense_if_excluded(self):
        a=degerle_v02(dict(BASE,sbc_marjda_dahil=False,sbc_ilave_gider_orani=.03))
        self.assertAlmostEqual(a['tablo'][0]['ebit'],110*.17)
    def test_consistent_midyear_discount(self):
        a=degerle_v02(BASE);b=degerle_v02(dict(BASE, iskonto_zamani='yil_ortasi'))
        self.assertAlmostEqual(a['uc_deger_bd'],b['uc_deger_bd'])
        self.assertGreater(b['acik_donem_bd'],a['acik_donem_bd'])
    def test_invalid_growth_list(self):
        with self.assertRaises(ValueError): degerle_v02(dict(BASE,buyume=[.1,.2]))
    def test_terminal_nol_tax_normalization(self):
        a=degerle_v02(dict(BASE,baslangic_zarar=500))
        self.assertEqual(a['tablo'][-1]['nakit_vergi'],0)
        self.assertAlmostEqual(a['uc_nopat_normalize'],a['tablo'][-1]['gelir']*1.02*.2*.75)

class TestReverseDCFV02(unittest.TestCase):
    def test_recovers_known_growth(self):
        known = degerle_v02(dict(BASE, buyume=.12))["hisse_basi_deger"]
        result = ters_dcf_v02(BASE, known, .08, .16, grid_steps=1024)
        self.assertEqual(result["durum"], "tek_cozum_dogrulandi")
        self.assertAlmostEqual(result["ima_edilen_buyume"], .12, 5)
        self.assertFalse(result["tum_kokler_bulundu_garantisi"])
    def test_unverified_is_not_no_solution_proof(self):
        result = ters_dcf_v02(BASE, 1000000, .05, .3, grid_steps=256)
        self.assertEqual(result["durum"], "cozum_dogrulanamadi")
        self.assertIsNone(result["ima_edilen_buyume"])
    def test_rejects_growth_below_minus_one(self):
        with self.assertRaises(ValueError):
            ters_dcf_v02(BASE, 10, lower=-1.1, upper=.2)
    def test_boundary_root(self):
        known = degerle_v02(dict(BASE, buyume=.10))["hisse_basi_deger"]
        result = ters_dcf_v02(BASE, known, lower=.10, upper=.2, grid_steps=256)
        self.assertEqual(result["durum"], "tek_cozum_dogrulandi")
        self.assertAlmostEqual(result["ima_edilen_buyume"], .10, 5)

if __name__ == '__main__': unittest.main()