# INVEST_AI — Dondurulmuş 0.1 Değerleme Kuralları

Bu dosya 0.1'in hesap sözleşmesini korur. 0.2 modülleri geriye dönük olarak 0.1 hesaplarını değiştirmez.

## Girdiler

- `gelir_0`: son bilinen yıllık gelir
- `yillar`: açık tahmin dönemi (N)
- `buyume`: yıllık gelir büyümesi (tek oran veya N oranlık dizi)
- `faaliyet_marji`: EBIT / gelir (SBC gideri dahil; tek oran veya N oranlık dizi)
- `vergi_orani`: 0 ile 1 arasında etkin işletme vergisi
- `satis_sermaye`: marjinal satış / yatırılan sermaye oranı
- `iskonto`: yıllık iskonto oranı r
- `uc_buyume`: terminal nominal büyüme g
- `uc_buyume_tavani`: g için para birimiyle uyumlu limit (varsayılan 0.04)
- `uc_roic`: terminal yeni sermaye getirisi
- `net_borc`: borç eksi nakit
- `hisse`: mevcut seyreltilmiş pay sayısı
- `iskonto_zamani`: `yil_sonu` veya `yil_ortasi`
- `sbc_yontemi`: `gider` veya **deneysel** `sulandirma`

## Hesaplama sözleşmesi

Gelir(t) = Gelir(t−1) × (1 + büyüme(t)).

NOPAT(t) = Gelir(t) × faaliyet_marji(t) × (1 − vergi_orani).

Yeniden yatırım(t) = [Gelir(t) − Gelir(t−1)] / satis_sermaye.

FCFF(t) = NOPAT(t) − yeniden yatırım(t).

Açık dönem bugünkü değeri, yıl sonu yaklaşımında FCFF(t)/(1+r)^t; yıl ortası yaklaşımında FCFF(t)/(1+r)^(t−0.5).

Terminal yılın sonrası NOPAT = Gelir(N) × (1+g) × son faaliyet marjı × (1−vergi).

Terminal FCFF = Terminal NOPAT × (1 − g/uc_roic).

Terminal değer = Terminal FCFF / (r−g). Her iki iskonto yaklaşımında (1+r)^N ile bugüne indirgenir.

Firma değeri = açık dönem bugünkü değerleri + terminal bugünkü değer.

Özsermaye değeri = firma değeri − net borç. Negatif değerler sıfırlanmaz.

Hisse başı değer = özsermaye değeri / hisse sayısı.

0.1 `sulandirma` seçeneği, SBC gelire oranını marja geri ekler ve değeri N yıl sonraki tahmini hisse sayısına böler. **Bu yöntem ekonomik bakımdan kaba olduğundan gerçek şirketlerde kullanılmayacak.** 0.1'e özel uyumluluk için korunmuştur.

## Geçersizlik koşulları

- g ≥ r; g > nominal büyüme tavanı
- iskonto ≤ 0; uç ROIC ≤ 0; satış/sermaye ≤ 0
- hisse sayısı ≤ 0; vergi < 0 veya ≥ 1; yıl sayısı < 1
- tahmin dizileri N uzunluğunda değil
- geçersiz SBC veya iskonto-zamanı seçimi
- SBC gider olarak sayılmışken ek sulandırma seçimi

## Uyarılar

- Büyüme değer yıkıyor: son marj × (1−vergi) × satış/sermaye < r ve pozitif büyüme var
- Açık yıllarda negatif FCFF var
- Terminal bugünkü değer toplam firma değerinin %85'inden fazla
- Uç ROIC iskonto oranının altında
- Özsermaye değeri negatif

## Ters DCF

Sabit yıllık gelir büyümesi −%50 ile +%100 aralığında çözülür; marj, vergi, sermaye verimliliği, iskonto, uç büyüme, uç ROIC, net borç ve hisse sabittir. Tek çözümde büyüme verilir; çoklu çözümde liste, kök bulunamadığında sayı uydurulmaz. 0.1 aralıklı tarayıcısı çift/teğet köklerde eksik kalabilir.

## Elle kontrol — K03

Baz gelir 1000; büyüme 0.20, 0.15, 0.10; marj 0.15, 0.18, 0.20; vergi 0.25; satış/sermaye 2; r 0.09; g 0.03; uç ROIC 0.15; net borç 300; hisse sayısı 50.

| Yıl | Gelir | NOPAT | Yeniden yatırım | FCFF | Bugünkü değer |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1200 | 135 | 100 | 35 | 32.1101 |
| 2 | 1380 | 186.3 | 90 | 96.3 | 81.0538 |
| 3 | 1518 | 227.7 | 69 | 158.7 | 122.5455 |

Terminal değer = 3127.08; terminal bugünkü değer = 2414.6795; firma değeri = 2650.3889; özsermaye değeri = 2350.3889; hisse başı değer = 47.0078; terminal payı ≈ %91.1.

**0.2 için değişiklik gerekiyorsa test seti, belgelendirme ve sürüm birlikte ilerletilir.**
