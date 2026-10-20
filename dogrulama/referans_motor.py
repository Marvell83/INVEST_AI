# -*- coding: utf-8 -*-
"""
YATIRIM AI — Değerleme Çekirdeği REFERANS MOTORU (doğrulama seti için)

Bu dosya üretim motoru değildir. Amacı, KONVANSIYONLAR.md'de tanımlanan hesap
kurallarının bağımsız ve okunabilir bir uygulamasını sağlamak; doğrulama setindeki
beklenen değerler buradan ve elle hesaplardan gelir. Üretim motoru farklı kodla
yazılabilir ama aynı girdiye aynı sonucu vermelidir.
"""
import math

SURUM = "referans-0.1"
UC_DEGER_BASKIN_ESIGI = 0.85


def _liste(deger, n, ad):
    if isinstance(deger, (int, float)):
        return [float(deger)] * n
    deger = [float(v) for v in deger]
    if len(deger) != n:
        raise ValueError(f"{ad}: {n} değer bekleniyordu, {len(deger)} geldi")
    return deger


def _hatalar(g):
    h = []
    if g["yillar"] < 1:
        h.append("YIL_SAYISI_GECERSIZ")
    if g["iskonto"] <= 0:
        h.append("ISKONTO_GECERSIZ")
    if g["uc_buyume"] >= g["iskonto"]:
        h.append("UC_BUYUME_ISKONTOYU_ASIYOR")
    if g["uc_buyume"] > g.get("uc_buyume_tavani", 0.04):
        h.append("UC_BUYUME_TAVAN_USTU")
    if g["uc_roic"] <= 0:
        h.append("UC_ROIC_GECERSIZ")
    if g["satis_sermaye"] <= 0:
        h.append("SATIS_SERMAYE_GECERSIZ")
    if g["hisse"] <= 0:
        h.append("HISSE_GECERSIZ")
    if not 0 <= g["vergi_orani"] < 1:
        h.append("VERGI_GECERSIZ")
    if g.get("sbc_yontemi", "gider") not in ("gider", "sulandirma"):
        h.append("SBC_YONTEMI_GECERSIZ")
    if g.get("sbc_yontemi", "gider") == "gider" and g.get("yillik_sulandirma", 0) > 0:
        # marjlar zaten hisse bazlı ücreti gider olarak içeriyor; ayrıca sulandırma uygulamak çift sayım
        h.append("SBC_CIFT_SAYIM")
    if g.get("iskonto_zamani", "yil_sonu") not in ("yil_sonu", "yil_ortasi"):
        h.append("ISKONTO_ZAMANI_GECERSIZ")
    return h


def degerle(girdi):
    g = dict(girdi)
    hatalar = _hatalar(g)
    if hatalar:
        return {"durum": "gecersiz", "hatalar": hatalar, "uyarilar": []}
    n = int(g["yillar"])
    try:
        buyume = _liste(g["buyume"], n, "buyume")
        marj = _liste(g["faaliyet_marji"], n, "faaliyet_marji")
    except ValueError:
        return {"durum": "gecersiz", "hatalar": ["LISTE_UZUNLUGU_UYUMSUZ"], "uyarilar": []}
    t, r, sc = g["vergi_orani"], g["iskonto"], g["satis_sermaye"]
    g_uc, roic_uc = g["uc_buyume"], g["uc_roic"]
    sbc_yontemi = g.get("sbc_yontemi", "gider")
    sbc_orani = g.get("sbc_gelire_orani", 0.0) if sbc_yontemi == "sulandirma" else 0.0
    yil_ortasi = g.get("iskonto_zamani", "yil_sonu") == "yil_ortasi"

    uyarilar, tablo = [], []
    onceki_gelir, acik_bd = float(g["gelir_0"]), 0.0
    for i in range(n):
        yil = i + 1
        gelir = onceki_gelir * (1 + buyume[i])
        nopat = gelir * (marj[i] + sbc_orani) * (1 - t)       # sulandırma yönteminde SBC geri eklenir
        yeniden_yatirim = (gelir - onceki_gelir) / sc          # büyüme bedava değildir
        fcff = nopat - yeniden_yatirim
        faktor = (1 + r) ** -(yil - 0.5 if yil_ortasi else yil)
        bd = fcff * faktor
        acik_bd += bd
        tablo.append({"yil": yil, "gelir": gelir, "nopat": nopat, "yeniden_yatirim": yeniden_yatirim,
                      "fcff": fcff, "iskonto_faktoru": faktor, "bugunku_deger": bd})
        onceki_gelir = gelir

    # uç değer: N+1 yılı, kalıcı durum. Yeniden yatırım oranı = g / ROIC (Damodaran)
    gelir_uc = onceki_gelir * (1 + g_uc)
    nopat_uc = gelir_uc * (marj[-1] + sbc_orani) * (1 - t)
    fcff_uc = nopat_uc * (1 - g_uc / roic_uc)
    uc_deger = fcff_uc / (r - g_uc)
    uc_bd = uc_deger * (1 + r) ** -n                           # her iki konvansiyonda da N. yıl sonuna
    firma = acik_bd + uc_bd
    ozsermaye = firma - g.get("net_borc", 0.0)
    hisse_n = g["hisse"] * (1 + g.get("yillik_sulandirma", 0.0)) ** n if sbc_yontemi == "sulandirma" else g["hisse"]
    hisse_basi = ozsermaye / hisse_n
    pay = uc_bd / firma if firma > 0 else None

    # yeni sermayenin getirisi, şirketin ulaştığı SON marjla ölçülür (ilk yılların zararı değil)
    marjinal_roic = (marj[-1] + sbc_orani) * (1 - t) * sc
    if any(b > 0 for b in buyume) and marjinal_roic < r:
        uyarilar.append("BUYUME_DEGER_YIKIYOR")
    if any(s["fcff"] < 0 for s in tablo):
        uyarilar.append("NEGATIF_FCFF_YILLARI")
    if pay is not None and pay > UC_DEGER_BASKIN_ESIGI:
        uyarilar.append("UC_DEGER_BASKIN")
    if roic_uc < r and g_uc > 0:
        uyarilar.append("UC_ROIC_ISKONTO_ALTINDA")
    if ozsermaye < 0:
        uyarilar.append("OZSERMAYE_NEGATIF")

    return {"durum": "gecerli", "hatalar": [], "uyarilar": uyarilar, "tablo": tablo,
            "acik_donem_bd": acik_bd, "uc_deger": uc_deger, "uc_deger_bd": uc_bd,
            "firma_degeri": firma, "ozsermaye_degeri": ozsermaye, "hisse_sayisi_kullanilan": hisse_n,
            "hisse_basi_deger": hisse_basi, "uc_deger_payi": pay, "motor_surumu": SURUM}


def ters_dcf(girdi, fiyat, alt=-0.5, ust=1.0, adim=1500):
    """Fiyatın ima ettiği SABİT yıllık gelir büyümesi. Marj, satış/sermaye, vergi, iskonto ve
    uç varsayımlar sabit tutulur. Çözüm yoksa ya da birden çoksa sayı uydurmaz, durumu söyler."""
    sabitler = ["faaliyet_marji", "satis_sermaye", "vergi_orani", "iskonto", "uc_buyume", "uc_roic",
                "net_borc", "hisse", "sbc_yontemi", "iskonto_zamani"]

    def fark(b):
        gg = dict(girdi)
        gg["buyume"] = b
        s = degerle(gg)
        if s["durum"] != "gecerli":
            raise ValueError(s["hatalar"])
        return s["hisse_basi_deger"] - fiyat

    noktalar = [alt + (ust - alt) * k / adim for k in range(adim + 1)]
    degerler = [fark(b) for b in noktalar]
    kokler = []
    for (b0, f0), (b1, f1) in zip(zip(noktalar, degerler), zip(noktalar[1:], degerler[1:])):
        if f0 == 0:
            kokler.append(b0)
        elif f0 * f1 < 0:
            a, c, fa = b0, b1, f0
            for _ in range(200):
                m = (a + c) / 2
                fm = fark(m)
                if fa * fm <= 0:
                    c = m
                else:
                    a, fa = m, fm
            kokler.append((a + c) / 2)
    if degerler[-1] == 0:
        kokler.append(noktalar[-1])
    durum = "tek_cozum" if len(kokler) == 1 else ("cozum_yok" if not kokler else "coklu_cozum")
    return {"durum": durum, "ima_edilen_buyume": kokler[0] if len(kokler) == 1 else None,
            "tum_cozumler": kokler, "sabit_tutulanlar": sabitler, "arama_araligi": [alt, ust]}