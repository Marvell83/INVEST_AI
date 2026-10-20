# YATIRIM AI — Değerleme Çekirdeği: Hesap Konvansiyonları (dogrulama-0.1)

Bu belge, kabul testinin beklenen değerlerinin dayandığı hesap kurallarını tanımlar. Üretim motoru farklı kodla yazılabilir; ama aynı girdiye, aşağıdaki kurallarla aynı sonucu vermelidir. Bir kural değişecekse bu belge, vakalar ve sürüm numarası birlikte değişir.

## 1. Girdi

| Alan | Anlamı |
| --- | --- |
| `gelir_0` | Son gerçekleşen yıllık gelir (baz yıl) |
| `yillar` | Açık tahmin dönemi N (yıl) |
| `buyume` | Yıllık gelir büyümesi; tek sayı ya da N uzunluğunda liste |
| `faaliyet_marji` | Faaliyet kârı / gelir; tek sayı ya da N uzunluğunda liste. **Hisse bazlı ücret (SBC) gider olarak dahil** |
| `vergi_orani` | Faaliyet kârına uygulanan oran (0 ≤ t < 1) |
| `satis_sermaye` | Satış / yatırılan sermaye: 1 birim ek gelir için gereken yatırım = 1 / satis_sermaye |
| `iskonto` | Ortak referans iskonto oranı r |
| `uc_buyume` | Uç dönem büyümesi g (para birimiyle uyumlu nominal) |
| `uc_buyume_tavani` | g için üst sınır (varsayılan 0,04) |
| `uc_roic` | Uç dönemde yeni sermayenin getirisi |
| `net_borc` | Borç − nakit (negatifse net nakit) |
| `hisse` | Bugünkü seyreltilmiş hisse sayısı |
| `sbc_yontemi` | `gider` (varsayılan) ya da `sulandirma` |
| `sbc_gelire_orani`, `yillik_sulandirma` | Yalnız `sulandirma` yönteminde |
| `iskonto_zamani` | `yil_sonu` (varsayılan) ya da `yil_ortasi` |

## 2. Hesap kuralları

1. **Gelir:** Gelir(t) = Gelir(t−1) × (1 + büyüme(t)).
2. **NOPAT:** Gelir(t) × marj(t) × (1 − vergi). v0.1 basitleştirmesi: zarar yıllarında vergi simetrik uygulanır (devreden zarar yok).
3. **Büyüme bedava değildir:** Yeniden yatırım(t) = [Gelir(t) − Gelir(t−1)] / satis_sermaye. Aynı yıl içinde. Gelir düşerse sermaye serbest kalır (negatif yatırım).
4. **FCFF(t)** = NOPAT(t) − yeniden yatırım(t).
5. **İskonto:** Yıl sonu: (1 + r)^−t. Yıl ortası: (1 + r)^−(t − 0,5).
6. **Uç değer:** Gelir(N+1) = Gelir(N) × (1 + g); NOPAT(N+1) son yılın marjıyla; FCFF(N+1) = NOPAT(N+1) × (1 − g / uç ROIC); Uç değer = FCFF(N+1) / (r − g). Her iki konvansiyonda da (1 + r)^−N ile bugüne getirilir.
7. **Firma değeri** = açık dönem bugünkü değer + uç değerin bugünkü değeri. **Özsermaye** = firma − net borç; negatifse negatif raporlanır, sıfıra yuvarlanmaz.
8. **Hisse başı değer:** `gider` yönteminde özsermaye / bugünkü hisse. `sulandirma` yönteminde marja sbc_gelire_orani geri eklenir ve özsermaye, N yıl sonraki hisse sayısına bölünür: hisse × (1 + yillik_sulandirma)^N.
9. **Uç değer payı** = uç değerin bugünkü değeri / firma değeri (firma değeri ≤ 0 ise tanımsız).

## 3. Geçersiz girdiler (durum = `gecersiz`, sayı üretilmez)

`UC_BUYUME_ISKONTOYU_ASIYOR` (g ≥ r), `UC_BUYUME_TAVAN_USTU` (g > tavan), `SBC_CIFT_SAYIM` (`gider` yönteminde sulandırma > 0), `LISTE_UZUNLUGU_UYUMSUZ`, `ISKONTO_GECERSIZ`, `UC_ROIC_GECERSIZ`, `SATIS_SERMAYE_GECERSIZ`, `HISSE_GECERSIZ`, `VERGI_GECERSIZ`, `YIL_SAYISI_GECERSIZ`, `SBC_YONTEMI_GECERSIZ`, `ISKONTO_ZAMANI_GECERSIZ`.

## 4. Uyarılar (sayı üretilir, yanında işaret)

| Kod | Koşul |
| --- | --- |
| `BUYUME_DEGER_YIKIYOR` | Herhangi bir yılda büyüme > 0 ve yeni sermayenin getirisi (son yıl marjı × (1 − vergi) × satis_sermaye) < r |
| `NEGATIF_FCFF_YILLARI` | Açık dönemde en az bir yıl FCFF < 0 |
| `UC_DEGER_BASKIN` | Uç değer payı > %85 |
| `UC_ROIC_ISKONTO_ALTINDA` | uç ROIC < r ve g > 0 |
| `OZSERMAYE_NEGATIF` | Özsermaye değeri < 0 |

## 5. Ters DCF

Fiyatın ima ettiği **sabit yıllık gelir büyümesi** çözülür. Marj, satış/sermaye, vergi, iskonto, uç büyüme, uç ROIC, net borç, hisse, SBC yöntemi ve iskonto zamanı **sabit tutulur** ve çıktıda `sabit_tutulanlar` olarak listelenir. Arama aralığı −%50 ile +%100. Durumlar:

- `tek_cozum`: tek kök; `ima_edilen_buyume` verilir.
- `cozum_yok`: aralıkta hiçbir büyüme fiyatı haklı çıkarmıyor; `ima_edilen_buyume` = None. **Sayı uydurulmaz.**
- `coklu_cozum`: birden çok kök; hepsi `tum_cozumler` içinde, tekil değer None.

## 6. Elle hesap: K03

Girdi: gelir 1.000; büyüme %20, %15, %10; marj %15, %18, %20; vergi %25; satış/sermaye 2; r %9; g %3; uç ROIC %15; net borç 300; hisse 50.

| Yıl | Gelir | NOPAT | Yeniden yatırım | FCFF | İskonto faktörü | Bugünkü değer |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1.200,0000 | 135,0000 | 100,0000 | 35,0000 | 0,917431 | 32,1101 |
| 2 | 1.380,0000 | 186,3000 | 90,0000 | 96,3000 | 0,841680 | 81,0538 |
| 3 | 1.518,0000 | 227,7000 | 69,0000 | 158,7000 | 0,772183 | 122,5455 |

Uç değer: 1.518 × 1,03 × %20 × 0,75 × (1 − 0,03/0,15) / (0,09 − 0,03) = **3.127,08**, bugünkü değeri 2.414,6795.
Firma değeri **2.650,3889**; özsermaye 2.350,3889; hisse başı **47,0078**; uç değer payı %91,1.

## 7. Üretim motorunu bağlama

1. `motor_adaptoru.py` içindeki içe aktarma satırını kendi `degerle(girdi)` ve `ters_dcf(girdi, fiyat)` fonksiyonlarınızla değiştirin. Çıktı alan adları referans motorla aynı olmalı.
2. `python kabul_testi.py` çalıştırın. 17/17 geçmeden motor gerçek şirket verisine bağlanmaz.
3. `python -m unittest test_dogrulama_seti -v`: setin kendisinin dişli olduğunu gösterir. Bilinen yedi DCF hatasını içeren bozuk motorlar ilgili vakalarda kalır.