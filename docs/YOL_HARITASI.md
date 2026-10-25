# INVEST_AI Yol Haritası — 10 ders, tek mimari

"Yapay Zekâ ile Finansal Analiz" eğitiminin 10 dersi, INVEST_AI'nin geliştirme sırasına dönüştürüldü. Her aşama bir öncekinin verisini kullanır, böylece yeni özellikler ayrı ayrı eklenmez, aynı mimari tamamlanır.

```
SEC Company Facts (10-K / 10-Q, XBRL)  ── sec_arsiv · sec_companyfacts · sec_gap_audit
        │
        ▼
Ortak finansal tablolar  ── finansal_tablolar  (gelir · nakit akışı · bilanço)
        │
        ├─► Oranlar ve finansal kalite ── finansal_oranlar · piotroski_fscore · kredi_notlari
        ├─► TTM ──────────────────────── sec_ttm · ttm_finansallar · sec_ttm_crosscheck
        ▼
Tahmin motoru  (taban senaryo + analist varsayımları, Tahmin Defteri'ne kayıt)
        │
        ▼
Senaryo ve değerleme  ── degerleme_v02 · ters DCF · duyarlılık
        │
        ▼
Araştırma asistanı  (yalnız rapordaki kaynaklı verilere dayanan yorum)
```

## Ders → modül → durum (25 Ekim 2026)

| Ders | Konu | INVEST_AI karşılığı | Durum |
|---|---|---|---|
| 1 | Yapay zekâyı doğru konumlandırmak | Kaynak/tarih kuralları, eksik ≠ 0, birleşik puan yok, araştırma asistanı | İlkeler kodda var; asistan yok |
| 2 | Gelir tablosu ve kârlılık | `finansal_tablolar` gelir tablosu; marjlar, büyüme | **Tamam** (yıllık + çeyreklik); çeyreklik oranlar yok |
| 3 | Nakit akışı | CFO, CapEx, serbest nakit akışı, nakit dönüşümü; TTM motorları | **Tamam** (yıllık + çeyreklik + TTM) |
| 4 | Bilanço ve sağlamlık | bilanço kalemleri, toplam borç, cari oran, borç / özkaynak, faiz karşılama, hisse sayısı | **Tamam** (yıllık + çeyrek sonu) |
| 5 | Oranlarla karar | `finansal_oranlar` (ROA, ROE, ROIC …), Piotroski 9 gösterge | **v0.1 tamam**; Piotroski henüz ortak katmana bağlı değil |
| 6 | Tahminleme | `tahmin_motoru`: tarihsel baz, temkinli / baz / iyimser gelir ve faaliyet kârı senaryoları, Tahmin Defteri kaydı | **v0.1 tamam**; nakit akışı projeksiyonu ve web girişi yok |
| 7 | Senaryo / what-if | `degerleme_v02`, ters DCF, Apple üç senaryo örneği | Motor var; duyarlılık tablosu ve rapora bağlantı yok |
| 8 | Bütçe ve sapma | `tahmin_defteri` + `sapma_analizi`: tahminlerin ilk bildirilen SEC değerleriyle otomatik eşlenmesi, hata ve senaryo aralığı isabeti | **v0.1 tamam**; yalnız yıllık hedefler |
| 9 | Yönetim için içgörü | şirket araştırma raporu (HTML) | Veri bölümleri var; güçlü/zayıf yön özeti yok |
| 10 | Yapay zekâ çalışma seti | SEC toplama, toplu tarama, web formu, CI | Temel altyapı var |

## Sıradaki adımlar

1. **Ortak katmanı genişlet:**
   - ~~çeyreklik tablolar ve çeyrek türetme (Q4 = FY − 9 ay)~~ tamam (tablolar v0.2),
   - ~~hisse sayısı (dei kapak sayfası)~~ tamam (tablolar v0.2),
   - menkul kıymetler ve kira yükümlülükleri,
   - çeyreklik ve TTM oranları.
2. **Motorları ortak katmana taşı:**
   - ~~Önce mutabakat~~ tamam (`katman_mutabakati.py`). Her rapor Piotroski ve TTM girdilerini ortak katmanla karşılaştırır, farkları gösterir.
   - **Açık karar:** Piotroski gelir etiketlerinde %5'e kadar farkı kabul ediyor, ortak katman %0,5'te duruyor. Taşıma bu eşiklerden birinde birleşmeyi gerektirir:
     - %0,5'te birleşirse etiketleri %0,5–%5 arası ayrışan şirketlerde Piotroski göstergeleri "bilinmiyor" olur ve 117 şirketlik kapsam raporundaki sayılar değişir.
     - %5'te birleşirse ortak tablolar daha fazla belirsiz değer kabul eder.
   - Karar, gerçek SEC verisiyle mutabakat raporlarında kaç şirketin etkilendiği görüldükten sonra verilmeli.
3. **Tahmin motoru (Ders 6):** ~~v0.1~~ tamam ([TAHMIN_MOTORU_V01.md](TAHMIN_MOTORU_V01.md)).
   - Şirketin kendi geçmişinin çeyreklerinden başlayan, analistin kaynaklı uzun vadeli oranına sönümlenen üç senaryo üretir.
   - Projeksiyonlar istenirse Tahmin Defteri'ne yazılır.
   - Kalan işler: nakit akışı ve yeniden yatırım projeksiyonu, web formunda uzun vadeli oran girişi.
4. **Sapma analizi (Ders 8):** ~~v0.1~~ tamam ([SAPMA_ANALIZI_V01.md](SAPMA_ANALIZI_V01.md)). Defterdeki tahminler yeni 10-K'larla eşlenir. Puanlama ilk bildirilen değere göre yapılır. Özet, sistematik yanlılığı ve gerçekleşenin senaryo aralığında kalıp kalmadığını gösterir.
5. **Senaryo ve duyarlılık (Ders 7) — sıradaki:** Temkinli / baz / iyimser senaryolar ve iskonto × büyüme duyarlılık tablosu araştırma raporuna eklenir. Net borç ve hisse sayısı ortak katmandan önerilir, analist onaylar.
6. **Araştırma asistanı (Ders 1, 9):**
   - Rapordaki JSON'dan yalnız kaynaklı rakamlarla güçlü/zayıf yön ve risk özeti yazar.
   - Her cümle bir veri hücresine bağlanır.
   - Bir dil modeli API'si gerektirir. Bu adım ücretsiz değildir ve API anahtarı ister; diğer bütün adımlar standart Python ile çalışır.

## Değişmeyen ilkeler

- Eksik veri 0 değildir; çelişen kaynak çözülmüş gibi gösterilmez.
- Her rakam SEC accession ve dosyalama tarihine kadar izlenebilir; `as_of` sonrası bilgi kullanılmaz.
- Piotroski, oranlar, kredi notları ve DCF ayrı kanıt katmanlarıdır; tek bir "yatırım puanı"na dönüştürülmez.
- Al/sat sinyali ve hedef fiyat üretilmez.
