# SEC TTM finansal motoru v0.1 — Apple gerçek şirket kontrolü

**Modül:** [sec_ttm.py](../sec_ttm.py) · **Test:** [tests/test_sec_ttm.py](../tests/test_sec_ttm.py)

## Kaynak seçimi

Yerel `veri_seti_100_SEC_20261018.zip` arşivindeki `ham_SEC_companyfacts/CIK0000320193_AAPL.json` ham SEC Company Facts verisi kullanıldı. **Bilgi kesme tarihi:** 2026-10-24. Kaynak arşivi 18 Ekim tarihli olduğundan **sonradan oluşan yeni SEC bildirimlerini kapsadığı garanti edilmez**.

Kaynaklar:
- Apple FY2025 10-K: https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm (filing 2025-10-31; accession `0000320193-25-000079`)
- Apple FY2026 Q3 10-Q: https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm (filing 2026-07-31; accession `0000320193-26-000020`)

## Apple — Haziran 2026 sonu TTM

Formül: `2025 mali yıl toplamı + 2026 ilk 9 ay - 2025 ilk 9 ay`. Tüm tutarlar **milyar nominal USD**. Kaynak SEC XBRL'deki değerler USD olup yalnız okunabilirlik için burada milyara bölündü.

| Akış | FY2025 | 9A 2026 | 9A 2025 | TTM (2026-06-27) |
|---|---:|---:|---:|---:|
| Gelir | 416,161 | 364,357 | 313,695 | **466,823** |
| EBIT | 133,050 | 122,432 | 100,623 | **154,859** |
| Faaliyet nakit akışı | 111,482 | 116,996 | 81,754 | **146,724** |
| Maddi duran varlık yatırım ödemeleri | 12,715 | 6,799 | 9,473 | **10,041** |

Operasyonel nakit akışı - CapEx = **136,683 milyar USD**, fakat **FCFF değildir**. Faaliyet kâr marjı: 154,859 / 466,823 = **%33,17** (yaklaşık).

## Neden bu hesap kullanılıyor?

Mevcut deneysel Apple DCF pilotu FY2025 net satışını, FY2026 Q3 bilançosunu ve 2026 Temmuz hisse sayısını birleştirmişti. Yeni TTM çıktısı, yalnız tarihsel işletme gelir/kâr/nakit akışı **tabanı** için ileri bir adım sağlar. **DCF varsayımlarını otomatik düzeltmez**, son tarihli bilanço veya hisse sayısı sağlamaz ve yeniden yatırım tahminini doğrulamaz.

## Denetim kuralları

- Kullanılan üç bileşen: önceki mali yılın 10-K/10-K/A yıllık verisi; güncel 10-Q/10-Q/A yılbaşından bugüne akışı; önceki mali yılın aynı süresine ait karşılaştırmalı 10-Q akışı.
- Tüm bileşenler aynı şirket, USD birimi, aynı mali başlangıç/bitiş düzeni ve `as_of` tarihine kadar yayımlanmış olmalı.
- Aynı dönemde farklı yıllık gelir etiketi, maliyet vb. tutarları **%0,5'i aşan farkla** çelişiyorsa otomatik sonuç reddedilir. Bu %0,5 güvenlik eşiğidir, US-GAAP standardı değildir.
- 13 haftalık tek çeyrek, 39 haftalık YTD yerine kullanılmaz. Eksik karşılaştırmalı dönemler tahmin edilmez.
- IFRS, 20-F, diğer döviz birimleri, finansal bilançolar, EPS, sulandırma, ROIC ve FCFF kapsam dışında.

## Komut

```bash
python sec_ttm.py --companyfacts CIK0000320193_AAPL.json --as-of 2026-10-24 --prior-fy-end 2025-09-27 --current-ytd-end 2026-06-27 --out Apple_TTM.json
python -m unittest discover -s tests -p 'test_sec_ttm.py' -v
```

**Test statüsü:** Çevrimdışı sentetik 12 regresyon testi yerelde başarılı. GitHub Actions'ın push iş akışı başarısı ayrıca teyit edilmelidir. Gerçek Apple SEC veri eşleştirmesinde gelir, EBIT, nakit akışı ve CapEx için tutarlar hesaplandı; sonraki yıllık dönem verileri olmadığına dair kesin iddia yoktur.
