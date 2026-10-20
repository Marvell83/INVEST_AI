# SEC 10-K gelir satırı mutabakatı — 7 araştırılmış aday

**Kesme tarihi:** 2026-10-20. **Durum:** Resmî SEC 10-K belgelerinde tablo satırları incelendi; yerel SEC Company Facts arşivinde **7/7 mali dönem, XBRL tutarı ve accession eşleşti**. Bu çalışma bir **inceleme adayı dosyasıdır**, henüz yetkilendirilmiş analist imzası değildir.

| CIK | Şirket | FY sonu | Yıllık konsolide gelir (USD) | Gerekçe |
| --- | --- | --- | ---: | --- |
| 0000004457 | U-Haul Holding Company | 2026-03-31 | 6,037,819,000 | Grup konsolide hasılatı; alternatif etiketler alt faaliyetleri içeriyor |
| 0000014693 | Brown-Forman | 2026-04-30 | 3,928,000,000 | 5,082 milyon USD brüt satış eksi 1,154 milyon tüketim vergisi |
| 0000016918 | Constellation Brands | 2026-02-28 | 9,139,000,000 | 9,755.5 milyon USD brüt satış eksi 616.5 milyon tüketim vergisi |
| 0000018926 | Lumen Technologies | 2025-12-31 | 12,402,000,000 | Grup konsolide faaliyet hasılatı; daha dar 11,331 milyonluk ASC606 etiketi değil |
| 0000024545 | Molson Coors | 2025-12-31 | 11,140,800,000 | 13,040.3 milyon USD satış eksi 1,899.5 milyon tüketim vergisi |
| 0000030625 | Flowserve | 2025-12-31 | 4,729,260,000 | Konsolide gelir tablosundaki Sales; alternatif sıfır etiket reddedilmeli |
| 0000033533 | Espey Mfg. & Electronics | 2026-06-30 | 46,124,325 | Gelir tablosundaki Net sales; küçük alternatif etiket farklı bir bileşen |

## Her satırın birincil SEC kanıtı

- [U-Haul FY2026 10-K](https://www.sec.gov/Archives/edgar/data/4457/000119312526241850/uhal-20260331.htm) — Consolidated Statements of Operations; consolidated revenue.
- [Brown-Forman FY2026 10-K](https://www.sec.gov/Archives/edgar/data/14693/000001469326000024/bfb-20260430.htm) — Consolidated Statements of Operations, FY2026 net sales.
- [Constellation Brands FY2026 10-K](https://www.sec.gov/Archives/edgar/data/16918/000001691826000011/stz-20260228.htm) — Consolidated Statements of Comprehensive Income (Loss).
- [Lumen FY2025 10-K](https://www.sec.gov/Archives/edgar/data/18926/000001892626000014/lumn-20251231.htm) — Consolidated Statements of Operations, Operating Revenue.
- [Molson Coors FY2025 10-K](https://www.sec.gov/Archives/edgar/data/24545/000002454526000006/tap-20251231.htm) — Consolidated Statements of Operations, Net sales.
- [Flowserve FY2025 10-K](https://www.sec.gov/Archives/edgar/data/30625/000003062526000003/fls-20251231.htm) — Consolidated Statements of Income, Sales.
- [Espey FY2026 10-K](https://www.sec.gov/Archives/edgar/data/33533/000117494726000891/esp-20260630.htm) — Statements of Comprehensive Income, Net sales.

Birincil kanıtların tarih/dönem/tutarları [ham araştırma adayları JSON](../evidence/sec_2026_revenue_review_candidates.json) içerisinde saklı. Çelişkileri belirleyen özgün inceleme raporu: [SEC kaynak kalite kapısı](SEC_KAYNAK_DENETIMI_V02.md).

## İşletim ve onay politikası

`sec_revenue_reconciliation.py` yalnızca **açık şekilde `approved` olan** ve analist kimliği, onay tarihi, CIK, FY sonu, XBRL etiketi, tutar, accession, doğrudan SEC 10-K bağlantısı ve gerekçesi tutan insan-onaylı kayıtları kabul eder. SEC XBRL tutarını ve kaynak URL biçimini kodla denetler. **10-K'nin HTML içeriğini otomatik okuyup kanıtlamaz**; onayın gerçek bir insandan geldiğini kriptografik olarak kanıtlamaz.

`sec_reviewed_pipeline.analyze_and_record(..., revenue_review=review)` isteğe bağlı onay kaydını kullanır. Onay yoksa yedi çelişki için model hâlâ durur; sahte hisse başı değer üretmez. Tam uzlaştırma olmadan doğrudan `sec_v02_bridge.py` kullanmak korumayı atlayabilir.

Örnek akış: araştırma JSON'undan tek şirketin alanlarını alıp kaynak dosyayı bizzat kontrol eden kişi `status` alanını `approved` yapar ve `reviewer`, `reviewed_at`, `rationale` alanlarını tamamlar; onay JSON'u `--revenue-review review.json` üzerinden CLI'ye verilir.

### Test ve ekonomik sınırlar

Yerel sentetik testler için koşul: `PYTHONPATH=. python -m unittest discover -s tests -v`. Test ortamında SQLite için ayrı bir uyumluluk adaptörü kullanıldığı için **GitHub'daki asıl TahminDefteri ile CI doğrulaması ayrıca gerekir**. Yedi gerçek SEC tutarının Company Facts alanları yerel arşivde ayrı denetlenmiştir.

**Bu çözüm yalnız gelir veri kalitesi sorunudur.** Gelecekteki büyüme, marj, iskonto, net borç ve hisse adedi ayrıca belgelenmeden DCF veya yatırım kararı üretilmez. Lumen'in negatif EBIT'i, Espey'nin konsantrasyon riski gibi meseleler ayrı normalizasyon/risktir. Ayrıca kaynak çıktıları analistin onayladığı tarihle otomatik geçmişe dönük tahmin sayılmamalıdır.
