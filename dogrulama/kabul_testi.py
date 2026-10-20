# -*- coding: utf-8 -*-
"""INVEST_AI valuation acceptance runner (frozen 0.1 contract)."""
import importlib
import json
import math
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent

def yakin(a, b, rel, mutlak):
    if a is None or b is None:
        return a is b
    return math.isclose(a, b, rel_tol=rel, abs_tol=mutlak)

def denetle(vaka, motor, rel, mutlak):
    tur, b = vaka["tur"], vaka.get("beklenen", {})
    sorunlar = []

    def sonuc_denetle(s, b):
        if s.get("durum") != b["durum"]:
            sorunlar.append(f"durum {s.get('durum')} != beklenen {b['durum']}")
            return
        for h in b.get("hatalar_icermeli", []):
            if h not in s.get("hatalar", []):
                sorunlar.append(f"hata kodu eksik: {h}")
        if "uyarilar_tam" in b and sorted(s.get("uyarilar", [])) != b["uyarilar_tam"]:
            sorunlar.append(f"uyarilar {sorted(s.get('uyarilar', []))} != {b['uyarilar_tam']}")
        for k in ("acik_donem_bd", "uc_deger", "uc_deger_bd", "firma_degeri", "ozsermaye_degeri",
                  "hisse_basi_deger", "uc_deger_payi"):
            if k in b and not yakin(s.get(k), b[k], rel, mutlak):
                sorunlar.append(f"{k}: {s.get(k)} != {b[k]}")
        for i, satir in enumerate(b.get("tablo", [])):
            for k, v in satir.items():
                if not yakin(s["tablo"][i].get(k), v, rel, mutlak):
                    sorunlar.append(f"tablo yil {satir['yil']} {k}: {s['tablo'][i].get(k)} != {v}")

    if tur == "degerle":
        sonuc_denetle(motor.degerle(vaka["girdi"]), b)
    elif tur == "karsilastirma":
        s1, s2 = motor.degerle(vaka["girdi"]), motor.degerle(vaka["girdi_karsilastirma"])
        if b:
            sonuc_denetle(s1, b)
        v1, v2 = s1.get("firma_degeri"), s2.get("firma_degeri")
        if v1 is None or v2 is None:
            sorunlar.append("karsilastirma icin deger uretilmedi")
        elif vaka["iliski"] == "kucuk" and not v1 < v2:
            sorunlar.append(f"beklenen {v1} < {v2}")
        elif vaka["iliski"] == "buyuk" and not v1 > v2:
            sorunlar.append(f"beklenen {v1} > {v2}")
    elif tur == "degismezlik":
        s1, s2 = (motor.degerle(g) for g in vaka["girdiler"])
        if vaka["iliski"] == "kat":
            for k in ("firma_degeri", "hisse_basi_deger"):
                if not yakin(s2[k] / s1[k], vaka["beklenen_oran"], rel, mutlak):
                    sorunlar.append(f"{k} orani {s2[k] / s1[k]} != {vaka['beklenen_oran']}")
        elif vaka["iliski"] == "uc_deger_orani":
            if not yakin(s2["uc_deger"] / s1["uc_deger"], vaka["beklenen_oran"], rel, mutlak):
                sorunlar.append(f"uc deger orani {s2['uc_deger'] / s1['uc_deger']} != {vaka['beklenen_oran']}")
    elif tur == "ters_dcf":
        s = motor.ters_dcf(vaka["girdi"], vaka["fiyat"])
        if s.get("durum") != b["durum"]:
            sorunlar.append(f"durum {s.get('durum')} != {b['durum']}")
        if b.get("ima_edilen_buyume") is None:
            if s.get("ima_edilen_buyume") is not None:
                sorunlar.append("cozum yokken sayi uretildi")
        elif not yakin(s.get("ima_edilen_buyume"), b["ima_edilen_buyume"], 1e-6, 1e-7):
            sorunlar.append(f"ima edilen buyume {s.get('ima_edilen_buyume')} != {b['ima_edilen_buyume']}")
        for k in b.get("sabit_tutulanlar_icermeli", []):
            if k not in s.get("sabit_tutulanlar", []):
                sorunlar.append(f"sabit tutulan degisken listesinde yok: {k}")
    else:
        sorunlar.append(f"bilinmeyen vaka turu {tur}")
    return sorunlar

def calistir(motor_modulu="motor_adaptoru", sessiz=False):
    paket = json.loads((KOK / "dogrulama_seti_v0_1.json").read_text(encoding="utf-8"))
    motor = importlib.import_module(motor_modulu)
    satirlar, gecen = [], 0
    for v in paket["vakalar"]:
        try:
            sorunlar = denetle(v, motor, paket["tolerans_goreli"], paket["tolerans_mutlak"])
        except Exception as e:
            sorunlar = [f"motor hata verdi: {type(e).__name__}: {e}"]
        gecen += not sorunlar
        satirlar.append(f"{'GECTI ' if not sorunlar else 'KALDI '} {v['kod']}  {v['ad']}")
        satirlar += [f"         - {s}" for s in sorunlar]
    ozet = f"\n{gecen}/{len(paket['vakalar'])} vaka gecti ({paket['surum']})"
    rapor = "\n".join(satirlar) + ozet
    if not sessiz:
        print(rapor)
        (KOK / "kabul_raporu.txt").write_text(rapor + "\n", encoding="utf-8")
    return gecen, len(paket["vakalar"]), rapor

if __name__ == "__main__":
    g, n, _ = calistir(sys.argv[1] if len(sys.argv) > 1 else "motor_adaptoru")
    sys.exit(0 if g == n else 1)
