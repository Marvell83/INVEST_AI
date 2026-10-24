# Finansal Tablolar ve Oranlar v0.1

`finansal_tablolar.py` ve `finansal_oranlar.py`, SEC Company Facts verisini **tek bir ortak kurallar setiyle** okuyup yıllık gelir tablosu, nakit akışı ve bilanço üretir; bunlardan kârlılık, büyüme, nakit kalitesi, getiri ve borçluluk oranlarını hesaplar. Yol haritasındaki 2., 3., 4. ve 5. derslerin veri temelidir ([YOL_HARITASI.md](YOL_HARITASI.md)).

## Neden ayrı bir katman?

Bu katmandan önce SEC verisini okuyan beş ayrı kod vardı: `sec_companyfacts`, `sec_ttm`, `ttm_finansallar`, `piotroski_fscore`, `sec_finansal_degisim`. Her biri kendi XBRL etiket listesini ve kendi seçim kuralını kullanıyordu, toplamda da yalnız ~12 kalem okunuyordu. Özkaynak, nakit, toplam borç, faiz gideri, vergi, amortisman ve hisse sayısı hiç okunmadığı için ROIC, ROE ve faiz karşılama gibi oranlar hesaplanamıyordu.

Bu sürüm 27 raporlanan kalemi (brüt kâr bildirilmemişse türetilir) ve 2 türetilen kalemi tek yerde toplar. Mevcut motorlar şimdilik eski okuyucularını kullanmaya devam eder; ortak katmana geçiş sonraki adımlardan biridir.

## Kurallar

| Kural | Açıklama |
|---|---|
| Kaynak | Yalnız `10-K` / `10-K/A`, yalnız `USD` (hisse adedinde `shares`) |
| Bilgi tarihi | `filed` ve dönem sonu `as_of` tarihinden sonra olan kayıtlar görünmez |
| Mali yıl | Kaydın kendi `start`/`end` tarihlerinden belirlenir (330–400 gün). SEC'in `fy`/`fp` alanları **dosyaya** aittir, kayda değil; bu yüzden kullanılmaz |
| Revizyon | Aynı dönem için en son dosyalanan değer seçilir; farklı ilk değer `first_reported` alanında saklanır (`revised: true`) |
| Etiket çelişkisi | Aynı kalemin XBRL eşanlamlıları %0,5'ten fazla ayrışırsa hücre `CONFLICT` olur, değer yazılmaz, adaylar `alternatives` alanında listelenir |
| Eksik veri | `MISSING`, değer `null`; asla 0 kabul edilmez |
| Türetme | Brüt kâr (gelir − satışların maliyeti), serbest nakit akışı (CFO − CapEx) ve toplam borç yalnız **aynı SEC dosyasındaki** kayıtlardan türetilir |

Her hücre şunları taşır: `status` (`REPORTED` / `DERIVED` / `MISSING` / `CONFLICT`), `value`, `unit`, `concept`, `accession`, `form`, `filed`, `start`, `end`.

## Kalemler

- **Gelir tablosu:** gelir, satışların maliyeti, brüt kâr, Ar-Ge, faaliyet kârı, faiz gideri, vergi öncesi kâr, gelir vergisi, net kâr (ana ortaklık), seyreltilmiş ortalama hisse.
- **Nakit akışı:** faaliyet nakit akışı, CapEx, amortisman, hisse bazlı ödeme, ödenen temettü, hisse geri alımı, serbest nakit akışı†.
- **Bilanço:** nakit ve nakit benzerleri, dönen ve toplam varlıklar, kısa vadeli ve toplam yükümlülükler, ticari senet, kısa vadeli borçlanma, uzun vadeli borç (kısa vadeli kısmı ile birlikte veya ayrı), özkaynak, toplam finansal borç†.

† türetilen kalem.

**Toplam borç:** raporlanan bileşenlerin toplamıdır. `LongTermDebt` kısa vadeli kısmı zaten içerdiği için yalnız `LongTermDebtNoncurrent` yoksa kullanılır, çift sayım yapılmaz. Toplanan ve bildirilmeyen bileşenler `components` / `components_not_reported` alanlarında listelenir. Kira yükümlülükleri dahil değildir.

## Oranlar

| Grup | Oranlar |
|---|---|
| Kârlılık | brüt, faaliyet ve net kâr marjı |
| Büyüme | gelir ve faaliyet kârı büyümesi (yalnız 330–400 gün önceki mali yılla) |
| Nakit akışı | serbest nakit akışı marjı, nakit dönüşümü (CFO / net kâr), CapEx yoğunluğu, hisse bazlı ödeme / gelir, hissedarlara dağıtım / net kâr |
| Getiri | ROA, ROE, efektif vergi oranı, ROIC |
| Bilanço | cari oran, borç / özkaynak, net borç, faiz karşılama |

Her oran `formula`, kullanılan `inputs` ve hesaplanamadığında `reason` taşır. Örnekler: `INPUT_UNAVAILABLE:interest_expense`, `NONPOSITIVE_DENOMINATOR:average_equity`, `PRIOR_FISCAL_YEAR_REQUIRED`, `TAX_RATE_OUTSIDE_0%_50%`.

- **ROA / ROE / ROIC:** dönem sonu ile önceki dönem sonu bakiyelerinin ortalamasıyla hesaplanır.
- **ROIC:** `faaliyet kârı × (1 − efektif vergi) / ortalama (özkaynak + toplam borç − nakit)`. Efektif vergi %0–%50 dışındaysa ROIC hesaplanmaz. Yatırılan sermayeden yalnız nakit ve nakit benzerleri düşülür; menkul kıymetler düşülmez. Bu yüzden Apple gibi büyük menkul kıymet portföyü olan şirketlerde ROIC düşük görünebilir.
- **Negatif özkaynak:** ROE ve borç / özkaynak hesaplanmaz.

## Kullanım

Tek komutluk şirket araştırması (`sirket_arastirma_akisi.py`) ve web arayüzü raporlara bu iki bölümü kendiliğinden ekler. Bağımsız kullanım:

```bash
python finansal_oranlar.py --companyfacts CIK0000320193.json --as-of 2026-10-24 --years 5 --out reports/apple_tablolar.json
```

```python
from finansal_tablolar import build_annual_statements
from finansal_oranlar import compute_ratios
statements = build_annual_statements(raw_companyfacts, as_of="2026-10-24", years=5)
ratios = compute_ratios(statements)
```

## Sınırlar

- Yalnız yıllık 10-K. Çeyreklik tablolar ve çeyrek türetme (Q4 = FY − 9 ay) sonraki sürümdedir.
- Seçili US-GAAP kalemleri: segment verisi, kira yükümlülükleri, menkul kıymetler, azınlık payları ve şirkete özel (extension) etiketler yoktur. IFRS / 20-F desteklenmez.
- Bankalar ve sigorta şirketlerinde bu kalemler ve oranlar anlamlı olmayabilir.
- Etiket eşanlamlıları otomatik eşleşmeyi kolaylaştırır ama konsolide tablonun insan tarafından okunmasının yerini tutmaz.
- Geçmiş oranlar tahmin, puan veya yatırım tavsiyesi değildir.

## Testler

`tests/test_finansal_tablolar.py` ve `tests/test_finansal_oranlar.py` (36 test). Kapsadıkları durumlar:
- bilgi tarihi koruması, revizyon ve etiket çelişkisi,
- eksik verinin 0 sayılmaması, aynı dosya şartı, borçta çift sayım,
- 10-K içindeki çeyreklik kayıtların mali yıl sayılmaması,
- negatif özkaynak, olağan dışı vergi oranı, mali yıllar arasında boşluk,
- HTML karakter kaçışı ve Apple FY2025 demo değerleri.
