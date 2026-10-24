# INVEST_AI — Şirket Araştırma Akışı v0.1

**Geliştirme amacı:** Kişisel portföylerden bağımsız olarak, herhangi bir **SEC US-GAAP Company Facts** kapsamındaki şirketin tarihli yıllık verilerini ve varsa TTM sonuçlarını **tek komutla** araştırmak.

Modül: `sirket_arastirma_akisi.py`.

## Mimari

```text
Tek şirketin SEC Company Facts dosyası (ham JSON)
         │
         ├── CIK ve as_of bilgi kesme tarihi kontrolü
         │
         ├── sec_gap_audit.py
         │      └─ Yıllık gelir/EBIT kaynak kontrolü
         │
         ├── kredi_notlari.py + piotroski_fscore.py
         │      └─ Eksik sinyalleri [alt,üst] aralığında tutan F-Score
         │         + varsa kaynaklı manuel ihraççı kredi notları
         │
         ├── sec_ttm_crosscheck.py
         │      ├─ ttm_finansallar.py
         │      └─ sec_ttm.py
         │           └─ Tutar, dönem, SEC accession, yayımlanma tarihi mutabakatı
         │
         └── JSON araştırma nesnesi + çevrimdışı Türkçe HTML
                 └─ Kaynak tarihi, hesap sonuçları, eksikler, sınırlar
```

Kod mevcut muhasebe/DCF motorlarını değiştirmez. DCF çıktısı veya yatırım önerisi **kendiliğinden oluşturulmaz**. Finansal olmayan sektör varsayımı otomatik yapılmaz.

## Windows / PowerShell komutları

Depoyu klonladıktan veya ZIP olarak indirdikten sonra Python 3.11 veya üzeri yeterlidir. Yeni paket, ücretli abonelik, bulut GPU veya ek donanım gerektirmez.

### A. Hazır SEC Company Facts JSON dosyasından

```powershell
python sirket_arastirma_akisi.py --cik 320193 --as-of 2026-10-21 --sector non_financial --companyfacts ornekler/apple_ttm_evidence_2026-10-21.json --out-json reports/apple_arastirma.json --out-html reports/apple_arastirma.html
```

**Not:** Bu Apple örneği gerçek SEC 10-K ve 10-Q satırlarından *elle aktarılmış* bir demonstrasyondur; ham SEC API JSON dosyası değildir. Kaynak alanı `manually_transcribed_source=true` ve `INPUT_IS_MANUAL_TRANSCRIPTION_NOT_RAW_SEC_DOWNLOAD` uyarısı bunu korur. Bu örnekte TTM dönem hesabı mutabık olsa da geçmiş iki tam yıl Piotroski kapsamı sınırlıdır.

### B. SEC API'den tek şirkete doğrudan erişim (ücretsiz)

SEC User-Agent içinde gerçek iletişim e-postanız bulunmalıdır:

```powershell
$env:SEC_USER_AGENT = "INVEST_AI Research real-contact@example.com"
python sirket_arastirma_akisi.py --cik 320193 --as-of 2026-10-24 --sector non_financial --download --snapshot-out data/apple_companyfacts.json --out-json reports/apple_research.json --out-html reports/apple_research.html
```

Yukarıdaki adres **örnektir**, gerçek iletişim adresiyle değiştirilmelidir. Her çalıştırma en fazla bir Company Facts indirme isteği yapar; SEC'nin erişim politikası ve kullanım sınırlarına uyun. Canlı API verisi için `--snapshot-out` zorunludur; bu sayede araştırma tekrar üretilebilir. Kaydedilen SEC dosyasındaki `filed` tarihleri, kesme tarihinden sonraki kayıtları dışlar ancak o gün itibarıyla mevcut tüm bildirilerin arşivde olduğu garanti değildir.

**Kritik sınır:** 10-K/10-Q verilerini kullanan US-GAAP/USD odaklı akıştır. IFRS/20-F (ör. TSMC), özel sektör muhasebesi, finans kuruluşlarına özgü Piotroski, Q1/Q2 TTM, fiyat akışı, canlı haberler ve yatırım tavsiyesi **bu sürümde yoktur**.

## Girdi parametreleri

| Argüman | Amaç |
| --- | --- |
| `--cik` | SEC'de tekil şirket CIK numarası. JSON içindeki CIK ile eşleşmesi zorunlu |
| `--as-of` | Araştırmanın bilgi kesme tarihi, `YYYY-MM-DD` |
| `--sector` | `non_financial`, `financial` veya `unknown`; analist açıkça seçer |
| `--companyfacts` | SEC Company Facts uyumlu yerel JSON; `--download` alternatifi |
| `--download` | SEC'den bir dosya çek; `SEC_USER_AGENT` ve `--snapshot-out` gerekir |
| `--expected-fiscal-end` | İsteğe bağlı mali yıl sonu bekçisi: farklıysa araştırmayı reddeder |
| `--ratings-db` | İsteğe bağlı **mevcut** manuel kaynaklı kredi notu SQLite defteri |
| `--equity-evidence` | İsteğe bağlı tarihlenmiş ve insan tarafından incelenmiş hisse ihracı kanıt JSON'u |
| `--out-json` / `--out-html` | Kaynak izli makine çıktısı ve Türkçe çevrimdışı rapor |

Mevcut kaynağın üzerine dosya yazılmasını önlemek için giriş ve çıkış dosya yollarının eşit olmasına izin verilmez.

## Çıktı güvenilirlik seviyeleri

**`annual_source_audit`:** `READY_FOR_MANUAL_ASSUMPTIONS` yalnızca sayısal yıllık kaynak ön kontrolünün geçtiğini belirtir. Yıllık gelirin muhasebesel kapsama uygunluğunu doğrulayan insan imzası **değildir**.

**`quality.piotroski`:** Dokuz gösterge varsa gerçek `score`; herhangi biri eksikse `score=null`, `score_range=[alt,üst]` ve `missing_reasons`. Banka, sigorta veya sektörü belirlenmemiş şirketler otomatik sıralanmaz. Kredi notları ayrı kaydedilir, birleşik puan yapılmaz.

**`ttm_crosscheck`:** Hesaplayıcıların kaynak tarihleri ve tutarları eşleşirse `RECONCILED_CALCULATIONS`; eksik veya çelişkiliyse `BLOCKED` veya `UNAVAILABLE_NO_ELIGIBLE_ANNUAL_DATA`. Bloke durumda HTML sayfasında **doğrulanmış gibi sayısal TTM gösterilmez**.

**`coverage_status`:**
- `ELIGIBLE_COMPONENT_MATH_COMPLETE`: Desteklenen yıllık, kalite ve TTM hesap kontrolleri geçti. Bu durum yalnız hesap kapsamı içindir, veri kökeninin bağımsız teyidi, ekonomik değerleme veya yatırım getirisi doğruluğu anlamına gelmez.
- `PARTIAL_OR_REVIEW_REQUIRED`: Hangi şartların karşılanmadığı `research_gaps` alanında belirtilir.

**`source`:** Girdi yolu türü, SEC Company Facts URL'si, JSON'un kanonik SHA-256 özeti ve manuel aktarım işareti. Özet, SEC dijital imzası **değildir**. SEC'den indirilen dosyanın tarihli, ham sürümü sonradan denetlenebilmesi için saklanır.

`actual_price`, `dcf`, `investment_recommendation`, `combined_investment_score` alanları bilerek **null**; `forecast_created=false`.

## Araştırmacı için kabul testleri

```powershell
python -m unittest discover -s tests -p test_sirket_arastirma_akisi.py -v
python -m unittest discover -s tests -v
```

Testler kaynağı yetersiz şirketi reddetmeden **kısmi rapor** oluşturmayı, yanlış şirket CIK'ini durdurmayı, geç açıklanmış 10-Q'yu geri tarihli analizden hariç bırakmayı, gelir etiketi çelişkisini, eksik CapEx'i, tarihlenmiş ihraç kanıtını, el ile aktarılmış Apple örneğini ve HTML kaçışını sınar. Çevrimdışı testler canlı SEC erişimi gerektirmez.

## Sonraki ürün gereksinimleri

1. Ücretsiz ve resmî CIK/ticker eşlemesi, veri indirme önbelleği, SEC erişim hız kontrolü ve kaynak arşivi sürümleme.
2. 10-K mali tablo ve dipnotlarıyla **kaynak tutarı karşılaştıran** şirkete özgü doğrulama.
3. 20-F / IFRS ayrı metrik eşleme ve endüstriye özel modeller.
4. DCF için onaylı gerçek şirket temel verilerinden ileriye dönük varsayımların kaynağını zorunlu tutan karar kapısı.
5. Tahmin Defteri tahmin/gerçekleşme ayrımı ve ileriye dönük doğrulama; 2026'da geriye dönük oluşturulan eski tarihli analizler gerçek geçmiş tahmin diye puanlanamaz.
6. Birden fazla şirket için tarama, karşılaştırma ve zaman içinde yeni 10-Q geldiğinde güncelleme; yatırım öneri algoritmasından önce doğrulanabilir veri altyapısı kurulmalı.

## Ürün prensibi

**Eksik veri = bilinmiyor.** `0`, tahmini kur, tahmini bilanço kalemi, kaynaklanmamış fiyat, tarih dışı beyan, otomatik sektör sınıflandırması veya doğrulanmamış hedef fiyat ile boşluklar kapatılmaz.
