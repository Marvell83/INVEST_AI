# Temel analiz tarayıcısı (v0.5) — Excel benzeri çalışma ekranı

**Amaç:** Daha önce kaydedilmiş şirket araştırmalarının çok sayıda bilanço, kârlılık, büyüme, nakit ve değerleme göstergesini tek bir satır/şirket matrisinde görmek; birkaç koşulu birlikte kullanarak süzmek. Bu tablo bir al/sat tavsiyesi değildir.

## Nasıl açılır?

INVEST_AI web sitesi → **Analiz çalıştır** → terminaldeki web anahtarını gir → **Temel analiz tablosu**.

- **Sütunları seç:** tabloda görünmesini istediğin veri ve rasyoları işaretle; bütün sütunlar CSV'ye değil, seçilen sütunlar yazılır.
- **Sırala:** sütun başlığını tıkla; tekrar tıklamak sıralama yönünü değiştirir.
- **Filtrele:** oran veya finansal kalem seç, alt/üst sınır yaz, **Koşulu ekle**. Filtreler aynı anda (AND mantığıyla) çalışır. Filtre rozetine tıklayarak kaldırılabilir.
- **Eksik veriler:** bir filtrenin gerektirdiği veri eksikse varsayılan olarak listelenmez; isteğe bağlı olarak bekleyenleri de gösterebilirsin. Eksik değer **sıfır değildir**.
- **7 koşullu ön eleme:** kullanıcı tarafından girilen referans faiz, ROE/ROIC, (ROE/10)/PD/DD, PEG, net borç/FAVÖK, üç yıllık CFO/net kâr ve üç yıllık FCF. Durum `Geçti`, `Elendi`, `Veri bekliyor`. ROIC uyarılıysa güvenilir geçiş olarak değerlendirilmez. Fiyat/PEG kaynağı bulunmazsa `Geçti` uydurulmaz.
- **CSV:** seçilmiş sütunları ve uygulanan tüm filtrelerin sonuçlarını UTF-8 BOM / noktalı virgül ayıracıyla Excel'e aktarır. Tabloda performans için yalnız ilk 200 satır çizilir, CSV'de filtreye uyan bütün satırlar bulunur.

## Veri ve formüller

`hisse_tarama_tablosu.py`, `reports/` altında önceden yaratılmış ve `financial_statements`, `financial_ratios` içeren JSON raporlarını okur. Bir CIK için en son kayıt kullanılır. Bu uç nokta **SEC'ye veya ücretli fiyat servisine istek yapmaz**. `SEC verilerini tara` düğmesi yalnız ticker dizinini açar; şirketlerin Company Facts dosyalarının otomatik olarak indirildiği anlamına gelmez.

### Tarihsel SEC tablosundan gelenler

ROE, ROIC, ROA, brüt / faaliyet / net marj, yıllık satış ve faaliyet kârı büyümesi, 3 yıllık gelir CAGR, 3 yıllık net kâr CAGR, CFO / net kâr, üç yıllık toplam CFO / toplam net kâr, FCF marjı ve üç yıllık FCF, cari oran, borç/özkaynak, faiz karşılama, net borç, nakit, varlıklar, özkaynak, faaliyet kârı, gelir, net kâr, CapEx, çalışan hisse bazlı ödemesi/gelir ve geri alım+temettü/kâr. Yeterli, tarihsel olarak karşılaştırılabilir mali yıl yoksa değer bilinmiyor olarak işaretlenir.

**FAVÖK\*** = SEC faaliyet kârı + SEC nakit akışı amortisman/depreciation kalemi. Raporlanan veya şirketçe düzeltilmiş EBITDA değildir; işletme kârlılığı tahmini ve farklı yatırım harcamaları nedeniyle emsalde dikkatle kullanılmalı.

### Fiyat gerektirenler

F/K, PD/DD, fiyat/satışlar, (ROE/10)/PD/DD, EV/EBIT, EV/FAVÖK*, FCF getirisi ve Fiyat/FCF için kaynaklı, tarihli hisse fiyatı gerekir. Bir hisseye ait piyasa fiyatı **yalnız yatırımcı tarafından ayrı bir senaryo/ters DCF araştırması sırasında kaynak ve tarih ile kaydedildiyse** alınır. SEC dosyasındaki tek güncel hisse adedi ile fiyatın tarihi arasında 100 günden büyük açıklık varsa karşılaştırmalı çarpan üretilmez. Fiyatın SEC bilgi kesme tarihinden sonra olması da çarpanı engeller. Bunun nedeni gelecekteki fiyatları geçmiş bilançoya yanlış uygulamamaktır.

**PEG:** İleriye dönük hisse başına kâr büyüme tahmini, fiyat ve F/K dönemi uyumlu olana kadar **boş**. 3 yıllık ciro CAGR otomatik olarak PEG büyüme oranı yapılmaz.

**Hisse sayısı değişimi (3Y):** SEC'den yıllar bazında karşılaştırılabilir pay adedi serisi kurulana kadar boş.

## Ölçüt kısıtları

- Referans faiz kullanıcı tarafından girilir, otomatik güncel ABD 10 yıllık tahvil verisi olduğu iddia edilmez.
- Emsal karşılaştırması ve finansal sektör farklılıkları ayrı aşamada ele alınacaktır.
- Çok sayıda SEC şirketinin otomatik finansal indirilmesi ve kayıtlara eklenmesi henüz yeni bir çalışmadır; tablo şimdilik mevcut raporlarla dolacaktır.
- Hisse fiyatı, veri kapsamı veya PEG eksikse şirketi otomatik olarak başarısız saymak doğru değildir.

## Kontrol

`python3 -m unittest discover -s tests -v`

Web sunucusunu `python3 invest_ai_web.py` ile başlat. Codespaces bağlantı noktasını **PRIVATE** tut.
