# INVEST_AI Ana Sayfa — Codespaces (v0.1)

## Nedir?

INVEST_AI artık depo kökünde `index.html` dosyasına sahip. Bu dosya, Python'un mevcut `http.server` komutuyla **8000 numaralı bağlantı noktasındaki ana adres** açıldığında otomatik görüntülenir. Herhangi bir sunucu çatısı, npm, özel kütüphane, bulut GPU veya ücretli API gerektirmez.

Ekran geliştirici prototipidir, halka açık bir üretim/abonelik sitesi **değildir**. Mevcut analiz motorlarının yerini almaz; bunların oluşturduğu **statik HTML araştırma raporları için giriş merkezidir**.

### Menü

- **Ana sayfa:** Raporlara hızlı erişim ve modül özeti.
- **Raporlarım:** `reports/` klasörü ve içindeki alt klasörlerdeki HTML dosyalarını listeler. Dosya adına göre arama, aynı sayfada sınırlandırılmış görüntüleyici, ayrıca yeni sekmede açma.
- **Analiz çalıştır:** Terminalde çalıştırabileceğiniz mevcut Python komutlarını kopyalar. Tarayıcıda Python kodu yürütmez.
- **Sistem hakkında:** Kaynakların ve mevcut sınırların özeti.

Yeni rapor eklendiğinde **Raporlarım → Listeyi yenile** tıklanır. Dosyalar tarayıcıdan indirilmez; mevcut Codespaces sunucusu üzerinden açılır.

## Şu anda açık Codespaces üzerinde

Ekrandaki terminalinizde zaten:

~~~bash
python3 -m http.server 8000
~~~

çalışıyorsa **kapatmayın**. VS Code menüsünden **Terminal → Yeni Terminal** seçerek ikinci terminali açın. Proje kökünde:

~~~bash
cd /workspaces/INVEST_AI
git pull --ff-only origin main
~~~

komutlarını çalıştırın. Sonra Codespaces **Bağlantı Noktaları (Ports)** sekmesinden **8000 → Tarayıcıda Aç** seçin veya açık sekmede ana adrese gidip sayfayı yenileyin.

**Önemli:** Git güncellemesi yerel değişiklikler yüzünden engellenirse `git reset --hard` veya dosya silme yapmayın; çıktıdaki mesajı inceleyin. Üretilmiş `reports/*.html` dosyalarını koruyun.

Sunucu henüz açık değilse proje kökünde:

~~~bash
python3 -m http.server 8000
~~~

komutunu çalıştırın. Sunucu çalışan terminal meşgul görünür; normaldir. Durdurmak için **Ctrl+C**.

## İlk raporu üret

Diğer terminalde:

~~~bash
python3 sirket_arastirma_akisi.py --cik 320193 --as-of 2026-10-21 --sector non_financial --companyfacts ornekler/apple_ttm_evidence_2026-10-21.json --out-json reports/apple_arastirma.json --out-html reports/apple_arastirma.html
~~~

Bu **ham SEC API verisi değil**, daha önce belgelerden elle aktarılmış Apple örnek verisidir. Araştırma raporu veri eksiklerini gösterebilir. İşlemden sonra ana sayfada **Raporlarım → Listeyi yenile → apple arastirma** yolunu izleyin.

## Keşif mekanizması

Ana sayfa tarayıcı tarafında aynı origin üzerindeki `reports/` klasörünün Python `SimpleHTTPRequestHandler` **dizin listeleme sayfasını** okur. En fazla 3 seviye alt klasöre girer; yalnız `.html` veya `.htm` uzantılı belgeleri görüntüleyiciye ekler. Başka origin veya `reports/` dışındaki yollara gitmez; kaynak dosya adlarını HTML olarak eklemek yerine `textContent` ile metin olarak işler.

**Dizin listeleme Python `http.server` uygulamasına özgüdür.** Eğer ileride Nginx, Vercel, GitHub Pages veya başka statik barındırma sistemine geçilirse, raporları otomatik listelemek için önceden oluşturulmuş `reports/index.json` gibi ayrı bir manifest gerekir.

Görüntüleyici `iframe` sandbox kullanır. Rapora yeni sekmeden erişim de sağlanır. Bu sayfa dış kütüphane indirmez, fiyat veya SEC API sorgusu yapmaz.

## Sorun giderme

- **Yine dosya listesi çıkıyor:** `index.html` henüz bu Codespaces çalışma alanına gelmemiştir. Yeni terminalde `git pull --ff-only origin main` ve `ls index.html` komutlarıyla doğrulayın.
- **Raporlar boş:** `reports/` altında HTML dosyası oluşturun; **Listeyi yenile** deyin. Rapor üretildikten sonra sunucuyu yeniden başlatmanız gerekmez.
- **8000 numaralı port açık değil:** Terminalin proje kökünde sunucuyu çalıştırdığını doğrulayın; Ports sekmesinden açın.
- **404 yalnız `favicon.ico`:** Site simgesi istenmiş ama bulunamamıştır. Analiz programının çalışmasına engel değildir.
- **Tarayıcı açmıyor:** Codespaces port görünürlüğünü ve URL'yi kontrol edin. Portu gereksiz yere public yapmayın.
- **Oluşturulan dosyayı `git pull` ezer mi?** Önce `git status` ile yerel değişiklikleri kontrol edin. Çakışma varsa körlemesine üzerine yazmayın.
- **Kaynak veriler ve yatırım önerisi:** Bu site yalnız mevcut raporları gösterir; otomatik yatırım tavsiyesi üretmez.

## Kabul testi

~~~bash
python3 -m unittest discover -s tests -p test_ana_sayfa.py -v
python3 -m unittest discover -s tests -v
~~~

Site bağlantısı, `http.server` tarafından ana adreste `index.html` sunulması ve `reports/` dizininin erişilebilirliği Python standart kütüphanesiyle test edilir.
