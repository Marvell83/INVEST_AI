# Temel analiz tarayıcısı (v0.6) — Excel benzeri çalışma ekranı

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

**Toplu arşiv varsa** `sec_piyasa_toplu_tarama.py` bütün SEC `companyfacts.zip` içindeki ticker ile eşleşen CIK dosyalarını hesaplayıp `veri/invest_ai_evren.sqlite3` içine yazar. `Temel analiz tablosu` bu veri tabanını okur. **Toplu arşiv henüz yoksa** `hisse_tarama_tablosu.py` önceden kaydedilmiş `reports/` JSON raporlarını listeler. Tablo ekranını açmak yeni finansal dosya indirmez; bunun için ayrıca **Tüm SEC finansallarını indir ve tara** düğmesine bas. `SEC verilerini tara` ise yalnız ticker listesini açar. [Toplu tarama kılavuzu](SEC_TOPLU_PIYASA_TARAMASI.md).

### Tarihsel SEC tablosundan gelenler

ROE, ROIC, ROA, brüt / faaliyet / net marj, yıllık satış ve faaliyet kârı büyümesi, 3 yıllık gelir CAGR, 3 yıllık net kâr CAGR, CFO / net kâr, üç yıllık toplam CFO / toplam net kâr, FCF marjı ve üç yıllık FCF, cari oran, borç/özkaynak, faiz karşılama, net borç, nakit, varlıklar, özkaynak, faaliyet kârı, gelir, net kâr, CapEx, çalışan hisse bazlı ödemesi/gelir ve geri alım+temettü/kâr. Yeterli, tarihsel olarak karşılaştırılabilir mali yıl yoksa değer bilinmiyor olarak işaretlenir.

**FAVÖK\*** = SEC faaliyet kârı + SEC nakit akışı amortisman/depreciation kalemi. Raporlanan veya şirketçe düzeltilmiş EBITDA değildir; işletme kârlılığı tahmini ve farklı yatırım harcamaları nedeniyle emsalde dikkatle kullanılmalı.

### Fiyat gerektirenler

F/K, PD/DD, fiyat/satışlar, (ROE/10)/PD/DD, EV/EBIT, EV/FAVÖK*, FCF getirisi ve Fiyat/FCF için kaynaklı, tarihli hisse fiyatı gerekir. Bir hisseye ait piyasa fiyatı **yalnız yatırımcı tarafından ayrı bir senaryo/ters DCF araştırması sırasında kaynak ve tarih ile kaydedildiyse** alınır. SEC dosyasındaki tek güncel hisse adedi ile fiyatın tarihi arasında 100 günden büyük açıklık varsa karşılaştırmalı çarpan üretilmez. Fiyatın SEC bilgi kesme tarihinden sonra olması da çarpanı engeller. Bunun nedeni gelecekteki fiyatları geçmiş bilançoya yanlış uygulamamaktır.

**PEG:** İleriye dönük hisse başına kâr büyüme tahmini, fiyat ve F/K dönemi uyumlu olana kadar **boş**. 3 yıllık ciro CAGR otomatik olarak PEG büyüme oranı yapılmaz.

**Hisse sayısı değişimi (3Y):** son mali yılın ağırlıklı ortalama seyreltilmiş hisse sayısı ÷ 3 yıl önceki aynı değer − 1. Kapak sayfasındaki güncel adet değil, iki mali yılın aynı türden sayısı kullanılır.

**Seyreltilmiş EPS ve EPS CAGR (3Y):** EPS = ana ortaklık net kârı ÷ ağırlıklı ortalama seyreltilmiş hisse (aynı mali yıl). Şirketin bildirdiği EPS rakamı değildir; imtiyazlı hisse temettüleri düşülmez. 3 yıllık CAGR yalnız iki yılın EPS'i de pozitifse hesaplanır. Bu tarihsel bir büyümedir; ileriye dönük analist EPS beklentisi değildir.

**Net kâr büyümesi (1Y):** yalnız bir önceki mali yıl 330–400 gün önce bitmişse ve o yılın net kârı pozitifse.

**Son mali yıl yaşı (gün):** SEC bilgi tarihi ile son mali yıl sonu arasındaki gün. 456 günü aşan şirketlerin finansalları güncel değildir (yeni 10-K vermemiş, el değiştirmiş veya kapanmış olabilir); bugünkü fiyatla çarpan hesaplamak yanıltır. Tabloda bu sütuna "en fazla 456" filtresi koymak güncel dosyalayıcıları bırakır.

## Ölçüt kısıtları

- Referans faiz kullanıcı tarafından girilir, otomatik güncel ABD 10 yıllık tahvil verisi olduğu iddia edilmez.
- Emsal karşılaştırması ve finansal sektör farklılıkları ayrı aşamada ele alınacaktır.
- Toplu SEC dosyasını kullanıcı Codespaces'te açıkça indirdiğinde liste tüm eşleşen ticker ve şirketlere genişler; veri bulunmayan dosyalayıcılar boş/missing olarak işaretlenir.
- Hisse fiyatı, veri kapsamı veya PEG eksikse şirketi otomatik olarak başarısız saymak doğru değildir.

## Kontrol

`python3 -m unittest discover -s tests -v`

Web sunucusunu `python3 invest_ai_web.py` ile başlat. Codespaces bağlantı noktasını **PRIVATE** tut.
