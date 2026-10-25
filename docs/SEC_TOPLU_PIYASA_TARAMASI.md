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

## Sonuçların yorumu

SQLite/Excel finansal satırları şunları içerir: ROE, ROIC, ROA, gelir/kâr büyümesi, marjlar, CFO, nakit dönüşümü, FCF, net borç, borç/özkaynak, yaklaşık net borç/FAVÖK, faiz karşılama, CapEx, D&A, yıllık gelir/varlık/özkaynak/borç tutarları. Üç yıllık finansal geçmiş bulunursa çok yıllık büyüme ve CFO/FCF ölçümleri gösterilir.

**SEC ticker listesi yalnız CIK/ticker/dizin listesidir:** ETF, ADR, kapatılmış veya eski kayıtlar, halka açık olmayan dosyalayıcılar, pay sınıfları ve finansal veri yetersizliği ayrı incelenmelidir. Finansallar bir CIK için hesaplanır, aynı CIK'nin farklı pay sınıflarına ayrı ticker satırı açılır. Çok sınıflı şirketlerde sınıf bazında fiyat ve pay adedi otomatik doğrulanmadığı için fiyat çarpanları boş kalır.

**Önemli eksiklik:** SEC Company Facts **borsa fiyatı veya ileri EPS büyümesi** sağlamaz. Dolayısıyla ilk toplu aktarımda F/K, PD/DD, PEG, EV/EBIT, FCF Yield, ROE/10/PD/DD gibi piyasa çarpanlarını güvenilir biçimde otomatik üretemeyiz; bunlar veri yoksa **boş** kalır. Tam 7 koşulun hepsini geçen listeyi uydurmak yerine `VERİ BEKLİYOR` statüsü korunur. Fiyat kaynakları ve ileri EPS beklentileri sonraki veri katmanında eklenecek.

**ROIC yöntem uyarısı:** çok küçük yatırım sermayesi paydasında aşırı oranlar oluşur. Finans sektörlerinde banka/sigorta muhasebesi farklıdır; üniform genel ölçütlerle kesin olumlu sonuç çıkarmayız. SEC US-GAAP dışı IFRS/20-F kayıtlarında uygun standart finansallar bulunmayabilir.

## Kontrol

`python3 -m unittest discover -s tests -v`

Güncel SEC arşiv bağlantısı: [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · [resmî companyfacts.zip](https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip)
