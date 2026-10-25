# INVEST_AI — Değişiklik Günlüğü

En yeni değişiklik en üstte. «Önceki sürüm notları» bölümü, README'nin önceki
sürümünden olduğu gibi taşındı. Oradaki test sayıları (16/16, 20/20, 38/38, 58/58 vb.)
**o tarihteki yerel alt kümelerin** sayımıdır; güncel toplam için README'deki
«Test durumu» tablosuna bakın.

## 2026-10-25 — Bankalarda net borç hesaplanmıyor (tablolar v0.5.1)

- Beşinci gerçek veri denemesinde v0.5'in nakit yedek etiketi JPM'de merkez bankası rezervlerini "nakit" yaptı ve
  anlamsız bir net borç (−278,6 milyar $) çıktı. Bankanın nakdi ve borcu faaliyetin kendisidir; `financial`
  sektöründe net borç artık `NOT_MEANINGFUL_FOR_FINANCIAL_SECTOR` nedeniyle hesaplanmaz. Bileşen kalemler tabloda
  kalır. Tablo fonksiyonlarına `net_debt` parametresi, katman sağlığına `NOT_APPLICABLE_FINANCIAL` değeri eklendi.
- Aynı denemede v0.5 düzeltmeleri doğrulandı: Microsoft, J&J ve P&G'de ROIC, P&G'de net borç, Coca-Cola'da
  menkul kıymetler geldi. Nvidia'nın menkul kıymet satırı standart etikette yok; belgelendi.
- **Testler:** 4 yeni test. Toplam `tests/` 628/628. 6 hedefli mutasyonun hepsi yakalanıyor.
## 2026-10-25 — Fiyat katmanı: kaynaklı fiyatla bütün şirketlerde değerleme çarpanları (v0.7)

- **`fiyat_katmani.py`:** Ücretsiz Nasdaq hisse tarayıcısı CSV'si veya `ticker,date,close` dosyası (Türkçe Excel `;`
  ayracı ve virgül ondalığı dahil) tarih ve kaynakla `veri/invest_ai_fiyat.sqlite3`'e alınır. Gelecek tarihli,
  imtiyazlı / birim, sıfır fiyatlı ve tekrarlanan satırlar nedenleriyle atlanır. Ağ isteği yoktur.
- **Toplu tablo:** Her hisse kodu kendi fiyatını alır; F/K, PD/DD, fiyat/satış, (ROE/10)/PD/DD, EV/EBIT, EV/FAVÖK*,
  fiyat/FCF, FCF getirisi ve **tarihsel PEG** (F/K ÷ 3Y EPS CAGR) hesaplanır. Çarpanlar yalnız fiyat tarihi SEC bilgi
  tarihine 10 gün içinde, finansallar güncel (456 gün) ve pay adedi en çok 200 gün eskiyse üretilir; "Değerleme
  durumu" nedenini söyler. SEC tarihine en yakın uygun fiyat seçilir.
- **Arayüz:** 7 koşulda PEG türü seçimi (ileri / tarihsel), fiyat kaynağının sektör filtresi ("Finance hariç"),
  değerleme durumunun Türkçe gösterimi. Hata düzeltmesi: değeri hiç olmayan (eski satır) bir oran şirketi
  "Elendi" sayıyordu; artık "Veri bekliyor".
- **Kapsam raporu:** fiyat ve değerleme durum sayıları. Satır şeması 3: yeni sütunlar için bir kez `--rebuild`.
- **Testler:** 14 yeni test (`tests/test_fiyat_katmani.py`). Toplam `tests/` 624/624. Tarayıcıda uçtan uca denendi.

## 2026-10-25 — Toplu tarama: kapsam raporu, yerel yeniden hesaplama ve yeni SEC sütunları (v0.7)

- **`--coverage`:** 5.003 `OK` şirkette her oranın kaç şirkette dolu olduğunu, 7 koşulun girdilerinin hazır olma
  sayısını, güncel olmayan (son mali yılı 456 günden eski) şirketleri ve yeniden hesaplanması gereken satırları
  gösterir. Salt okunur.
- **`--rebuild`:** Aynı yerel `companyfacts.zip` ve aynı bilgi tarihiyle bütün şirketleri yeniden hesaplar; indirme
  yapmaz, kesilirse devam eder.
- **Yeni sütunlar:** seyreltilmiş EPS (net kâr / ortalama seyreltilmiş hisse), 3 yıllık EPS CAGR, 1 yıllık net kâr
  büyümesi, 3 yıllık hisse adedi değişimi (önceden hep boştu), pay adedi tarihi, son mali yıl yaşı (gün).
- Eski sürümle kaydedilmiş satırlar tabloda yeni sütunları boş gösterir; mali yıl yaşı yükleme sırasında hesaplanır.
- **Testler:** 9 yeni test (`tests/test_kapsam_raporu.py`). Toplam `tests/` 610/610.

## 2026-10-25 — Bilanço etiket çeşitleri ve ROIC uyarısı (tablolar v0.5)

Dördüncü gerçek veri denemesinin etiket kontrolünden.

- **Farklı dosyalardaki bilanço parçaları:** Bir sonraki 10-K önceki yılın satırlarından yalnız bazılarını tekrar
  ediyor; bu yüzden Microsoft ve Nvidia'nın önceki yıl toplam borcu ve ROIC'i hesaplanamıyordu. Hiçbir parçası
  revize edilmemişse farklı dosyalardaki parçalar toplanır (`..._UNREVISED_ACROSS_FILINGS`); revize edilmiş parça
  varsa toplam yapılmaz (`revised_components`).
- **Menkul kıymet etiketleri:** `OtherShortTermInvestments` her zaman eklenir; vade ayrımsız `MarketableSecurities`
  yalnız kısa / uzun vadeli kalemler bildirilmemişse kullanılır (Coca-Cola).
- **Yedek etiketler:** nakit için kısıtlı nakit dahil toplam (P&G), özkaynak için azınlık payı dahil toplam
  (J&J, P&G; gerçek veriyle doğrulanacak). Rapordaki yedek etiket notu her etiketin kapsamını ayrı açıklar.
- **ROIC uyarısı:** ROIC %100'ün üstündeyse `caution: VERY_SMALL_INVESTED_CAPITAL`, raporda ! işareti (Apple %479).
- **Testler:** 8 yeni test, 4 testin beklentisi yeni kurala göre güncellendi. Toplam `tests/` 570/570. Yeni
  satırlarda 14 hedefli mutasyonun hepsi yakalanıyor.

## 2026-10-25 — Menkul kıymetler, kira yükümlülükleri ve net borç (tablolar v0.4)

- **Yeni bilanço kalemleri:** kısa vadeli yatırımlar, kısa / uzun vadeli menkul kıymetler, faaliyet ve finansal
  kiralama yükümlülükleri (kısa / uzun vadeli).
- **Türetilen kalemler:** `liquid_investments` (menkul kıymetler toplamı), `lease_liabilities` (kira toplamı) ve
  `net_debt` (toplam borç − nakit − menkul kıymetler). Kısa vadeli yatırımlar ile kısa vadeli menkul kıymetler
  birlikte bildirilmişse çift sayılmaz; büyüğü kullanılır ve alt sınır olarak işaretlenir.
- **Tek net borç:** Net borç oranı, ROIC'in yatırılan sermayesi, tarihsel bazdaki satış / sermaye ve DCF'in SEC net
  borç girdisi artık aynı `net_debt` hücresini kullanır. Apple, Alphabet, Microsoft, Nvidia gibi büyük menkul kıymet
  portföyü olan şirketlerde net borç, ROIC ve hisse başı değer önceki sürümde olduğundan kötü görünüyordu.
- **Kira yükümlülükleri** gösterilir ama net borca eklenmez: faaliyet kârı kira giderini zaten düşüyor.
- **Değerleme uyarıları:** `NET_DEBT_EXCLUDES_SECURITIES_AND_LEASES` yerine `NET_DEBT_EXCLUDES_LEASES`,
  `NET_DEBT_NO_SECURITIES_REPORTED`, `NET_DEBT_SECURITIES_LOWER_BOUND`.
- **Toplu tarama:** katman sağlığına `net_debt_securities` (CSV'de 1 yeni sütun, özet satırı).
- **Testler:** 12 yeni test (`tests/test_menkul_kiymetler.py`), 1 testin beklentisi güncellendi. Toplam `tests/`
  562/562. Değişen satırlarda 17 hedefli mutasyonun hepsi yakalanıyor.

## 2026-10-25 — CapEx yedek etiketi ve bankalarda yaklaşık faaliyet kârı koruması

İkinci gerçek veri denemesinin bulguları.

- **CapEx yedek etiketi:** Bir kalemin hiçbir eşanlamlısı bildirilmemişse daha geniş kapsamlı yedek etiket okunur
  (`FALLBACK_ALIASES`). CapEx için `PaymentsToAcquireProductiveAssets`: Nvidia ve Amazon CapEx'i bu etiketle
  bildiriyor, bu yüzden TTM'leri kısmi kalıyordu. Hücre `fallback_concept: true` taşır, çıktıda
  `fallback_concepts` listesi ve raporda not var. Asıl etiket varsa yedek etikete bakılmaz.
- **Sektör koruması:** Yaklaşık faaliyet kârı (vergi öncesi kâr + faiz gideri) yalnız `non_financial` sektörde
  hesaplanır. Bankada faiz gideri asıl faaliyetin parçası olduğu için bu sayı anlamsızdır; `financial` ve `unknown`
  sektörde hücre `EBIT_PROXY_DISABLED_FOR_SECTOR` nedeniyle eksik kalır. Tablo fonksiyonlarına `ebit_proxy`
  parametresi eklendi.
- **Coca-Cola ve Exxon:** TTM'in 1. çeyrekte bitmesi kod hatası değil; indirilen SEC dosyasında 2. çeyrek kaydı
  yoktu ([docs/SEC_TOPLU_TARAMA_V01.md](docs/SEC_TOPLU_TARAMA_V01.md)).
- **Testler:** 8 yeni test. Toplam `tests/` 550/550. Yeni satırlarda 10 hedefli mutasyonun hepsi yakalanıyor.

## 2026-10-25 — Gerçek veri düzeltmeleri (tablolar v0.3)

11 şirketlik ilk gerçek SEC denemesinde bulunan dört sorun giderildi.

- **Hisse bazlı ödeme:** `AllocatedShareBasedCompensationExpense` eşanlamlı listesinden çıkarıldı. Bu farklı bir
  kavramdır ve Alphabet, J&J, Coca-Cola'da yanlış etiket çelişkisi üretiyordu. Artık yalnız nakit akışı
  tablosundaki `ShareBasedCompensation` okunur.
- **Gelir etiketleri (%5 kuralı):** Gelir etiketleri arasında %0,5–%5 fark varsa öncelikli etiket kullanılır, hücre
  `REPORTED` kalır, fark `alias_gap` alanında ve raporda ‡ işaretiyle görünür. %5 üstü fark çelişkidir. Piotroski
  ile ortak katman artık aynı kuralı uygular; yol haritasındaki açık eşik kararı kapandı. Diğer kalemler %0,5'te
  kalır. Walmart'ın gelir hücresi bu kuralla kullanılabilir hale gelir.
- **Yaklaşık faaliyet kârı:** `OperatingIncomeLoss` bildirilmemişse faaliyet kârı = vergi öncesi kâr + faiz gideri
  (aynı SEC dosyası); `DERIVED`, `approximate: true`, `EBIT_PROXY_PRETAX_PLUS_INTEREST`. Bunu kullanan oranlar,
  tarihsel baz, senaryolar, değerleme ve Tahmin Defteri kaydı uyarı taşır; raporda ≈ ile gösterilir. Sapma
  analizi yaklaşık gerçekleşenleri puanlamaz.
- **Her çeyrekte TTM:** `finansal_tablolar.trailing_twelve_months()` ve çeyreklik çıktının `ttm` alanı: en son
  çeyrekle biten art arda dört çeyreğin toplamı (1., 2., 3. veya 4. çeyrek). Raporda "Son 12 ay (TTM)" bölümü.
  Eski iki TTM motoru 9 aylık dönemlerde çapraz kontrol olarak kalır; `reconcile_ttm` artık aynı fonksiyonu
  kullanır. Eski motorlar çalışmadığında rapor açığı `TTM_SINGLE_METHOD_ONLY:<durum>` olur.
- **Toplu tarama:** Katman sağlığına `shared_ttm_status`, `shared_ttm_end`, `latest_operating_income` eklendi
  (CSV'de 3 yeni sütun); Türkçe özet satırları güncellendi.
- **Belgeler:** finansal tablolar (v0.3 kuralları, TTM), toplu tarama (ilk denemenin bulguları ve düzeltmeler),
  yol haritası, README.
- **Testler:** 36 yeni test (`test_gercek_veri_kurallari.py`, `test_ortak_ttm.py`, mutabakat). 6 testin
  beklentisi yeni kurala göre güncellendi. Toplam `tests/` 542/542. Değişen satırlarda 24 hedefli mutasyonun
  hepsi testlerce yakalanıyor.

## 2026-10-25 — Gerçek veri kontrolü: çoklu şirket katman sağlığı

- **`katman_mutabakati.layer_health()`:** Bir araştırma raporundaki ortak katmanların özeti:
  - yıllık yıl sayısı ve etiket çelişkileri,
  - son iki yılın gelir etiketi farkı ve kovası (`HALF_TO_FIVE_PERCENT`: Piotroski kabul ediyor, ortak
    tablolar çelişki görüyor),
  - çeyrek sayısı, hisse sayısı durumu, Piotroski / TTM mutabakatı, senaryo tabanı, hesaplanabilen oran sayısı.
- **`sec_toplu_tarama.py`:** Her şirket kaydına `layer_health` alanı, özete `layer_health_counts` alanı, CSV'ye
  12 yeni sütun eklendi. Komut sonunda kısa bir Türkçe katman sağlığı özeti basılır.
- **`ornekler/gercek_veri_kontrol_evreni.json`:** 11 tanınmış şirket. Çok sınıflı hisse (GOOGL) ve banka (JPM)
  bilerek dahil edildi.
- **Belgeler:** Tek komutluk gerçek veri denemesi ve Piotroski eşik kararının nasıl okunacağı
  ([docs/SEC_TOPLU_TARAMA_V01.md](docs/SEC_TOPLU_TARAMA_V01.md)), yol haritası, README.
- **Testler:** 7 yeni test. Toplam `tests/` 506/506.

## 2026-10-25 — Ters DCF senaryolara bağlandı (Ders 7 tamamlandı)

- **`senaryo_degerleme.implied_growth()`:** Analistin girdiği tarihli ve kaynaklı hisse fiyatının, baz senaryonun
  diğer bütün varsayımları korunarak ima ettiği yıllık sabit gelir büyümesi (`ters_dcf_v02`, −%50…+%100).
  - Sonuç şirketin kendi büyüme geçmişine göre konumlandırılır (en düşüğün altında … en yüksekten de üstte).
  - Tek kök yoksa `NO_UNIQUE_SOLUTION` döner.
  - Fiyat tarihi SEC bilgi tarihinden sonraysa veya 7 günden fazla uzaksa uyarı verilir.
- **Rapor:** JSON'a `implied_growth` alanı, HTML'e "Ters DCF — fiyatın ima ettiği büyüme" bölümü eklendi. CLI
  bayrakları: `--price`, `--price-date`, `--price-source` (`senaryo_degerleme.py`, `sirket_arastirma_akisi.py`).
- **Web:** Formda fiyat, fiyat tarihi ve kaynağı alanları var. Sunucu bu üç alanın birlikte verilmesini,
  değerleme girdilerini, tarihin bugünden ileri olmamasını ve fiyat aralığını doğrular; sonuç kutusunda ima
  edilen büyüme gösterilir.
- **Belgeler:** senaryo değerlemesi, web rehberi, yol haritası, README.
- **Testler:** 14 yeni test. Toplam `tests/` 499/499.

## 2026-10-25 — Web formu v0.3: senaryo ve değerleme girdileri

- **`index.html`:** Analiz formuna isteğe bağlı "Senaryo ve değerleme girdileri" bölümü eklendi: uzun vadeli
  nominal büyüme (%) ve iskonto oranı (%), her biri kaynağıyla.
  - İstemci tarafında eşleşme ve kaynak uzunluğu kontrol edilir; yüzdeler orana çevrilir.
  - Sonuç kutusunda senaryo ve DCF durumu gösterilir.
  - Rapor listesi senaryo girdili raporları "Analist senaryo girdili" olarak tanır.
- **`invest_ai_web.py` (v0.3.0):**
  - Girdiler analizden önce doğrulanır: aralıklar, 8–300 karakter kaynak, değer ve kaynağın birlikte
    verilmesi, iskontonun büyüme olmadan kullanılamaması, değerlemede %4 uç büyüme tavanı. Hatalar Türkçe
    mesajla döner.
  - Senaryo girdili raporların dosya adına `_s<hash>` eklenir; farklı varsayımlar birbirinin üzerine yazılmaz.
  - İstek gövdesi sınırı 512 → 4096 bayt. Yanıta `projection_status`, `valuation_status`,
    `valuation_missing` eklendi.
- **Doğrulama:** Gerçek tarayıcıda (Playwright / Chromium) form doldurulup gönderildi. Web üzerinden üretilen
  senaryo değerleri komut satırıyla birebir aynı çıktı.
- **Belgeler:** [docs/WEB_SIRKET_ANALIZI_V02.md](docs/WEB_SIRKET_ANALIZI_V02.md), tahmin motoru, yol haritası,
  README.
- **Testler:** 9 yeni test. Toplam `tests/` 485/485.

## 2026-10-25 — Senaryo değerlemesi v0.1 (yol haritası Ders 7)

- **`senaryo_degerleme.py` (yeni):** Tahmin motorunun her senaryosu, aynı gelir ve faaliyet marjı yoluyla
  deneysel v0.2 DCF'de değerlenir. DCF gelir yolunun projeksiyonla aynı olduğu her çalıştırmada kontrol
  edilir.
  - **Girdi kökenleri:**
    - analist: iskonto oranı (zorunlu, kaynaklı), uç büyüme;
    - şirket geçmişi: vergi, satış / sermaye medyanları;
    - SEC dosyası: net borç = toplam borç − nakit, kapak sayfası hisse sayısı;
    - yöntem varsayılanı: uç RONIC = iskonto.
  - Her girdi kaynaklı olarak değiştirilebilir. Eksik girdi tahmin edilmez (`INPUTS_MISSING`).
  - Baz senaryo için 5 × 5 iskonto × uç büyüme duyarlılık tablosu üretilir. Uyarılar: net borç kapsamı, nötr
    RONIC, geçmişe dönük projeksiyon, motor uyarıları.
- **`degerleme_v02.py`:** Opsiyonel `marj_yolu` (yıllık marj listesi). Verilmezse davranış aynıdır.
- **`tahmin_motoru.py`:** Projeksiyon çıktısına son yılın geliri ve marjı (`base`) eklendi.
- **Rapor:** `--discount-rate` / `--discount-source` (ayrıca uzun vadeli oran) verilirse "Senaryo değerlemesi"
  bölümü eklenir; JSON'da `scenario_valuation` alanı var.
- **Belgeler:** [docs/SENARYO_DEGERLEME_V01.md](docs/SENARYO_DEGERLEME_V01.md), yol haritası, README.
- **Testler:** 17 yeni test. Toplam `tests/` 476/476.

## 2026-10-25 — Sapma analizi v0.1 (yol haritası Ders 8)

- **`sapma_analizi.py` (yeni):** Tahmin Defteri'ndeki bir şirketin tahminleri hedefledikleri mali yılla eşlenir
  ve ortak tablolardaki **ilk bildirilen** SEC değeriyle karşılaştırılır.
  - Desteklenen hedefler: `FY+k_AFTER_<mali yıl sonu>` (`tahmin_motoru`), `FY_END:<tarih>`
    (`sec_reviewed_pipeline`, ±7 gün).
  - Ölçütler: gelir, faaliyet kârı / EBIT. FCFF puanlanmaz.
  - Çıktılar: işaretli, mutlak ve yüzde hata; senaryo ve ölçüt bazında ortalama mutlak yüzde hata ve
    yanlılık; senaryo aralığı isabeti.
  - `--record` ile gerçekleşen ve puan kayıtları tek işlemde, tekrar eklenmeden yazılır. Türkçe HTML rapor
    üretilir.
- **`tahmin_defteri.py`:**
  - Yeni okuma yöntemleri: `tahminleri_listele(ayrintili=True)`, `gerceklesenleri_listele()`,
    `puanlari_listele()`.
  - `gerceklesen_kaydet` ve `puanla` dış işleme katılır; dış işlem yokken davranış aynıdır.
- **`sirket_analiz_paneli.py`:** Sayfa stili `PAGE_STYLE` sabitine taşındı (iki rapor ortak kullanır); görünüm
  değişmedi.
- **Belgeler:** [docs/SAPMA_ANALIZI_V01.md](docs/SAPMA_ANALIZI_V01.md), yol haritası, README.
- **Testler:** 12 yeni test. Toplam `tests/` 459/459.

## 2026-10-24 — Tahmin motoru v0.1 (yol haritası Ders 6)

- **`tahmin_motoru.py` (yeni):**
  - `historical_baseline()`: şirketin kendi yıllık geçmişinden büyüme, faaliyet marjı, efektif vergi, FCF
    marjı ve satış / yatırılan sermaye artışı istatistikleri (medyan, çeyrekler, gözlem sayısı) ile gelir
    CAGR'ı. Kullanılan SEC dosyaları saklanır.
  - `project_scenarios()`: temkinli / baz / iyimser senaryolar şirketin kendi geçmişinin alt çeyrek / medyan
    / üst çeyreğinden başlar. Büyüme son yılda analistin **kaynaklı** uzun vadeli oranına, marj senaryo
    hedefine doğrusal olarak ulaşır. Sistem uzun vadeli oranı kendisi seçmez. Kısa geçmişte yalnız baz
    senaryo gösterilir; uyarılar ve geçmişe dönük senaryo bayrağı var.
  - `record_projection()`: gelir ve faaliyet kârını `FY+k_AFTER_<mali yıl sonu>` hedefleriyle Tahmin
    Defteri'ne tek işlemde yazar; tekrar kayıt engellenir.
  - CLI: `python tahmin_motoru.py ...`.
- **Rapor:** Tarihsel baz her araştırma raporunda yer alır. `--long-run-growth` ve `--long-run-source`
  birlikte verilirse senaryo tablosu da eklenir.
- **Belgeler:** [docs/TAHMIN_MOTORU_V01.md](docs/TAHMIN_MOTORU_V01.md), yol haritası, README.
- **Testler:** 20 yeni test. Toplam `tests/` 447/447.

## 2026-10-24 — Katman mutabakatı v0.1

- **`katman_mutabakati.py` (yeni):** Her araştırma raporunda iki kontrol yapar; hiçbir motorun sonucunu
  değiştirmez.
  - Piotroski'nin kullandığı her SEC kaydını aynı yılın ortak tablo hücresiyle karşılaştırır (tutar ve SEC
    dosyası).
  - Mutabık TTM'i, TTM bitişinde sona eren art arda dört ortak çeyreğin toplamıyla karşılaştırır (%0,1'e
    kadarki fark yuvarlama sayılır).
- **Rapor:** JSON'a `layer_reconciliation` eklendi; HTML'de "Katman mutabakatı" bölümü var. Dikkat gerektiren
  fark açık eksiklere eklenir: `SHARED_STATEMENTS_DIFFER_FROM_PIOTROSKI_INPUTS`,
  `SHARED_QUARTERS_DIFFER_FROM_TTM`.
- **Bulgu:** Piotroski gelir etiketlerinde %5'e kadar farkı kabul ediyor, ortak katman %0,5'te duruyor.
  Piotroski'nin ortak katmana taşınması bu yüzden bir eşik kararı gerektiriyor
  ([docs/YOL_HARITASI.md](docs/YOL_HARITASI.md)).
- **Testler:** 15 yeni test. Toplam `tests/` 427/427.

## 2026-10-24 — Finansal tablolar v0.2: çeyreklik tablolar ve hisse sayısı

- **`build_quarterly_statements()`:** Son 8 (en çok 40) ayrık mali çeyrek: gelir tablosu, nakit akışı ve
  çeyrek sonu bilançosu.
  - Bildirilmiş 3 aylık değer yoksa aynı XBRL kavramının iki YTD değerinin farkı alınır.
  - 4. çeyrek = yıllık 10-K − 9 aylık 10-Q.
  - Türetilen hücreler iki SEC dosyasını da `sources` alanında taşır.
  - Ortalama hisse sayısının farkı alınmaz.
  - Devam eden mali yıl listelenir; sınırları bilinmeyen çeyrek listelenmez.
  - Son 4 çeyreğin toplamı mevcut `sec_ttm` TTM sonucuyla birebir eşleşir (testle sınanır).
- **`shares_outstanding()`:** Kapak sayfası `dei:EntityCommonStockSharesOutstanding`; birden fazla hisse
  sınıfı değeri toplanmaz, `CONFLICT` olarak işaretlenir. Yıllık ve çeyreklik çıktılarda yer alır.
- **Okuyucu:** Form ve süre kuralı parametreli, önbellekli tek okuyucu. Yıllık çıktı değişmedi; yalnız
  `shares_outstanding` alanı eklendi ve çelişki listesi `start`/`end` alanlarıyla verilir. Sürüm
  `finansal-tablolar-0.2.0`.
- **Rapor:** Araştırma JSON'una `quarterly_statements` eklendi. HTML'de "Çeyreklik tablolar" bölümü ve yıllık
  tablonun altında dolaşımdaki hisse satırı var.
- **Testler:** 23 yeni test (`tests/test_finansal_ceyrekler.py`). Toplam `tests/` 412/412.

## 2026-10-24 — Finansal tablolar ve oranlar v0.1 (yol haritası 1. aşama)

- **`finansal_tablolar.py` (yeni):** SEC Company Facts verisini tek bir kurallar setiyle okuyan, tarihli ve
  kaynağı izlenen yıllık gelir tablosu, nakit akışı ve bilanço. 27 raporlanan kalem; brüt kâr, serbest nakit
  akışı (CFO − CapEx, FCFF değildir) ve toplam borç yalnız aynı SEC dosyasından türetilir. Mali yıllar
  SEC `fy`/`fp` alanlarından değil, kaydın kendi tarihlerinden belirlenir. Revizyonlarda ilk değer saklanır.
  XBRL eşanlamlıları %0,5'ten fazla ayrışırsa değer yazılmaz (`CONFLICT`).
- **`finansal_oranlar.py` (yeni):** 18 oran: marjlar, büyüme, nakit dönüşümü, ROA / ROE / ROIC, cari oran,
  borç / özkaynak, net borç, faiz karşılama. Her oranda formül, girdiler ve hesaplanamama nedeni var. CLI:
  `python finansal_oranlar.py --companyfacts ... --as-of ... --out ...`.
- **Araştırma raporu:** `sirket_arastirma_akisi.py` JSON'a `financial_statements` ve `financial_ratios`
  ekler. HTML'de iki yeni bölüm var: hücre üzerinde XBRL kavramı, accession ve tarih; oran üzerinde formül
  görünür. Web arayüzündeki raporlar da bunları içerir. Eski raporlar sorunsuz açılır.
- **Belgeler:** [docs/FINANSAL_TABLOLAR_V01.md](docs/FINANSAL_TABLOLAR_V01.md),
  [docs/YOL_HARITASI.md](docs/YOL_HARITASI.md) (10 ders → modül → durum).
- **Testler:** 36 yeni test. Toplam `tests/` 389/389.

## 2026-10-24 — Bakım: yapı, CI ve dokümantasyon

- **`sec_arsiv.py` (yeni):** SEC arşiv/istek yardımcıları (`atomic_write`, `canonical_bytes`,
  `load_json`, `check_doc`, `cached_capture`, `save_capture`, `ticker_mapping`,
  `download_ticker_map`, `SECThrottle`, `StopSECRequests`, `iso_date`) `sec_toplu_tarama.py`
  içinden ortak, alt çizgisiz (public) bir modüle taşındı. `invest_ai_web.py`,
  `sec_finansal_degisim.py` ve `sec_degisim_raporu.py` artık başka modülün özel (`_`)
  fonksiyonlarını içe aktarmıyor. Davranış değişmedi.
- **Denetim kapısı uyarısı:** `sec_v02_bridge.value_sec_snapshot()` doğrudan çağrıldığında
  `UnauditedSECBaselineWarning` verir, çıktıya `"source_audit_gate": "bypassed"` ve bir uyarı
  satırı ekler. `sec_reviewed_pipeline` köprüyü yalnız denetim geçtikten sonra
  `source_audited=True` ile çağırır (`"passed"`). 2 yeni test.
- **CI:** `tests.yml` ve `python-tests.yml` tek iş akışında birleştirildi: Python
  3.11 / 3.12 / 3.13 matrisi; ana paket + v0.1 kabul + `test_dogrulama_seti` (önceden
  CI'da hiç çalışmıyordu) + `test_moduller_v02`. Ayrı `lint` işi: `ruff check .`
  (yalnız sözdizimi hatası ve kullanılmayan/tanımsız adlar).
- **`pyproject.toml` (yeni):** yalnız ruff ayarı; paketleme veya bağımlılık eklenmedi.
- **`BASLAT_TESTLER.bat`:** artık ana `tests/` paketini de çalıştırıyor ve sonunda tek
  satırlık genel sonuç basıyor.
- **Temizlik:** 14 kullanılmayan import ve 1 kullanılmayan değişken kaldırıldı.
  `sec_ttm.py`, `piotroski_fscore.py`, `kredi_notlari.py`, `sirket_kalite_cli.py`,
  `ttm_raporu.py`, `sirket_analiz_paneli.py` dosyalarında yalnız boşluk/hizalama düzeltildi
  (PEP 8 E2xx/E12x/E70x); AST karşılaştırmasıyla mantığın birebir aynı kaldığı doğrulandı.
  Donmuş v0.1 dosyalarına (`dogrulama/uretim_motoru.py`, `dogrulama/referans_motor.py`)
  dokunulmadı.
- **Metodoloji notları:** `degerleme_v02.py` içinde yıl ortası iskontoda uç değerin yine
  `n` ile iskontolandığı açıkça yazıldı. Piotroski varlık devir hızında ortalama varlık
  kullanımının orijinal tanımdan (dönem başı varlık) sapma olduğu
  `docs/PIOTROSKI_KREDI_KATMANI_V01.md` ve kodda belirtildi. Hesaplar değişmedi.
- **README** kısa bir genel bakışa indirildi; tarihli bölümler bu dosyaya taşındı.

## Önceki sürüm notları (README'den taşındı)

### Tahmin Defteri v0.1 (yeni)

`tahmin_defteri.py` yalnızca Python standart kütüphanesi ve SQLite kullanır. Kaynak gösterilerek kaydedilen tahminleri, daha sonra açıklanan gerçekleşen değerleri ve mutlak/imzalı tahmin hatalarını **ayrı, eklemeli kayıtlar** olarak saklar. Kayıtlar SQL tetikleyicileriyle güncelleme/silmeye karşı korunur. Bu, dosyaya erişen kötü niyetli birinin veritabanını değiştiremeyeceği anlamına gelmez; kriptografik değiştirilemezlik veya dış zaman damgası sağlamaz.

Çalıştırma: `python -m unittest discover -s tests -v`

Bu modül `degerleme_kaydi.py` aracılığıyla değerleme motorlarına bağlanmıştır. GitHub Actions koşusu henüz doğrulanmış değildir. Test girdileri sentetiktir. Değerlendirme şu anda mutlak hata ve imzalı hatadır; olasılık kalibrasyonu ve ölçeğe duyarlı skorlar daha sonra eklenecektir.


### DCF → Tahmin Defteri entegrasyonu

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

### v0.2 alpha — deterministik DCF + ters DCF

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



### SEC Company Facts — tarihli gerçek finansal veri altyapısı (yeni)

**Yeni modüller:** `sec_companyfacts.py` ve `sec_v02_bridge.py`. ABD SEC'nin Company Facts XBRL API'sinden yalnız USD birimindeki seçilmiş 10-K / 10-K/A yıllık muhasebe olguları alınır. Her satır açıklanma tarihi (`filed`), dönem başı/sonu (`start/end`), accession, XBRL kavramı ve kaynak URL'siyle korunur. `--as-of` filtresi, geçmiş bir analiz tarihinde henüz yayımlanmamış bilgilerle hesaplama yapılmasını engeller.

**DCF bağlantısı:** Son ortak tarihsel gelir ve EBIT kaydından `gelir_0` ve `marj_0` çıkarılır; büyüme, iskonto, hedef marj, terminal varsayımlar, hisse adedi ve net borç kaynakları kullanıcı tarafından belirtilmeden değerleme oluşturulmaz. CFO - CapEx, FCFF sanılmaz. Bu modül sadece SEC yıllık XBRL verisini kapsar; **InvestingPro, canlı fiyat, sektör araştırması veya otomatik yatırım önerisi içermez.**

[SEC kurulum, komutlar, sentetik örnek ve sınırlamalar](docs/SEC_INTEGRASYON.md)

Test komutu: `python -m unittest discover -s tests -v`. SEC modülleri için yerelde **20/20 sentetik test başarılı**. Gerçek şirket verileriyle kapsamlı kontrol ve GitHub Actions sonuç doğrulaması ayrıca gereklidir.


### SEC kaynak kalite kapısı ve v0.2 tahmin kaydı (20.10.2026)

Yeni, korunmalı veri akışı:

`SEC ham Company Facts` → `sec_gap_audit.py` (dönem/kaynak/çelişki) → `sec_v02_bridge.py` → `degerleme_v02.py` → `sec_reviewed_pipeline.py` → `tahmin_defteri.py`.

- 117 yerel SEC dosyasının yeniden denetiminde **86** şirket yalnızca ön incelemeyi geçti; **31** şirketin manuel kontrol gerektirdiği saptandı. Bunların **7** tanesinde birden fazla yıllık gelir etiketi arasında %5'ten büyük tutar ayrışması var.
- `sec_gap_audit.py`: kaynak ve mali yıl uyuşmazlığını ayrı raporlar; IFRS/eksik EBIT/pozitif olmayan geliri uydurma verilerle doldurmaz.
- `sec_reviewed_pipeline.py`: yalnız kaynak denetimini geçen ham SEC verilerinden deneysel v0.2 DCF üretip gelir, EBIT ve FCFF tahminlerini **kaynaklı, dönemli SQLite kayıtlarına** dönüştürür. Eski doğrudan `sec_v02_bridge.py` kullanımı **bu yeni denetim kapısını atlar**; yeni araştırmalarda korumalı akışı tercih edin.
- `sec_reviewed_cli.py`: bu akışı dosyalar üzerinden çalıştırır. Kullanıcı tüm gelecek varsayımları ve gelecekteki **mali yıl bitiş tarihlerini** verir; sistem bunları kendiliğinden tahmin etmez.
- Denetim, kaynak ve kullanım ayrıntısı: [docs/SEC_KAYNAK_DENETIMI_V02.md](docs/SEC_KAYNAK_DENETIMI_V02.md).

Test komutu: `python -m unittest discover -s tests -v`. Yerelde SEC modülleri için sentetik dosyalar ve SQLite uyumlu bir test adaptörüyle **38/38 test** geçmiştir. **GitHub üzerindeki gerçek tahmin defteriyle yeni CI sonucu henüz onaylanmamıştır**. Üretime hazır veya yatırım tavsiyesi değildir.


### SEC 10-K gelir etiketi mutabakatı — yedi araştırma adayı (2026-10-20)

Yedi şirketin resmî 10-K tablolarında konsolide gelir satırı araştırıldı ve yerel SEC Company Facts XBRL arşivinde **7/7 CIK / mali dönem / accession / tutar eşleşmesi** bulundu. Kanıtlar ve tutarlar: [SEC 7 gelir mutabakatı](docs/SEC_7_GELIR_MUTABAKATI.md); makine-okunur **onaylanmamış** adaylar: [evidence/sec_2026_revenue_review_candidates.json](evidence/sec_2026_revenue_review_candidates.json).

**Önemli:** Birincil kaynak araştırması, yetkili analistin imzaladığı muhasebe incelemesiyle aynı şey değildir. Aday JSON'un `status` alanı `proposed_requires_human_signoff` olduğu için sistem **bu 7 şirket için değerleme kilidini açmaz**. Kaynak okunup doğrulandıktan sonra `sec_revenue_reconciliation.py`, açıkça `approved` ve kaynak alanları dolu bir incelemeyi SEC XBRL verileriyle karşılaştırabilir.

`sec_reviewed_pipeline.analyze_and_record(..., revenue_review=...)` ve `sec_reviewed_cli.py --revenue-review approved_review.json` ile bu karar kayıt altına alınır. Yeni testler doğru onay, yanlış şirket, yanlış yıl, yanlış accession, yanlış tutar, sahte kaynak adresi ve eksik EBIT gibi durumları kapsar. Asıl GitHub CI sonucu ayrıca doğrulanmalıdır.

Veri sınırı: 117 şirketin ilk örnekleminde 86 aday daha önce teknik ön kontrolden geçiyordu; 7 kaynak açıklaması bulunsa bile **31 manuel inceleme gerektiren şirketin sayısı yetkili onay olmadan azaltılmaz**. Kalan 24 dosya başka veri sorunları yüzünden ayrıca incelenecek.


### Finansal kalite: Piotroski F-Score + kredi notları (v0.1)

`piotroski_fscore.py` SEC 10-K/10-K/A yıllık US-GAAP olgularından dokuz Piotroski göstergesini hesaplar. Eksik/kapsamı çelişen veri **0 puana dönüştürülmez**: `score=null`, `score_range=[alt,üst]`, `missing_reasons` ile raporlanır. Banka/sigorta ve doğrulanmamış sektörleri otomatik sıralamayız. Sermaye ihracı göstergesi için hisse sayısı değişimine bakmak yerine tarihli ve kaynaklı manuel inceleme gerekir.

`kredi_notlari.py` Moody's, S&P, Fitch **uzun vadeli ihraççı notlarını** ayrı, append-only SQLite olay defterinde saklar. Yayımlanma tarihi, etki tarihi, kaynak URL ve görünüm korunur; not geri çekilmişse eski not etkin sayılmaz. **Kredi notlarından doğrudan WACC, Piotroski puanı veya hisse değerlemesi üretilmez.**

`sirket_kalite_cli.py` bu iki kalite görünümünü tek JSON raporunda **birleştirmeden yan yana** sunar:

```bash
python sirket_kalite_cli.py report --companyfacts companyfacts.json --as-of 2026-10-21 --sector non_financial --out kalite_raporu.json
```

Ayrıntılı sözleşme, 9 gösterge, kredi notu girişi, veri sınırlamaları ve testler: [Piotroski + kredi modülü rehberi](docs/PIOTROSKI_KREDI_KATMANI_V01.md).

**Doğrulama:** Geliştirme ortamında 23 sentetik birim testi başarılıdır. GitHub Actions sonuçları ayrıca kontrol edilmelidir. Bu muhasebe testi geçmiş fiyat performansı/gelecek getirisi doğrulaması değildir.


### Piotroski SEC veri kalitesi v0.2 (21 Ekim 2026)

- `piotroski_fscore.py` artık `GrossProfit` doğrudan bildirilmediğinde, **aynı SEC accession ve mali dönemdeki** gelir eksi `CostOfGoodsAndServicesSold` / `CostOfRevenue` / `CostOfGoodsSold` üzerinden kaynaklı brüt kâr türetebilir.
- `LongTermDebt` (kısa vadeli kısmı da içerebilir) doğrudan `LongTermDebtNoncurrent` ile eşit sayılmaz. Sadece aynı belgede `LongTermDebtCurrent` de bulunuyorsa çıkarım yapılır. Eksik borç sıfır kabul edilmez.
- Alternatif maliyet veya borç mutabakatları %0,5 üzerinde farklıysa ilgili Piotroski sinyali bilinmeyen kalır.
- Yerel 117 SEC şirket örnekleminde brüt kâr marjı sinyalindeki eksik sayısı **61→40**, borç kaldıraç sinyalindeki eksik sayısı **66→60** olarak değişti. Borçta 20 yeniden hesaplanabilir, 14 önceki güvensiz hesap ise reddedildi. **Bu bir veri kapsama raporudur, hisse başarı testi değildir.**
- Kaynak ve test yöntemleri: [docs/PIOTROSKI_SEC_VERI_ESLEME_V02.md](docs/PIOTROSKI_SEC_VERI_ESLEME_V02.md). Yeni doğrulama testleri: `tests/test_piotroski_coverage_v02.py`. Eski kuralların hesapları değişebildiği için önceki F-Score raporları yeniden üretilmelidir.

Yerel geliştirme sürümünde toplam 50 birim testi başarılıdır; GitHub Actions sonucunu ayrıca teyit edin. Özellikle TSMC gibi IFRS/20-F şirketler bu modülün mevcut kapsamı dışındadır.


### Şirket araştırma paneli v0.1

Yeni `sirket_analiz_paneli.py` statik ve internet gerektirmeyen **HTML şirket raporu** üretir. Piotroski'nin 9 ayrı koşulu, manuel kaynaklı Moody's / S&P / Fitch ihraççı notları ve opsiyonel deneysel SEC DCF çıktısı birbirinden ayrılır; **birleşik yatırım puanı yoktur**.

```bash
python sirket_analiz_paneli.py --quality kalite.json --valuation dcf.json --out rapor.html
```

`--valuation` isteğe bağlıdır. Aynı CIK eşleşmesi, HTML karakter kaçışı, eksik F-Score'un kesin puana dönüşmemesi ve kredi notlarından değerleme üretilmemesi korunur. Kullanım ve sınırlamalar: [docs/SIRKET_ANALIZ_PANELI_V01.md](docs/SIRKET_ANALIZ_PANELI_V01.md). Testler `tests/test_sirket_analiz_paneli.py` içindedir. Yeni yerel geliştirme test seti **58/58** başarılıdır; bu sayı GitHub CI veya gerçek yatırım başarısı garantisi değildir.


### İlk gerçek SEC şirket pilotu — Apple (FY2025)

Çevrimdışı kaynak izi korunmuş **gerçek şirket** pilotu eklendi: `gercek_sirket_pilotu.py`, `tests/test_gercek_sirket_pilotu.py`, [Apple teknik raporu](docs/APPLE_GERCEK_SEC_PILOTU.md), [Apple sonuç JSON](reports/Apple_SEC_Piotroski_2026-10-21.json) ve [Apple HTML paneli](reports/Apple_SEC_Piotroski_2026-10-21.html).

21 Ekim 2026 bilgi kesme tarihinde 18 Ekim tarihli **yerel SEC arşivinden** alınan Apple FY2025 10-K verilerinde Piotroski'nin 9 göstergesinden **8'i hesaplanabildi**: 7 olumlu, 1 olumsuz, sermaye ihracı kanıtı eksik. Sonuç **kesin puan değil, 7–8 aralığıdır**. Gerçek veri 31 Ekim 2025 tarihli 10-K ile dönem/tutar düzeyinde çapraz kontrol edilmiştir: [SEC resmî 10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm).

Örnek kullanım:

```bash
python gercek_sirket_pilotu.py --companyfacts CIK0000320193_AAPL.json --expected-cik 0000320193 --sector non_financial --as-of 2026-10-21 --expected-fiscal-end 2025-09-27 --out-json apple.json --out-html apple.html
```

Ham SEC JSON depoya eklenmedi; veri kaynağı [SEC Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json). Yerel arşiv SHA-256 özeti, kullanılan finansal olguların accession/kavram/dosyalama tarihleri JSON raporunda saklı. **Bu canlı fiyat takibi, güncel 2026 tam yıl bilançosu, doğrulanmış kredi notu veya DCF hedef fiyatı değildir.** Kaynaklı ileriye dönük varsayımlar olmadan DCF üretilmez.

`python -m unittest discover -s tests -v` yeni pilota ait çevrimdışı regresyon testlerini de keşfeder. Yerel kalite bileşenleriyle **31 test** geçti. **GitHub'daki birebir sürüm üzerinde CI durumu henüz teyit edilmedi**; test sayısını tüm depo onayı gibi değerlendirmeyin.


### Apple: kaynaklı üç senaryolu DCF ve ters DCF örneği (21 Ekim 2026)

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


### TTM Finansal Motoru — 23 Ekim 2026

`ttm_finansallar.py`: US-GAAP 10-K yıllık FY + 10-Q Q3 dokuz aylık YTD − karşılaştırmalı önceki dokuz aylık YTD üzerinden kaynaklı son 12 ay (TTM) hesaplar. `filed` kesme tarihi, SEC accession, mali yıl başlangıcı/bitişi, birim ve çelişkili gelir etiketleri koruma altındadır. CFO−CapEx **FCFF olarak kullanılmaz**.

`ttm_dcf_bridge.py`: TTM gelir/EBIT tabanını v0.2 deneysel DCF'ye bağlar; yıllık/ara dönem bildirimleri, CIK, bilanço, hisse adedi ve varsayımların tarih/kaynak mutabakatını zorunlu tutar. `ttm_raporu.py`: internetsiz HTML rapor üretir. **Gerçek Apple SEC toplamlarından elle hazırlanmış (ham SEC API dosyası olmayan) demonstrasyon:** `ornekler/apple_ttm_evidence_2026-10-21.json`.

Apple'ın 21 Ekim 2026 bilgi kesitinde TTM: **466,823 milyar USD gelir**, **154,859 milyar USD EBIT**, **146,724 milyar USD CFO**, **10,041 milyar USD CapEx**. Aynı eski varsayımlar korunarak yapılan stres testindeki hisse başı değerler: **80,88 / 149,46 / 273,18 USD**. Bunlar yatırım tavsiyesi veya güvenilir hedef fiyat değildir.

Kullanım, kaynak ve sınırlamalar: [docs/TTM_FINANSAL_MOTORU_V01.md](docs/TTM_FINANSAL_MOTORU_V01.md). Yeni TTM, DCF köprüsü ve HTML testleri: `tests/test_ttm_finansallar.py`, `tests/test_ttm_dcf_bridge.py`, `tests/test_ttm_raporu.py`. Yerelde **39/39 TTM paketi testi başarılı**; GitHub Actions sonucu ayrı doğrulama gerektirir.


### SEC TTM finansal akış motoru v0.1

`sec_ttm.py`, ham SEC Company Facts verisinden **TTM = FY + güncel mali yıl YTD − önceki mali yılın karşılaştırılabilir YTD'si** formülüyle gelir, EBIT, faaliyet nakit akışı ve CapEx hesaplar. Yalnız US-GAAP / USD / 10-K / 10-Q kapsamındadır; açıklanma tarihini, SEC accession numarasını ve kullanılan üç kaynak olgusunu saklar. Tek çeyrek tutarını dokuz aylık toplam diye kabul etmez.

Apple'ın Haziran 2026 sonunda biten TTM kontrolü: **466,823 milyar USD gelir**, **154,859 milyar USD EBIT**, **146,724 milyar USD faaliyet nakit akışı**, **10,041 milyar USD CapEx**. Bunlar 18 Ekim tarihli yerel arşivdeki kayıtlarla hesaplanmıştır; daha yeni bildirimin yokluğu kanıtlanmış değildir. `CFO - CapEx` otomatik olarak FCFF değildir. Bağımsız testlerde 12/12 başarı; GitHub Actions sonucu ayrıca teyit edilmeli.

Komutlar ve kaynak mutabakatı: [docs/SEC_TTM_V01_APPLE.md](docs/SEC_TTM_V01_APPLE.md). TTM'nin tek başına DCF'yi otomatik ve güvenilir hedef fiyata dönüştürmediğine dikkat edin.


### SEC TTM çift motor mutabakatı (24 Ekim 2026)

`sec_ttm_crosscheck.py`, aynı ham SEC Company Facts JSON'u üzerinde `ttm_finansallar.py` ve `sec_ttm.py` hesaplarını karşılaştırır. Gelir, EBIT, CFO, CapEx tutarlarının yanı sıra dönem başlangıcı/bitişi, filing tarihi, SEC accession ve XBRL kavramı eşleşmelidir. Fark varsa otomatik mutabakat engellenir. Resmî SEC indirme isteğe bağlıdır; internet gerektirmeyen dosya modu ve indirilen ham JSON'u saklama seçeneği vardır. **Bu kontrol, ham dosyanın gerçekliğini bağımsız doğrulamaz; CFO-CapEx FCFF değildir; otomatik DCF üretmez.**

Windows PowerShell'de (iletişim adresinizi değiştirin):

```powershell
$env:SEC_USER_AGENT = "INVEST_AI Research your-real-email@example.com"
python sec_ttm_crosscheck.py --cik 320193 --as-of 2026-10-24 --download --snapshot-out apple_companyfacts_raw.json --out apple_ttm_audit.json
```

Sözleşme, çevrimdışı çalışma, hata durumları ve testler: [SEC TTM çift motor rehberi](docs/SEC_TTM_CROSSCHECK_V01.md).


### Portföy Risk Motoru v0.1 — kesirli hisseler ve AI yoğunlaşması

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


### Tek komutla genel şirket araştırması — v0.1 (24 Ekim 2026)

**Yeni:** `sirket_arastirma_akisi.py`, portföy adetleri veya kişisel işlem geçmişi gerektirmeden **SEC Company Facts kapsamındaki tek bir şirketi** analiz eder. Halihazırdaki `sec_gap_audit.py` (yıllık kaynak kontrolü), `piotroski_fscore.py` (9 gösterge), `kredi_notlari.py` (opsiyonel manuel ihraççı notları), `sec_ttm_crosscheck.py` (iki ayrı TTM hesap motoru) ve `sirket_analiz_paneli.py` (Türkçe HTML) bileşenlerini tek iş akışında birleştirir.

Eksik veya çelişkili kaynak **kısmi araştırma raporunda belirtilir**; bilinmeyen F-Score kesin sayıya, TTM noksanlığı sıfıra, geçmiş finansallar otomatik hedef fiyata çevrilmez. CIK, sektör sınıflandırması, bilgi tarihi ve isteğe bağlı mali yıl sonu açıkça denetlenir. Çıktı hem kaynakları koruyan JSON hem de internet gerektirmeyen HTML'dir. Ücretsiz Python standart kütüphanesini kullanır.

Depodaki **manuel SEC aktarımı** Apple örneğiyle çevrimdışı kullanım:

```powershell
python sirket_arastirma_akisi.py --cik 320193 --as-of 2026-10-21 --sector non_financial --companyfacts ornekler/apple_ttm_evidence_2026-10-21.json --out-json reports/apple_research.json --out-html reports/apple_research.html
```

Bu Apple dosyası gerçek ham API indirmesi değildir, **manuel transkripsiyon** olarak raporlanır. Bir SEC API dosyası doğrudan indirilecekse gerçek iletişim e-postası içeren `SEC_USER_AGENT` ve arşivlemek için `--snapshot-out` zorunludur.

[Genel şirket araştırma rehberi, durum sözleşmeleri ve sonraki ürün aşamaları](docs/SIRKET_ARASTIRMA_AKISI_V01.md).


### SEC Çoklu Şirket Toplama ve Tarama v0.1 (24 Ekim 2026)

Yüzlerce farklı **SEC CIK** için `sec_toplu_tarama.py` ile tarihli ham Company Facts arşivi oluşturma, içerik hash'iyle eski sürümleri koruma, önbellekten yeniden kullanma, SEC ticker–CIK eşlemesini kontrol etme ve `sirket_arastirma_akisi.py` üzerinden her şirket için JSON/HTML araştırması üretme desteği eklendi.

Kişisel portföy adetleri, alış fiyatları veya al/sat önerileri kullanılmaz. Sektör kodu açık analist girdisidir; bilinmiyorsa `unknown` kalır. Puanı oluşturulamayan şirketler yanlışlıkla sıfır skor almaz. Bankalar, IFRS/20-F ve SEC açıklama dipnotlarının manuel mutabakatı ayrıca geliştirilmelidir.

- SEC Fair Access: varsayılan 1 istek/saniye ve en fazla 2 istek/saniye; 403/429 ile erişim engeli görülürse sonraki SEC istekleri durur.
- Kaynak arşivi: `CIKXXXXXXXXXX/<sha256>.json` ve en son yakalama işaretçisi; ham dosya SHA-256 doğrulanmadan analiz edilmez.
- Üç çıktı katmanı: ham arşiv, şirket başına SEC araştırma JSON/HTML, tüm şirketler için tarama JSON/CSV özeti.
- İndirme yapmadan aynı arşivi yeniden analiz eden `--offline` modu vardır.

**Dört genel şirketli örnek evren:** `ornekler/sec_tarama_evreni_4_sirket.json` (AAPL, MSFT, NVDA, JPM). Dosya özel portföy değildir.

**[Kurulum, Windows komutları, SEC verisi ve erişim sınırları](docs/SEC_TOPLU_TARAMA_V01.md).**


### SEC Finansal Değişim ve Düzeltme Gözlem Motoru v0.1

**Yeni** `sec_finansal_degisim.py`, aynı SEC CIK şirketinin **iki farklı zamanda alınmış ham SEC Company Facts arşivini**, aynı bilgi kesme tarihinde (as-of) karşılaştırır. SEC accession, form, mali dönem başı/sonu, yayımlanma tarihi ve XBRL kavramını koruyarak eklenen/kaybolan/değişen kayıtları kaynaklarıyla listeler. Bir 10-Q/A kaydını otomatik kesinleşmiş finansal restatement olarak adlandırmaz; manuel inceleme işareti verir.

Ayrıca mevcut `sec_ttm_crosscheck.py` mutabakatını kullanarak, **aynı mali dönem** için TTM değer revizyonunu gerçek dönem büyümesinden ayırır. Son SEC dosyasının karşılaştırılabilir **9 aylık YTD** verileri üzerinde gelir, EBIT, CFO, CapEx yıllık nominal USD değişimini ve faaliyet marjındaki yüzde puan farkını hesaplar. Bu sonuçlar üçüncü çeyrek tek başına büyüme veya otomatik gelecek tahmini değildir.

`sec_degisim_raporu.py`, JSON'u tamamen çevrimdışı **Türkçe HTML değişim raporuna** dönüştürür. Harici JS/CSS, ücretli hizmet veya canlı fiyat yoktur.

~~~powershell
python sec_finansal_degisim.py --old eski_companyfacts.json --new yeni_companyfacts.json --cik 320193 --as-of 2026-10-24 --out reports/degisim.json
python sec_degisim_raporu.py --report reports/degisim.json --out reports/degisim.html
~~~

**[Teknik kılavuz: olay tanımları, SEC kaynakları, dönem eşlemesi ve sınırlamalar](docs/SEC_FINANSAL_DEGISIM_V01.md).**


### INVEST_AI Ana Sayfa (Codespaces ve yerel geliştirme)

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


### Web üzerinden doğrudan şirket araştırması — v0.2

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
