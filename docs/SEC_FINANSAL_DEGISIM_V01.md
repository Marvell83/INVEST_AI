# INVEST_AI — SEC Finansal Değişim Motoru v0.1

**Hedef:** Tek şirketin **iki farklı SEC Company Facts arşivi** arasındaki kaynak/dönem farklarını açıklamak; finansal faaliyet değişimlerini kaynaklı ve karşılaştırılabilir dönemler üzerinden göstermek. Yatırımcıya alım-satım tavsiyesi üretmez. Python 3.11+, ücretsiz, yalnız standart kütüphane.

## Ne incelenir?

Üç farklı kavram birbirinden **mutlaka ayrı tutulur**:

| Kavram | Tanım | Yorum |
|---|---|---|
| SEC arşiv değişikliği | İki farklı Company Facts JSON'u arasında eklenen, artık bulunmayan ya da aynı bildirim kimliğinde tutarı değişen bir US-GAAP olgusu | Arşivin *içeriği* değişti; şirketin büyümesi kanıtlanmaz |
| Aynı dönem TTM revizyonu | İki arşivde de bağımsız hesap motorlarının dönem/tutar/kaynak mutabakatı tamamlanmış ve **FY ve 9A dönemleri tamamen eşleşiyor** | Fark muhasebe/kaynak revizyonudur; yeni yıllık büyüme değildir |
| 9A yıllık karşılaştırma | **Son arşivde** güncel ve önceki mali yılın karşılaştırılabilir **9 aylık kümülatif** tutarları | Gelir, EBIT, CFO ve CapEx için 9A/9A nominal USD büyüme; **tek başına üçüncü çeyrek değildir** |

İlk iki hesapta kaynak kimliği: SEC XBRL kavramı, USD para birimi, başlangıç ve bitiş tarihi, 10-K veya 10-Q formu, mali dönem etiketi, SEC yayımlanma tarihi (`filed`) ve `accn` accession numarası. Dönem veya kaynak değişmişse aynı gözlem kabul edilmez.

Bir 10-K/A veya 10-Q/A görüldüğünde otomatik **kesin muhasebe yeniden düzenlemesi** ilan edilmez; bildirimin dipnotlarının gözden geçirilmesi istenir. Eski bir dönem için aynı concept / start / end ile yeni accession ve farklı tutar gelirse `NEWER_SOURCE_DIFFERENT_AMOUNT_REVIEW` işaretlenir.

## Windows / PowerShell

Önce [SEC Çoklu Tarama rehberindeki](SEC_TOPLU_TARAMA_V01.md) komutla veya daha önce kaydedilmiş Company Facts dosyalarıyla iki **gerçekten farklı zamanda yakalanmış** arşiv oluşturun.

Önceki toplu tarama modülü ham dosyaları şuraya koyar:

~~~text
veri/sec_kaynaklari/CIK0000320193/
    index.json
    <eskiden_indirilen_sha256>.json
    <yeniden_indirilen_sha256>.json
~~~

`index.json` yalnızca **son yakalamayı** içerir; eski hash dosyasının yakalama sırasını kendiliğinden ispatlamaz. Hangi dosyanın önce ve sonra indirildiğini araştırmacı doğrulamalıdır.

### 1. Finansal değişimleri hesapla

~~~powershell
python sec_finansal_degisim.py --old veri/sec_kaynaklari/CIK0000320193/ESKI_SHA256.json --new veri/sec_kaynaklari/CIK0000320193/YENI_SHA256.json --cik 320193 --as-of 2026-10-24 --out reports/apple_degisim.json
~~~

`ESKI_SHA256` ve `YENI_SHA256` yer tutucudur; gerçekte o klasörde bulunan 64 karakterlik dosya adlarını kullanın.

### 2. Türkçe HTML değişim raporu

~~~powershell
python sec_degisim_raporu.py --report reports/apple_degisim.json --out reports/apple_degisim.html
~~~

Tarayıcıda `reports/apple_degisim.html` dosyasını açın. Haricî CSS, JavaScript, API veya ücretli hizmet içermez. Farklı arşivlerden gelen şirket kimlikleri uyuşmazsa komut iptal edilir. Kaynak hash'i dosya adına yazılmış arşivlerde dosya içeriği ile hash aynı değilse iptal edilir.

## Araştırma çıktısı

JSON alanları:

- `old_snapshot_sha256`, `new_snapshot_sha256`: kanonik SEC JSON'larının içerik özetleri. Resmî SEC imzası değildir.
- `snapshot_record_changes`: eklenen, değişen, son arşivde bulunmayan ve manuel inceleme isteyen kaynak kayıtları. En fazla 1.000 olay listelenir; daha fazlası varsa **toplam ve atlanan sayı açıkça raporlanır**.
- `same_period_ttm_reconciliation`: yalnız **her iki TTM raporu mutabık ve aynı dönemlerdeyse** dört TTM metrik tutar farklarını gösterir. Dönem farklıysa `DIFFERENT_PERIODS_NO_DIRECT_COMPARISON`.
- `new_snapshot_9m_yoy`: son dosyanın 9A satış, faaliyet kârı, işletme nakit akışı ve yatırım harcaması için önceki 9A yıl karşılaştırması. `change_usd`, `change_pct` ve iki kaynak bildirimi birlikte korunur.
- `margin.change_percentage_points`: Faaliyet marjındaki **yüzde puan** değişimi; göreli yüzdelik artış değildir.
- `requires_manual_review`: kaynak düzeltmesi, kaybolan kayıt veya belirsiz TTM; **hisseyi sat** anlamına gelmez.
- `investment_recommendation`, `forecast`, `price_target`: bilerek `null`.

Önceki karşılaştırma bazı dönemlerde 0 ya da negatif ise yüzde büyüme hesaplanmaz (`null`). SEC olgusunun kaybolması, şirketin onu SEC nezdinde geri çektiğini kanıtlamaz. Tarihli bildirim bağlamı olmadan ekonomik sebep yorumlanmaz.

## Kapsam sınırlamaları

- Yalnız **US-GAAP / USD** için 10-K / 10-K/A **FY** 330–400 günlük ve 10-Q / 10-Q/A **Q3 9A** 240–310 günlük akımlar. Q1/Q2, bağımsız üçüncü çeyrek ve IFRS/20-F henüz desteklenmez.
- TTM mutabakatında iki motor aynı ham kaynağı paylaşır. **Bağımsız SEC doğrulaması değildir.**
- `--as-of` kesme tarihi her iki dosyaya uygulanır. Mevcut arşivdeki geç yayımlanan olguları gizlemek, geçmiş SEC arşivinin tamlığını kanıtlamaz.
- 9A büyüme **organik büyüme**, kur sabitiyle büyüme, FCF, FCFF, sermaye getirisi, rekabet gücü, gelecek tahmini veya hissedeki beklenen getiri anlamına gelmez.
- Arşiv sırasını tarih/snapshot hash'inden çıkaramayız; dosyalar doğru kronolojik sırayla verilmelidir.
- Önceki dönem yeni SEC formuyla karşılaştırıldığında, yeni tutarın neden değiştiğini açıklamak için **gerçek 10-Q/A veya 10-K/A dipnotlarını** manuel incelemek gerekir.

## Test

~~~powershell
python -m unittest discover -s tests -p test_sec_finansal_degisim.py -v
python -m unittest discover -s tests -p test_sec_degisim_raporu.py -v
python -m unittest discover -s tests -v
~~~

Yerel/sentetik testler; aynı kimlikte tutar değişimi, değiştirilmiş SEC accession, 10-Q/A, gelecek tarihli bildirimin dışlanması, kaynak kaydı kaybolması, aynı dönem TTM uyumu ve farklı dönemlerin karşılaştırılmaması, yüzde payda eksikliği ve HTML karakter kaçışını kontrol eder. **Gerçek SEC canlı arşivleri üzerinde uçtan uca kabul testinin yerine geçmez.**

## Sonraki aşama

Toplu indirme sistemine **yakalama zaman çizelgesi** eklemek; sıralı iki kaydı otomatik tanımlayarak güncel SEC değişimlerini gruplandırmak. Daha sonra şirkete özgü dipnot kontrollü finansal marj/ROIC/sermaye verimliliği sinyalleri ve şirketler arasında karşılaştırılabilirlik koşullarını geliştirmek.
