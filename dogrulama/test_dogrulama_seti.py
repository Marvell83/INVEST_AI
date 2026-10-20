# -*- coding: utf-8 -*-
"""Doğrulama setinin kendisini test eder:
1) referans motor bütün vakaları geçer,
2) bilinen DCF hataları içeren 'bozuk' motorlar ilgili vakalarda KALIR (set dişlidir)."""
import re
import sys
import types
import unittest
from pathlib import Path

import kabul_testi

KAYNAK = (Path(__file__).parent / "referans_motor.py").read_text(encoding="utf-8")

MUTASYONLAR = {
    # ad: (değiştirilecek metin, yerine, yakalaması gereken vakalar)
    "buyume_bedava": ("yeniden_yatirim = (gelir - onceki_gelir) / sc", "yeniden_yatirim = 0.0", {"K03", "K05"}),
    "uc_degerde_yatirim_yok": ("fcff_uc = nopat_uc * (1 - g_uc / roic_uc)", "fcff_uc = nopat_uc", {"K02", "K03"}),
    "g_r_kontrolu_yok": ('if g["uc_buyume"] >= g["iskonto"]:', "if False:", {"K06"}),
    "tavan_kontrolu_yok": ('if g["uc_buyume"] > g.get("uc_buyume_tavani", 0.04):', "if False:", {"K07"}),
    "sbc_cift_sayim_serbest": ('if g.get("sbc_yontemi", "gider") == "gider" and g.get("yillik_sulandirma", 0) > 0:',
                               "if False:", {"K10"}),
    "yil_ortasi_uc_deger_yanlis": ("uc_bd = uc_deger * (1 + r) ** -n",
                                   "uc_bd = uc_deger * (1 + r) ** -(n - 0.5 if yil_ortasi else n)", {"K12"}),
    "ters_dcf_sayi_uyduruyor": ('"ima_edilen_buyume": kokler[0] if len(kokler) == 1 else None',
                                '"ima_edilen_buyume": kokler[0] if kokler else 0.0', {"K16"}),
}


def bozuk_motor(ad, eski, yeni):
    assert eski in KAYNAK, f"mutasyon metni bulunamadı: {ad}"
    modul = types.ModuleType(f"bozuk_{ad}")
    exec(compile(KAYNAK.replace(eski, yeni), ad, "exec"), modul.__dict__)
    sys.modules[modul.__name__] = modul
    return modul.__name__


class DogrulamaSeti(unittest.TestCase):
    def test_referans_motor_tum_vakalari_gecer(self):
        gecen, toplam, rapor = kabul_testi.calistir("referans_motor", sessiz=True)
        self.assertEqual(gecen, toplam, rapor)

    def test_bozuk_motorlar_yakalanir(self):
        for ad, (eski, yeni, beklenen) in MUTASYONLAR.items():
            with self.subTest(mutasyon=ad):
                _, _, rapor = kabul_testi.calistir(bozuk_motor(ad, eski, yeni), sessiz=True)
                kalanlar = set(re.findall(r"KALDI\s+(K\d+)", rapor))
                self.assertTrue(beklenen <= kalanlar, f"{ad}: {beklenen - kalanlar} yakalanmadı\n{rapor}")


if __name__ == "__main__":
    unittest.main(verbosity=2)