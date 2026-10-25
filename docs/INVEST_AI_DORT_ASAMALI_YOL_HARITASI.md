# INVEST_AI — dört aşamalı şirket keşif ve araştırma yol haritası

**Karar: 25 Ekim 2026.** Asıl ürün, SEC verisinden başlayıp temel, sektörel ve gelecek analizleriyle araştırmaya değer şirketleri filtreleyen **kaynaklı bir keşif platformudur**. Piotroski zorunlu ölçüt değildir; **web, toplu tarama ve yeni CLI araştırma raporlarının aktif akışından çıkarılmıştır**. Eski HTML/JSON raporları ve bağımsız eski analiz kodu, geriye dönük uyumluluk için silinmez.

## 1. Uygun şirket evreni ve SEC veri toplama — İLK ÖNCELİK

1. SEC `company_tickers.json` kaynağından CIK–ticker eşlemesini zaman damgası ve hash ile sakla. Bu liste tek başına tüm aktif borsa kotasyonlarını, ADR/ETF ayrımını ya da tarihsel ticker kimliğini doğrulamaz.
2. SEC 10-K, 10-Q ve Company Facts bilgilerini, yayımlanma/erişim tarihlerine göre arşivle. İleriye bakma (look-ahead) ve sonradan değiştirilmiş dosya riskini takip et.
3. Evreni sayfalara/batch'lere böl; eksik veri, 403/429, mükerrer CIK, zayıf likidite veya kapsama dışı formları **sessizce eleme**. Yeniden başlatılabilir iş, SHA-256, günlük kayıt, artımlı yenileme, SEC Fair Access.
4. **Kapsam:** mevcut motor ABD'ye ait SEC US-GAAP/USD 10-K/10-Q finansallarını destekliyor. Örneğin yabancı IFRS/20-F dosyalayıcıları ve fonlar için ayrı yöntem gerekir. "SEC'de listeleniyor" = "temel analiz tamam" değildir.
5. Çıktı: tarihli, kayıt kaynağına bağlanabilen ve neden elendiği/bekletildiği takip edilebilen şirket evreni.

**Mevcut:** `sec_arsiv.py`, `sec_toplu_tarama.py`, `sec_companyfacts.py` ve tekil web analizleri. Toplu motorun varsayılan sınırı 100, yapılandırılabilir tavanı 500 şirkettir. **Bütün piyasa otomatik olarak henüz taranmıyor.**

**Tamamlanma ölçütü:** tanımlanmış evrenin tüm desteklenen üyeleri, kesintiden sonra sürdürme ve işlem kaydıyla güvenilir biçimde işlenir; 0 bilinmeyen veri ile 0 gerçek değer birbirine karıştırılmaz.

## 2. Temel analiz ve ilk eleme

Kaynaklı yıllık ve TTM finansallarla şirketleri incele:

- Gelir büyümesi ve istikrarı; brüt, faaliyet ve net marj; büyümenin sürekliliği.
- CFO, CapEx, CFO−CapEx ve nakit dönüşümü; hisse bazlı ödemeler ve geri alımlar.
- Cari oran, borçluluk, net borç; anormal ROE/ROIC paydası ve veri kalitesi uyarıları.
- Şirketin olası değeri ile piyasa fiyatını ayrı tut; **canlı fiyat ve ileri dönem varsayımları şu an otomatik sağlanmıyor**.
- Eşikler açık, değiştirilebilir ve nedenleri açıklanabilir olmalı. `GEÇTİ`, `ELENDİ`, `VERİ EKSİK / İNCELEME GEREKLİ` ayrı durumlar. **Tek bileşik hisse puanı ve Piotroski yok.**

**Mevcut:** `finansal_tablolar.py`, `finansal_oranlar.py`, `sec_ttm_crosscheck.py`, `katman_mutabakati.py`. **Eksik:** evren çapında kayıtlı, tekrarlanabilir eşik tabanlı eleme ve eleme nedenleri.

## 3. Sektörel analiz — yalnız temel incelemeyi geçenler

- Desteklenen şirketleri kaynaklı SIC/NAICS/sektör sınıfına göre ayır; hatalı/eksik sınıflamayı doğrulamadan emsal belirleme.
- Rakipler, sektör içi medyan/marj/büyüme/nakit getirisi, yatırım yoğunluğu ve iş modeli; bankalar, sigortacılar, gayrimenkul gibi özel sektörlere uygun göstergeler.
- Pazar payı, sipariş akışı, fiyatlama gücü, maliyet riski, regülasyon ve sektör döngüsü **Company Facts dışı belge ve kanıt** gerektirir.
- Çıktı: karşılaştırılabilir emsaller, sektörün yapısal avantaj/dezavantajları ve güçlü aday kısa listesi.

**Mevcut:** sektör alanı yalnızca analist varsayımı ve bazı muhasebe kurallarını etkiliyor. **Ayrı sektörel araştırma motoru henüz yok.**

## 4. Gelecek analizi — kalan adaylar için araştırma tezi

- Yönetim rehberliği, 8-K, 10-K/10-Q metin açıklamaları, yatırımcı sunumları, yeni ürün, sözleşme ve siparişler, kapasite/CapEx, rekabet, birleşme ve davalar, düzenlemeler.
- Her gelecek iddiası: **beklenen olay + yön + zaman ufku + belgenin tarihi + doğrudan kaynak + karşı kanıt + belirsizlik**.
- Baz, temkinli ve iyimser senaryolarda gelir, marj, nakit akışı, sermaye ihtiyacı; DCF/ters DCF yalnız kaynaklı varsayımlarla; yıllık tahmin–gerçekleşen kıyası.
- Katalizörün fiyatlara yansımış olup olmadığını araştır; veri olmayan şirket için kesin gelecek tahmini üretme.
- Çıktı: yatırım önerisi değil, **izlenecek şirketler listesi ve her aday için kaynaklı tez, riskler, tetikleyiciler ve hangi şartta tezden vazgeçileceği**.

**Mevcut:** `tahmin_motoru.py`, `senaryo_degerleme.py`, `tahmin_defteri.py` çekirdekleri. **Eksik:** SEC metin/8-K, beklenti/katalizör kanıt toplama, otomatik sektörel/future kaynak entegrasyonu.

## Öncelik ve disiplin

**Sıra:** 1. tam ve güvenilir evren → 2. şeffaf temel eleme → 3. emsal/sektör → 4. kaynaklı gelecek tezleri.

İlk uygulama işi: `sec_toplu_tarama.py` için **tüm desteklenen evreni sayfalara bölme, artımlı yeniden başlatma ve tarama kapsamı istatistiği**. Sonrasında kaynağına bağlı temel eleme şeması. Uygun olmayan mali formlar, ek açıklamalar ve manuel kaynak denetimi `UNKNOWN` olarak görünür. Şimdilik ek ücretli servis veya yeni donanım gerektirecek iş planlanmıyor.

## Eski raporlar ve uyumluluk

Eski Piotroski HTML/JSON dosyaları korunur; eski hesap modülleri geriye dönük testler için depoda kalır. **Yeni web raporlarının dosya adında `_fundamentals` eki bulunur**. Eski ve yeni raporlar birbirini ezmez. Yeni toplu CSV'de F-Score kolonları üretilmez. Etkin ekranın kaynağı finansal veriler ve SEC/TMM kapsamı; eski kayıtlara geri dönülürse eski Piotroski tabloları yalnız arşiv olarak görünür.
