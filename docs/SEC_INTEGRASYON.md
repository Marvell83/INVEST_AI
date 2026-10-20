# SEC Company Facts → INVEST_AI v0.2 (ilk entegrasyon)

Bu aşama, **ABD SEC XBRL Company Facts** verisinden yıllık tarihsel gelir ve faaliyet kârını denetlenebilir biçimde çıkarır. Dönem başı/bitişi, başvuru (accession), form türü ve SEC dosyasının ne zaman yayımlandığı kaydedilir.

## Kurulum

Python 3.11+ ve standart kütüphane yeterlidir. İki ayrı modül vardır:

- `sec_companyfacts.py`: SEC ham JSON → normalize edilmiş tarihsel JSON.
- `sec_v02_bridge.py`: Tarihsel gelir ve EBIT → **yalnız kaynaklı, kullanıcı tarafından girilmiş** senaryo varsayımlarıyla deneysel `degerleme_v02.py` modeline aktarım.

### A. Çevrimdışı SEC JSON

```bash
python sec_companyfacts.py --cik 320193 --as-of 2026-10-20 --file companyfacts.json --years 10 --out sec_history.json
```

Veri kaynağı dosyasını manuel indirip `--file` ile verebilirsiniz. Verilen CIK dosya içindeki CIK ile eşleşmelidir.

### B. SEC'den tek şirket için indirme

SEC'nin bot kurallarına uygun **gerçek kişi/kurum ve iletişim adresini** içeren User-Agent gerekir. Örnek değerdeki e-posta adresini gerçek iletişim adresinizle değiştirin.

Windows PowerShell:

```powershell
$env:SEC_USER_AGENT = "INVEST_AI Research your-real-email@example.com"
python sec_companyfacts.py --cik 320193 --as-of 2026-10-20 --download --out sec_history.json
```

Linux/macOS:

```bash
export SEC_USER_AGENT="INVEST_AI Research your-real-email@example.com"
python sec_companyfacts.py --cik 320193 --as-of 2026-10-20 --download --out sec_history.json
```

Önemli: `--download` ağı kullanır; bağlantı kurulmazsa **yerel dosya modu** ile çalışın. Her komut tek şirketin Company Facts JSON verisini indirir. Çok şirketli toplu sorgularda SEC erişim sınırları, aralıklandırma ve hata yönetimi ayrıca gereklidir.

### C. DCF v0.2 senaryosu

Önce manuel senaryonuzu ayrı JSON olarak hazırlayın. Kaynaksız **varsayılan iskonto oranı, büyüme veya hisse sayısı otomatik oluşturulmaz**. Aşağıdaki rakamlar **tamamen sentetik test örneğidir** ve gerçek hisse değerlemesinde kullanılmamalıdır:

```json
{
  "scenario": "SYNTHETIC ONLY",
  "assumptions": {
    "yillar": 3, "buyume": 0.10, "marj_hedef": 0.20,
    "yakinlasma": 0.5, "satis_sermaye": 2,
    "vergi_orani": 0.25, "iskonto": 0.10,
    "uc_buyume": 0.02, "uc_roic": 0.12,
    "hisse": 10, "net_borc": 0
  },
  "assumption_sources": ["SYNTHETIC demonstration; replace with dated citations"],
  "share_count_source": "SYNTHETIC; replace with verified share count source",
  "net_debt_source": "SYNTHETIC; replace with verified net debt calculation"
}
```

```bash
python sec_v02_bridge.py --sec sec_history.json --assumptions senaryo.json --out sec_dcf_v02.json
```

Gerçek rakamlar için `hisse` **adet**, `net_borc` **USD**, `gelir_0` **USD** birimindedir. Bu nedenle `hisse_basi_deger` **USD/hisse** üretir. `gelir_0` ve `marj_0` manuel senaryo tarafından değiştirilemez; SEC tarihsel verisinden alınır. Gelir ile EBIT aynı yıllık dönem başı ve bitişine sahip değilse köprü değerlemeyi reddeder.

## Bilerek kapsanmayan alanlar

- SEC biçimi **US-GAAP USD yıllık 10-K/10-K/A** ve yaklaşık 12 aylık kayıtlar içindir. 10-Q, 20-F, IFRS, KAP, bankalar/finans kuruluşlarının özel sektör muhasebesi ve döviz dönüşümü henüz yoktur.
- **CFO - CapEx, unlevered FCFF değildir.** Tarihsel bu hesap yalnız yardımcı bir ölçüdür; v0.2'nin FCFF hesaplamasına otomatik aktarılmaz.
- SEC satırlarının geçmişte bilinebilirliği `filed <= as_of` ile korunur. Geçmişe dönük analizde rapor yayımlanmadan önceki bilgi sızdırılmaz. Bir şirketin şirket düzeyi farklı yeniden sınıflandırmaları hâlâ insan kontrolü gerektirir.
- Sonradan düzeltilen tablolar, sadece istenen as-of tarihinden önce SEC'ye verilmişse kullanılabilir.
- Özsermaye/dolaşımdaki hisse sayısı, borç, nakit, güncel fiyat, hisse bölünmeleri ve sulandırma otomatik hesaplanmaz.
- Eski tahminlerin karşılaştırılması ayrı Tahmin Defteri modülünün konusudur; bu SEC köprüsü henüz Tahmin Defteri'ne otomatik yazmaz.
- DCF modelinin kendi v0.2 **alpha** ekonomik sınırlamaları sürer. Hesap çıktısı yatırım tavsiyesi değildir.

## Testler

```bash
python -m unittest discover -s tests -v
```

SEC normalleştirme ve SEC→DCF köprüsü için toplam **20 sentetik, çevrimdışı test** hazırlanmıştır. Yerelde geçmiştir. GitHub Actions sonucunu GitHub'da ayrıca kontrol edin. Testler gerçek SEC verisini veya yatırım getirilerini doğrulamaz.

## Sonraki adım

SEC gerçek finansalları için şirkete özgü satır eşleştirmeleri, bilanço/borç ve hisse adedi kaynak kontrolü, ilgili dönem ve birim uyuşmazlıkları, güncel fiyat, senaryo varsayım kontrolü ve Tahmin Defteri bağlantısı.
