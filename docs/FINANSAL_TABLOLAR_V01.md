# Finansal Tablolar ve Oranlar (tablolar v0.5 · oranlar v0.1)

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
| Etiket çelişkisi | Aynı kalemin XBRL eşanlamlıları %0,5'ten fazla ayrışırsa hücre `CONFLICT` olur, değer yazılmaz, adaylar `alternatives` alanında listelenir. **Gelir için** sınır %5'tir (aşağıya bakın) |
| Gelir etiketleri | Gelir etiketleri tanım gereği farklı kapsamda olabilir (ör. Walmart: net satışlar ile üyelik gelirini de içeren toplam gelir). %0,5–%5 arası farkta **öncelikli etiket** kullanılır, hücre `REPORTED` kalır ve fark `alias_gap` alanında (oran, diğer etiketler ve değerleri) görünür kalır. %5'ten büyük fark `CONFLICT`'tir. Piotroski aynı kuralı uygular |
| Eksik veri | `MISSING`, değer `null`; asla 0 kabul edilmez |
| Türetme | Brüt kâr (gelir − satışların maliyeti) ve serbest nakit akışı (CFO − CapEx) yalnız **aynı SEC dosyasındaki** kayıtlardan türetilir. Bilanço toplamları (toplam borç, menkul kıymetler, kira) de aynı dosyayı tercih eder; bir sonraki 10-K önceki yılın satırlarından yalnız bazılarını tekrar ettiği için, **hiçbir parçası sonradan revize edilmemişse** farklı dosyalardaki parçalar da toplanır (`..._UNREVISED_ACROSS_FILINGS`, `sources`). Revize edilmiş bir parça varsa toplam yapılmaz (`revised_components`) |
| Yaklaşık faaliyet kârı | Şirket `OperatingIncomeLoss` bildirmemişse (ör. J&J, Exxon) faaliyet kârı = vergi öncesi kâr + faiz gideri, aynı SEC dosyasından. Hücre `DERIVED`, `approximate: true`, yöntem `EBIT_PROXY_PRETAX_PLUS_INTEREST`. Faiz geliri, özkaynak yöntemi sonuçları ve diğer faaliyet dışı kalemleri içerir. Raporda ≈ ile gösterilir. Girdiler yoksa veya farklı dosyalardansa hücre `MISSING` kalır ve `proxy_unavailable` nedeni taşır Yalnız `non_financial` sektörde kullanılır: bankada faiz gideri asıl faaliyetin parçasıdır, `financial` ve `unknown` sektörde hücre `EBIT_PROXY_DISABLED_FOR_SECTOR` nedeniyle `MISSING` kalır |
| Yedek etiket | Bir kalemin hiçbir eşanlamlısı o dönem için bildirilmemişse daha geniş kapsamlı yedek etiket okunur; hücre `fallback_concept: true` taşır ve raporda notla gösterilir. Asıl etiket bildirilmişse yedek etikete bakılmaz. CapEx: `PaymentsToAcquireProductiveAssets` (Nvidia, Amazon; maddi olmayan duran varlık alımlarını da içerebilir). Nakit: `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents` (P&G; kısıtlı nakdi de içerebilir). Özkaynak: `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` (azınlık paylarını da içerir) |

Her hücre şunları taşır: `status` (`REPORTED` / `DERIVED` / `MISSING` / `CONFLICT`), `value`, `unit`, `concept`, `accession`, `form`, `filed`, `start`, `end`.

Yıllık ve çeyreklik çıktılarda ayrıca `conflicts`, `alias_gaps` (öncelikli etiketle kabul edilen gelir farkları), `approximations` (yaklaşık değerler) ve `fallback_concepts` (yedek etiketten okunan hücreler) listeleri ile `ebit_proxy` (yaklaşık faaliyet kârına izin verildi mi) alanı bulunur. Kütüphane fonksiyonlarında `ebit_proxy` varsayılanı `True`'dur; araştırma raporu, web ve toplu tarama bunu analistin girdiği sektöre göre belirler.

## Kalemler

- **Gelir tablosu:** gelir, satışların maliyeti, brüt kâr, Ar-Ge, faaliyet kârı, faiz gideri, vergi öncesi kâr, gelir vergisi, net kâr (ana ortaklık), seyreltilmiş ortalama hisse.
- **Nakit akışı:** faaliyet nakit akışı, CapEx, amortisman, hisse bazlı ödeme, ödenen temettü, hisse geri alımı, serbest nakit akışı†.
  - Hisse bazlı ödeme yalnız nakit akışı tablosundaki `ShareBasedCompensation` kaydından okunur. `AllocatedShareBasedCompensationExpense` farklı bir kavramdır (gider tablosundaki dağıtılmış tutar); v0.2'de eşanlamlı sayıldığı için Alphabet, J&J ve Coca-Cola'da yanlış çelişki üretiyordu, v0.3'te kaldırıldı.
- **Bilanço:** nakit ve nakit benzerleri, dönen ve toplam varlıklar, kısa vadeli ve toplam yükümlülükler, ticari senet, kısa vadeli borçlanma, uzun vadeli borç (kısa vadeli kısmı ile birlikte veya ayrı), özkaynak, toplam finansal borç†.

† türetilen kalem.

**Toplam borç:** raporlanan bileşenlerin toplamıdır. `LongTermDebt` kısa vadeli kısmı zaten içerdiği için yalnız `LongTermDebtNoncurrent` yoksa kullanılır, çift sayım yapılmaz. Toplanan ve bildirilmeyen bileşenler `components` / `components_not_reported` alanlarında listelenir. Kira yükümlülükleri dahil değildir.

**Menkul kıymetler (v0.4):** Üç bilanço kalemi okunur: kısa vadeli yatırımlar (`ShortTermInvestments`), kısa vadeli ve uzun vadeli menkul kıymetler (`MarketableSecuritiesCurrent`, `MarketableSecuritiesNoncurrent`). Toplamları `liquid_investments` (yalnız aynı SEC dosyasından, bildirilmeyen bileşen 0 sayılmaz). Kısa vadeli yatırımlar kalemi bazı şirketlerde kısa vadeli menkul kıymetleri zaten içerir; ikisi birlikte bildirilmişse **toplanmaz**, büyük olan kullanılır ve sonuç alt sınır olarak işaretlenir (`overlap.lower_bound`). Bu, iki kalemin gerçekten ayrı olduğu şirketlerde (ör. Coca-Cola) menkul kıymetleri olduğundan az gösterir; çift saymaktan daha güvenlidir.

**Menkul kıymet etiket çeşitleri (v0.5):** `OtherShortTermInvestments` (diğer kısa vadeli yatırımlar) tanım gereği menkul kıymetleri içermediği için her zaman eklenir. Vade ayrımı olmayan `MarketableSecurities` toplamı (ör. Coca-Cola) yalnız kısa / uzun vadeli menkul kıymet kalemleri hiç bildirilmemişse kullanılır; kısa vadeli yatırımlarla birlikteyse yine yalnız büyüğü düşülür.

**Net borç (v0.4):** `net_debt` = toplam borç − nakit − menkul kıymetler. Oranlar (net borç, ROIC), tarihsel baz (satış / yatırılan sermaye) ve DCF'in SEC net borç girdisi bu tek hücreyi kullanır.
- Şirket hiç menkul kıymet kalemi bildirmemişse yalnız nakit düşülür; yöntem `TOTAL_DEBT_MINUS_CASH_NO_SECURITIES_REPORTED` olarak görünür.
- Menkul kıymetler belirlenemiyorsa (farklı dosyalar, çelişki) net borç `MISSING` olur; yalnız nakitle hesaplanmaz.
- `financial` (banka, sigorta) sektöründe net borç hesaplanmaz (`NOT_MEANINGFUL_FOR_FINANCIAL_SECTOR`): bankanın nakdi ve borcu (mevduat, merkez bankası rezervi) faaliyetin kendisidir. Kalemler tabloda görünmeye devam eder. Tablo fonksiyonlarındaki `net_debt` parametresi bunu belirler; araştırma raporu analistin girdiği sektöre göre ayarlar.
- Nvidia bilançodaki menkul kıymetler satırını SEC'in standart etiketleriyle bildirmiyor. Company Facts'teki `AvailableForSaleSecuritiesDebtSecurities` toplamı nakit benzerlerini de içerdiği için kullanılmaz; net borçtan yalnız nakit düşülür (`NONE_REPORTED`). Değerlemede analist net borcu kaynağıyla girebilir.

**Kira yükümlülükleri (v0.4):** Faaliyet ve finansal kiralama yükümlülükleri (kısa / uzun vadeli) tabloda gösterilir, toplamı `lease_liabilities`. Net borca **eklenmez**: US-GAAP'te faaliyet kârı faaliyet kiralaması giderini zaten düşer, kirayı bir de borca eklemek aynı yükü iki kez saymak olur. Bazı şirketler finansal kiralamayı bildirdikleri borca zaten dahil eder; bu yüzden finansal kiralama da ayrıca eklenmez.

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

**Doğrulama:** Son dört çeyreğin toplamı, mevcut `sec_ttm.py` motorunun "FY + güncel YTD − önceki YTD" TTM sonucuyla birebir eşleşir. Bu eşleşme testlerle sınanır.

## Son 12 ay (TTM) — her çeyrekte (v0.3)

Çeyreklik çıktının `ttm` alanı ve `trailing_twelve_months(quarterly, end=None)` fonksiyonu, en son çeyrekle biten **art arda dört çeyreğin** gelir tablosu ve nakit akışı kalemlerini toplar. Son çeyrek 1., 2., 3. veya 4. çeyrek olabilir. Eski iki TTM motoru ise yalnız son dönem 9 aylık 10-Q olduğunda çalışıyordu; gerçek veri denemesinde 11 şirketin yalnız birinde TTM çıkmasının nedeni buydu.

- Durum: `OK` (gelir, faaliyet kârı, CFO ve CapEx hesaplandı), `PARTIAL` (bunlardan biri eksik; `core_unavailable` listesi), `INSUFFICIENT_QUARTERS` (art arda dört çeyrek yok).
- Her kalem `SUM_OF_FOUR_QUARTERS` yöntemiyle `DERIVED` olur; dayandığı bütün SEC dosyaları `sources` alanındadır.
- Bir çeyrek eksik veya çelişkiliyse o kalem `MISSING` / `CONFLICT` kalır ve hangi çeyreğin eksik olduğu `quarters_unavailable` alanında yazar. Ortalama hisse sayısı toplanmaz.
- Çeyreklerden biri yaklaşık faaliyet kârıysa TTM değeri de `approximate` işaretlenir.
- Son dönem 9 aylıksa eski iki motor aynı dört çeyreği hâlâ bağımsız olarak karşılaştırır (katman mutabakatı). Aksi halde araştırma raporu `TTM_SINGLE_METHOD_ONLY:<durum>` açığını yazar: TTM vardır ama ikinci bir yöntemle karşılaştırılmamıştır.

## Dolaşımdaki hisse sayısı

`shares_outstanding(raw, as_of=...)`, 10-K / 10-Q kapak sayfasındaki `dei:EntityCommonStockSharesOutstanding` değerini döndürür. Bilgi tarihine kadar en son dosyalanan değer seçilir ve kapak sayfasındaki tarihi taşır; bu tarih genellikle dönem sonundan birkaç hafta sonradır.

Birden fazla hisse sınıfı olan şirketler (ör. A/B/C sınıfı) aynı dosyada birden fazla değer bildirebilir. Bu durumda değerler toplanmaz ve aralarından seçim yapılmaz; sonuç `CONFLICT` olur. Yıllık ve çeyreklik çıktıların ikisinde de `shares_outstanding` alanı bulunur.

## Katman mutabakatı

Piotroski ve iki TTM motoru SEC verisini hâlâ kendi kurallarıyla okur. `katman_mutabakati.py` her araştırma raporunda bu motorların kullandığı rakamları ortak katmanla karşılaştırır ve raporda "Katman mutabakatı" bölümünde gösterir. Hiçbir motorun sonucunu değiştirmez.

| Kontrol | Nasıl karşılaştırılır | Dikkat gerektiren durum |
|---|---|---|
| Piotroski girdileri ↔ yıllık tablolar | Piotroski'nin kullandığı her SEC kaydı (net kâr, CFO, gelir, brüt kâr, varlıklar, borç, dönen varlık ve yükümlülükler) aynı yılın ortak hücresiyle birebir | `VALUE_DIFFERS` (tutar farklı), `SHARED_CONFLICT` (Piotroski bir değer kullandı, ortak katman etiket çelişkisi gördü) |
| TTM ↔ son dört çeyrek | Mutabık TTM, TTM bitişinde sona eren ortak TTM ile (`trailing_twelve_months`) | %0,1'i aşan fark (`VALUE_DIFFERS`); %0,1'e kadarki fark yuvarlama sayılır (`ROUNDING`); ortak değer yaklaşık faaliyet kârıysa not (`SHARED_APPROXIMATE`) |

Dikkat gerektiren bir fark araştırma raporunun açık eksiklerine eklenir:
- `SHARED_STATEMENTS_DIFFER_FROM_PIOTROSKI_INPUTS`
- `SHARED_QUARTERS_DIFFER_FROM_TTM`

Gelir etiketi eşiği v0.3'te birleştirildi: Piotroski ve ortak katman %5'e kadar farkta aynı öncelikli etiketi kullanır, %5'ten büyük farkta ikisi de değeri bilinmiyor sayar. Gerçek veri denemesinde bu karar yalnız Walmart'ı (%0,95 fark) etkiledi.

## Oranlar

| Grup | Oranlar |
|---|---|
| Kârlılık | brüt, faaliyet ve net kâr marjı |
| Büyüme | gelir ve faaliyet kârı büyümesi (yalnız 330–400 gün önceki mali yılla) |
| Nakit akışı | serbest nakit akışı marjı, nakit dönüşümü (CFO / net kâr), CapEx yoğunluğu, hisse bazlı ödeme / gelir, hissedarlara dağıtım / net kâr |
| Getiri | ROA, ROE, efektif vergi oranı, ROIC |
| Bilanço | cari oran, borç / özkaynak, net borç, faiz karşılama |

Her oran `formula`, kullanılan `inputs` ve hesaplanamadığında `reason` taşır. Örnekler: `INPUT_UNAVAILABLE:interest_expense`, `NONPOSITIVE_DENOMINATOR:average_equity`, `PRIOR_FISCAL_YEAR_REQUIRED`, `TAX_RATE_OUTSIDE_0%_50%`.

Faaliyet kârını kullanan oranlar (faaliyet marjı, faaliyet kârı büyümesi, ROIC, faiz karşılama) yaklaşık faaliyet kârıyla hesaplandıysa `approximate: "OPERATING_INCOME_PROXY"` taşır ve raporda ≈ ile gösterilir. Tarihsel baz bu yılları `approximate_operating_income_years` alanında listeler; senaryolar, değerleme ve Tahmin Defteri kaydı aynı uyarıyı taşır. Sapma analizi yalnız bildirilmiş (`REPORTED`) gerçekleşenleri puanlar; yaklaşık bir gerçekleşen puanlanmaz.

- **ROA / ROE / ROIC:** dönem sonu ile önceki dönem sonu bakiyelerinin ortalamasıyla hesaplanır.
- **ROIC:** `faaliyet kârı × (1 − efektif vergi) / ortalama (özkaynak + net borç)`. Efektif vergi %0–%50 dışındaysa ROIC hesaplanmaz. v0.4'ten itibaren net borçtan menkul kıymetler de düşülür; Apple gibi büyük menkul kıymet portföyü olan şirketlerde ROIC artık olduğundan düşük görünmez. ROIC %100'ün üstündeyse `caution: VERY_SMALL_INVESTED_CAPITAL` taşır ve raporda ! ile gösterilir: hesap doğrudur ama sermaye tabanı o kadar küçüktür ki oran tek başına yorumlanmamalıdır (ör. Apple).
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
- Yaklaşık faaliyet kârı faaliyet dışı kalemleri içerir; özkaynak yöntemiyle büyük iştirak geliri olan şirketlerde (ör. Exxon) gerçek faaliyet kârından belirgin farklı olabilir.
- Ara dönemde mali yıl değiştiren şirketlerde çeyrek takvimi kurulamayabilir; o çeyrekler listelenmez.
- Seçili US-GAAP kalemleri: segment verisi, azınlık payları, uzun vadeli stratejik yatırımlar ve şirkete özel (extension) etiketler yoktur. IFRS / 20-F desteklenmez.
- Bankalar ve sigorta şirketlerinde bu kalemler ve oranlar anlamlı olmayabilir.
- Etiket eşanlamlıları otomatik eşleşmeyi kolaylaştırır ama konsolide tablonun insan tarafından okunmasının yerini tutmaz.
- Geçmiş oranlar tahmin, puan veya yatırım tavsiyesi değildir.

## Testler

`tests/test_finansal_tablolar.py`, `tests/test_finansal_oranlar.py` (36 test) ve `tests/test_finansal_ceyrekler.py` (23 test). v0.3 kuralları `tests/test_gercek_veri_kurallari.py` (27 test: hisse bazlı ödeme, gelir etiketi %5 kuralı ve sınırı, yaklaşık faaliyet kârı ve sektör koruması, CapEx yedek etiketi, oran / baz / defter / değerleme uyarıları) ve `tests/test_ortak_ttm.py` (16 test: 1., 3. ve 4. çeyrekte TTM, eksik / çelişkili çeyrek, eski motorlarla mutabakat, rapor açığı) ile sınanır. Menkul kıymetler, kira ve net borç `tests/test_menkul_kiymetler.py` (19 test: menkul kıymet ve kira toplamları, çakışma kuralı, etiket çeşitleri, nakit / özkaynak yedek etiketleri, ROIC uyarısı) ile sınanır. Çeyrek testleri şunları kapsar:
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
