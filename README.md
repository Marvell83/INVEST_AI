# INVEST_AI — Bağımsız Değerleme Çekirdeği

**Durum:** geliştirme ve doğrulama aşamasında. Bu depo INVEST_AI'nın kaynaklı SEC şirket araştırması, finansal kalite, tarihli TTM verileri, deneysel değerleme ve tahmin kaydı modüllerini içerir.

## Amaç

Hedef, tek bir kullanıcının portföyüyle sınırlı olmayan, şirketler için **kaynağı izlenebilir tarihli SEC finansal veri analizi, veri kalite denetimi, Piotroski F-Score, TTM, kaynaklı senaryolu DCF/ters DCF ve Tahmin Defteri** sunan bağımsız bir yatırım araştırma altyapısı oluşturmaktır. **Henüz üretime hazır otomatik yatırım önerisi, canlı fiyat/haber takip sistemi, InvestingPro bağlantısı veya IFRS/20-F desteği yoktur.**

## Modüller

- `dogrulama/uretim_motoru.py`: dondurulmuş 0.1 DCF ve ters DCF kurallarının bağımsız Python uygulaması.
- `dogrulama/moduller_v02.py`: deneysel vergi zarar devri, marj yakınsaması, marjinal getiri tanısı ve kök bulma işlevleri.
- `dogrulama/KONVANSIYONLAR.md`: dondurulmuş 0.1 hesap sözleşmesi.
- `dogrulama/kabul_testi.py`, `dogrulama/dogrulama_seti_v0_1.json`: 17 vakalık kabul altyapısı.
- `dogrulama/test_moduller_v02.py`: 7 deneysel modül testi.

## Windows

Python 3 kurulu bilgisayarda `BASLAT_TESTLER.bat` dosyasını çalıştırın.

## Test durumu

Kaynak ZIP'de raporlanan sonuçlar: **0.1 üretim motoru 17/17**, doğrulama altyapısı **2/2**, 0.2 deneysel modüller **7/7**. Tam entegre 0.2 motoru ve bağımsız 0.2 kabul seti **henüz yoktur**.

> Finansal tavsiye değildir. 0.1'in simetrik vergi ve kaba sulandırma yöntemleri gerçek şirket değerlemeleri için uygun değildir. 0.2 modüllerinin kök araması tüm kökleri bulmayı garanti etmez.


## Tahmin Defteri v0.1 (yeni)

`tahmin_defteri.py` yalnızca Python standart kütüphanesi ve SQLite kullanır. Kaynak gösterilerek kaydedilen tahminleri, daha sonra açıklanan gerçekleşen değerleri ve mutlak/imzalı tahmin hatalarını **ayrı, eklemeli kayıtlar** olarak saklar. Kayıtlar SQL tetikleyicileriyle güncelleme/silmeye karşı korunur. Bu, dosyaya erişen kötü niyetli birinin veritabanını değiştiremeyeceği anlamına gelmez; kriptografik değiştirilemezlik veya dış zaman damgası sağlamaz.

Çalıştırma: `python -m unittest discover -s tests -v`

Bu modül `degerleme_kaydi.py` aracılığıyla değerleme motorlarına bağlanmıştır. GitHub Actions koşusu henüz doğrulanmış değildir. Test girdileri sentetiktir. Değerlendirme şu anda mutlak hata ve imzalı hatadır; olasılık kalibrasyonu ve ölçeğe duyarlı skorlar daha sonra eklenecektir.


## DCF → Tahmin Defteri entegrasyonu

`degerleme_kaydi.py` dondurulmuş v0.1 `degerle()` ya da deneysel v0.2 `degerle_v02()` motorundan gelen yıllık gelir (`revenue`) ve serbest nakit akışı (`fcff`) tahminlerini SQLite'a kaydeder. Her kayıt şirketi, para birimini, tahmin yılını, kaynak listesini, varsayımları, model sürümünü ve hesaplanan özsermaye/hisse değerini içerir. Geçersiz değerleme kaydedilmez. Çok satırlı kayıtlarda dış SQLite işlemi kullanılır; ara aşamada hata olursa geri alma hedeflenir.

Örnek kullanım (yalnız sentetik test girdileri):

```python
from degerleme_kaydi import degerle_ve_kaydet
sonuc = degerle_ve_kaydet(
    db_path="tahminler.sqlite", company="DEMO", currency="USD",
    base_year=2026, inputs={
        "yillar": 3, "gelir_0": 100, "buyume": 0.1,
        "faaliyet_marji": 0.2, "satis_sermaye": 2,
        "vergi_orani": 0.2, "iskonto": 0.1,
        "uc_buyume": 0.02, "uc_roic": 0.12,
        "net_borc": 0, "hisse": 10, "sbc_yontemi": "gider"
    }, sources=["synthetic example"]
)
print(sonuc["durum"], sonuc["tahmin_kimlikleri"])
```

GitHub Actions: `.github/workflows/python-tests.yml`. Çalıştırma: `python -m unittest discover -s tests -v`. Test sonuçları GitHub Actions üzerinden kontrol edilmelidir; testlerin bu değişiklikle geçtiği henüz doğrulanmış değildir. v0.1 ekonomik sınırlamaları sürmektedir.

## v0.2 alpha — deterministik DCF + ters DCF

**Yeni:** `degerleme_v02.py` içinde `degerle_v02(inputs)` ve `ters_dcf_v02(inputs, price, lower, upper)` bulunur. v0.1'in sözleşmesi ve referans testleri değiştirilmemiştir.

v0.2 şu hesapları birlikte yapar: her yıl `gelir = onceki_gelir * (1 + buyume)`, faaliyet marjının belirtilen hedefe üstel yakınsaması, EBIT, önceki yıllardan devreden basitleştirilmiş vergi zararı (NOL), yeniden yatırım `gelir_farki / satis_sermaye`, FCFF, dönemsel bugünkü değer, normalleştirilmiş uç dönem vergisi ve RONIC üzerinden uç dönem yeniden yatırım. ROIIC için önceki yılın yeniden yatırımı kullanılır (tanı göstergesi).

Örnek (sentetik veri, finansal öneri değildir):

```python
from degerleme_v02 import degerle_v02, ters_dcf_v02
girdi = dict(yillar=3, gelir_0=100, buyume=.10,
    marj_0=.15, marj_hedef=.20, yakinlasma=.5,
    satis_sermaye=2, vergi_orani=.25, iskonto=.10,
    uc_buyume=.02, uc_roic=.12, hisse=10)
hesap = degerle_v02(girdi)
print(hesap["hisse_basi_deger"])
arama = ters_dcf_v02(girdi, price=hesap["hisse_basi_deger"], lower=.05, upper=.15)
print(arama["durum"], arama["ima_edilen_buyume"])
```

Tahmin Defteri'ne kaydetmek için `degerle_ve_kaydet(..., inputs=girdi, engine="v0.2")` kullanılır. Motor sürümü kayıtta saklanır.

**Sınırlamalar:** NOL'de süre bitimi, ülke kısıtları veya faiz vergi kalkanı modellenmez. SBC yalnız gider yaklaşımıdır; hisse sulandırması otomatik modellenmez. Marjın yıllık yakınsaması büyüme oranına açıkça bağlı değildir. Uç büyüme nominal para birimiyle uyumlu biçimde kullanıcı tarafından belirlenmelidir. Uç dönem vergisi normalleştirilir. Ters DCF araması sınırlı bir aralıktaki **aday kökleri** tarar: kök bulunamaması çözümsüzlüğün matematiksel kanıtı değildir.

Yerelde çalıştırılan v0.2 testleri: **16/16 başarılı**. Daha önceki v0.1 kabul testleri: **17/17** ve deneysel modül testleri: **7/7**. GitHub Actions'ın bu değişiklikler üzerindeki sonucu ayrıca kontrol edilmelidir. Bunlar ekonomik tahmin doğruluğu kanıtı değildir.



## SEC Company Facts — tarihli gerçek finansal veri altyapısı (yeni)

**Yeni modüller:** `sec_companyfacts.py` ve `sec_v02_bridge.py`. ABD SEC'nin Company Facts XBRL API'sinden yalnız USD birimindeki seçilmiş 10-K / 10-K/A yıllık muhasebe olguları alınır. Her satır açıklanma tarihi (`filed`), dönem başı/sonu (`start/end`), accession, XBRL kavramı ve kaynak URL'siyle korunur. `--as-of` filtresi, geçmiş bir analiz tarihinde henüz yayımlanmamış bilgilerle hesaplama yapılmasını engeller.

**DCF bağlantısı:** Son ortak tarihsel gelir ve EBIT kaydından `gelir_0` ve `marj_0` çıkarılır; büyüme, iskonto, hedef marj, terminal varsayımlar, hisse adedi ve net borç kaynakları kullanıcı tarafından belirtilmeden değerleme oluşturulmaz. CFO - CapEx, FCFF sanılmaz. Bu modül sadece SEC yıllık XBRL verisini kapsar; **InvestingPro, canlı fiyat, sektör araştırması veya otomatik yatırım önerisi içermez.**

[SEC kurulum, komutlar, sentetik örnek ve sınırlamalar](docs/SEC_INTEGRASYON.md)

Test komutu: `python -m unittest discover -s tests -v`. SEC modülleri için yerelde **20/20 sentetik test başarılı**. Gerçek şirket verileriyle kapsamlı kontrol ve GitHub Actions sonuç doğrulaması ayrıca gereklidir.


## SEC kaynak kalite kapısı ve v0.2 tahmin kaydı (20.10.2026)

Yeni, korunmalı veri akışı:

`SEC ham Company Facts` → `sec_gap_audit.py` (dönem/kaynak/çelişki) → `sec_v02_bridge.py` → `degerleme_v02.py` → `sec_reviewed_pipeline.py` → `tahmin_defteri.py`.

- 117 yerel SEC dosyasının yeniden denetiminde **86** şirket yalnızca ön incelemeyi geçti; **31** şirketin manuel kontrol gerektirdiği saptandı. Bunların **7** tanesinde birden fazla yıllık gelir etiketi arasında %5'ten büyük tutar ayrışması var.
- `sec_gap_audit.py`: kaynak ve mali yıl uyuşmazlığını ayrı raporlar; IFRS/eksik EBIT/pozitif olmayan geliri uydurma verilerle doldurmaz.
- `sec_reviewed_pipeline.py`: yalnız kaynak denetimini geçen ham SEC verilerinden deneysel v0.2 DCF üretip gelir, EBIT ve FCFF tahminlerini **kaynaklı, dönemli SQLite kayıtlarına** dönüştürür. Eski doğrudan `sec_v02_bridge.py` kullanımı **bu yeni denetim kapısını atlar**; yeni araştırmalarda korumalı akışı tercih edin.
- `sec_reviewed_cli.py`: bu akışı dosyalar üzerinden çalıştırır. Kullanıcı tüm gelecek varsayımları ve gelecekteki **mali yıl bitiş tarihlerini** verir; sistem bunları kendiliğinden tahmin etmez.
- Denetim, kaynak ve kullanım ayrıntısı: [docs/SEC_KAYNAK_DENETIMI_V02.md](docs/SEC_KAYNAK_DENETIMI_V02.md).

Test komutu: `python -m unittest discover -s tests -v`. Yerelde SEC modülleri için sentetik dosyalar ve SQLite uyumlu bir test adaptörüyle **38/38 test** geçmiştir. **GitHub üzerindeki gerçek tahmin defteriyle yeni CI sonucu henüz onaylanmamıştır**. Üretime hazır veya yatırım tavsiyesi değildir.


## SEC 10-K gelir etiketi mutabakatı — yedi araştırma adayı (2026-10-20)

Yedi şirketin resmî 10-K tablolarında konsolide gelir satırı araştırıldı ve yerel SEC Company Facts XBRL arşivinde **7/7 CIK / mali dönem / accession / tutar eşleşmesi** bulundu. Kanıtlar ve tutarlar: [SEC 7 gelir mutabakatı](docs/SEC_7_GELIR_MUTABAKATI.md); makine-okunur **onaylanmamış** adaylar: [evidence/sec_2026_revenue_review_candidates.json](evidence/sec_2026_revenue_review_candidates.json).

**Önemli:** Birincil kaynak araştırması, yetkili analistin imzaladığı muhasebe incelemesiyle aynı şey değildir. Aday JSON'un `status` alanı `proposed_requires_human_signoff` olduğu için sistem **bu 7 şirket için değerleme kilidini açmaz**. Kaynak okunup doğrulandıktan sonra `sec_revenue_reconciliation.py`, açıkça `approved` ve kaynak alanları dolu bir incelemeyi SEC XBRL verileriyle karşılaştırabilir.

`sec_reviewed_pipeline.analyze_and_record(..., revenue_review=...)` ve `sec_reviewed_cli.py --revenue-review approved_review.json` ile bu karar kayıt altına alınır. Yeni testler doğru onay, yanlış şirket, yanlış yıl, yanlış accession, yanlış tutar, sahte kaynak adresi ve eksik EBIT gibi durumları kapsar. Asıl GitHub CI sonucu ayrıca doğrulanmalıdır.

Veri sınırı: 117 şirketin ilk örnekleminde 86 aday daha önce teknik ön kontrolden geçiyordu; 7 kaynak açıklaması bulunsa bile **31 manuel inceleme gerektiren şirketin sayısı yetkili onay olmadan azaltılmaz**. Kalan 24 dosya başka veri sorunları yüzünden ayrıca incelenecek.


## Finansal kalite: Piotroski F-Score + kredi notları (v0.1)

`piotroski_fscore.py` SEC 10-K/10-K/A yıllık US-GAAP olgularından dokuz Piotroski göstergesini hesaplar. Eksik/kapsamı çelişen veri **0 puana dönüştürülmez**: `score=null`, `score_range=[alt,üst]`, `missing_reasons` ile raporlanır. Banka/sigorta ve doğrulanmamış sektörleri otomatik sıralamayız. Sermaye ihracı göstergesi için hisse sayısı değişimine bakmak yerine tarihli ve kaynaklı manuel inceleme gerekir.

`kredi_notlari.py` Moody's, S&P, Fitch **uzun vadeli ihraççı notlarını** ayrı, append-only SQLite olay defterinde saklar. Yayımlanma tarihi, etki tarihi, kaynak URL ve görünüm korunur; not geri çekilmişse eski not etkin sayılmaz. **Kredi notlarından doğrudan WACC, Piotroski puanı veya hisse değerlemesi üretilmez.**

`sirket_kalite_cli.py` bu iki kalite görünümünü tek JSON raporunda **birleştirmeden yan yana** sunar:

```bash
python sirket_kalite_cli.py report --companyfacts companyfacts.json --as-of 2026-10-21 --sector non_financial --out kalite_raporu.json
```

Ayrıntılı sözleşme, 9 gösterge, kredi notu girişi, veri sınırlamaları ve testler: [Piotroski + kredi modülü rehberi](docs/PIOTROSKI_KREDI_KATMANI_V01.md).

**Doğrulama:** Geliştirme ortamında 23 sentetik birim testi başarılıdır. GitHub Actions sonuçları ayrıca kontrol edilmelidir. Bu muhasebe testi geçmiş fiyat performansı/gelecek getirisi doğrulaması değildir.


## Piotroski SEC veri kalitesi v0.2 (21 Ekim 2026)

- `piotroski_fscore.py` artık `GrossProfit` doğrudan bildirilmediğinde, **aynı SEC accession ve mali dönemdeki** gelir eksi `CostOfGoodsAndServicesSold` / `CostOfRevenue` / `CostOfGoodsSold` üzerinden kaynaklı brüt kâr türetebilir.
- `LongTermDebt` (kısa vadeli kısmı da içerebilir) doğrudan `LongTermDebtNoncurrent` ile eşit sayılmaz. Sadece aynı belgede `LongTermDebtCurrent` de bulunuyorsa çıkarım yapılır. Eksik borç sıfır kabul edilmez.
- Alternatif maliyet veya borç mutabakatları %0,5 üzerinde farklıysa ilgili Piotroski sinyali bilinmeyen kalır.
- Yerel 117 SEC şirket örnekleminde brüt kâr marjı sinyalindeki eksik sayısı **61→40**, borç kaldıraç sinyalindeki eksik sayısı **66→60** olarak değişti. Borçta 20 yeniden hesaplanabilir, 14 önceki güvensiz hesap ise reddedildi. **Bu bir veri kapsama raporudur, hisse başarı testi değildir.**
- Kaynak ve test yöntemleri: [docs/PIOTROSKI_SEC_VERI_ESLEME_V02.md](docs/PIOTROSKI_SEC_VERI_ESLEME_V02.md). Yeni doğrulama testleri: `tests/test_piotroski_coverage_v02.py`. Eski kuralların hesapları değişebildiği için önceki F-Score raporları yeniden üretilmelidir.

Yerel geliştirme sürümünde toplam 50 birim testi başarılıdır; GitHub Actions sonucunu ayrıca teyit edin. Özellikle TSMC gibi IFRS/20-F şirketler bu modülün mevcut kapsamı dışındadır.


## Şirket araştırma paneli v0.1

Yeni `sirket_analiz_paneli.py` statik ve internet gerektirmeyen **HTML şirket raporu** üretir. Piotroski'nin 9 ayrı koşulu, manuel kaynaklı Moody's / S&P / Fitch ihraççı notları ve opsiyonel deneysel SEC DCF çıktısı birbirinden ayrılır; **birleşik yatırım puanı yoktur**.

```bash
python sirket_analiz_paneli.py --quality kalite.json --valuation dcf.json --out rapor.html
```

`--valuation` isteğe bağlıdır. Aynı CIK eşleşmesi, HTML karakter kaçışı, eksik F-Score'un kesin puana dönüşmemesi ve kredi notlarından değerleme üretilmemesi korunur. Kullanım ve sınırlamalar: [docs/SIRKET_ANALIZ_PANELI_V01.md](docs/SIRKET_ANALIZ_PANELI_V01.md). Testler `tests/test_sirket_analiz_paneli.py` içindedir. Yeni yerel geliştirme test seti **58/58** başarılıdır; bu sayı GitHub CI veya gerçek yatırım başarısı garantisi değildir.


## İlk gerçek SEC şirket pilotu — Apple (FY2025)

Çevrimdışı kaynak izi korunmuş **gerçek şirket** pilotu eklendi: `gercek_sirket_pilotu.py`, `tests/test_gercek_sirket_pilotu.py`, [Apple teknik raporu](docs/APPLE_GERCEK_SEC_PILOTU.md), [Apple sonuç JSON](reports/Apple_SEC_Piotroski_2026-10-21.json) ve [Apple HTML paneli](reports/Apple_SEC_Piotroski_2026-10-21.html).

21 Ekim 2026 bilgi kesme tarihinde 18 Ekim tarihli **yerel SEC arşivinden** alınan Apple FY2025 10-K verilerinde Piotroski'nin 9 göstergesinden **8'i hesaplanabildi**: 7 olumlu, 1 olumsuz, sermaye ihracı kanıtı eksik. Sonuç **kesin puan değil, 7–8 aralığıdır**. Gerçek veri 31 Ekim 2025 tarihli 10-K ile dönem/tutar düzeyinde çapraz kontrol edilmiştir: [SEC resmî 10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm).

Örnek kullanım:

```bash
python gercek_sirket_pilotu.py --companyfacts CIK0000320193_AAPL.json --expected-cik 0000320193 --sector non_financial --as-of 2026-10-21 --expected-fiscal-end 2025-09-27 --out-json apple.json --out-html apple.html
```

Ham SEC JSON depoya eklenmedi; veri kaynağı [SEC Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json). Yerel arşiv SHA-256 özeti, kullanılan finansal olguların accession/kavram/dosyalama tarihleri JSON raporunda saklı. **Bu canlı fiyat takibi, güncel 2026 tam yıl bilançosu, doğrulanmış kredi notu veya DCF hedef fiyatı değildir.** Kaynaklı ileriye dönük varsayımlar olmadan DCF üretilmez.

`python -m unittest discover -s tests -v` yeni pilota ait çevrimdışı regresyon testlerini de keşfeder. Yerel kalite bileşenleriyle **31 test** geçti. **GitHub'daki birebir sürüm üzerinde CI durumu henüz teyit edilmedi**; test sayısını tüm depo onayı gibi değerlendirmeyin.


## Apple: kaynaklı üç senaryolu DCF ve ters DCF örneği (21 Ekim 2026)

İlk gerçek şirket örneğinin **yalnız tarihli ve varsayımsal stres modeli** olan çalışma, `ornekler/apple_dcf_stres_pilotu_2026_10.py` içinde. Apple'ın FY2025 SEC 10-K ciro ve EBIT'i, 2026 Haziran 10-Q bilançosu, Temmuz 2026 hisse sayısı ve **20 Ekim 2026 kapanış fiyatı** birbirinden farklı kaynak tarihleridir. Bu karışım güncel bir kesin hedef fiyat **değildir**. Model FY2026 ilk 9 aylık sonuçlarını TTM yıllık finansallara dönüştürmez.

- **Temkinli / baz / iyimser:** yalnız analist tarafından oluşturulmuş yıllık ciro büyümesi, hedef faaliyet marjı, sermaye devir oranı, iskonto ve terminal büyüme stresleri. Model çıktıları sırasıyla yaklaşık **71,83 / 132,61 / 242,28 USD/hisse**. Bunlar piyasa konsensüsü veya alış/satış tavsiyesi değildir.
- **Koşullu ters DCF:** 339,50 USD önceki seans kapanışı için, diğer baz senaryo varsayımları sabitken yaklaşık **%34,53** beş yıllık sabit yıllık büyüme. Kök araması kapsam garantisi vermez.
- **Piotroski ihraç ayrımı:** 2025'te çalışan vergisi sonrası 58,146 milyon hisse ihraç edildiği halde 401,672 milyon hisse geri alındı. «Hisse sayısı azaldı» ifadesi «hiç yeni hisse çıkarılmadı» anlamına gelmez. Dokuzuncu F-Score koşulu sürüm ve ihraç tanımı belirlenmeden kesinleştirilmez.
- Örnek testler `tests/test_apple_dcf_stres_pilotu.py`; ayrıntılı kaynaklar, yıl farkları ve varsayımlar: [docs/APPLE_UC_SENARYOLU_DCF_2026_10_21.md](docs/APPLE_UC_SENARYOLU_DCF_2026_10_21.md).

```bash
python -m ornekler.apple_dcf_stres_pilotu_2026_10 --out apple_stres_sonuclari.json
python -m unittest discover -s tests -v
```

Yeni kod için GitHub Actions sonucu henüz doğrulanmamıştır; canlı fiyat kaynağına otomatik bağlanmaz. Gelişmiş, bağımsız yerel HTML örneği ve daha sıkı tarih/doğrulama kontrolleri ayrıca indirilebilir ZIP paketi olarak hazırlanmıştır.


## TTM Finansal Motoru — 23 Ekim 2026

`ttm_finansallar.py`: US-GAAP 10-K yıllık FY + 10-Q Q3 dokuz aylık YTD − karşılaştırmalı önceki dokuz aylık YTD üzerinden kaynaklı son 12 ay (TTM) hesaplar. `filed` kesme tarihi, SEC accession, mali yıl başlangıcı/bitişi, birim ve çelişkili gelir etiketleri koruma altındadır. CFO−CapEx **FCFF olarak kullanılmaz**.

`ttm_dcf_bridge.py`: TTM gelir/EBIT tabanını v0.2 deneysel DCF'ye bağlar; yıllık/ara dönem bildirimleri, CIK, bilanço, hisse adedi ve varsayımların tarih/kaynak mutabakatını zorunlu tutar. `ttm_raporu.py`: internetsiz HTML rapor üretir. **Gerçek Apple SEC toplamlarından elle hazırlanmış (ham SEC API dosyası olmayan) demonstrasyon:** `ornekler/apple_ttm_evidence_2026-10-21.json`.

Apple'ın 21 Ekim 2026 bilgi kesitinde TTM: **466,823 milyar USD gelir**, **154,859 milyar USD EBIT**, **146,724 milyar USD CFO**, **10,041 milyar USD CapEx**. Aynı eski varsayımlar korunarak yapılan stres testindeki hisse başı değerler: **80,88 / 149,46 / 273,18 USD**. Bunlar yatırım tavsiyesi veya güvenilir hedef fiyat değildir.

Kullanım, kaynak ve sınırlamalar: [docs/TTM_FINANSAL_MOTORU_V01.md](docs/TTM_FINANSAL_MOTORU_V01.md). Yeni TTM, DCF köprüsü ve HTML testleri: `tests/test_ttm_finansallar.py`, `tests/test_ttm_dcf_bridge.py`, `tests/test_ttm_raporu.py`. Yerelde **39/39 TTM paketi testi başarılı**; GitHub Actions sonucu ayrı doğrulama gerektirir.


## SEC TTM finansal akış motoru v0.1

`sec_ttm.py`, ham SEC Company Facts verisinden **TTM = FY + güncel mali yıl YTD − önceki mali yılın karşılaştırılabilir YTD'si** formülüyle gelir, EBIT, faaliyet nakit akışı ve CapEx hesaplar. Yalnız US-GAAP / USD / 10-K / 10-Q kapsamındadır; açıklanma tarihini, SEC accession numarasını ve kullanılan üç kaynak olgusunu saklar. Tek çeyrek tutarını dokuz aylık toplam diye kabul etmez.

Apple'ın Haziran 2026 sonunda biten TTM kontrolü: **466,823 milyar USD gelir**, **154,859 milyar USD EBIT**, **146,724 milyar USD faaliyet nakit akışı**, **10,041 milyar USD CapEx**. Bunlar 18 Ekim tarihli yerel arşivdeki kayıtlarla hesaplanmıştır; daha yeni bildirimin yokluğu kanıtlanmış değildir. `CFO - CapEx` otomatik olarak FCFF değildir. Bağımsız testlerde 12/12 başarı; GitHub Actions sonucu ayrıca teyit edilmeli.

Komutlar ve kaynak mutabakatı: [docs/SEC_TTM_V01_APPLE.md](docs/SEC_TTM_V01_APPLE.md). TTM'nin tek başına DCF'yi otomatik ve güvenilir hedef fiyata dönüştürmediğine dikkat edin.


## SEC TTM çift motor mutabakatı (24 Ekim 2026)

`sec_ttm_crosscheck.py`, aynı ham SEC Company Facts JSON'u üzerinde `ttm_finansallar.py` ve `sec_ttm.py` hesaplarını karşılaştırır. Gelir, EBIT, CFO, CapEx tutarlarının yanı sıra dönem başlangıcı/bitişi, filing tarihi, SEC accession ve XBRL kavramı eşleşmelidir. Fark varsa otomatik mutabakat engellenir. Resmî SEC indirme isteğe bağlıdır; internet gerektirmeyen dosya modu ve indirilen ham JSON'u saklama seçeneği vardır. **Bu kontrol, ham dosyanın gerçekliğini bağımsız doğrulamaz; CFO-CapEx FCFF değildir; otomatik DCF üretmez.**

Windows PowerShell'de (iletişim adresinizi değiştirin):

```powershell
$env:SEC_USER_AGENT = "INVEST_AI Research your-real-email@example.com"
python sec_ttm_crosscheck.py --cik 320193 --as-of 2026-10-24 --download --snapshot-out apple_companyfacts_raw.json --out apple_ttm_audit.json
```

Sözleşme, çevrimdışı çalışma, hata durumları ve testler: [SEC TTM çift motor rehberi](docs/SEC_TTM_CROSSCHECK_V01.md).


## Portföy Risk Motoru v0.1 — kesirli hisseler ve AI yoğunlaşması

`portfoy_risk.py` artık **kullanıcıdan gelen hisse adedi (kesirli olabilir), tarihli USD fiyat, alış maliyeti, nakit, sektör ve temaları** kullanarak portföy ağırlıkları, USD gerçekleşmemiş kâr/zarar, HHI, en büyük üç pozisyon, tematik maruziyet ve elle tanımlanan stres senaryoları hesaplar.

- Özellikle NVDA/TSM/ASML/VRT/STRL/VST benzeri örtüşen AI temalarında **aynı hisse bir birleşik tema içinde iki kez sayılmaz**.
- Hisse adedi, maliyet veya fiyat eksikse otomatik tahmin üretmez; eksik maliyetin etkisini `null` olarak korur. Fiyat kaynağı sistem tarafından doğrulanmaz.
- Bir ETF girildiğinde altındaki hisseler otomatik ayrıştırılmaz; gerçek çeşitlendirme ayrıca incelenmelidir.
- Senaryo için **her hissenin şoku** analist tarafından verilmelidir; otomatik tahmin, hedef portföy ağırlığı veya sat/al sinyali üretilmez.
- İsteğe bağlı USD/TRY dönüşümü yalnız **bugünkü TL karşılık** üretir; geçmiş TL maliyet/kâr değildir.
- `portfoy_raporu.py` bu JSON'u HTML kaçışlı, bağımsız ve internet gerektirmeyen **Türkçe portföy risk raporuna** dönüştürür.

**Tamamen sentetik demonstrasyon:**

```powershell
python portfoy_risk.py --portfolio ornekler/portfoy_risk_SENTETIK_8_HISSE.json --out portfoy_ornek.json
python portfoy_raporu.py --report portfoy_ornek.json --out portfoy_ornek.html
python -m unittest discover -s tests -v
```

İçerik, örnek matematik, sınırlamalar ve Midas'tan manuel veri şablonu: [Portföy Risk Motoru v0.1](docs/PORTFOY_RISK_MOTORU_V01.md).


## Tek komutla genel şirket araştırması — v0.1 (24 Ekim 2026)

**Yeni:** `sirket_arastirma_akisi.py`, portföy adetleri veya kişisel işlem geçmişi gerektirmeden **SEC Company Facts kapsamındaki tek bir şirketi** analiz eder. Halihazırdaki `sec_gap_audit.py` (yıllık kaynak kontrolü), `piotroski_fscore.py` (9 gösterge), `kredi_notlari.py` (opsiyonel manuel ihraççı notları), `sec_ttm_crosscheck.py` (iki ayrı TTM hesap motoru) ve `sirket_analiz_paneli.py` (Türkçe HTML) bileşenlerini tek iş akışında birleştirir.

Eksik veya çelişkili kaynak **kısmi araştırma raporunda belirtilir**; bilinmeyen F-Score kesin sayıya, TTM noksanlığı sıfıra, geçmiş finansallar otomatik hedef fiyata çevrilmez. CIK, sektör sınıflandırması, bilgi tarihi ve isteğe bağlı mali yıl sonu açıkça denetlenir. Çıktı hem kaynakları koruyan JSON hem de internet gerektirmeyen HTML'dir. Ücretsiz Python standart kütüphanesini kullanır.

Depodaki **manuel SEC aktarımı** Apple örneğiyle çevrimdışı kullanım:

```powershell
python sirket_arastirma_akisi.py --cik 320193 --as-of 2026-10-21 --sector non_financial --companyfacts ornekler/apple_ttm_evidence_2026-10-21.json --out-json reports/apple_research.json --out-html reports/apple_research.html
```

Bu Apple dosyası gerçek ham API indirmesi değildir, **manuel transkripsiyon** olarak raporlanır. Bir SEC API dosyası doğrudan indirilecekse gerçek iletişim e-postası içeren `SEC_USER_AGENT` ve arşivlemek için `--snapshot-out` zorunludur.

[Genel şirket araştırma rehberi, durum sözleşmeleri ve sonraki ürün aşamaları](docs/SIRKET_ARASTIRMA_AKISI_V01.md).


## SEC Çoklu Şirket Toplama ve Tarama v0.1 (24 Ekim 2026)

Yüzlerce farklı **SEC CIK** için `sec_toplu_tarama.py` ile tarihli ham Company Facts arşivi oluşturma, içerik hash'iyle eski sürümleri koruma, önbellekten yeniden kullanma, SEC ticker–CIK eşlemesini kontrol etme ve `sirket_arastirma_akisi.py` üzerinden her şirket için JSON/HTML araştırması üretme desteği eklendi.

Kişisel portföy adetleri, alış fiyatları veya al/sat önerileri kullanılmaz. Sektör kodu açık analist girdisidir; bilinmiyorsa `unknown` kalır. Puanı oluşturulamayan şirketler yanlışlıkla sıfır skor almaz. Bankalar, IFRS/20-F ve SEC açıklama dipnotlarının manuel mutabakatı ayrıca geliştirilmelidir.

- SEC Fair Access: varsayılan 1 istek/saniye ve en fazla 2 istek/saniye; 403/429 ile erişim engeli görülürse sonraki SEC istekleri durur.
- Kaynak arşivi: `CIKXXXXXXXXXX/<sha256>.json` ve en son yakalama işaretçisi; ham dosya SHA-256 doğrulanmadan analiz edilmez.
- Üç çıktı katmanı: ham arşiv, şirket başına SEC araştırma JSON/HTML, tüm şirketler için tarama JSON/CSV özeti.
- İndirme yapmadan aynı arşivi yeniden analiz eden `--offline` modu vardır.

**Dört genel şirketli örnek evren:** `ornekler/sec_tarama_evreni_4_sirket.json` (AAPL, MSFT, NVDA, JPM). Dosya özel portföy değildir.

**[Kurulum, Windows komutları, SEC verisi ve erişim sınırları](docs/SEC_TOPLU_TARAMA_V01.md).**


## SEC Finansal Değişim ve Düzeltme Gözlem Motoru v0.1

**Yeni** `sec_finansal_degisim.py`, aynı SEC CIK şirketinin **iki farklı zamanda alınmış ham SEC Company Facts arşivini**, aynı bilgi kesme tarihinde (as-of) karşılaştırır. SEC accession, form, mali dönem başı/sonu, yayımlanma tarihi ve XBRL kavramını koruyarak eklenen/kaybolan/değişen kayıtları kaynaklarıyla listeler. Bir 10-Q/A kaydını otomatik kesinleşmiş finansal restatement olarak adlandırmaz; manuel inceleme işareti verir.

Ayrıca mevcut `sec_ttm_crosscheck.py` mutabakatını kullanarak, **aynı mali dönem** için TTM değer revizyonunu gerçek dönem büyümesinden ayırır. Son SEC dosyasının karşılaştırılabilir **9 aylık YTD** verileri üzerinde gelir, EBIT, CFO, CapEx yıllık nominal USD değişimini ve faaliyet marjındaki yüzde puan farkını hesaplar. Bu sonuçlar üçüncü çeyrek tek başına büyüme veya otomatik gelecek tahmini değildir.

`sec_degisim_raporu.py`, JSON'u tamamen çevrimdışı **Türkçe HTML değişim raporuna** dönüştürür. Harici JS/CSS, ücretli hizmet veya canlı fiyat yoktur.

~~~powershell
python sec_finansal_degisim.py --old eski_companyfacts.json --new yeni_companyfacts.json --cik 320193 --as-of 2026-10-24 --out reports/degisim.json
python sec_degisim_raporu.py --report reports/degisim.json --out reports/degisim.html
~~~

**[Teknik kılavuz: olay tanımları, SEC kaynakları, dönem eşlemesi ve sınırlamalar](docs/SEC_FINANSAL_DEGISIM_V01.md).**


## INVEST_AI Ana Sayfa (Codespaces ve yerel geliştirme)

Depo kökünde `index.html` bulunuyor. Böylece terminalden `python3 -m http.server 8000` çalıştırıldığında ana adreste klasör listesi yerine **INVEST_AI araştırma merkezi** açılır.

- **Ana sayfa:** platform modülleri ve oluşturulmuş raporlara hızlı erişim.
- **Raporlarım:** `reports/` altındaki tüm HTML raporlarını otomatik tarama, isimle arama, aynı sayfada inceleme veya yeni sekmede açma.
- **Analiz çalıştır:** mevcut Python araçları için kopyalanabilir komutlar.
- **Sistem hakkında:** yöntem ve kapsam sınırları.

Site, yalnızca raporları gösteren **statik geliştirme arayüzüdür**. Hisse fiyatı indirmez, Python kodunu tarayıcıda çalıştırmaz ve bulut sunucusuna kurulmuş üretim/abonelik hizmeti değildir. Python'un standart yerel HTTP sunucusu ve tarayıcı yeterlidir. Yeni rapor oluşturulduğunda listeden **Yenile** kullanılabilir.

Codespaces terminalin meşgulse, **Terminal → Yeni Terminal** açarak yeni değişiklikleri güvenli biçimde getirebilirsin:

~~~bash
cd /workspaces/INVEST_AI
git pull --ff-only origin main
~~~

Ardından zaten çalışan 8000 bağlantı noktasındaki sayfayı yenile. Yerel değişiklikler ile Git çakışırsa çalışma dosyalarını zorla sıfırlama.

**[Ana sayfa rehberi ve kullanım adımları](docs/ANA_SAYFA_V01.md).**


## Web üzerinden doğrudan şirket araştırması — v0.2

Yeni `invest_ai_web.py` sunucusu, Codespaces veya bilgisayarda çalışan mevcut INVEST_AI araştırma motorlarını **web formundan** başlatır. Böylece site artık yalnız statik HTML rapor görüntüleyici değildir. `index.html` menüsünde şirket kodu, SEC kaynak modu ve kullanıcı tarafından doğrulanacak sektör seçilir; sonuçlar `reports/research/` içinde JSON+HTML olarak saklanır ve sitede açılır.

**Codespaces'te eski sunucuyu durdur** (çalışan terminalde `Ctrl+C`). Proje kökünde `git pull --ff-only origin main` ile güncelle, sonra:

~~~bash
python3 invest_ai_web.py
~~~

Terminalde basılan **WEB ANALİZ ANAHTARI** değerini yalnız sitedeki parola kutusuna gir. Codespaces `8000` portunu **Private** tut.

İlk kullanımda kaynak olarak **Apple örneği (internetsiz)** seç; `AAPL`, sektörü bilinmiyor veya analist tarafından teyit edilmiş `non_financial` olarak belirle. Hesaplama raporu üretir. Bu örnek 2026-10-21 tarihli manuel SEC aktarımıdır, canlı veri değildir.

Canlı SEC için gerçek iletişim e-postanla:

~~~bash
export SEC_USER_AGENT="INVEST_AI Research REAL_CONTACT@example.com"
python3 invest_ai_web.py
~~~

Web sitesinde veri kaynağı **Güncel SEC Company Facts** seç, sembol ve sektör girdilerini doldur. Sunucu resmî SEC ticker haritasından CIK çözer, ham Company Facts dosyasını SHA-256 sürümüyle arşivler ve mevcut yıllık kaynak denetimi/Piotroski/TTM motorunu çalıştırır. `cache` seçeneği önceden indirilen arşivleri ağ isteği olmadan kullanır. Eksik/çelişkili veri, tamamlanmış puan gibi gösterilmez. DCF, canlı fiyat, yeni abonelik veya al/sat önerisi üretilmez.

**[Web analiz rehberi: adım adım kurulum, güvenlik ve test](docs/WEB_SIRKET_ANALIZI_V02.md).**

