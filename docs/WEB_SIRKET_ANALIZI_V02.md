# INVEST_AI v0.2 — Web Sitesinden Şirket Analizi Başlatma

## Başlangıç: GitHub Codespaces

Bu sürümde eski `python3 -m http.server 8000` komutunun yerini `invest_ai_web.py` alır. Web arayüzü artık "Şirket analiz merkezi" menüsünden mevcut SEC araştırma motorunu çalıştırabilir.

**1.** Codespaces'te önceki sunucunun çalıştığı terminalde `Ctrl+C` ile eski sunucuyu durdur.

**2.** Aynı terminalde veya yeni terminalde repo güncelle:

~~~bash
cd /workspaces/INVEST_AI
git pull --ff-only origin main
~~~

Bu komut yerel değişiklikler nedeniyle durursa `git reset --hard` gibi veri kaybettirecek bir komut kullanma; çakışma mesajını incele.

**3.** Önce internet gerektirmeyen örnek için sunucuyu başlat:

~~~bash
python3 invest_ai_web.py
~~~

Terminalde `WEB ANALİZ ANAHTARI` satırı görünecek. Bu anahtar **gizlidir ve her yeniden başlatmada değişir.** Yalnızca sitedeki **Web analiz anahtarı** kutusuna yapıştır. Sohbetlere veya ekran görüntülerine ekleme. Başka kişilerle paylaşma.

**4.** Codespaces **Ports / Bağlantı Noktaları** kısmında `8000` numaralı portu **Private** tutarak tarayıcıda aç. Önceden açtığın ana sayfanın URL'sini de yenileyebilirsin.

**5.** Soldaki **Analiz çalıştır** menüsünde:
- Hisse kodu: `AAPL`
- Veri kaynağı: **Apple örneği (internetsiz)**
- Sektör: `Bilinmiyor` (güvenli varsayılan; Piotroski kesin puanlanmaz) veya **Finans dışı şirket (doğrulandı)** (yalnız analist doğruladıysa)
- Web analiz anahtarı: terminalden kopyaladığın gizli değer

**Şirketi analiz et** düğmesine bas. Tamamlandığında rapor düğmesi görünür; onu seçerek aynı sitede HTML araştırma raporunu aç. Yeni rapor `reports/research/` içinde saklanır ve **Raporlarım** listesine otomatik eklenir.

Bu örnek `ornekler/apple_ttm_evidence_2026-10-21.json` dosyasını kullanır; **ham SEC API kaydı değil, tarihli finansal satırların el ile aktarılmış demonstrasyonudur**. Bilgi kesme tarihi bilerek 21 Ekim 2026'dır. Bu modda hiçbir SEC isteği gönderilmez.

## Gerçek SEC verilerini ücretsiz indirme

Gerçek şirketlere ait resmî ticker–CIK eşlemesi ve Company Facts JSON'unu SEC'den almak için sunucuyu şu şekilde başlat. Örnek e-postayı **kendi gerçek iletişim e-posta adresinle** değiştir:

~~~bash
# Eski web sunucusunu Ctrl+C ile kapat
export SEC_USER_AGENT="INVEST_AI Research YOUR_REAL_EMAIL@example.com"
python3 invest_ai_web.py
~~~

- "Veri kaynağı": **Güncel SEC Company Facts** seç.
- Hisse kodu: `AAPL`, `MSFT`, `NVDA` vb. SEC ticker listesinde bulunan geçerli bir ABD ticker'ı gir.
- Sektörü **kendin teyit ederek** seç. Emin değilsen `Bilinmiyor` bırak.
- Terminalde yeni üretilen analiz anahtarını gir.

Web sunucusu:
1. 24 saatten eskiyse SEC resmî `company_tickers.json` dosyasını indirip `veri/sec_ticker_esleme.json` olarak saklar.
2. Ticker'ı bu resmî eşlemeden SEC CIK ile eşleştirir; tahmin yapmaz.
3. SEC'den tek bir Company Facts JSON indirir, CIK kontrolünden sonra `veri/sec_kaynaklari` içine SHA-256 tabanlı arşive kaydeder.
4. Mevcut `sirket_arastirma_akisi.py` modüllerini çağırır: SEC yıllık kaynak denetimi, Piotroski koşulları ve mevcut Q3 TTM çift motor mutabakatı.
5. İki dosya üretir: JSON araştırma kanıtı ve aynı sitede açılabilen HTML.

**SEC Fair Access:** Tek web sunucusu içinde seri analiz yapılır ve saniyede yaklaşık bir istek sınırı uygulanır. 403/429 görülürse sunucu bu oturumda yeni SEC isteği denemez. Aynı IP'deki başka SEC istemcilerinin toplam taleplerini bu süreç koordine etmez.

**Önbellek kullanımı:** Önce canlı modda SEC verisini aldıysan, sonra "Önceden kaydedilmiş SEC verisi" seçeneğiyle aynı arşivi yeni SEC isteği göndermeden kullanabilirsin.

## Güvenlik

- **Geliştirme sunucusu**, `127.0.0.1` yerel arayüzüne bağlanır. İnternete açık üretim çok kullanıcılı uygulama değildir. Codespaces portu **Private** tutulmalı; kimlik doğrulama yerine geçmez.
- Her analiz POST isteğinde terminaldeki rastgele **web anahtarı** gerekir. Header üzerinden gönderilir; URL veya yerel tarayıcı depolamasına yazılmaz. Sunucu yeniden başladığında anahtar değişir.
- Cross-origin istekler reddedilir. Sunucu yalnız ana sayfayı ve `reports/` altındaki HTML belgelerini statik sunar. `.git`, `.env`, Python kaynak kodları, SEC ham JSON'ları ve raporların JSON verileri web üzerinden erişilebilir değildir.
- Hisse kodu sınırlı bir biçimde doğrulanır. Shell/subprocess veya kullanıcı yolundan dosya çalıştırma yoktur.
- Aynı anda yalnız bir şirket analizi başlatılır.
- Dosya arşivi kaynağın gerçekten SEC elektronik imzasını taşıdığını kanıtlamaz. İki hesap motorunun uyuşması kaynakların muhasebe kapsamını onaylayan insan denetimi değildir.
- F-Score eksikse kesin puan üretilemez; DCF ve ters DCF modelleri **otomatik bağlanmaz**, yatırım önerisi veya canlı hisse fiyatı yoktur.

## Testler

~~~bash
python3 -m unittest discover -s tests -p test_invest_ai_web.py -v
python3 -m unittest discover -s tests -v
~~~

Sentetik SEC kayıtlarıyla (gerçek SEC internet erişimi olmadan) şu durumlar doğrulanır: HTML formu ve API, anahtar/Origin kontrolleri, kaynak dosyalarının internete açılmaması, ücretsiz demo, resmî ticker CIK eşlemesi, tek kaynaktan tarihli çıktı, çevrimdışı önbellek, 429 devre kesici, eksik sektörün puanlanmaması ve eşzamanlı analiz engeli.

**Önemli kabul sınırı:** Testler gerçek SEC erişiminin Codespaces ağında başarılı olduğunu garantilemez. İlk canlı çalıştırmada SEC erişim yanıtını, 10-K/10-Q dönemlerini ve analiz raporunda "kaynak eksikleri" bölümünü kontrol et.

## Sonraki hedef

Web sunucusunu daha güçlü, yetkilendirilmiş ve üretime uygun yapıya taşıma; şirkete göre doğrulanmış sektör kimliği; ara dönem Q1/Q2 TTM; ROIC; gerçek değerleme varsayımlarının insan onaylı akışı; geçmiş sonuçlarla yeni verilerin kaynaklı kıyaslaması.


## Eski raporla yeni web analizini ayırma (v0.2 güncellemesi)

"Raporlarım" bölümünde artık **Web analizleri (v0.2)** ve **Önceki / terminal raporları** şeklinde iki grup vardır. Liste aynı zamanda ilgili gruba göre filtrelenebilir.

- `reports/Apple_SEC_Piotroski_2026-10-21.html` depoda önceden oluşturulmuş, `piotroski-sec-0.1.0` ve `quality-panel-0.1.0` sürümlü **eski örnek rapordur**. Korunur, değiştirilmez. Bu raporu açmak v0.2 çalıştırdığınız anlamına gelmez.
- Webden oluşturulan raporlar `reports/research/` içinde `AAPL_DEMO_2026-10-21_non_financial_<hash>.html` gibi saklanır. Tarayıcıda **Örnek / manuel aktarım**, **SEC üzerinden indirme**, **Yerel SEC arşivi** olarak ayrı gösterilir.
- Kartlarda görünen tarih **bilgi kesme (as-of) tarihidir**. Raporun üretildiği, ham SEC dosyasının indirildiği veya en güncel mali dönemi kapsadığı anlamına gelmez. Raporun içindeki **SEC kaynak kapsama denetimi** ve **TTM dönemini** mutlaka kontrol edin.
- Ana sayfada web araştırmaları, ardından eski raporlar listelenir. Önceki raporlar veri kaybını önlemek için silinmez.
- Yeni analiz yaptıktan sonra **Raporu sitede aç →** düğmesini kullanın. "Raporlarım" listesinden seçiyorsanız **Web analizleri (v0.2)** filtresini açın.
