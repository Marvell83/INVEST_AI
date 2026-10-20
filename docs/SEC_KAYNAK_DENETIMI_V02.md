# SEC kaynak güvenilirliği ve v0.2 tahmin kaydı

**İlk çevrimdışı örneklem tarihi:** 2026-10-20 · **Kapsam:** 117 yerel SEC Company Facts JSON kaydı. Bu bir canlı internet taraması veya şirket değerleme doğruluğu testi değildir.

## Sıkı kaynak denetiminin bulgusu

| Sınıf | Şirket |
| --- | ---: |
| Hazır: `READY_FOR_MANUAL_ASSUMPTIONS` | 86 |
| `REVENUE_ALIASES_CONFLICT` | 7 |
| `LATEST_EBIT_MISSING` | 13 |
| `NO_ELIGIBLE_USGAAP_ANNUAL_FACTS` | 8 |
| `LATEST_REVENUE_AND_EBIT_MISSING` | 1 |
| `LATEST_REVENUE_MISSING` | 1 |
| `NONPOSITIVE_REVENUE_BASELINE` | 1 |
| **Toplam** | **117** |

Önceki basit eşleşme 92/117 idi. Sıkı denetimde bu 92 şirketten 6'sı aynı mali yıl için farklı SEC gelir etiketlerinden belirgin şekilde farklı tutarlar verdiği için ayrıca beklemeye alınır. Kalan ilk 25'in birinde (Flowserve) de gelir etiketleri uyuşmazlığı vardır. Dolayısıyla toplam **31** şirkette manuel inceleme gerekir. 86 rakamı sadece bir **ön koşul** kontrolünü geçenleri gösterir; satışların konsolide kapsamı, EBIT'in ekonomik düzeltilmesi veya hisse değerinin doğruluğu onaylanmış değildir.

Çelişki eşiği: aynı mali yıl sonundaki iki veya daha fazla alternatif yıllık gelir etiketinin en büyük ve en küçük değerleri arasındaki fark / en yüksek mutlak tutar > %5. Bu *manuel inceleme eşiği*dir; US-GAAP muhasebe standardı değildir. Değerler farklı kırılım ve kapsamları yansıtabilir; en büyük veya en yeni tutar otomatik doğru sayılmaz.

## İnceleme gerektiren şirketler

| SEC CIK | Şirket | Durum |
| --- | --- | --- |
| 0000001750 | AAR CORP | LATEST_EBIT_MISSING |
| 0000002230 | (ad yok) | NO_ELIGIBLE_USGAAP_ANNUAL_FACTS |
| 0000002809 | AGNICO EAGLE MINES LIMITED | NO_ELIGIBLE_USGAAP_ANNUAL_FACTS |
| 0000004457 | U-Haul Holding Company | REVENUE_ALIASES_CONFLICT |
| 0000005094 | (ad yok) | NO_ELIGIBLE_USGAAP_ANNUAL_FACTS |
| 0000007084 | Archer-Daniels-Midland Co | LATEST_EBIT_MISSING |
| 0000007323 | ENTERGY CORPORATION | NO_ELIGIBLE_USGAAP_ANNUAL_FACTS |
| 0000008670 | Automatic Data Processing, Inc. | LATEST_EBIT_MISSING |
| 0000008818 | AVERY DENNISON CORPORATION | LATEST_EBIT_MISSING |
| 0000009389 | BALL CORPORATION | LATEST_EBIT_MISSING |
| 0000009521 | (ad yok) | NO_ELIGIBLE_USGAAP_ANNUAL_FACTS |
| 0000012659 | H&R BLOCK INC | LATEST_EBIT_MISSING |
| 0000014272 | BRISTOL-MYERS SQUIBB COMPANY | LATEST_EBIT_MISSING |
| 0000014693 | BROWN FORMAN CORP | REVENUE_ALIASES_CONFLICT |
| 0000015615 | MASTEC INC | LATEST_EBIT_MISSING |
| 0000016868 | CANADIAN NATIONAL RAILWAY CO | NO_ELIGIBLE_USGAAP_ANNUAL_FACTS |
| 0000016875 | CANADIAN PACIFIC KANSAS CITY LTD/CN | NO_ELIGIBLE_USGAAP_ANNUAL_FACTS |
| 0000016918 | CONSTELLATION BRANDS, INC. | REVENUE_ALIASES_CONFLICT |
| 0000017313 | Capital Southwest Corporation | LATEST_REVENUE_AND_EBIT_MISSING |
| 0000018926 | LUMEN TECHNOLOGIES, INC. | REVENUE_ALIASES_CONFLICT |
| 0000021076 | The Clorox Company | LATEST_EBIT_MISSING |
| 0000022444 | Commercial Metals Company | LATEST_EBIT_MISSING |
| 0000024545 | Molson Coors Beverage Company | REVENUE_ALIASES_CONFLICT |
| 0000027093 | U.S. GOLD CORP. | LATEST_REVENUE_MISSING |
| 0000030554 | EIDP, INC. | LATEST_EBIT_MISSING |
| 0000030625 | FLOWSERVE CORP | REVENUE_ALIASES_CONFLICT |
| 0000031667 | EDUCATIONAL DEVELOPMENT CORPORATION | LATEST_EBIT_MISSING |
| 0000032604 | EMERSON ELECTRIC CO. | LATEST_EBIT_MISSING |
| 0000033533 | ESPEY MFG. & ELECTRONICS CORP. | REVENUE_ALIASES_CONFLICT |
| 0000033934 | CORNERSTONE TOTAL RETURN FUND INC | NO_ELIGIBLE_USGAAP_ANNUAL_FACTS |
| 0000034956 | TENAX THERAPEUTICS, INC. | NONPOSITIVE_REVENUE_BASELINE |

## Çalıştırma (yalnızca Python standart kütüphanesi)

```bash
python sec_gap_audit.py --archive SEC_GENIS_KISIM_0001.zip --as-of 2026-10-20 --csv gap_report.csv --json gap_report.json
python -m unittest discover -s tests -v
```

ZIP arşivi depoda **bulunmaz**. Komutun beklediği format `ham_SEC/companyfacts/CIKXXXXXXXXXX.json.gz` yollarıdır. SEC Company Facts kaynağı: https://data.sec.gov/api/xbrl/companyfacts/CIK0000001800.json (CIK örneği). İndirmelerde güncel SEC erişim kurallarına uyulmalı; kişisel iletişim bilgisi içeren User-Agent gereklidir.

## SEC → DCF → Tahmin Defteri

`sec_reviewed_pipeline.py`, ham SEC verisini **önce** `audit_company()` ile kontrol eder. Yalnız `READY_FOR_MANUAL_ASSUMPTIONS` olan girdiler `sec_v02_bridge.value_sec_snapshot()` ve v0.2 deneyselli DCF motoruna aktarılır. Analistin kaynaklı, manuel büyüme/marj/iskonto/net borç/hisse sayısı girdileri zorunludur; InvestingPro fiyat verisi veya hesaplanan piyasa değeri yoktur.

`sec_reviewed_cli.py` örneği:

```bash
python sec_reviewed_cli.py --companyfacts CIK0000000042.json --as-of 2025-03-01 --proposal assumptions.json --fy-ends fy_end_dates.json --db forecast.sqlite --out result.json
```

Örnek `fy_end_dates.json` (3 yıllık sentetik yıl sonu takvimi): `["2025-12-31", "2026-12-31", "2027-12-31"]`. Gerçek şirketin mali yılı Aralık'ta bitmiyorsa **ilgili şirketin tahmin edilen gerçek mali yıl sonlarını** girin; kod otomatik 31 Aralık varsaymaz.

Analiz başına modelin her yıl için **gelir, EBIT ve FCFF** tahminleri, CIK, `FY_END:YYYY-MM-DD` dönemi, US dolar birimi, model versiyonu, SEC accession numaraları ve analist varsayımlarıyla SQLite'a kaydedilir. İşlemin ortasında hata çıkarsa veritabanı işlemi geri alınır. Aynı tahmin kaydını ikinci kez eklemek SHA-256 içerik benzersizliğiyle engellenir.

### Ekonomik ve veri sınırlamaları

- Ön incelemeyi geçmiş tarihsel SEC etiketleri dahi yanlış konsolide kapsamı temsil edebilir; 10-K dipnotlarıyla teyit gereklidir.
- Geliri olmayan şirketlerde bu DCF modeli çalıştırılmaz; ayrı biyoteknoloji/opsiyon bazlı yaklaşım gerekebilir.
- IFRS ve özel şirket etiketleri otomatik normalize edilmez. EBIT yoksa vergi öncesi kâr, EBITDA veya faaliyet dışı gelir sessizce kullanılmaz.
- **CFO - CapEx, FCFF değildir.** Tahmin Defteri'ndeki FCFF gerçekleşmeleri bu fark üzerinden otomatik puanlanmamalıdır.
- `as_of` bilgi kesme tarihidir, analizin fiilen yapıldığı tarih değildir. Geriye dönük oluşturulan tahminler geçmişte gerçekten yapılmış bir tahmin olarak puanlanamaz.
- Nominal para birimi/birim ve hisse sayısı uyumlu olmalı. Mali tablolardaki 1 USD ile 1 milyon USD asla karıştırılmamalıdır.
- 0.2 motoru deneysel: sabit iskonto, basitleştirilmiş vergi zararları, marj yakınsamasının büyümeye nedensel bağı bulunmaması, SBC ve terminal sermaye getirisi sınırlamaları devam eder.

**Doğrulama notu:** 38 yerel birim testi, bir yerel `TahminDefteri` arayüz adaptörüyle çalıştırılmıştır. Gerçek GitHub `tahmin_defteri.py` ile tümleşik GitHub Actions sonucu ayrıca teyit edilmelidir. Gelecekteki ekonomik başarı için doğrulama sağlamaz.
