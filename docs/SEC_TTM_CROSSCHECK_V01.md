# INVEST_AI — SEC TTM çift motor mutabakatı (v0.1)

**Modül:** `sec_ttm_crosscheck.py` · **Test:** `tests/test_sec_ttm_crosscheck.py`  
**Bağımlılıklar:** Python 3.11+, yalnızca standart kütüphane.

## Neden?

İki mevcut TTM finansal motoru aynı kaynaktan ayrı hesap yapar:

- `ttm_finansallar.calculate_ttm`: SEC 10-K + Q3 9 aylık 10-Q, tarihli ve eksik veriye karşı korumalı temel rapor.
- `sec_ttm.compute_ttm`: aynı şirkette, aynı bilgi kesme tarihinde, seçilen FY ve 9 aylık karşılaştırmalı dönemlerden ikinci hesaplama.

Bu yardımcı araç **gelir, faaliyet kârı, faaliyet nakit akışı ve CapEx** için hesap tutarları yanında her üç kaynak bileşenin `start / end / filed / accession / form / concept / value_usd` alanlarını da karşılaştırır. Bir tutar eşleşse bile dosyalama kaynağı farklıysa sonuç **BLOCKED** olur.

İki motor da aynı ham JSON'u kullandığı için bu yöntem **SEC verisinin gerçekliğini bağımsız olarak teyit etmez**. Resmî siteden doğrudan indirilen dosya ile kullanıcı tarafından verilen çevrimdışı dosya ayrı belirtilir. Geçmiş `as_of` filtresi tek başına arşiv bütünlüğünü ispatlamaz.

## Windows — Apple (resmî SEC API'sinden tek indirme)

Önce geçerli bir iletişim adresini gerçek adresinizle değiştirin:

```powershell
$env:SEC_USER_AGENT = "INVEST_AI Research your-real-email@example.com"
python sec_ttm_crosscheck.py --cik 320193 --as-of 2026-10-24 --download --snapshot-out apple_companyfacts_raw.json --out apple_ttm_audit.json
```

İnternetin kullanılmadığı, önceden indirilmiş ham JSON ile çalışma:

```powershell
python sec_ttm_crosscheck.py --cik 320193 --as-of 2026-10-24 --companyfacts apple_companyfacts_raw.json --out apple_ttm_audit_offline.json
```

Girdi *normalize edilmiş yıllık SEC özeti değil*, ham Company Facts JSON olmalıdır. Apple CIK: `0000320193`. Tek bir çalıştırmada en fazla **bir SEC isteği** yapılır. Kullanılan verinin tekrar incelenebilmesi için `--snapshot-out` ile indirilen kaynak JSON'u saklayın. Bir dosya kullanıcı tarafından veriliyorsa `input_mode=offline_file` olur; doğrudan API bağlantısına dair iddia edilmez.

## Çıktı

- `status = RECONCILED_CALCULATIONS`: iki hesap ve kaynak dönemi/dosyası eşleşti. Bu, **yalnız tarihsel muhasebe hesaplarına dair mutabakattır**.
- `status = BLOCKED`: temel veri eksik, ikinci motor reddediyor ya da herhangi bir tutar/kaynak izi uyuşmuyor. `discrepancies` araştırılmalıdır.
- `canonical_json_sha256`: giriş JSON'unun sıralı anahtarlarla yeniden serileştirilmiş biçiminin SHA-256 özeti. İndirilmiş dosyanın ham bayt özeti değildir, SEC dijital imzası değildir.
- `primary`, `secondary`: iki motorun kaynaklı sonuçları; ikinci motor eksik/kabul dışıysa `secondary` bulunmayabilir.
- `historical_baseline_crosschecked`: yalnız doğrulama işlemine ait boolean.
- `automatic_dcf_enabled = false`: bu aşama otomatik hedef fiyat üretmez.

Başarılı komut **0**, engellenen rapor **2** çıkış koduyla biter. Yanlış CIK, bozuk dosya veya SEC ağ hatası doğrudan hata olarak yükselir.

## Deneysel Apple TTM referansı

21–24 Ekim 2026 araştırma kesitinde 27 Haziran 2026'da sona eren TTM için önceki manuel aktarım çalışmasının karşılaştırma rakamları:

| Kalem | Referans TTM, milyar USD |
| --- | ---: |
| Gelir | 466,823 |
| EBIT | 154,859 |
| CFO | 146,724 |
| CapEx | 10,041 |

Bu sayılar **canlı API sorgusu bu kodla gerçekten çalıştırılmadan yeni doğrulanmış sonuç olarak ilan edilmez**. Referansın dayanağı `docs/TTM_FINANSAL_MOTORU_V01.md` ve `docs/SEC_TTM_V01_APPLE.md` belgeleridir. Geçmiş dönemdeki yeni SEC düzeltmeleri hesap sonucunu değiştirebilir.

## Test

```powershell
python -m unittest discover -s tests -p "test_sec_ttm_crosscheck.py" -v
python -m unittest discover -s tests -v
```

Regresyonlar canlı API'ye bağlanmaz. Kaynak uyuşmazlığı, eksik veri, tarih kesimi, 10-Q/A düzeltmesi, farklı hesap çıktısı, CIK koruması, giriş özeti ve indirmenin test taklidi gibi durumları kapsar. Gerçek SEC bağlantısı ayrıca çalıştırılıp doğrulanmalıdır.

## Bilerek tamamlanmamış alanlar

IFRS/20-F (TSMC dahil), Q1/Q2 TTM, otomatik bilanço/hisse sayısı/ROIC, geleceğe dönük finansal tahmin, güvenilir değerleme ve SEC erişim hız sınırı yönetimi bu modülde yer almaz. CFO−CapEx **FCFF değildir**.
