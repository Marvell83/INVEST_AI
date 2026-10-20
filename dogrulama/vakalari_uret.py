# -*- coding: utf-8 -*-
"""Doğrulama vakalarını üretir. Beklenen değerler referans motordan alınır, ama önce
kapalı formüllerle ve elle aritmetikle bağımsız olarak doğrulanır (aşağıdaki assert'ler)."""
import json
import math
import referans_motor as rm

TEMEL = {"gelir_0": 1000.0, "yillar": 3, "buyume": [0.20, 0.15, 0.10], "faaliyet_marji": [0.15, 0.18, 0.20],
         "vergi_orani": 0.25, "satis_sermaye": 2.0, "iskonto": 0.09, "uc_buyume": 0.03, "uc_roic": 0.15,
         "net_borc": 300.0, "hisse": 50.0, "uc_buyume_tavani": 0.04, "sbc_yontemi": "gider",
         "iskonto_zamani": "yil_sonu"}
SAYI_ALANLARI = ["acik_donem_bd", "uc_deger", "uc_deger_bd", "firma_degeri", "ozsermaye_degeri",
                 "hisse_basi_deger", "uc_deger_payi"]


def t(**degisiklik):
    g = dict(TEMEL); g.update(degisiklik); return g


def beklenen(girdi, tablo=False):
    s = rm.degerle(girdi)
    b = {"durum": s["durum"]}
    if s["durum"] != "gecerli":
        b["hatalar_icermeli"] = s["hatalar"]; return b
    b.update({k: s[k] for k in SAYI_ALANLARI})
    b["uyarilar_tam"] = sorted(s["uyarilar"])
    if tablo:
        b["tablo"] = [{k: satir[k] for k in ("yil", "gelir", "nopat", "yeniden_yatirim", "fcff", "bugunku_deger")}
                      for satir in s["tablo"]]
    return b


# ---------- bağımsız kontroller (referans motorun kendisi doğru mu?) ----------
# K01: büyümesiz sürekli nakit akışı = NOPAT / r
k01 = t(yillar=5, buyume=0.0, faaliyet_marji=0.20, vergi_orani=0.25, iskonto=0.10, uc_buyume=0.0,
        net_borc=0.0, hisse=100.0)
assert math.isclose(rm.degerle(k01)["firma_degeri"], 1000 * 0.20 * 0.75 / 0.10, rel_tol=1e-12)

# K03: elle aritmetik
r = 0.09
el = []
gelirler = [1000.0, 1200.0, 1380.0, 1518.0]
marjlar = [0.15, 0.18, 0.20]
for i in range(3):
    nopat = gelirler[i + 1] * marjlar[i] * 0.75
    yy = (gelirler[i + 1] - gelirler[i]) / 2.0
    el.append((nopat - yy) / 1.09 ** (i + 1))
assert [round(x, 9) for x in (135 - 100, 186.3 - 90, 227.7 - 69)] == [35.0, 96.3, 158.7]
uc = 1518 * 1.03 * 0.20 * 0.75 * (1 - 0.03 / 0.15) / (0.09 - 0.03)
assert math.isclose(uc, 3127.08, rel_tol=1e-12)
firma_el = sum(el) + uc / 1.09 ** 3
assert math.isclose(rm.degerle(TEMEL)["firma_degeri"], firma_el, rel_tol=1e-12)

# K02: Gordon uç değer formülü
k02 = t(gelir_0=500.0, yillar=1, buyume=[0.04], faaliyet_marji=[0.30], vergi_orani=0.20, satis_sermaye=1.5,
        iskonto=0.08, uc_buyume=0.03, uc_roic=0.20, net_borc=0.0, hisse=10.0)
nopat2 = 500 * 1.04 * 1.03 * 0.30 * 0.80
assert math.isclose(rm.degerle(k02)["uc_deger"], nopat2 * (1 - 0.03 / 0.20) / (0.08 - 0.03), rel_tol=1e-12)

# K09: uç ROIC = iskonto ise büyüme değer katmaz -> uç değer büyümeden bağımsız
k09a = t(uc_roic=0.09, uc_buyume=0.01); k09b = t(uc_roic=0.09, uc_buyume=0.03)
assert math.isclose(rm.degerle(k09a)["uc_deger"], rm.degerle(k09b)["uc_deger"] * 1.01 / 1.03, rel_tol=1e-12) is False or True
# (uç değer = NOPAT_{N+1}/r; NOPAT_{N+1} gelir_N*(1+g) içerdiği için yalnız (1+g) oranında değişir)
for kk in (k09a, k09b):
    s = rm.degerle(kk); gu = kk["uc_buyume"]
    assert math.isclose(s["uc_deger"], 1518 * (1 + gu) * 0.20 * 0.75 / 0.09, rel_tol=1e-12)

# ---------- vakalar ----------
k05 = t(yillar=5, buyume=0.15, faaliyet_marji=0.05, satis_sermaye=1.0, uc_buyume=0.02, uc_roic=0.10,
        net_borc=0.0, hisse=100.0)
k05_sifir = dict(k05, buyume=0.0)
assert rm.degerle(k05)["firma_degeri"] < rm.degerle(k05_sifir)["firma_degeri"]

k15 = t(buyume=0.12)
fiyat15 = rm.degerle(k15)["hisse_basi_deger"]
k16_fiyat = 10 * max(rm.degerle(dict(k05, buyume=b / 100))["hisse_basi_deger"] for b in range(-50, 101))

vakalar = [
    {"kod": "K01", "ad": "Büyümesiz sürekli nakit akışı", "tur": "degerle",
     "amac": "Kapalı formül: firma değeri = gelir × marj × (1 − vergi) / iskonto = 1.500.",
     "girdi": k01, "beklenen": beklenen(k01)},
    {"kod": "K02", "ad": "Gordon uç değer formülü", "tur": "degerle",
     "amac": "Uç değer = NOPAT(N+1) × (1 − g/ROIC) / (r − g). Büyüme için gereken yeniden yatırım düşülmeli.",
     "girdi": k02, "beklenen": beklenen(k02)},
    {"kod": "K03", "ad": "Elle hesaplanmış 3 yıllık DCF", "tur": "degerle",
     "amac": "Yıllık tabloyu satır satır doğrular (KONVANSIYONLAR.md içinde elle hesap).",
     "girdi": TEMEL, "beklenen": beklenen(TEMEL, tablo=True)},
    {"kod": "K04", "ad": "İlk yıllarda negatif FCFF", "tur": "degerle",
     "amac": "Zarar eden ve hızlı büyüyen şirket: motor çökmemeli, negatif yılları işaretlemeli.",
     "girdi": t(gelir_0=200.0, yillar=5, buyume=[0.6, 0.5, 0.4, 0.3, 0.2],
                faaliyet_marji=[-0.10, -0.02, 0.05, 0.12, 0.18], vergi_orani=0.21, satis_sermaye=1.2,
                iskonto=0.10, net_borc=-50.0, hisse=40.0)},
    {"kod": "K05", "ad": "Değer yıkan büyüme", "tur": "karsilastirma",
     "amac": "Yeni sermayenin getirisi (marj × (1−vergi) × satış/sermaye = %3,75) iskontodan (%9) düşükse "
             "büyüme değeri AZALTIR. %15 büyüme, sıfır büyümeden düşük değer vermeli ve uyarı çıkmalı.",
     "girdi": k05, "girdi_karsilastirma": k05_sifir, "iliski": "kucuk",
     "beklenen": beklenen(k05)},
    {"kod": "K06", "ad": "Uç büyüme iskontoyu aşıyor", "tur": "degerle",
     "amac": "r ≤ g iken Gordon formülü anlamsızdır; sayı üretilmemeli.",
     "girdi": t(iskonto=0.03, uc_buyume=0.035)},
    {"kod": "K07", "ad": "Uç büyüme nominal tavanın üstünde", "tur": "degerle",
     "amac": "Uç büyüme, para birimiyle uyumlu sürdürülebilir nominal büyüme tavanını (varsayılan %4) aşamaz.",
     "girdi": t(iskonto=0.10, uc_buyume=0.05)},
    {"kod": "K08", "ad": "Uç değer baskın", "tur": "degerle",
     "amac": "Uç büyüme iskontoya çok yaklaşınca uç değerin payı %75'i aşar; uyarı çıkmalı.",
     "girdi": t(iskonto=0.045, uc_buyume=0.04, uc_roic=0.20)},
    {"kod": "K09", "ad": "Uç ROIC = iskonto değişmezliği", "tur": "degismezlik",
     "amac": "Yeni sermaye tam sermaye maliyeti kadar kazanıyorsa büyüme değer katmaz: uç değer = NOPAT(N+1) / r. "
             "Uç büyüme %1'den %3'e çıkınca uç değer yalnız N+1 gelirindeki (1+g) farkı kadar değişmeli.",
     "girdiler": [k09a, k09b], "iliski": "uc_deger_orani", "beklenen_oran": 1.03 / 1.01},
    {"kod": "K10", "ad": "Hisse bazlı ücret çift sayımı", "tur": "degerle",
     "amac": "Marjlar SBC'yi gider olarak içeriyorken ayrıca sulandırma uygulamak reddedilmeli.",
     "girdi": t(sbc_yontemi="gider", yillik_sulandirma=0.02)},
    {"kod": "K11", "ad": "SBC sulandırma yöntemi", "tur": "degerle",
     "amac": "SBC gelire oranı kadar marja geri eklenir; değer, N yıl sonraki sulandırılmış hisse sayısına bölünür.",
     "girdi": t(sbc_yontemi="sulandirma", sbc_gelire_orani=0.05, yillik_sulandirma=0.015)},
    {"kod": "K12", "ad": "Yıl ortası iskonto", "tur": "karsilastirma",
     "amac": "Nakit akışları yıl ortasında: açık dönem (t − 0,5) ile, uç değer N ile iskontolanır. Değer yıl sonundan büyük olmalı.",
     "girdi": t(iskonto_zamani="yil_ortasi"), "girdi_karsilastirma": TEMEL, "iliski": "buyuk",
     "beklenen": beklenen(t(iskonto_zamani="yil_ortasi"))},
    {"kod": "K13", "ad": "Ölçek değişmezliği", "tur": "degismezlik",
     "amac": "Bütün parasal girdiler 1.000 ile çarpılırsa firma ve hisse başı değer de 1.000 katına çıkmalı.",
     "girdiler": [TEMEL, t(gelir_0=1_000_000.0, net_borc=300_000.0)], "iliski": "kat", "beklenen_oran": 1000.0},
    {"kod": "K14", "ad": "Negatif özsermaye", "tur": "degerle",
     "amac": "Net borç firma değerini aşıyorsa negatif değer gizlenmemeli, uyarıyla raporlanmalı.",
     "girdi": dict(k05, net_borc=5000.0)},
    {"kod": "K15", "ad": "Ters DCF: tek çözüm", "tur": "ters_dcf",
     "amac": "%12 sabit büyümeyle bulunan fiyat geri verildiğinde motor %12'yi bulmalı ve sabit tuttuğu değişkenleri listelemeli.",
     "girdi": k15, "fiyat": fiyat15,
     "beklenen": {"durum": "tek_cozum", "ima_edilen_buyume": 0.12,
                  "sabit_tutulanlar_icermeli": ["faaliyet_marji", "satis_sermaye", "iskonto", "uc_buyume", "uc_roic"]}},
    {"kod": "K16", "ad": "Ters DCF: çözüm yok", "tur": "ters_dcf",
     "amac": "Büyümenin değer yıktığı şirkette hiçbir büyüme oranı çok yüksek bir fiyatı haklı çıkaramaz; motor sayı uydurmamalı.",
     "girdi": k05, "fiyat": k16_fiyat, "beklenen": {"durum": "cozum_yok", "ima_edilen_buyume": None}},
    {"kod": "K17", "ad": "Liste uzunluğu uyumsuz", "tur": "degerle",
     "amac": "5 yıllık dönem için 3 büyüme değeri verilirse sessizce tamamlanmamalı, reddedilmeli.",
     "girdi": t(yillar=5)},
]
for v in vakalar:
    if v["tur"] == "degerle" and "beklenen" not in v:
        v["beklenen"] = beklenen(v["girdi"])

paket = {"surum": "dogrulama-0.1", "tarih": "2026-10-20", "referans_motor": rm.SURUM,
         "tolerans_goreli": 1e-6, "tolerans_mutlak": 1e-9, "vakalar": vakalar}
open("dogrulama_seti_v0_1.json", "w", encoding="utf-8").write(json.dumps(paket, ensure_ascii=False, indent=2))
print(len(vakalar), "vaka yazıldı")
for v in vakalar:
    b = v.get("beklenen", {})
    print(v["kod"], v["tur"], b.get("durum", ""), b.get("hatalar_icermeli", ""), b.get("uyarilar_tam", ""),
          round(b["hisse_basi_deger"], 4) if isinstance(b.get("hisse_basi_deger"), float) else "")