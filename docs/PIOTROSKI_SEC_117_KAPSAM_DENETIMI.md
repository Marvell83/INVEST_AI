# 117 SEC Company Facts kaydında Piotroski veri kapsamı

- **Veri arşivi:** Yerel `SEC_GENIS_KISIM_0001.zip` içindeki `ham_SEC/companyfacts/CIK*.json.gz` kayıtları
- **Çözümleme tarihi / bilgi kesiti:** 2026-10-20
- **Kayıt sayısı:** 117
- **İşlem:** `piotroski_fscore.compute_piotroski(..., sector="non_financial")` kullanılarak tamamen çevrimdışı **teknik veri kapsamı** kontrolü
- **Önemli uyarı:** Bu tarama 117 şirketin tamamının finans dışı olduğunu **doğrulamaz**. Fonlar, finansal şirketler veya US-GAAP dışı kurumlar bu örneklemde bulunabilir. Sektör sınıflandırması onaylanmadan üretilen aşağıdaki değerler gerçek şirket elemesi, tam Piotroski sıralaması veya yatırım tavsiyesi değildir.

| Hesaplanabilen 9 sinyal adedi | Şirket sayısı |
| --- | ---: |
| 0 | 8 |
| 1 | 0 |
| 2 | 0 |
| 3 | 1 |
| 4 | 3 |
| 5 | 14 |
| 6 | 23 |
| 7 | 37 |
| 8 | 31 |
| 9 | 0 |
| **Toplam** | **117** |

Sinyal başına **eksik veya hesaplanamaz** şirket sayısı:

| Sinyal | Eksik |
| --- | ---: |
| ROA > 0 | 8 |
| CFO > 0 | 15 |
| ROA iyileşmesi | 9 |
| CFO > net kâr | 15 |
| Uzun vadeli kaldıraç azalışı | **66** |
| Cari oran artışı | 10 |
| Özsermaye ihracı bulunmaması | **117** |
| Brüt marj iyileşmesi | **61** |
| Varlık devir hızı artışı | 22 |

Buna göre en büyük muhasebe normalizasyon açığı **uzun vadeli borç** ve **brüt kâr** etiketlerindedir. Özsermaye ihracı bilgisi ise bilinçli olarak otomatik tahmin edilmez; ilgili 10-K sermaye hareketleri ve ihraç açıklamalarının tarihli, kaynaklı incelenmesi gerekir.

**Puan alt/üst aralığı örneği:** Bir şirketin alt sınırı 6, üst sınırı 7 ise bu 6/9 veya 7/9 kesin puanı değildir; eldeki finansal verilere göre 6–7 arasında **olası** puandır. `Gercek_FScore=BILINMIYOR` alanı bu nedenle boş bir kesin puan yerine açık bilinmezlik bildirir.

[117 satırlık CSV](../reports/PIOTROSKI_SEC_117_KAPSAM_2026-10-20.csv)

## Sonraki kalite iyileştirmesi

1. SEC `CostOfRevenue`, `CostOfGoodsAndServicesSold` gibi kavramlar üzerinden brüt kârı ancak **aynı faaliyet kapsamı, birim, para birimi, mali dönem ve kaynak dosyası** onaylanırsa türet.
2. `LongTermDebtNoncurrent`, `LongTermDebt` ve kira yükümlülüklerini farklı muhasebe tanımlarıyla toplamadan önce karşılaştır. Eksik borç verisini sıfır kabul etme.
3. Yeni hisse ihracı için hissedar özkaynak hareketleri, 10-K dipnotları ve hisse bölünmesi etkilerinin manuel mutabakatını sakla.
4. Şirketin sektörünü doğrula. Banka/sigorta/fonları bu ilk Piotroski sıralamasından çıkar.
5. Geçmişte açıklanmayan hiçbir bilginin geriye dönük tarama skoruna girmesine izin verme.

**Not:** Bu bir veri altyapısı testidir; ekonomik tahmin/portföy getirisi doğruluğu testi değildir.
