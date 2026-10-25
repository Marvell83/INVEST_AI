# Tahmin Motoru v0.1 — tarihsel baz ve senaryolar

`tahmin_motoru.py`, yol haritasındaki 6. dersin ("Tahminleme ve karar destek sistemleri") ilk sürümüdür ([YOL_HARITASI.md](YOL_HARITASI.md)). Ortak finansal tablolardan ([FINANSAL_TABLOLAR_V01.md](FINANSAL_TABLOLAR_V01.md)) şirketin kendi geçmişini özetler ve bu geçmişe dayanan şeffaf senaryolar üretir.

## Temel ilke: sistem varsayım uydurmaz

Bir projeksiyonun iki kaynağı vardır:

1. **Şirketin kendi SEC geçmişi.** Yıllık gelir büyümesi, faaliyet kâr marjı, efektif vergi, serbest nakit akışı marjı ve satış / yatırılan sermaye artışı. Bunlar ölçümdür, varsayım değildir; kullanılan SEC dosyaları `sources` alanında tutulur.
2. **Analistin tek girdisi: uzun vadeli nominal büyüme oranı.** Kaynağı en az 8 karakterle yazılmadan kabul edilmez ve −%5 ile +%8 arasında olmalıdır. Sistem bu oranı hiçbir zaman kendisi seçmez.

## Tarihsel baz

`historical_baseline(statements, ratios)` her ölçü için medyan, alt çeyrek, üst çeyrek, en düşük, en yüksek ve gözlem sayısını verir. Ayrıca art arda gelen mali yıllar boyunca gelirin yıllık bileşik büyümesini (CAGR) hesaplar.

**Satış / yatırılan sermaye:** Yalnız gelirin ve yatırılan sermayenin (özkaynak + toplam borç − nakit) birlikte arttığı yıllarda hesaplanır. Diğer yıllarda oran anlamsız ya da negatif olur.

Taban, geçmiş yetersizse `INSUFFICIENT_HISTORY` döner ve gerekçeleri listeler. Yeterli geçmiş için şunlar gerekir:
- son yılın geliri pozitif olmalı,
- son yılın faaliyet marjı hesaplanabilmeli,
- en az iki büyüme ve iki marj gözlemi bulunmalı.

## Senaryolar

`project_scenarios(baseline, years=5, long_run_growth=..., long_run_growth_source=...)`

| Senaryo | Başlangıç büyümesi | Hedef faaliyet marjı |
|---|---|---|
| Temkinli | şirketin yıllık büyümelerinin alt çeyreği | marjların alt çeyreği |
| Baz | medyan | medyan |
| İyimser | üst çeyrek | üst çeyrek |

- Büyüme, başlangıç değerinden **son yılda tam olarak** uzun vadeli orana doğrusal olarak iner. k. yıldaki büyüme = başlangıç + (uzun vade − başlangıç) × k / yıl sayısı.
- Marj, son gerçekleşen marjdan senaryo hedefine doğrusal olarak gider.
- Faaliyet kârı = gelir × marj.
- Üçten az gözlem varsa yalnız baz senaryo gösterilir (`SHORT_HISTORY_ONLY_BASE_SCENARIO`).
- Uyarılar:
  - tarihsel medyan büyüme %25'in üzerindeyse `HIGH_HISTORICAL_GROWTH_RARELY_PERSISTS`,
  - uzun vadeli oran %5'in üzerindeyse `LONG_RUN_GROWTH_ABOVE_TYPICAL_NOMINAL_ECONOMY`.
- **Geçmişe dönük senaryo:** Bilgi tarihi (`as_of`) bugünden eskiyse `retrospective: true` olur. Böyle bir senaryo o tarihte yapılmış bir tahmin gibi değerlendirilemez.

Senaryolar olasılık dağılımı değildir; şirketin kendi geçmişinin yayılımını geleceğe taşıyan basit, açık bir yöntemdir.

## Tahmin Defteri kaydı (Ders 8'e hazırlık)

`record_projection(projection, db_path=..., scenarios=("baz",))` her senaryo yılı için gelir ve faaliyet kârını sadece eklemeli SQLite Tahmin Defteri'ne yazar.

- **Hedef dönem:** `FY+k_AFTER_<son mali yıl sonu>` (ör. `FY+1_AFTER_2025-09-27`). Sonraki 10-K'lar gelince bu dönemler ortak tablolardaki gerçekleşen mali yıllarla eşleştirilecek; sapma analizi sıradaki adımdır.
- **Kaydedilenler:** varsayımlar (senaryo, başlangıç büyümesi, hedef marj, uzun vadeli oran, yöntem, geçmişe dönük olup olmadığı) ve kaynaklar (SEC dosyaları, uzun vadeli oranın kaynağı).
- **Bütünlük:**
  - Kayıt tek işlemdir; yarıda hata olursa hiçbir satır kalmaz.
  - Aynı projeksiyon iki kez yazılamaz.

## Kullanım

Tek komutluk şirket araştırmasında tarihsel baz her zaman rapora eklenir. Senaryolar için analistin oranı ve kaynağı birlikte verilmelidir:

```bash
python sirket_arastirma_akisi.py --cik 320193 --as-of 2026-10-24 --sector non_financial \
  --download --snapshot-out veri/aapl.json \
  --long-run-growth 0.03 --long-run-source "Analist varsayımı: uzun vadeli nominal büyüme, kaynak ..." \
  --out-json reports/aapl.json --out-html reports/aapl.html
```

Bağımsız kullanım ve deftere kayıt:

```bash
python tahmin_motoru.py --companyfacts CIK0000320193.json --as-of 2026-10-24 --years 5 \
  --long-run-growth 0.03 --long-run-source "..." \
  --ledger tahminler.sqlite --record-scenarios temkinli,baz,iyimser --out reports/aapl_senaryo.json
```

Web formunda da "Senaryo ve değerleme girdileri" bölümünden uzun vadeli oran ve kaynağı girilebilir ([WEB_SIRKET_ANALIZI_V02.md](WEB_SIRKET_ANALIZI_V02.md)).

## Sınırlar

- Yalnız gelir ve faaliyet kârı projekte edilir. Serbest nakit akışı, yeniden yatırım ve DCF bağlantısı sonraki adımdır (Ders 7).
- Gözlem sayısı az olduğunda (5 yıllık geçmişte 4 büyüme gözlemi) çeyrekler kaba bir yayılım ölçüsüdür.
- Satın alma, elden çıkarma, döviz ve muhasebe değişiklikleri geçmiş büyümeyi bozabilir; motor bunları ayırt etmez.
- Senaryolar tahmin isabeti kanıtı değildir. İsabet, Tahmin Defteri'nde gerçekleşen değerlerle zamanla ölçülmelidir.

## Testler

`tests/test_tahmin_motoru.py` (20 test) şunları kapsar:
- çeyrek ve medyan hesapları, CAGR, satış / sermaye koşulu,
- yetersiz geçmiş, senaryo sırası ve son yılda uzun vadeli orana ulaşma,
- aritmetik, uyarılar ve girdi doğrulama,
- geçmişe dönük senaryo bayrağı,
- deftere kayıt, tekrar kaydın engellenmesi ve yarıda hata durumunda hiçbir satır kalmaması,
- CLI, rapor bölümü ve HTML karakter kaçışı.
