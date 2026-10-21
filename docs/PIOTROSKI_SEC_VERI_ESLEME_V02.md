# INVEST_AI — Piotroski SEC veri eşleştirmesi v0.2

**Durum:** deneysel muhasebe veri kalite kontrolü; yatırım tavsiyesi veya şirket değerleme onayı değil.  
**Yerel arşiv:** `SEC_GENIS_KISIM_0001.zip`, 117 ayrı SEC Company Facts JSON kaydı  
**Bilgi kesme tarihi:** 2026-10-20  
**Kapsam sayımı için sektör kabulü:** `non_financial` (117 şirketin gerçekten finans dışı olduğu doğrulanmış değildir).

## Neden değişti?

v0.1 Piotroski motoru iki önemli boşluk bırakıyordu:

1. US-GAAP `GrossProfit` etiketi olmayan şirketleri başka veri yokmuş gibi değerlendiriyordu.
2. `LongTermDebt` ve `LongTermDebtNoncurrent` etiketlerini alternatif ve eşdeğer sayıyordu. Oysa `LongTermDebt` **kısa vadede ödenecek kısmı da içerebilir**. Bu iki değer doğrudan karşılaştırılamaz.

v0.2, mevcut dokuz Piotroski ölçütünü değiştirmeden finansal veri seçiminde daha sıkı mutabakat uygular.

## Brüt kâr türetme

Önce doğrudan raporlanan `GrossProfit` denenir. Yoksa:
- `RevenueFromContractWithCustomerExcludingAssessedTax` gibi daha önce çelişkisiz seçilmiş SEC gelir etiketinin kaydı esas alınır.
- `CostOfGoodsAndServicesSold`, `CostOfRevenue` veya `CostOfGoodsSold` adayları **aynı mali dönem başlangıcı, bitişi ve accession (SEC filing) numarasıyla** aranır.
- Birden fazla maliyet etiketi varsa tutarlar arasında **%0,5'ten fazla** farkta hesaplama reddedilir. Bu eşik analitik güvenlik parametresidir, muhasebe standardı değildir.
- Eşleşirse `brüt kâr = gelir - maliyet` üretilir; hem gelir hem maliyet orijinal kaynakları `provenance.*.derivation` alanında korunur.
- Negatif maliyet veya pozitif olmayan gelir otomatik olarak yorumlanmaz. Kaynak uyumu, tüm alt kırılımların aynı konsolidasyon kapsamına ait olduğunu **garanti etmez**.

## Uzun vadeli borcun kısa vadeli olmayan kısmı

Önce `LongTermDebtNoncurrent` doğrudan aranır. Yoksa, aynı SEC belgesindeki:

`LongTermDebt - LongTermDebtCurrent`

hesaplanabilir. Her iki kalem aynı bilanço tarihi, USD birimi ve SEC accession numarasına sahip olmalıdır. Kısa vadeli kısım **yoksa sıfır sayılmaz**. Kısa vadeli tutarın negatif ya da toplamdan büyük olması reddedilir.

Doğrudan noncurrent veri ile türetilen rakam aynı belgede mevcutsa ve fark **%0,5'i aşıyorsa**, borç göstergesi `UNKNOWN` olur. Aynı veri döneminde birden fazla farklı maliyet kapsamı veya borç tanımı olabileceği için insan incelemesi gerekebilir.

## 117 şirketlik geriye dönük kapsam karşılaştırması

| Piotroski ölçütü | Eski bilinmeyen | Yeni bilinmeyen | Güvenle hesaplanabilir hale gelen | Eski hesap reddedilen |
| --- | ---: | ---: | ---: | ---: |
| `DELTA_GROSS_MARGIN` | 61 | **40** | 21 | 0 |
| `DELTA_LEVERAGE` | 66 | **60** | 20 | **14** |

`DELTA_LEVERAGE` için net iyileşme +6 şirket olmasına rağmen 20 dosya yeniden hesaplanabilir hale geldi ve **14 önceki hesap olası kapsam/etiket hatası nedeniyle bloke edildi**. Yani 66 − 20 + 14 = 60. Bu davranış hatalı kesinlik üretmekten daha güvenlidir.

Buradaki `known` ifadesi, ham SEC verisinin tanımlı aritmetiğe girebildiğini gösterir. Şirketin borç kalemlerinin dipnotla teyit edildiği anlamına gelmez. SEC arşivi, önceki/sonraki yayım düzeltmeleri yüzünden `as_of` alanı ile filtrelenir.

## Puanın yorumlanması

- Eksik / çelişkili veri **0 puan** sayılmaz; `signals.X=None` kalır.
- Dokuz göstergeden biri bilinmiyorsa `score=None`, `score_range=[min,max]` çıkar.
- Sermaye ihracı için kayıtlı, tarihli insan incelemesi hâlâ zorunludur.
- Banka/sigorta gibi şirketlerde özgün Piotroski şeması otomatik uygulanmaz.
- Moody's, Fitch, S&P kredi notları Piotroski puanına veya tek bir indirim oranına çevrilmez.
- TSMC gibi 20-F / IFRS bildiren ihraççılar bu US-GAAP 10-K modülünün **dışındadır**.

## Yerel test

```bash
python -m unittest discover -s tests -v
```

Yeni regression testleri özellikle aynı bildirim zorunluluğu, sonradan yayımlanmış olguların geçmişe sızmaması, maliyet etiket çelişkisi, eksik kısa vadeli borç, bilanço borç mutabakat farkı ve döviz birimi hatalarını kapsar.

Yerel geliştirme kopyasında önceki 23 test + yeni 27 kontrol = **50/50** başarılı. GitHub Actions'ta aynı kodun son uçtan uca testi doğrulanmadığından CI'yi geçmiş saymayın.

## Referans

- FASB XBRL Revenue Implementation Guidance: https://xbrl.fasb.org/impguidance/Rev2_TIG/Revenue.htm
- XBRL US `LongTermDebt` tanımı (current + noncurrent): https://www.xbrlsite.com/LinkedData/GetObjectInfo_HTML.aspx?name=us-gaap%3ALongTermDebt
- Piotroski (2000), DOI: https://doi.org/10.2307/2672906
