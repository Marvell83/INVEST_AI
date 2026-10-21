# INVEST_AI — İlk gerçek şirket pilotu: Apple (AAPL)

**Kapsam:** 21 Ekim 2026 bilgi kesme tarihinden önce yayımlanan **yıllık** SEC Company Facts verileriyle çevrimdışı finansal kalite incelemesi. Verinin saklandığı arşiv 18 Ekim 2026 tarihli yerel SEC paketinden alınmıştır. Bu, canlı SEC API çağrısı veya 2026 tam yıl bilançosu değildir.

## Kaynaklar

- **Birincil denetim kaynağı:** Apple 2025 Form 10-K, SEC Accession `0000320193-25-000079`, 31 Ekim 2025 tarihinde sunulmuştur. [SEC 10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm).
- Ham XBRL: [SEC Company Facts, CIK 0000320193](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json).
- 2025 mali yılı: 27 Eylül 2025'te biter; 2024 mali yılı: 28 Eylül 2024'te biter.
- Yerel kaynak dosyası: `veri_seti_100_SEC_20261018.zip` içindeki `ham_SEC_companyfacts/CIK0000320193_AAPL.json`.
- Kullanılan ham JSON'un SHA-256 özeti **`057f527aaef52cf6e3da7b3c1582fbd46c69695f5e27b75b9a1c3e27c2cfecd7`**; arşivin SHA-256 özeti **`58636d6d73d05f8814a648b551bb4a9abc0698e39b6ec512d447dff3f71c7b7f`**.

## 2025 finansal gerçekler (milyon USD)

| Kalem | 2025 FY | Seçilen US-GAAP XBRL kavramı |
| --- | ---: | --- |
| Net satış | 416.161 | `RevenueFromContractWithCustomerExcludingAssessedTax` |
| Net kâr | 112.010 | `NetIncomeLoss` |
| Faaliyetlerden nakit akışı | 111.482 | `NetCashProvidedByUsedInOperatingActivities` |
| Brüt kâr | 195.201 | `GrossProfit` |
| Toplam varlıklar | 359.241 | `Assets` |
| Uzun vadeli borç, cari olmayan | 78.328 | `LongTermDebtNoncurrent` |
| Dönen varlıklar | 147.957 | `AssetsCurrent` |
| Kısa vadeli yükümlülükler | 165.631 | `LiabilitiesCurrent` |

Verilerin tümü SEC kaynağında nominal **USD** olarak yer alır; tablodaki birim *milyon USD* için bölünmüştür. Bu kalemler SEC 10-K ile örnek çapraz kontrole uygundur. Bilgi kesme tarihi, 2026 mali yılı 10-K raporunun mevcut olduğu iddiası değildir.

## Piotroski F-Score — 7 ile 8 aralığında

| Dokuz ölçüt | 2025 hesaplama sonucu |
| --- | --- |
| ROA pozitif | 1 |
| Faaliyet nakit akışı pozitif | 1 |
| ROA artıyor | 1 |
| **Faaliyet nakit akışı > net kâr** | **0**; 111,482 milyar < 112,010 milyar USD |
| Uzun vadeli borç oranı düşüyor | 1 |
| Cari oran artıyor | 1 |
| Yeni özsermaye ihracı yok | **Bilinmiyor**; kaynaklı insan incelemesi bekliyor |
| Brüt marj artıyor | 1 |
| Varlık devir hızı artıyor | 1 |

**Sonuç:** 8 bilinen sinyalden 7'si 1 puan. Dokuzuncu kanıt beklediğinden kesin bir **7/9** veya **8/9** yayımlanmaz; `score=null`, `score_range=[7,8]`.

## Örnek çalıştırma

```bash
python gercek_sirket_pilotu.py \
  --companyfacts CIK0000320193_AAPL.json \
  --expected-cik 0000320193 \
  --sector non_financial \
  --as-of 2026-10-21 \
  --expected-fiscal-end 2025-09-27 \
  --snapshot-note "Archived Company Facts snapshot, 2026-10-18" \
  --out-json apple_quality.json \
  --out-html apple_quality.html
```

Windows komut satırında `\` satır sonları yerine **tek satır** kullanın. Python 3.11+ ve standart kütüphane yeterlidir. `piotroski_fscore.py`, `kredi_notlari.py`, `sec_companyfacts.py`, `sirket_analiz_paneli.py` aynı proje kökünde bulunmalıdır. Test: `python -m unittest discover -s tests -v`.

## Sınırlar ve sonraki çalışma

1. Puan kârlılığın **iyileşmesini** ölçer; hissenin düşük fiyatlı olduğunu kanıtlamaz.
2. Özsermaye ihracı göstergesini yalnızca azalan hisse sayısıyla doğrulamayın; 10-K özkaynak, opsiyon ve çalışan hisseleri incelemesi gerekir.
3. Moody's/S&P/Fitch notları **bu raporda girilmedi**, gerçek kredi notu varmış gibi gösterilmez.
4. Net borç ve hisse adedi için aynı tarihli kaynaklı varsayımlar olmadan DCF rakamı **üretilmez**. Şirketin 2025 bilgilerini bugünkü hisse fiyatına doğrudan karşılaştırmayın.
5. SEC Company Facts anlık arşivi her standardın ve şirketin tüm finansal dipnotlarını temsil etmez; borç göstergeleri özellikle dipnot kontrolüne tabidir.
6. Analizin çalıştırıldığı tarih ile bilgi kesme tarihi karıştırılmaz; bu geriye dönük yapılmış bir yatırım tahmini değildir.
7. Gelecek araştırması için: çoklu sektör senaryoları, sermaye giderleri ve ters DCF; bunlar bu pilotta henüz yoktur.