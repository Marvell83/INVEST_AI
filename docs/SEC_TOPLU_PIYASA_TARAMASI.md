# INVEST_AI v0.6 — SEC tüm şirket finansallarını topluca alma ve süzme

## Başlatma (tarayıcıdan)

1. Codespaces'te `git pull --ff-only origin main`.
2. Gerçek e-posta adresinle `export SEC_USER_AGENT="INVEST_AI Research GERCEK_ADRES@ALAN.COM"`. Bu e-postayı sohbetlere / GitHub dosyalarına yazma.
3. `python3 invest_ai_web.py`. Mevcut sunucuyu önceden Ctrl+C ile durdur; 8000 portunu PRIVATE tut.
4. Web → **Analiz çalıştır** → sunucunun ürettiği **Web analiz anahtarı**.
5. **Tüm SEC finansallarını indir ve tara** düğmesi; tek seferlik **resmî SEC `companyfacts.zip` arşivini** ve SEC ticker haritasını alır, yerel SQLite'a işler.
6. Durum satırında toplam, işlenen şirket sayısı, kaynakta veri eksikliği ve hatalar görülür. İşlem tamamlandığında **Temel analiz tablosu** düğmesine bas, sütunları seç ve alt/üst eşikleri koy. Filtreleri `CSV indir` ile Excel'de aç.

**Not:** SEC toplu ZIP sıkıştırılmış olarak 2026 sonbaharında yaklaşık **1,4 GB** ve büyüyebilir. İndirme başlamadan **en az 4,5 GB boş disk** kontrol edilir. Dosyaların hepsi dizine tek tek çıkarılmaz; ZIP doğrudan okunur. Bu, ücretli API/GPU gerektirmez. Kod tek bir resmi arşivi indirir, her hisse için ayrı SEC API çağrısı göndermez.

## Terminal alternatifi

```bash
cd /workspaces/INVEST_AI
export SEC_USER_AGENT="INVEST_AI Research GERCEK_ADRES@ALAN.COM"
python3 sec_piyasa_toplu_tarama.py --root .
```

Yalnız mevcut şirketler için örnek işleme denemesi: `python3 sec_piyasa_toplu_tarama.py --root . --limit 100`. Daha sonra sınırsız komut aynı arşiv ve as-of tarihiyle tamamlanmayan CIK'lerden devam eder. **Farklı güne geçildiğinde bilgi kesme tarihi değiştiği için veriler yeniden hesaplanabilir**; aynı gün yarım kalan iş yeniden başlatılabilir. Yerel olarak indirilmiş ZIP için `--zip /dosya/yolu/companyfacts.zip` kullanılabilir.

Dosyalar:
- `veri/companyfacts.zip`: SEC gece güncellenen büyük arşiv.
- `veri/companyfacts.zip.part`: kesilmiş HTTP indirmesi; SEC Range destekliyorsa devam.
- `veri/sec_ticker_esleme.json`: SEC şirket ticker–CIK dizini.
- `veri/invest_ai_evren.sqlite3`: şirket bazında işlem durumu, tarihli finansal tablo/rasyo sonucu, eksik nedenleri.

Tüm bunlar `.gitignore` altındadır; GitHub'a yüklenmez. Codespaces depolaması kalıcı olabilir ancak ortamın silinmesi arşivi de silebilir. Sunucunun Ctrl+C ile kesilmesi çalışan işçi thread'ini de durdurur; yeniden başlatınca aynı veri ve aynı kesme tarihi kapsamındaki iş tamamlanmamış şirketlerden sürdürülür.

## 8.024 kayıt tarandığında ERROR sayısına nasıl bakılır? (v0.6.1)

İşlenen toplam kayıt ile başarılı şirket sayısı aynı değildir. Örnek: `{"OK":5003,"ERROR":2020,"NO_COMPANYFACTS":1001}` olduğunda yalnız **5.003** kayıt için desteklenen finansal tablo/rasyo sonucu çıkmış demektir. `NO_COMPANYFACTS`, SEC ZIP içinde eşleşen CIK dosyasının bulunmamasıdır; tek başına yazılım hatası olduğu veya hisse kötü olduğu anlamına gelmez. `ERROR` ise ayrıntı incelemesi gerektirir.

**Veritabanını silmeden teşhis:**

```bash
cd /workspaces/INVEST_AI
python3 sec_piyasa_toplu_tarama.py --diagnose
```

Komut yalnız SQLite'ı okur; SEC'ye bağlanmaz. `status_counts`, `error_reasons`, `error_examples`, kayıt tarihi ve arşiv imzası gösterilir. Eski v0.6 kayıtlarında hata mesajları yalnız `ValueError`, `TypeError` gibi genel etiketler içerir.

**İlk 20 ERROR şirketini yeniden dene ve hata ayrıntısını kaydet:**

```bash
python3 sec_piyasa_toplu_tarama.py --retry-errors --limit 20
python3 sec_piyasa_toplu_tarama.py --diagnose
```

Bu işlem var olan `veri/companyfacts.zip` arşivini kullanır. **5.003 OK ve 1.001 NO_COMPANYFACTS kaydı yeniden hesaplanmaz veya silinmez.** İndirme yapmaz; `SEC_USER_AGENT` tekrar zorunlu değildir. Hata çözülmeden `--retry-errors` ile bütün 2.020 hatayı tekrarlamak ek fayda sağlamaz.

Hatanın hangi kavram/tarih/türden kaynaklandığı doğrulandıktan sonra belirli hesaplama/normalizasyon kuralı düzeltilir. Ardından aynı arşivde `python3 sec_piyasa_toplu_tarama.py --retry-errors` tüm kalan ERROR kayıtlarını yeniden işler. **Farklı SEC arşivi veya farklı kesme tarihi** kullanılırsa hata kayıtları korunarak yeniden deneme yapılmaz; bu durumda yeni kaynak kesiti için ayrı veri yenileme gerekir.

## Desteklenen yıllık 10-K verisi olmayan şirketler — veri kapsamı düzeltmesi

Bazı SEC dosyalayıcılarında `companyfacts.zip` içinde CIK'ye ait dosya **vardır**, ancak INVEST_AI'nin kullandığı **US-GAAP/USD, 10-K mali yıl** veri yapısı yoktur. Eski kod `ValueError: Failed to construct financial ratio row` üretip bunları yanlışlıkla `ERROR` sayıyordu. Artık bu şirketler `NO_SUPPORTED_ANNUAL_DATA` durumuna alınır.

- `NO_US_GAAP_NAMESPACE`: SEC şirket JSON'unda desteklenen `us-gaap` verileri bulunmadı.
- `NO_ELIGIBLE_US_GAAP_10K_FISCAL_YEAR`: `us-gaap` verileri bulunuyor ancak seçilen bilgi kesme tarihine göre uygun 10-K mali yılı çıkarılamadı.
- `NO_COMPANYFACTS`: SEC arşivinde eşleşen CIK JSON dosyası yok; farklı bir durumdur.
- `ERROR`: Gerçek hesaplama/doğrulama hataları ayrı tutulur.

### 2.020 eski hatayı güvenli biçimde yeniden sınıflandır

```bash
cd /workspaces/INVEST_AI
git pull --ff-only origin main
python3 sec_piyasa_toplu_tarama.py --retry-errors
python3 sec_piyasa_toplu_tarama.py --diagnose
```

Bu işlem **indirilmiş ZIP'i yeniden indirmez**, aynı snapshot as-of tarihini kullanır ve 5.003 başarılı şirketin finansallarını **yeniden işlemez**. Yeniden sınıflandırma tamamlandıktan sonra **Temel analiz tablosu** ekranını yenile; `Finansal kapsam` sütunu ve `SEC finansal kapsama durumu` filtresi üzerinden hangi şirketlerin finansallarının mevcut olduğunu görebilirsin.

Bu bir veri kapsamı sınıflandırmasıdır, IFRS/20-F ve fonlar için yeni hesaplama desteği değildir. Gerçek analiz edilebilir şirket sayısı ancak işlemin sonuç raporu alındığında netleşir.

## SEC ZIP ile JSON içeriğindeki CIK farklıysa (v0.6.3)

İlk gerçek 25 Ekim 2026 arşivinde 8.024 şirkete ait son durum:
5.003 `OK`, 2.009 `NO_SUPPORTED_ANNUAL_DATA`,
1.001 `NO_COMPANYFACTS` ve 11 `ValueError: CIK mismatch between ZIP path and JSON`.

Bu 11 kayıt için finansallar **başka bir CIK'ye ait olabilir**. Yeni kod bu
kayıtları `SOURCE_CIK_MISMATCH` durumunda ayrı tutar; yanlış şirkete ROE,
ROIC veya diğer finansal oranları atamaz. Beklenen (ZIP yolundaki) CIK ile
SEC JSON içindeki CIK birlikte kaydedilir. Gerçek kaynak kimliği
doğrulanana kadar şirket **analiz edilmiş sayılmaz**.

Başarıyla işlenen 5.003 satırı silmeden yalnız eski 11 `ERROR` kaydını
yeniden sınıflandırmak için:

```bash
cd /workspaces/INVEST_AI
git pull --ff-only origin main
python3 sec_piyasa_toplu_tarama.py --retry-errors
python3 sec_piyasa_toplu_tarama.py --diagnose
```

Tanılama çıktısında `identity_mismatches` dizisi ZIP ve iç JSON kimliklerini
gösterir. `Temel analiz tablosu` → `SEC finansal kapsama durumu` filtresinde
`SEC kimlik uyuşmazlığı — denetim` seçeneği var.
`Kapsam ayrıntısı / SEC kimlik kontrolü` sütunu isteğe bağlı açılabilir.

**İlerleme sayacı düzeltmesi:** Önceki kod hata kayıtlarını yeniden
işlerken 8.024 toplam şirket sayısına ayrıca deneme sayısını ekleyip
10.024 / 8.024 gibi yanıltıcı ilerleme gösteriyordu. Yeni sürüm
`processed` alanını yalnız benzersiz CIK sayısından hesaplar;
`retry_attempted/retry_total` yeniden denemeyi ayrı izler.

Sıfır yeni indirme; aynı SEC ZIP, aynı `as_of` ve mevcut SQLite korunur.

## Sonuçların yorumu

SQLite/Excel finansal satırları şunları içerir: ROE, ROIC, ROA, gelir/kâr büyümesi, marjlar, CFO, nakit dönüşümü, FCF, net borç, borç/özkaynak, yaklaşık net borç/FAVÖK, faiz karşılama, CapEx, D&A, yıllık gelir/varlık/özkaynak/borç tutarları. Üç yıllık finansal geçmiş bulunursa çok yıllık büyüme ve CFO/FCF ölçümleri gösterilir.

**SEC ticker listesi yalnız CIK/ticker/dizin listesidir:** ETF, ADR, kapatılmış veya eski kayıtlar, halka açık olmayan dosyalayıcılar, pay sınıfları ve finansal veri yetersizliği ayrı incelenmelidir. Finansallar bir CIK için hesaplanır, aynı CIK'nin farklı pay sınıflarına ayrı ticker satırı açılır. Çok sınıflı şirketlerde sınıf bazında fiyat ve pay adedi otomatik doğrulanmadığı için fiyat çarpanları boş kalır.

**Önemli eksiklik:** SEC Company Facts **borsa fiyatı veya ileri EPS büyümesi** sağlamaz. Dolayısıyla ilk toplu aktarımda F/K, PD/DD, PEG, EV/EBIT, FCF Yield, ROE/10/PD/DD gibi piyasa çarpanlarını güvenilir biçimde otomatik üretemeyiz; bunlar veri yoksa **boş** kalır. Tam 7 koşulun hepsini geçen listeyi uydurmak yerine `VERİ BEKLİYOR` statüsü korunur. Fiyat kaynakları ve ileri EPS beklentileri sonraki veri katmanında eklenecek.

**ROIC yöntem uyarısı:** çok küçük yatırım sermayesi paydasında aşırı oranlar oluşur. Finans sektörlerinde banka/sigorta muhasebesi farklıdır; üniform genel ölçütlerle kesin olumlu sonuç çıkarmayız. SEC US-GAAP dışı IFRS/20-F kayıtlarında uygun standart finansallar bulunmayabilir.

## Kontrol

`python3 -m unittest discover -s tests -v`

Güncel SEC arşiv bağlantısı: [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · [resmî companyfacts.zip](https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip)


## Kapsam raporu ve yeniden hesaplama (v0.7)

**Hangi oran kaç şirkette dolu?** Veritabanını değiştirmeden:

```bash
python3 sec_piyasa_toplu_tarama.py --coverage
```

Çıktı Türkçedir ve yalnız `OK` şirketleri sayar:
- her sayısal sütunda değeri olan şirket sayısı ve yüzdesi,
- 7 koşulun her girdisinin kaç şirkette hazır olduğu; ROIC yalnız uyarısızsa sayılır,
- fiyat gerektirmeyen 5 girdinin (ROE, ROIC, net borç/FAVÖK, 3Y CFO/net kâr, 3Y FCF) hepsi dolu şirket sayısı,
- son mali yılı 456 günden eski (güncel olmayan) şirket sayısı,
- eski sürümle hesaplanmış ve yeni sütunları boş kalan satır sayısı.

**Yeni sütunlar için yeniden hesaplama (indirme yok):** Tabloya SEC'den türetilen yeni bir sütun eklendiğinde, daha önce işlenmiş satırlarda o sütun boş görünür. Aynı yerel `veri/companyfacts.zip` ve aynı bilgi tarihiyle bütün şirketleri yeniden hesaplamak için:

```bash
python3 sec_piyasa_toplu_tarama.py --rebuild
python3 sec_piyasa_toplu_tarama.py --coverage
```

- İnternete bağlanmaz, `SEC_USER_AGENT` gerekmez.
- Kesilirse aynı komut kaldığı yerden devam eder; o sırada tablo eski satırları göstermeye devam eder.
- Farklı bir ZIP veya farklı bilgi tarihiyle çalıştırılmaz; `--retry-errors` ile birlikte kullanılmaz.

## Fiyat ve değerleme çarpanları (v0.7)

SEC verisi fiyat içermez. Ücretsiz Nasdaq hisse tarayıcısı CSV'sini (veya `ticker,date,close` dosyasını) `fiyat_katmani.py` ile içeri aldıktan sonra tablo F/K, PD/DD, (ROE/10)/PD/DD, EV/EBIT, EV/FAVÖK*, FCF getirisi ve tarihsel PEG'i bütün şirketler için hesaplar. Adımlar ve eşleştirme kuralları: [TEMEL_ANALIZ_EXCEL_TARAYICI.md](TEMEL_ANALIZ_EXCEL_TARAYICI.md#fiyat-gerektirenler). Fiyattan önce bir kez `--rebuild` çalıştır: pay adedi tarihi ve FAVÖK* sütunları yeni satırlarda bulunur.

## Yalnız SEC verisiyle eleme raporu (v0.8)

Fiyat ve PEG olmadan, yalnız şirketlerin kendi SEC tablolarıyla kalite elemesi:

```bash
export SEC_USER_AGENT="INVEST_AI Research GERCEK_ADRES@ALAN.COM"
python3 sec_sirket_profili.py                 # SEC submissions.zip: SIC sektör kodu, borsa (bir kez)
python3 sec_eleme_raporu.py --rate 4.3        # 10 yıllık ABD tahvil getirisini kendin doğrula
```

- **Huni:** OK şirketler → son mali yılı güncel olanlar (456 gün) → finans / sigorta / gayrimenkul (SIC 6000–6799) hariç → yıllık gelir en az 50 milyon $ (`--min-revenue`) → 5 koşul.
- **5 koşul:** ROE > referans faiz, ROIC > referans faiz, net borç / FAVÖK* ≤ 2, 3 yıllık CFO / net kâr ≥ 1, 3 yıllık FCF > 0. Her biri geçti / elendi / veri bekliyor; eksik değer elenme sebebi değildir. Çok küçük sermaye nedeniyle uyarılı ROIC (! işareti) koşulu geçer ama işaretlenir.
- **Çıktı:** `reports/sec_eleme.html` (huni, koşul sayıları, sektör dağılımı, öne çıkanlar, geçenlerin tam listesi), `reports/sec_eleme.csv` (Excel, `;` ayraçlı), `reports/sec_eleme.json`.
- SEC profili (SIC) yoksa şirket "Sektör bilinmiyor" olarak dahil tutulur ve sayısı huni notunda yazar.

### İlk tam eleme sonrası düzeltmeler (v0.9)

İlk tam çalıştırma (25 Ekim 2026, referans faiz %4,3): 5.003 → 4.772 güncel → 3.642 finans dışı → 2.122 gelir ≥ 50 milyon $ → **222 geçti**, 1.231 elendi, 669 veri bekliyor. Liste incelenince bulunan sorunlar ve düzeltmeleri:

| Sorun | Düzeltme |
|---|---|
| Birden çok kodu olan şirkette alfabetik ilk kod seçiliyordu (Amcor `AMCCF`, MSA `MNESP`, Victoria's Secret `VSXY`) | SEC listesinin kendi sırası korunur; raporda SEC profilindeki NYSE / Nasdaq kodu kullanılır |
| Coca-Cola'nın ~42 milyar $ uzun vadeli borcu okunmuyordu (`LongTermDebtAndCapitalLeaseObligations`) | Bu etiket ailesi yedek etiket; `DebtCurrent` (kısa vadeli toplam) bildirilmişse kısa vadeli parçaların yerine kullanılır |
| FAVÖK amortismanı farklı etiketle bildiren şirketlerde yoktu (Microsoft tipi) | `DepreciationAmortizationAndOther`, `DepreciationAmortizationAndAccretionNet` yedek etiket |
| ROE %1.603 (Colgate) gibi küçük özkaynak değerleri | ROE %100'ün üstünde `VERY_SMALL_EQUITY` uyarısı, raporda ! |
| Hisse bölünmesi hisse adedi değişimini (Fastenal +%99,8) ve EPS CAGR'ı bozuyordu | SEC'e bildirilmiş bölünme 3 yıllık pencerede ise ikisi hesaplanmaz; bildirilmemiş ama 0,6–1,6 bandı dışındaki değişim ? ile işaretlenir |
| "Veri bekliyor"un nedeni görünmüyordu | Raporda her koşul için neden dökümü (ör. "amortisman bildirilmemiş", "hiç borç kalemi bildirilmemiş") |

Yeni sütunlar ve nedenler için bir kez `--rebuild`, kodlar için bir kez `python3 sec_sirket_profili.py` (ZIP zaten indirildiyse yeniden indirmez) çalıştırılır.
