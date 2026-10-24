# Finansal Tablolar ve Oranlar (tablolar v0.2 · oranlar v0.1)

`finansal_tablolar.py` ve `finansal_oranlar.py`, SEC Company Facts verisini **tek bir ortak kurallar setiyle** okuyup yıllık ve çeyreklik gelir tablosu, nakit akışı ve bilanço üretir; yıllık tablolardan kârlılık, büyüme, nakit kalitesi, getiri ve borçluluk oranlarını hesaplar. Yol haritasındaki 2., 3., 4. ve 5. derslerin veri temelidir ([YOL_HARITASI.md](YOL_HARITASI.md)).

## Neden ayrı bir katman?

Bu katmandan önce SEC verisini okuyan beş ayrı kod vardı: `sec_companyfacts`, `sec_ttm`, `ttm_finansallar`, `piotroski_fscore`, `sec_finansal_degisim`. Her biri kendi XBRL etiket listesini ve kendi seçim kuralını kullanıyordu, toplamda da yalnız ~12 kalem okunuyordu. Özkaynak, nakit, toplam borç, faiz gideri, vergi, amortisman ve hisse sayısı hiç okunmadığı için ROIC, ROE ve faiz karşılama gibi oranlar hesaplanamıyordu.

Bu sürüm 27 raporlanan kalemi (brüt kâr bildirilmemişse türetilir) ve 2 türetilen kalemi tek yerde toplar. Mevcut motorlar şimdilik eski okuyucularını kullanmaya devam eder; ortak katmana geçiş sonraki adımlardan biridir.

## Kurallar

| Kural | Açıklama |
|---|---|
| Kaynak | Yıllık tablolar `10-K` / `10-K/A`; çeyreklik tablolar `10-Q` / `10-Q/A` ve 4. çeyrek için `10-K`. Yalnız `USD` (hisse adedinde `shares`) |
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

## Çeyreklik tablolar (v0.2)

`build_quarterly_statements(raw, as_of=..., quarters=8)` en son çeyrekten geriye doğru ayrık mali çeyrekleri döndürür.

- **Çeyrek takvimi:** Mali yıllar 10-K'lardan, çeyrek sınırları mali yıl başında başlayan 3, 6 ve 9 aylık birikimli (YTD) kayıtlardan bulunur. Son 10-K'dan sonra devam eden mali yıl da listelenir; `fiscal_year_end` alanı `null` olur. Başlangıcı veya bitişi bilinmeyen çeyrek listelenmez.
- **Etiket:** `MY2025 Ç2` biçimindedir. MY, mali yılın bittiği takvim yılıdır; Apple'ın Ekim 2025'te başlayan yılı MY2026'dır.
- **Gelir tablosu ve nakit akışı kalemleri:**
  - Bildirilmiş 3 aylık değer varsa o kullanılır (`REPORTED`).
  - Yoksa aynı XBRL kavramının iki YTD değerinin farkı alınır (`DERIVED`, `YTD_DIFFERENCE`). 4. çeyrek = yıllık 10-K − 9 aylık 10-Q (`ANNUAL_MINUS_NINE_MONTHS`).
  - Türetilen hücre her iki SEC dosyasını `sources` alanında taşır. İki YTD değeri farklı kavramlarla bildirilmişse fark alınmaz (`YTD_CONCEPTS_DIFFER`).
  - Şirketler nakit akışını 10-Q'larda çoğunlukla yalnız YTD olarak bildirdiği için bu kalemler genellikle türetilmiştir.
- **Ortalama hisse sayısı:** Ağırlıklı ortalama olduğu için toplanamaz; YTD farkı alınmaz (`NON_ADDITIVE_NOT_DERIVED`).
- **Bilanço:** Çeyrek sonundaki bildirilmiş değerdir.
- **Brüt kâr ve serbest nakit akışı:** Yalnız iki girdi aynı SEC dosya(lar)ına dayanıyorsa türetilir.

**Doğrulama:** Son dört çeyreğin toplamı, mevcut `sec_ttm.py` motorunun "FY + güncel YTD − önceki YTD" TTM sonucuyla birebir eşleşir. Bu eşleşme testlerle sınanır ve ileride TTM motorlarının ortak katmana taşınmasının temelini oluşturur.

## Dolaşımdaki hisse sayısı

`shares_outstanding(raw, as_of=...)`, 10-K / 10-Q kapak sayfasındaki `dei:EntityCommonStockSharesOutstanding` değerini döndürür. Bilgi tarihine kadar en son dosyalanan değer seçilir ve kapak sayfasındaki tarihi taşır; bu tarih genellikle dönem sonundan birkaç hafta sonradır.

Birden fazla hisse sınıfı olan şirketler (ör. A/B/C sınıfı) aynı dosyada birden fazla değer bildirebilir. Bu durumda değerler toplanmaz ve aralarından seçim yapılmaz; sonuç `CONFLICT` olur. Yıllık ve çeyreklik çıktıların ikisinde de `shares_outstanding` alanı bulunur.

## Katman mutabakatı

Piotroski ve iki TTM motoru SEC verisini hâlâ kendi kurallarıyla okur. `katman_mutabakati.py` her araştırma raporunda bu motorların kullandığı rakamları ortak katmanla karşılaştırır ve raporda "Katman mutabakatı" bölümünde gösterir. Hiçbir motorun sonucunu değiştirmez.

| Kontrol | Nasıl karşılaştırılır | Dikkat gerektiren durum |
|---|---|---|
| Piotroski girdileri ↔ yıllık tablolar | Piotroski'nin kullandığı her SEC kaydı (net kâr, CFO, gelir, brüt kâr, varlıklar, borç, dönen varlık ve yükümlülükler) aynı yılın ortak hücresiyle birebir | `VALUE_DIFFERS` (tutar farklı), `SHARED_CONFLICT` (Piotroski bir değer kullandı, ortak katman etiket çelişkisi gördü) |
| TTM ↔ son dört çeyrek | Mutabık TTM, TTM bitişinde sona eren art arda dört ortak çeyreğin toplamıyla | %0,1'i aşan fark (`VALUE_DIFFERS`); %0,1'e kadarki fark yuvarlama sayılır (`ROUNDING`) |

Dikkat gerektiren bir fark araştırma raporunun açık eksiklerine eklenir:
- `SHARED_STATEMENTS_DIFFER_FROM_PIOTROSKI_INPUTS`
- `SHARED_QUARTERS_DIFFER_FROM_TTM`

Bilinen kural farkı: Piotroski gelir etiketleri arasında **%5'e kadar** farkı kabul eder, ortak katman **%0,5'te** durur. Bu yüzden etiketleri %0,5–%5 arası ayrışan şirketlerde Piotroski girdisi `SHARED_CONFLICT` olarak işaretlenir. Piotroski'nin ortak katmana taşınması bu eşiğin hangisinde birleşeceğine bağlıdır ([YOL_HARITASI.md](YOL_HARITASI.md)).

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

Tek komutluk şirket araştırması (`sirket_arastirma_akisi.py`) ve web arayüzü raporlara yıllık tablolar, oranlar ve son 8 çeyrek bölümlerini kendiliğinden ekler. Bağımsız kullanım:

```bash
python finansal_oranlar.py --companyfacts CIK0000320193.json --as-of 2026-10-24 --years 5 --out reports/apple_tablolar.json
```

```python
from finansal_tablolar import build_annual_statements, build_quarterly_statements
from finansal_oranlar import compute_ratios
statements = build_annual_statements(raw_companyfacts, as_of="2026-10-24", years=5)
ratios = compute_ratios(statements)
quarters = build_quarterly_statements(raw_companyfacts, as_of="2026-10-24", quarters=8)
```

## Sınırlar

- Oranlar şimdilik yalnız yıllık tablolardan hesaplanır; çeyreklik ve TTM oranları sonraki adımdadır.
- Ara dönemde mali yıl değiştiren şirketlerde çeyrek takvimi kurulamayabilir; o çeyrekler listelenmez.
- Seçili US-GAAP kalemleri: segment verisi, kira yükümlülükleri, menkul kıymetler, azınlık payları ve şirkete özel (extension) etiketler yoktur. IFRS / 20-F desteklenmez.
- Bankalar ve sigorta şirketlerinde bu kalemler ve oranlar anlamlı olmayabilir.
- Etiket eşanlamlıları otomatik eşleşmeyi kolaylaştırır ama konsolide tablonun insan tarafından okunmasının yerini tutmaz.
- Geçmiş oranlar tahmin, puan veya yatırım tavsiyesi değildir.

## Testler

`tests/test_finansal_tablolar.py`, `tests/test_finansal_oranlar.py` (36 test) ve `tests/test_finansal_ceyrekler.py` (23 test). Çeyrek testleri şunları kapsar:
- çeyrek takvimi ve devam eden mali yıl,
- doğrudan 3 aylık değer önceliği, YTD farkı ve 4. çeyrek,
- farklı kavramların ve ortalama hisse sayısının farkının alınmaması,
- `sec_ttm` ile TTM eşleşmesi, hisse sınıfı çelişkisi,
- HTML karakter kaçışı.

Yıllık katman testlerinin kapsadığı durumlar:
- bilgi tarihi koruması, revizyon ve etiket çelişkisi,
- eksik verinin 0 sayılmaması, aynı dosya şartı, borçta çift sayım,
- 10-K içindeki çeyreklik kayıtların mali yıl sayılmaması,
- negatif özkaynak, olağan dışı vergi oranı, mali yıllar arasında boşluk,
- HTML karakter kaçışı ve Apple FY2025 demo değerleri.
