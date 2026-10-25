# INVEST_AI — SEC Çoklu Şirket Veri Toplama ve Tarama v0.1

**Amaç:** Kişisel portföylerden bağımsız olarak yüzlerce ABD ihraççısını SEC ham Company Facts dosyalarından kaynaklı incelemek. **Ücretsiz Python 3.11+ standart kütüphanesi.**

## Resmî kaynaklar ve erişim

- SEC Fair Access: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- SEC Company Facts: https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json
- SEC ticker/CIK listesi: https://www.sec.gov/files/company_tickers.json

SEC, saniyede **en fazla 10 istek** ve uygulama adı + gerçek iletişim adresi bulunan User-Agent ister. Bizim modülümüz sırayla, varsayılan **bir istek/saniye** hızında çalışır. En hızlı ayar iki istek/saniyedir. Limit yalnız *bu süreçte* geçerlidir; aynı IP'nin diğer işlemlerini kapsamaz. HTTP 403/429 gelirse kalan istekler kesilir; farklı kimlikle engel aşma veya otomatik hızlı yeniden deneme yoktur.

## Windows PowerShell

Örnek evren: `ornekler/sec_tarama_evreni_4_sirket.json` — AAPL, MSFT, NVDA, JPM. JPM için manuel `financial` sektörü seçildiği için standart Piotroski puanı hesaplanmaz.

**A. Güncel SEC dosyalarını indirme, eşlemeyi saklama ve tarama**

Gerçek iletişim e-postanızı girin:

~~~powershell
$env:SEC_USER_AGENT = "INVEST_AI Research your-real-email@example.com"
python sec_toplu_tarama.py --universe ornekler/sec_tarama_evreni_4_sirket.json --as-of 2026-10-24 --online --download-ticker-map --ticker-map-out veri/sec_ticker_esleme.json --archive-dir veri/sec_kaynaklari --reports-dir reports/coklu --out-json reports/tarama_ozet.json --out-csv reports/tarama_ozet.csv
~~~

**B. Sıfır ağ trafiğiyle arşivdeki dosyaları tekrar kullanma**

~~~powershell
python sec_toplu_tarama.py --universe ornekler/sec_tarama_evreni_4_sirket.json --as-of 2026-10-24 --offline --ticker-map veri/sec_ticker_esleme.json --archive-dir veri/sec_kaynaklari --reports-dir reports/coklu --out-json reports/tarama_offline.json --out-csv reports/tarama_offline.csv
~~~

Yalnız ticker girilen şirketler için ticker–CIK haritası zorunludur. CIK ile ticker birlikte girilmişse harita bulunan her kayıtta eşleşmeleri denetlenir. Sadece CIK ile haritasız çalışılabilir; bu durumda ticker kimliği doğrulanmış kabul edilmez. Aynı CIK iki kez girilemez. Sektör etiketleri `non_financial`, `financial`, `unknown` arasından açıkça girilir; girilmezse `unknown`.

Evren biçimi:

~~~json
[
  {"ticker":"AAPL","cik":320193,"sector":"non_financial"},
  {"ticker":"MSFT","cik":789019,"sector":"non_financial"},
  {"ticker":"NVDA","cik":1045810,"sector":"non_financial"},
  {"ticker":"JPM","cik":19617,"sector":"financial"}
]
~~~

## Arşiv, bütünlük ve tekrarlanabilirlik

~~~text
veri/sec_kaynaklari/
  CIK0000320193/
    index.json
    <SHA256>.json
    <ONCEKI_SHA256>.json
~~~

Her ham Company Facts JSON'u önce SEC CIK ve temel yapı açısından kontrol edilir. Kanonik JSON baytlarının SHA-256 özeti dosya adına eklenir. **Hash, SEC elektronik imzası değildir.** Yeni içerik yeni dosyada saklanır; eski hash dosyası korunur. `index.json` son yakalama UTC zamanını, SEC URL'sini ve en yeni SHA-256 özetini tutar. Önbellek kullanılırken ham dosyanın SHA-256 değeri **yeniden doğrulanır**.

Güncel dosya varsayılan 24 saat önbellekte tutulur. Tekrar indirmeyi zorlamak için `--cache-ttl-hours 0` kullanılabilir. Bozuk SHA-256, geçersiz CIK veya eksik arşiv kaydı halinde sessizce başarılı analiz üretilmez. İndirilen ticker–CIK haritası da ayrıca dosyaya yazılır ve özeti rapora eklenir.

**Tarihsel kullanım sınırı:** 2026'da indirilen güncel SEC dosyasını `--as-of 2022-12-31` ile filtrelemek 2022 arşivinin eksiksiz kopyasını yaratmaz. Sadece dosyadaki `filed` tarihlerine göre bilgi sızdırma azaltılır; geçmiş arşiv bütünlüğü ve hisse getirisi tahmin doğruluğu kanıtlanmaz.

## Çıktı dosyaları

- `reports/tarama_ozet.json` ve `.csv`: şirket CIK/ticker, yıllık kaynak kontrol durumu, F-Score ve bilinmeyen aralık, TTM durumu, yakalama tarihi, SHA-256 ve araştırma dosyası yolları.
- `reports/coklu/CIK...json`: şirket bazlı araştırma verisi ve SEC kaynak izi.
- `reports/coklu/CIK...html`: internetsiz açılabilen Türkçe araştırma ekranı.
- `ANALYZED_CONTROLS_COMPLETE` yalnız tanımlı hesap denetimlerinin geçtiğini ifade eder; yatırım puanı değildir.
- `ANALYZED_PARTIAL` eksik muhasebe/kalite/TTM veya kaynak denetimi gösterir.
- `CACHE_MISS` çevrimdışı dosyanın bulunmadığını, `INPUT_OR_ANALYSIS_ERROR` veri hatasını, `SEC_ACCESS_RESTRICTED` erişim engelini gösterir.

Tüm şirketlerde fiyat, DCF, geleceğe dönük tahmin ve otomatik al-sat sonucu **boş** kalır. Bankalar için ayrı muhasebe yaklaşımı gerekir; IFRS/20-F bu sürüme dahil değildir.

## Gerçek veri kontrolü — katman sağlığı

Her şirket kaydında artık bir `layer_health` alanı var. Bu alan aynı zamanda CSV'de sütun olarak yer alır ve ortak finansal tabloların ve mutabakatın o şirkette nasıl çalıştığını özetler:

| Alan | Anlamı |
|---|---|
| `statement_years`, `latest_fiscal_year_end` | Bulunan yıllık 10-K yılı sayısı ve son mali yıl sonu |
| `statement_conflicts` | XBRL etiketleri birbirini tutmayan kalemler |
| `revenue_alias_bucket`, `revenue_alias_gap` | Son iki yılda gelir etiketleri arasındaki fark: `NO_REVENUE_CONFLICT` (%0,5'e kadar), `HALF_TO_FIVE_PERCENT` (Piotroski ve ortak tablolar öncelikli etiketi kullanır, fark raporda notla görünür), `ABOVE_FIVE_PERCENT` (ikisinde de çelişki) |
| `quarters` | Sınırları belirlenebilen çeyrek sayısı (en çok 8) |
| `shares_status` | Kapak sayfası hisse sayısı: `REPORTED`, `CONFLICT` (çok sınıflı hisse), `MISSING` |
| `piotroski_reconciliation`, `piotroski_attention` | Piotroski girdileri ↔ ortak tablolar ve fark çıkan girdiler |
| `shared_ttm_status`, `shared_ttm_end` | Ortak çeyreklerden TTM: `OK`, `PARTIAL`, `INSUFFICIENT_QUARTERS`; hangi çeyrek en son olursa olsun hesaplanır |
| `ttm_reconciliation` | Eski iki TTM motoru ↔ ortak TTM. Eski motorlar yalnız son dönem 9 aylık 10-Q olduğunda çalışır; diğer durumlarda `NOT_APPLICABLE` normaldir |
| `latest_operating_income` | Son yılın faaliyet kârı: `REPORTED`, `APPROXIMATE` (vergi öncesi kâr + faiz gideri), `MISSING` |
| `baseline_status` | Senaryolar için yeterli geçmiş var mı |
| `latest_ratios_available` | Son yılda hesaplanabilen oran sayısı (18 üzerinden) |

Özet JSON'da `layer_health_counts` alanı bütün şirketlerin sayımını verir. Komut sonunda da kısa bir Türkçe özet basılır.

**On bir tanınmış şirketle tek komutluk deneme.** Hazır liste `ornekler/gercek_veri_kontrol_evreni.json`; çok sınıflı hisse (GOOGL) ve banka (JPM) bilerek listede. SEC'in istediği iletişim adresini kendi e-postanla gir:

~~~bash
export SEC_USER_AGENT="INVEST_AI Research gercek-adresin@ornek.com"
python3 sec_toplu_tarama.py --universe ornekler/gercek_veri_kontrol_evreni.json --as-of 2026-10-25 \
  --online --archive-dir veri/sec_kaynaklari --reports-dir reports/gercek_kontrol \
  --out-json reports/gercek_kontrol.json --out-csv reports/gercek_kontrol.csv
~~~

Saniyede en fazla bir istek gider; 11 şirket yaklaşık 15 saniye sürer. Bir kez indirilen dosyalar `--offline` ile ağsız yeniden kullanılabilir.

**İlk gerçek veri denemesi (25 Ekim 2026) ve sonrasında yapılanlar**

| Bulgu | Düzeltme (tablolar v0.3) |
|---|---|
| Alphabet, J&J ve Coca-Cola'da hisse bazlı ödeme "çelişki" | `AllocatedShareBasedCompensationExpense` eşanlamlı listesinden çıkarıldı; yalnız nakit akışı tablosundaki `ShareBasedCompensation` okunur |
| Walmart'ta iki gelir etiketi %0,95 ayrışıyor (net satışlar / toplam gelir): yalnız 10 oran, yetersiz baz, Piotroski farkı | Gelir etiketlerinde %5'e kadar fark: öncelikli etiket + görünür not; %5 üstü çelişki. Piotroski ile aynı kural |
| J&J ve Exxon faaliyet kârı bildirmiyor: yetersiz baz | Yaklaşık faaliyet kârı = vergi öncesi kâr + faiz gideri (aynı dosya), ≈ ile işaretli |
| TTM 11 şirketin yalnız birinde | Ortak çeyreklerden TTM her çeyrekte; eski motorlar 9 aylık dönemde çapraz kontrol olarak kalır |
| Alphabet hisse sayısı yok (çok sınıflı) | Bilerek değişmedi: sınıflar toplanmaz, analist girer |
| JPM (banka) | Bilerek değişmedi: banka muhasebesi ayrı yöntem ister |

Aynı komutu yeniden çalıştırıp `layer_health_counts` sayımlarını önceki çıktıyla karşılaştırın. Beklenen: `statement_conflict_items` içinde `share_based_compensation` kalmaz, `shared_ttm_status` çoğunlukla `OK` olur, `latest_operating_income` J&J ve Exxon'da `APPROXIMATE` olur (faiz gideri bildiriyorlarsa).

## Testler

~~~powershell
python -m unittest discover -s tests -p test_sec_toplu_tarama.py -v
python -m unittest discover -s tests -v
~~~

GitHub testleri gerçek SEC ağına erişmeden **sentetik şirketler ve taklit ağ yanıtları** kullanır. Canlı SEC çoklu indirme kabul testini ayrıca yapmak gerekir.

## Sonraki ürün adımı

Yeni SEC bildirimleri geldikçe değişen kayıtları karşılaştırmak, kaynaklı dönem farklarını izlemek, şirketler arası karşılaştırılabilirlik filtreleri eklemek, analist onaylı metriklerden ROIC/sermaye verimliliğini çıkarıp hisse keşif motoruna hazırlamak.
