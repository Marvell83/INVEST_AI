# -*- coding: utf-8 -*-
"""Sentetik örnek; gerçek şirket verisi veya yatırım önerisi değildir."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "dogrulama"))
from uretim_motoru import degerle, ters_dcf

params = {
    "gelir_0": 1000,
    "yillar": 3,
    "buyume": [0.20, 0.15, 0.10],
    "faaliyet_marji": [0.15, 0.18, 0.20],
    "vergi_orani": 0.25,
    "satis_sermaye": 2.0,
    "iskonto": 0.09,
    "uc_buyume": 0.03,
    "uc_roic": 0.15,
    "net_borc": 300,
    "hisse": 50,
    "uc_buyume_tavani": 0.04,
    "sbc_yontemi": "gider",
    "iskonto_zamani": "yil_sonu"
}

sonuc = degerle(params)
print("SENTETIK SIRKET DEGERLEMESI")
print(json.dumps(sonuc, ensure_ascii=False, indent=2))
print("\nFiyatin ima ettigi yillik buyume (varsayimsal fiyat = 45):")
print(json.dumps(ters_dcf(params, fiyat=45), ensure_ascii=False, indent=2))
