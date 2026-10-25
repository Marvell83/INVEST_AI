# INVEST_AI — Kaynaklı SEC Şirket Araştırması ve Değerleme Çekirdeği

**Durum:** geliştirme ve doğrulama aşamasında. Üretime hazır yatırım önerisi sistemi **değildir**.

**Ürün hedefi (25 Ekim 2026):** **1. SEC evreni ve veri toplama → 2. temel analizle eleme → 3. sektörel analiz → 4. kaynaklı gelecek analizi.** Yeni web/CLI ve toplu tarama raporlarında Piotroski kullanılmaz. Eski bağımsız motor ve eski raporlar silinmeden arşivde tutulur. [Dört aşamalı resmi yol haritası](docs/INVEST_AI_DORT_ASAMALI_YOL_HARITASI.md). Stage 1 tarama tüm pazarı henüz kapsamıyor; stage 2 filtre, stage 3 emsal ve stage 4 beklenti/katalizör modülleri tamamlanmadı.

**Yeni temel analiz tarayıcısı (v0.5):** Web → Analiz çalıştır → **Temel analiz tablosu**. ROE/ROIC, büyüme, marjlar, nakit, borç, kaynaklı fiyat varsa F/K–PD/DD–EV/EBIT–FCF getirisi, sütun seçimi, çoklu alt/üst eşik, sıralama, CSV/Excel dışa aktarımı ve eksik verili şirketleri ayrı tutma. [Nasıl kullanılır ve oran sınırlamaları](docs/TEMEL_ANALIZ_EXCEL_TARAYICI.md). Bu ekran şimdilik yalnız **önceden kaydedilmiş araştırmaları** gösterir; toplu SEC Company Facts indirme ve PEG ileri EPS kaynağı ayrı geliştirme aşamasıdır.


INVEST_AI, ABD SEC Company Facts (XBRL) verisinden **kaynağı ve yayımlanma tarihi izlenebilir** şirket araştırması üretir: veri kalite denetimi, Piotroski F-Score, TTM (son 12 ay) finansalları, kullanıcı varsayımlı DCF / ters DCF ve sonradan puanlanabilen bir tahmin defteri. Yalnız Python standart kütüphanesi kullanılır; ek paket gerekmez.

Değişiklik geçmişi ve her modülün tarihli sürüm notları: **[CHANGELOG.md](CHANGELOG.md)**.

> Finansal tavsiye değildir. Hiçbir modül al/sat sinyali, hedef fiyat veya birleşik yatırım puanı üretmez.

## Kapsam

| Var | Yok |
|---|---|
| SEC Company Facts (US-GAAP, USD, 10-K / 10-Q) | IFRS / 20-F (ör. TSMC), KAP, döviz dönüşümü |
| `as_of` bilgi kesme tarihi (look-ahead koruması) | Canlı fiyat, haber, InvestingPro bağlantısı |
| Piotroski 9 gösterge, eksik veri için puan aralığı | Banka/sigorta için sektöre özel yöntem |
| İki bağımsız TTM motoru ve mutabakat | Otomatik büyüme / iskonto / marj varsayımı |
| v0.1 (dondurulmuş) ve v0.2 (deneysel) DCF + ters DCF | Hisse sulandırması (SBC yalnız gider) |
| Kaynaklı, sadece eklemeli SQLite tahmin defteri | Kriptografik değiştirilemezlik / dış zaman damgası |
| Çevrimdışı Türkçe HTML raporlar, yerel web formu | Bulut / abonelik hizmeti |

## Veri akışı

```
SEC Company Facts (ham JSON, SHA-256 ile arşiv: sec_arsiv)
  ├─ sec_gap_audit ─────────► sec_v02_bridge ─► degerleme_v02 ─► tahmin_defteri
  │   (kaynak/dönem/çelişki)    (sec_reviewed_pipeline yalnız denetim geçince çağırır)
  ├─ finansal_tablolar ─► finansal_oranlar (yıllık tablolar ve oranlar)
  ├─ piotroski_fscore + kredi_notlari (yan yana, birleştirilmez)
  ├─ ttm_finansallar + sec_ttm ─► sec_ttm_crosscheck (iki motor eşleşmeli)
  └─ sirket_arastirma_akisi ─► sirket_analiz_paneli (HTML) ─► index.html / invest_ai_web
```

## Modüller

| Alan | Dosya | Görev |
|---|---|---|
| **Değerleme** | `dogrulama/uretim_motoru.py` | Dondurulmuş v0.1 DCF / ters DCF ([sözleşme](dogrulama/KONVANSIYONLAR.md)) |
| | `degerleme_v02.py` | Deneysel v0.2: NOL, marj yakınsaması, RONIC'li uç değer, ters DCF |
| | `dogrulama/moduller_v02.py` | v0.2 yardımcıları (kök bulucu vb.) |
| | `degerleme_kaydi.py`, `tahmin_defteri.py` | Değerleme tahminlerini kaynaklı SQLite kaydına yazma ve puanlama |
| **Finansal tablolar** | `finansal_tablolar.py` | Ortak, tarihli ve kaynaklı yıllık ve çeyreklik gelir tablosu / nakit akışı / bilanço (27 kalem); kapak sayfası hisse sayısı |
| | `finansal_oranlar.py` | Marj, büyüme, nakit kalitesi, ROA / ROE / ROIC, borçluluk; her oranın formülü ve hesaplanamama nedeni |
| | `katman_mutabakati.py` | Piotroski ve TTM girdilerinin ortak tablolarla aynı rakam ve SEC dosyalarını kullanıp kullanmadığı |
| **Tahmin** | `tahmin_motoru.py` | Şirketin kendi geçmişinden tarihsel baz; analistin kaynaklı uzun vadeli oranıyla temkinli / baz / iyimser senaryolar; Tahmin Defteri kaydı |
| | `sapma_analizi.py` | Defterdeki tahminleri ilk bildirilen SEC değerleriyle eşleyip hata, yanlılık ve senaryo aralığı isabetini ölçer |
| | `senaryo_degerleme.py` | Senaryoları aynı gelir / marj yoluyla v0.2 DCF'de değerler; her girdinin kökeni; iskonto × büyüme duyarlılığı; analistin tarihli fiyatıyla ters DCF (ima edilen büyüme ve şirket geçmişine göre konumu) |
| **SEC verisi** | `sec_companyfacts.py` | Company Facts indirme / normalize etme |
| | `sec_arsiv.py` | Ortak arşiv yardımcıları: SHA-256 arşiv, atomik yazma, ticker–CIK haritası, istek hızı sınırı |
| | `sec_gap_audit.py` | Yıllık kaynak / dönem / etiket çelişkisi denetimi |
| | `sec_revenue_reconciliation.py` | İnsan onaylı gelir etiketi mutabakatı |
| | `sec_reviewed_pipeline.py`, `sec_reviewed_cli.py` | **Önerilen** denetimli SEC → DCF → tahmin defteri akışı |
| | `sec_v02_bridge.py` | Eski doğrudan köprü; denetimi atlar, uyarı verir |
| **TTM** | `ttm_finansallar.py`, `sec_ttm.py` | İki bağımsız TTM hesabı (FY + YTD − önceki YTD) |
| | `sec_ttm_crosscheck.py` | İki motorun tutar/dönem/accession mutabakatı |
| | `ttm_dcf_bridge.py`, `ttm_raporu.py` | TTM tabanlı DCF stres örneği ve HTML |
| **Kalite** | `piotroski_fscore.py` | 9 gösterge; eksik veri 0 sayılmaz |
| | `kredi_notlari.py`, `sirket_kalite_cli.py` | Manuel kaynaklı Moody's / S&P / Fitch notları; kalite raporu |
| **Araştırma** | `sirket_arastirma_akisi.py` | Tek şirket için uçtan uca JSON + HTML |
| | `sirket_analiz_paneli.py`, `gercek_sirket_pilotu.py` | HTML panel; Apple gerçek veri pilotu |
| | `sec_toplu_tarama.py` | Çoklu şirket indirme / arşiv / tarama |
| | `sec_finansal_degisim.py`, `sec_degisim_raporu.py` | İki SEC arşivi arasındaki değişiklik ve revizyonlar |
| **Portföy** | `portfoy_risk.py`, `portfoy_raporu.py` | Ağırlık, HHI, tema yoğunlaşması, analist tanımlı stres |
| **Arayüz** | `index.html`, `invest_ai_web.py` | Rapor listesi; anahtarla korunan yerel analiz formu; isteğe bağlı kaynaklı büyüme ve iskonto girdileriyle senaryo ve deneysel DCF |

## Hızlı başlangıç

Tüm komutlar depo kökünden çalıştırılır (Python 3.11+).

```bash
# Tüm testler (Windows: BASLAT_TESTLER.bat)
python -m unittest discover -s tests -v
(cd dogrulama && python kabul_testi.py && python -m unittest test_dogrulama_seti test_moduller_v02 -v)

# Tek şirket araştırması — internetsiz Apple örneği (manuel SEC aktarımı, canlı veri değil)
python sirket_arastirma_akisi.py --cik 320193 --as-of 2026-10-21 --sector non_financial \
  --companyfacts ornekler/apple_ttm_evidence_2026-10-21.json \
  --out-json reports/apple_research.json --out-html reports/apple_research.html

# Gerçek veri kontrolü: 11 tanınmış şirket, her biri için katman sağlığı ve toplu Türkçe özet
export SEC_USER_AGENT="INVEST_AI Research gercek-adresin@ornek.com"
python3 sec_toplu_tarama.py --universe ornekler/gercek_veri_kontrol_evreni.json --as-of 2026-10-25 --online --archive-dir veri/sec_kaynaklari --reports-dir reports/gercek_kontrol --out-json reports/gercek_kontrol.json --out-csv reports/gercek_kontrol.csv

# Senaryo projeksiyonu (uzun vadeli oranı ve kaynağını analist verir; sistem seçmez)
python tahmin_motoru.py --companyfacts CIK0000320193.json --as-of 2026-10-24 --long-run-growth 0.03 --long-run-source "..." --out reports/senaryo.json

# Senaryoları deneysel DCF ile değerle (iskonto oranını ve kaynağını analist verir)
python senaryo_degerleme.py --companyfacts CIK0000320193.json --as-of 2026-10-25 --long-run-growth 0.03 --long-run-source "..." --discount-rate 0.09 --discount-source "..." --out reports/degerleme.json

# Sonraki 10-K açıklandıktan sonra deftere yazılmış tahminleri puanla
python sapma_analizi.py --ledger tahminler.sqlite --companyfacts YENI_CIK.json --as-of 2027-11-15 --record --out reports/sapma.json --out-html reports/sapma.html

# Yıllık finansal tablolar ve oranlar (ham SEC Company Facts JSON ile)
python finansal_oranlar.py --companyfacts CIK0000320193.json --as-of 2026-10-24 --years 5 --out reports/tablolar.json

# Yerel web arayüzü (terminalde basılan anahtarı forma gir; Codespaces portunu Private tut)
export SEC_USER_AGENT="INVEST_AI Research gercek-adresiniz@example.com"   # canlı SEC için
python invest_ai_web.py
```

Ayrıntılı kullanım: [web analizi](docs/WEB_SIRKET_ANALIZI_V02.md) · [şirket araştırma akışı](docs/SIRKET_ARASTIRMA_AKISI_V01.md) · [toplu tarama](docs/SEC_TOPLU_TARAMA_V01.md) · [portföy riski](docs/PORTFOY_RISK_MOTORU_V01.md) · [SEC entegrasyonu](docs/SEC_INTEGRASYON.md).

## Test durumu

25 Ekim 2026, yerel çalıştırma, Python 3.11 ve 3.13:

| Paket | Komut | Sonuç |
|---|---|---|
| Ana paket (`tests/`) | `python -m unittest discover -s tests` | **570/570** |
| Dondurulmuş v0.1 kabul | `dogrulama/kabul_testi.py` | **17/17** |
| Kabul altyapısı + v0.2 modülleri | `unittest test_dogrulama_seti test_moduller_v02` | **9/9** (2 + 7) |

CI (`.github/workflows/python-tests.yml`) bunların hepsini Python 3.11 / 3.12 / 3.13'te çalıştırır, ayrıca `ruff check .` lint işi vardır. Testlerin çoğu **sentetik** veriyle çalışır; gerçek veri örneği Apple ile sınırlıdır. Testler muhasebe ve hesap doğruluğunu sınar; yatırım getirisi veya tahmin isabetini kanıtlamaz.

## Bilinen metodoloji sınırları

- **v0.1** simetrik vergi ve kaba sulandırma konvansiyonlarını korur; gerçek şirket değerlemesi için uygun değildir.
- **v0.2 DCF:** NOL'de süre/ülke kısıtı yok; uç dönem vergisi normalleştirilir; SBC yalnız gider olarak modellenir; marj yakınsaması büyümeye bağlı değildir. `yil_ortasi` iskontoda açık dönem `t−0,5` ile, uç değer ise `n` ile iskontolanır.
- **Ters DCF** sınırlı aralıkta aday kök arar; kök bulunamaması çözümsüzlüğün kanıtı değildir.
- **Piotroski:** sermaye ihracı göstergesi manuel, tarihli kanıt gerektirir. Devir hızı ve kaldıraçta ortalama varlık kullanılır; orijinal tanım devir hızında dönem başı varlığı kullanır. Finans sektörü puanlanmaz.
- **TTM:** CFO − CapEx, FCFF yerine kullanılmaz. İki motorun eşleşmesi ham dosyanın gerçekliğini bağımsız olarak doğrulamaz.
- **Kaynak denetimi:** 117 şirketlik yerel örnekte 31 şirket manuel inceleme bekliyor. Bunun 7'sinde gelir etiketi çelişkisi var; aday mutabakatlar insan onayı olmadan değerleme kilidini açmaz.

## Geliştirme notları

- Yeni bir SEC arşiv/istek ihtiyacında `sec_arsiv.py` içindeki fonksiyonları kullanın; başka modüllerin `_` ile başlayan fonksiyonlarını içe aktarmayın.
- SEC verisinden DCF üretirken `sec_reviewed_pipeline` kullanın. `sec_v02_bridge.value_sec_snapshot()` doğrudan çağrılırsa `UnauditedSECBaselineWarning` verir ve sonucu `"source_audit_gate": "bypassed"` olarak işaretler.
- `dogrulama/uretim_motoru.py` ve `dogrulama/referans_motor.py` v0.1 sözleşmesi gereği değiştirilmez.
- Lint: `ruff check .` ([pyproject.toml](pyproject.toml); yalnız sözdizimi hatası ve kullanılmayan/tanımsız adlar).

## Belgeler

**[Yol haritası (10 ders)](docs/YOL_HARITASI.md)** · [Finansal tablolar ve oranlar](docs/FINANSAL_TABLOLAR_V01.md) · [Tahmin motoru](docs/TAHMIN_MOTORU_V01.md) · [Sapma analizi](docs/SAPMA_ANALIZI_V01.md) · [Senaryo değerlemesi](docs/SENARYO_DEGERLEME_V01.md) · [SEC kaynak denetimi](docs/SEC_KAYNAK_DENETIMI_V02.md) · [7 gelir mutabakatı](docs/SEC_7_GELIR_MUTABAKATI.md) · [117 dosya denetimi](docs/SEC_117_DOSYA_DENETIMI.md) · [Piotroski + kredi](docs/PIOTROSKI_KREDI_KATMANI_V01.md) · [Piotroski veri eşleme v0.2](docs/PIOTROSKI_SEC_VERI_ESLEME_V02.md) · [Piotroski 117 kapsam](docs/PIOTROSKI_SEC_117_KAPSAM_DENETIMI.md) · [TTM motoru](docs/TTM_FINANSAL_MOTORU_V01.md) · [SEC TTM](docs/SEC_TTM_V01_APPLE.md) · [TTM çift motor](docs/SEC_TTM_CROSSCHECK_V01.md) · [Finansal değişim](docs/SEC_FINANSAL_DEGISIM_V01.md) · [Şirket paneli](docs/SIRKET_ANALIZ_PANELI_V01.md) · [Apple pilotu](docs/APPLE_GERCEK_SEC_PILOTU.md) · [Apple üç senaryolu DCF](docs/APPLE_UC_SENARYOLU_DCF_2026_10_21.md) · [Ana sayfa](docs/ANA_SAYFA_V01.md)

## Metodolojik referanslar

- CFA Institute, Free Cash Flow Valuation (2026): https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/free-cash-flow-valuation
- Aswath Damodaran, Cash Flows: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/littlebook/cashflows.htm
- Aswath Damodaran, Terminal Value & Excess Returns: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/termvalueexreturns.htm
