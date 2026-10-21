# INVEST_AI — Piotroski F-Score ve kredi derecelendirme katmanı v0.1

**Durum:** deneysel / araştırma. Canlı hisse fiyatları, InvestingPro hesabı, ücretli Moody's/S&P/Fitch veri lisansı veya otomatik yatırım tavsiyesi içermez.

## Katmanlar neden ayrı?

1. **Piotroski F-Score (0–9)**: ağırlıklı olarak tarihsel muhasebe eğilimi. Dokuz ölçüt için önce hesaplanabilirlik kontrolü gerekir. Özellikle Piotroski'nin orijinal çalışması, yüksek defter/piyasa oranlı şirketler evreninde uygulanmıştır. Genel piyasanın bütün şirketlerine aynı başarı sonuçlarını genelleştirmeyin.
2. **Moody's/S&P/Fitch**: uzun vadeli *ihraççı kredi* kalitesi. Tahvil geri ödeme riskinin bağımsız değerlendirmesi; hissenin ucuzluğu veya yükseliş olasılığı değildir.
3. **DCF / ters DCF**: analistin kaynaklı varsayımlarına göre gelecekteki işletme nakit akışlarının bugünkü değerini ve fiyata gömülü büyüme beklentilerini inceleyen ayrı motor.

**Bu üçü bir toplama veya tek puana dönüşmez.** Kredi notundan otomatik WACC ya da hedef hisse fiyatı hesaplanmaz.

## Piotroski'nin dokuz göstergesi

| Kod | 1 puan koşulu |
| --- | --- |
| `ROA_POSITIVE` | Dönem net kârı / dönem başı toplam varlıklar pozitif |
| `CFO_POSITIVE` | Dönem faaliyetlerden nakit akışı pozitif |
| `DELTA_ROA` | ROA önceki yıla göre yükseldi |
| `QUALITY_OF_EARNINGS` | Faaliyetlerden nakit akışı net kârdan yüksek |
| `DELTA_LEVERAGE` | Uzun vadeli borç / ortalama varlıklar azaldı; veya her iki yılda borç sıfır |
| `DELTA_LIQUIDITY` | Dönen varlıklar / kısa vadeli yükümlülükler arttı |
| `NO_EQUITY_OFFERING` | Dönem içinde yeni özsermaye ihracı olmadığının kaynaklı, tarihli analist incelemesi |
| `DELTA_GROSS_MARGIN` | Brüt kâr / gelir marjı yükseldi |
| `DELTA_ASSET_TURNOVER` | Gelir / ortalama toplam varlıklar yükseldi |

**Muhasebe sözleşmesi:** ROA paydasında *dönem başı* toplam varlıklar; devir hızı ve kaldıraç paydasında ilgili yılın dönem başı ve sonu toplam varlıklarının aritmetik ortalaması kullanılır. Önceki yıl ROA ve varlık devir hızı için bir ek açılış bilançosu gerekebilir. Aynı gelir etiketi alternatiflerinde >%5 kapsam/tutar ayrışması varsa bunlar otomatik çözülmez. Bu %5 eşik yalnız **veri kalite alarmı**dır.

**Eksik veri sıfır puan değildir:** Örneğin 8 ölçütü olumlu ama sermaye ihracı kanıtı eksikse sonuç **8/9 değil**, `score=null`, `score_range=[8,9]` ve `status=partial` olur. Eksik bir verinin yanlışlıkla "kötü" kabul edilmesini önler. 9/9 tamamlanmadan sınıflama/otomatik sıralama yapılmamalıdır.

İhraç değerlendirmesi hisse adedine bakarak otomatik yapılmaz: **hisse bölünmesi**, çalışan hisse planları, geri alımlar ve yeni ihraç farklı işlemlerdir. Kayıt `issued`, `fiscal_start`, `fiscal_end`, `reviewed_at`, `source_url` ve gerekçeli `review_note` içerir. Kod kaynak URL'sini otomatik doğrulamaz.

US-GAAP USD 10-K/10-K/A esas alınır. SEC `filed` tarihi bilgi kesme tarihinden sonra olan olgular reddedilir. Yalnız aynı mali dönem bitişi yeterli değildir; ilgili akış tablolarında `start` tarihi de eşleşmelidir. Banka/sigorta gibi finans sektörleri otomatik puanlanmaz (`sector=financial`); sektörü doğrulanmamış şirket de (`sector=unknown`) puanlanmaz. Şirketin sektör sınıflandırması manuel doğrulanır.

## Yerel kullanım: ekstra abonelik gerekmez

Python 3.11+, standart kütüphane. `sec_companyfacts.py` aynı klasörde olmalı. Varsayılan işlem **çevrimdışı**dır; dosyanın önceden indirilmiş ham SEC Company Facts JSON'u olması gerekir.

```bash
python sirket_kalite_cli.py report --companyfacts CIKXXXXXXXXXX.json --as-of 2026-10-21 --sector non_financial --out kalite_raporu.json
```

Sermaye ihracı incelemesi eklemek için `--equity-evidence equity_review.json` kullanın. Bu yapılmadığında 9. ölçüt eksik olarak kalır.

Kaynağı araştırılmış derecelendirme olayı örnek **şema** (gerçek bir şirket veya doğrulanmış not değildir):

```json
{
  "cik": 42,
  "issuer_name": "SYNTHETIC COMPANY",
  "agency": "MOODYS",
  "rating": "Aa2",
  "outlook": "stable",
  "rating_scope": "long_term_issuer",
  "effective_date": "2025-02-12",
  "published_date": "2025-02-12",
  "source_url": "https://example.org/synthetic-rating",
  "review_note": "Manually checked hypothetical long-term issuer rating source"
}
```

```bash
python sirket_kalite_cli.py rating-add --ratings-db ratings.sqlite --event issuer_rating.json
python sirket_kalite_cli.py report --companyfacts CIKXXXXXXXXXX.json --as-of 2026-10-21 --sector non_financial --ratings-db ratings.sqlite --out kalite_raporu.json
```

`rating_scope` zorunlu olarak **long_term_issuer** kabul edilir: şubeye, finansman yan kuruluşuna veya tek bir tahvile ait not, ana şirket notunun yerine konulamaz. `MOODYS`, `S&P` ve `FITCH` puan ölçekleri ayrı tutulur. Geri çekilmiş/`NR`/`WR`/`WD` gibi not statülerinde eski notun hâlâ etkin olduğu varsayılmaz. Kaynak atfı girilmesi otomatik içerik doğrulaması anlamına gelmez.

## Testler

```bash
python -m unittest discover -s tests -v
```

Yerel sürümün 23 sentetik testi geçti; GitHub kaynaklarının CI sonucunu ayrıca doğrulayın. Testler, yatırım getirisi tahmini veya Piotroski'nin gelecekteki başarısı için kanıt değildir.

## Kaynaklar ve yöntem

- Joseph D. Piotroski (2000), *Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers*, Journal of Accounting Research. DOI: https://doi.org/10.2307/2672906
- SEC Company Facts resmi API dokümantasyonu: https://www.sec.gov/search-filings/edgar-application-programming-interfaces

**Sınırlamalar:** Bu ilk sürüm IFRS/20-F normalleştirme ve bankacılık sektörü uyarlaması içermez; net kâr ve faaliyet nakit akışı etiketlerinin ekonomik muhasebe kapsamı ayrıca kontrol edilmelidir. Puan yüksek olduğu için hisse ucuz sayılmaz. Rating ajansları arasındaki yatırım yapılabilir not grubu işaretlemesi varsayımsal sınıflamadır, borç ödemesinin garantisi değildir.
