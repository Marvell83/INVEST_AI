# INVEST_AI — TTM Finansal Motoru v0.1

**Geliştirme:** 23 Ekim 2026 · **Örnek araştırma kesiti:** 21 Ekim 2026  
**Bağımlılık:** Python 3.11+, standart kütüphane; DCF köprüsü için depodaki `degerleme_v02.py` ve `dogrulama/moduller_v02.py`. Ücretli hizmet veya abonelik gerektirmez.

## Amaç ve hesaplama

TTM (son 12 ay), **FY2025 + 2026 ilk dokuz ay − 2025 ilk dokuz ay** formülüyle hesaplanır. Şirketin mali yılı aralıkta bitmek zorunda değildir. Güncel ara dönem ile eski tam mali yılın ve karşılaştırmalı dokuz ayın başlama/bitiş tarihleri aynı şirket ve döneme ait olmalıdır.

`ttm_finansallar.calculate_ttm(raw_companyfacts, as_of="2026-10-21")`:
- 10-K/10-K/A FY tam yıl, 10-Q/10-Q/A Q3 **dokuz aylık YTD** verileri alır. Üç aylık tek Q3 verisini dokuz aylık kabul etmez.
- Yalnız **US-GAAP/USD**, pozitif olmayan veya eksik CapEx kurallarını açıkça denetler, farklı birimden kur tahmini yapmaz.
- Bütün hesapları gerçek USD cinsinden yapar; tablo birimi milyar USD olsa bile model girdisinde milyon/milyar çarpanı karıştırılmaz.
- Yalnız bilgi kesme tarihinden önce **dosyalanmış** kayıtları kullanır. Daha sonra yayımlanan 10-K/A ancak o tarihten sonra geçerli olur.
- Birden fazla alternatif gelir etiketi %0,5'ten fazla ayrışırsa veya gelir etiketi dönemler arasında değişirse otomatik seçimi durdurur. Bu eşik muhasebe standardı değil güvenlik filtresidir.
- Kaynak tanımı, `accession` numarası, açıklanma tarihi ve mali dönemleri her metriğin üç ayrı girişinde korur.
- Eksik kalemleri sıfır saymaz, ilgili ölçümü `null` ile işaretler. Bütün temel kalemler yoksa deneysel DCF köprüsü çalışmaz.
- `CFO - CapEx` gösterimini **FCFF diye adlandırmaz**.

## Apple'ın gerçek SEC tablosu (manuel aktarım)

`ornekler/apple_ttm_evidence_2026-10-21.json`, Apple'ın resmî SEC 10-K/10-Q toplam satırlarından **elle aktarılarak oluşturulmuş, Company Facts uyumlu demonstrasyon dosyasıdır**. Ham API indirmesi veya SEC'nin otomatik olarak doğruladığı JSON değildir. Bunu gerçek ham veriden ayırt eden `evidence_notes.status` kaydı bilinçli olarak korunmuştur.

| Kalem (milyar USD) | 2025 mali yıl | 2026 9 ay | 2025 9 ay | TTM |
| --- | ---: | ---: | ---: | ---: |
| Gelir | 416,161 | 364,357 | 313,695 | **466,823** |
| Faaliyet kârı (EBIT) | 133,050 | 122,432 | 100,623 | **154,859** |
| Brüt kâr | 195,201 | 178,782 | 146,860 | **227,123** |
| Net kâr | 112,010 | 101,464 | 84,544 | **128,930** |
| Faaliyet nakit akışı | 111,482 | 116,996 | 81,754 | **146,724** |
| CapEx (nakit harcaması + işaretiyle) | 12,715 | 6,799 | 9,473 | **10,041** |

TTM faaliyet kâr marjı **%33,17**; CFO−CapEx yaklaşık **136,683 milyar USD** olup **FCFF değildir**.

Kaynaklar: [2025 Form 10-K, accession 0000320193-25-000079](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm) (31 Ekim 2025); [2026 Q3 Form 10-Q, accession 0000320193-26-000020](https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm) (31 Temmuz 2026).

## Eski ve TTM bazlı deneysel Apple DCF

TTM köprüsü `ttm_dcf_bridge.py` mevcut Apple stres senaryolarındaki büyüme, marj, sermaye verimliliği, vergi ve iskonto varsayımlarını değiştirmez. Yalnız geçmiş yılın gelir/EBIT tabanını TTM ile günceller; bilgilerin CIK, `accession`, tarihler ve mali yıl bazında mutabakatını zorunlu tutar.

| Senaryo | Eski yıllık FY2025 baz | Yeni TTM baz |
| --- | ---: | ---: |
| Temkinli | 71,83 USD/hisse | **80,88 USD/hisse** |
| Baz | 132,61 USD/hisse | **149,46 USD/hisse** |
| İyimser | 242,28 USD/hisse | **273,18 USD/hisse** |

20 Ekim 2026 kapanışına ait 339,50 USD fiyat ve diğer baz varsayımlar sabitken ters DCF büyümesi **%34,53'ten %30,94'e** değişir. Bunlar **varsayımsal stres testi sonuçlarıdır, hedef fiyat veya piyasa konsensüsü değildir**. Ters DCF algoritması bütün kökleri bulma garantisi vermez.

Önemli tarih ayrımı: TTM finansallar 27 Haziran 2026'da; bilanço aynı gün; hisse sayısı 17 Temmuz 2026'da; örnek piyasa fiyatı 20 Ekim 2026'da ölçülmüştür. Dolayısıyla piyasa-veri tarihleri tamamen eş zamanlı değildir. FY2026 tamamlanmış olsa da kesit tarihinde FY2026 10-K verisi henüz yer almamaktadır. Nakit ve bütün menkul kıymetleri fazla nakit kabul etmek ayrı **model varsayımıdır**.

## Windows'ta kullanım

Depo kökünden:

```bash
python ttm_finansallar.py --companyfacts ornekler/apple_ttm_evidence_2026-10-21.json --as-of 2026-10-21 --out apple_ttm.json
python ttm_dcf_bridge.py --ttm apple_ttm.json --scenarios ornekler/apple_ttm_dcf_assumptions_2026-10-21.json --out apple_ttm_dcf.json
python ttm_raporu.py --ttm apple_ttm.json --dcf apple_ttm_dcf.json --out apple_ttm.html
python -m unittest discover -s tests -v
```

`apple_ttm.html` internet gerektirmeyen, statik ve HTML kaçışlı Türkçe araştırma ekranıdır. Kaynaklı DCF yoksa yalnız `--ttm` kullanılır. SEC ham Company Facts dosyası ayrıca `sec_companyfacts.py` ile güncel SEC erişim kurallarına uyarak elde edilebilir; bu sürüm otomatik ağ indirmesi yapmaz.

## Sınırlamalar ve test

- İlk sürüm **Q3 dokuz aylık** TTM üretir; Q1/Q2 üç/altı aylık TTM kapsam dışı; 53 haftalık mali takvim farklılıkları ayrıca sınanmalıdır.
- IFRS/20-F kapsamı yoktur. TSMC gibi şirketler için henüz kullanmayın.
- `--as-of` bilgi kesme filtresi, yerel arşivde o gün mevcut bütün SEC verilerinin bulunduğunu kanıtlamaz.
- FCFF, ROIC, SBC sulandırma, terminal RONIC ve vergi modelleme kısıtları hâlâ sürüyor.
- Yerel çalışmada **39 TTM/DCF/HTML testi** geçti. GitHub üzerinde aynı revizyonun CI sonucu ayrıca doğrulanmalıdır; muhasebe aritmetiği testleri gelecekte hisse getirisi doğruluğu kanıtı değildir.
