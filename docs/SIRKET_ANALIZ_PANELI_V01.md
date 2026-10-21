# INVEST_AI — Şirket analiz ekranı v0.1

**Amaç:** Piotroski F-Score, Moody's/S&P/Fitch ihraççı kredi notları ve deneysel DCF sonuçlarını **ayrı** panellerde göstermek.

## Yerel kullanım

Python 3.11+ ve internet bağlantısı gerektirmez; rapor elindeki JSON dosyalarından üretilir.

**1. SEC kalite raporu:**
```bash
python sirket_kalite_cli.py report --companyfacts CIKXXXXXXXXXX.json --as-of 2026-10-21 --sector non_financial --ratings-db ratings.sqlite --out kalite.json
```

**2. Opsiyonel DCF:** `sec_reviewed_cli.py` ile **aynı CIK** için SEC denetiminden geçmiş kaynaklı değerleme üret; `recorded_experimental` durumunda bir `dcf.json` dosyası elde et.

**3. Tarayıcıda görüntüle:**
```bash
python sirket_analiz_paneli.py --quality kalite.json --valuation dcf.json --out rapor.html
```
DCF verisi henüz yoksa `--valuation` parametresini kaldır. `rapor.html` dosyasını tarayıcıda aç.

## Güvenlik ve yorumlama

- Modül **piyasa verisi çekmez**, reklam, ağ bağlantısı, JavaScript izleyicisi veya harici CSS barındırmaz.
- Şirket `CIK` değerleri uyuşmazsa raporu durdurur; örneğin A şirketinin finansal kalitesiyle B şirketinin DCF'sini yan yana getirmez.
- F-Score eksikse kesin 8/9 gibi göstermez, yalnız `score_range` sunar. Dokuz sinyal ayrı görünür.
- Kredi notları yalnız `CreditRatingLedger` kaynaklı gözlemlerdir; ajans açıklamalarını otomatik doğrulamaz ve **hisse değerlemesine puan eklemez**.
- DCF yalnız `recorded_experimental` SEC akışına ait, geçerli model çıktısıysa görüntülenir. Hisse alış/satış kararı, güvenilir hedef fiyat veya istatistiksel tahmin isabeti iddiası yoktur.
- Piotroski ve DCF bilgi tarihlerinin farklı olması uyarılır; geleceğe ait verilerle hazırlanmış geriye dönük raporlar geçmişte yapılmış tahmin yerine geçmez.
- HTML'de şirket adları, alanlar ve açıklamalar kaçışlanır. Kredi kaynak linkleri yalnız `https://` ile başlıyorsa tıklanabilir. **Yalnız güvenilir kullanıcı dosyalarını içeri al.**
- Statik panelin içerdiği kararlar **finansal veri kapsamı, piyasa fiyatı, sektör tipi, IPO/ihraç, IFRS/20-F** uyarlamalarını otomatik tamamlamaz.

## Kontrol

```bash
python -m unittest discover -s tests -v
```

Geliştirme prototipinde 58 sentetik birim testi yerelde geçmiştir; GitHub Actions sonucu ayrıca teyit edilmelidir.

Örnek ekran yalnız **SENTETİK** şirket ve yapay verilerden oluşturulmuştur. Gerçek şirket, gerçek not veya yatırım önerisi değildir.
