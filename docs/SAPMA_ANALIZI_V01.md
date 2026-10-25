# Sapma Analizi v0.1 — tahmin ve gerçekleşen

`sapma_analizi.py`, yol haritasındaki 8. dersin ("Bütçe ve sapma analizi") yatırımcı karşılığıdır ([YOL_HARITASI.md](YOL_HARITASI.md)). Tahmin Defteri'ndeki tahminleri, hedefledikleri mali yılın SEC'e bildirilmiş gerçekleşen değeriyle eşler. Ardından hatayı ölçer, istenirse sonucu deftere kaydeder.

## Ne eşlenir?

| Tahmin kaynağı | Hedef dönem biçimi | Eşleşme kuralı |
|---|---|---|
| `tahmin_motoru.py` | `FY+k_AFTER_2025-09-27` | Taban mali yıldan sonraki k. mali yıl. Aradaki her yıl ortak tablolarda art arda olmalı (330–400 gün). Bir yıl eksikse eşleşme yapılmaz (`FISCAL_YEAR_CHAIN_BROKEN`). |
| `sec_reviewed_pipeline.py` | `FY_END:2026-09-26` | Mali yıl sonu bu tarihe en çok 7 gün uzak olan tek yıl (52/53 haftalık mali takvimler için). |

| Tahmin ölçütü | Gerçekleşen değer |
|---|---|
| `revenue` | ortak tablolarda gelir |
| `operating_income`, `ebit` | ortak tablolarda faaliyet kârı |
| `fcff` | **puanlanmaz** (`NOT_OBSERVABLE`): şirketler FCFF bildirmez, CFO − CapEx de FCFF değildir |

Yalnız raporu istenen şirketin (`CIK:<10 hane>`) tahminleri değerlendirilir. Bilgi tarihinden (`as_of`) sonra dosyalanan 10-K görünmez; o tahmin `NOT_YET_REPORTED` kalır.

## Hata ölçüleri

- **İşaretli hata** = tahmin − gerçekleşen. Pozitif değer, tahminin gerçekleşenden yüksek olduğunu gösterir.
- **Yüzde hata** = işaretli hata / |gerçekleşen|.
- **Senaryo ve ölçüt özeti:**
  - ortalama mutlak yüzde hata,
  - ortalama işaretli yüzde hata (sistematik iyimserlik veya kötümserlik).
- **Senaryo aralığı isabeti:** Aynı projeksiyonun temkinli ve iyimser tahminleri varsa, gerçekleşen değerin bu ikisinin arasında kalıp kalmadığı sayılır.

**Gerçekleşen değer ilk bildirilen değerdir.** Şirket rakamı sonradan revize ederse yeni değer ve "revize edildi" işareti raporda görünür, ama puan değişmez. Böylece bir tahmin, tahmin yapıldıktan sonra öğrenilen bir düzeltmeye göre yargılanmaz.

## Kayıt

- Varsayılan olarak hiçbir şey yazılmaz; yalnız rapor üretilir.
- `record=True` (CLI'da `--record`) ile, Tahmin Defteri'ne şunlar sadece eklemeli olarak yazılır:
  - her hedef ve ölçüt için bir **gerçekleşen** kaydı; kaynakta SEC accession, dosyalama tarihi, XBRL kavramı ve mali yıl bulunur,
  - her tahmin için bir **puan** kaydı.
- Yazma tek işlemdir: yarıda hata olursa hiçbir satır kalmaz.
- Aynı analiz tekrar çalıştırılırsa yeni satır eklenmez; satırlar `already_recorded` olarak işaretlenir.

Bu amaçla Tahmin Defteri'ne üç okuma yöntemi eklendi:
- `tahminleri_listele(ayrintili=True)`,
- `gerceklesenleri_listele()`,
- `puanlari_listele()`.

Ayrıca `gerceklesen_kaydet` ve `puanla` artık dışarıda açılmış bir işleme katılıyor (`tahmin_kaydet` ile aynı davranış).

## Kullanım

```bash
# 1) Bugün: senaryoları deftere yaz
python tahmin_motoru.py --companyfacts CIK0000320193.json --as-of 2026-10-25 \
  --long-run-growth 0.03 --long-run-source "..." --ledger tahminler.sqlite \
  --record-scenarios temkinli,baz,iyimser --out reports/aapl_senaryo.json

# 2) Bir sonraki 10-K açıklandıktan sonra: güncel SEC verisiyle puanla
python sapma_analizi.py --ledger tahminler.sqlite --companyfacts CIK0000320193_yeni.json \
  --as-of 2027-11-15 --record --out reports/aapl_sapma.json --out-html reports/aapl_sapma.html
```

## Sınırlar

- Yalnız yıllık hedefler. Çeyreklik tahmin ve sapma sonraki adımdır.
- Birkaç tahmine dayanan isabet, gelecekteki tahmin başarısının kanıtı değildir. Anlamlı bir ölçüm için çok sayıda şirket ve yıl birikmelidir.
- Bilgi tarihi bugünden eski kurulan (geçmişe dönük) projeksiyonlar defterde `retrospective: true` taşır. Bunların puanı gerçek bir "önceden tahmin" başarısı sayılmamalıdır.
- Satın alma, elden çıkarma veya muhasebe değişikliği olan yıllarda sapma, tahmin yönteminden çok kapsam değişikliğini yansıtabilir.

## Testler

`tests/test_sapma_analizi.py` (12 test). Kapsadıkları durumlar:
- puanlanan ve henüz açıklanmamış yıllar,
- kayıt yapılmayan çalışma, tekrar kaydın engellenmesi, tek gerçekleşen kaydı,
- revizyonda ilk bildirilen değerin kullanılması, dosyalama tarihinden önce görünmezlik,
- `FY_END` hedefleri ve 7 gün toleransı, FCFF'nin puanlanmaması, eksik mali yılın atlanmaması,
- desteklenmeyen dönem biçimi ve başka şirketin tahminleri,
- özet istatistikleri, yarıda hata durumunda hiçbir satır kalmaması,
- CLI, HTML karakter kaçışı ve defterin dış işleme katılması.
