# Senaryo Değerlemesi v0.1 — senaryolardan DCF'ye

`senaryo_degerleme.py`, yol haritasındaki 7. dersin ("Senaryo planlama ve What-if analizleri") ilk sürümüdür ([YOL_HARITASI.md](YOL_HARITASI.md)). Tahmin motorunun ([TAHMIN_MOTORU_V01.md](TAHMIN_MOTORU_V01.md)) temkinli, baz ve iyimser senaryolarını deneysel v0.2 DCF motoruyla değerler. Baz senaryo için iskonto oranı × uç dönem büyümesi duyarlılık tablosu üretir.

## Aynı yol, aynı rakamlar

Her senaryo DCF'ye **aynı gelir ve faaliyet marjı yoluyla** girer. Bunun için `degerleme_v02.py` opsiyonel `marj_yolu` (yıllık marj listesi) girdisi kazandı. Bu girdi verilmezse motorun eski yakınsama formülü değişmeden çalışır.

Modül, DCF'nin yıllık gelirinin projeksiyonla aynı olduğunu her çalıştırmada kontrol eder. Fark çıkarsa değerleme yapmaz ve hata verir.

## Her girdinin kökeni

| Girdi | Varsayılan kaynak | Köken |
|---|---|---|
| İskonto oranı | **zorunlu analist girdisi** (%4–%20, kaynaklı) | Analist |
| Uç dönem büyümesi | projeksiyondaki uzun vadeli oran (aynı kaynak); en fazla %4 | Analist |
| Vergi oranı | şirketin efektif vergi oranlarının medyanı | Şirket geçmişi (SEC) |
| Satış / yatırılan sermaye | şirketin satış / sermaye artışı medyanı | Şirket geçmişi (SEC) |
| Net borç | son mali yıl sonunda toplam borç − nakit ve nakit benzerleri | SEC dosyası |
| Hisse sayısı | kapak sayfası dolaşımdaki hisse (`dei`) | SEC dosyası |
| Uç dönem RONIC | iskonto oranına eşit: büyüme tek başına değer yaratmaz | Yöntem varsayılanı |

- **Değiştirme:** Analist bu girdilerin her birini kaynağıyla değiştirebilir (`overrides`; CLI'da `--net-debt`, `--net-debt-source` vb.).
- **Eksik girdi:** Bir girdi geçmişten veya SEC'ten bulunamazsa sistem tahmin etmez. Örneğin birden çok hisse sınıfı varsa sonuç `INPUTS_MISSING` olur ve eksik girdiler listelenir.
- **Net borç uyarısı:** SEC tablolarından gelen net borç, menkul kıymetleri ve kira yükümlülüklerini içermez. Bu yüzden büyük menkul kıymet portföyü olan şirketlerde (ör. Apple) özkaynak değeri düşük çıkar. Analistin net borcu düzeltmesi önerilir.
- **Nötr RONIC:** Uç dönem RONIC iskontoya eşitken uç büyümenin değere etkisi küçüktür. Büyümenin değer yaratması için RONIC'in iskontonun üstünde olduğuna dair kanıt gerekir.

## Duyarlılık

Baz senaryo, iskonto oranı ve uç dönem büyümesinin ±%0,5 ve ±%1 değişimleriyle 5 × 5 tabloda yeniden değerlenir.
- Nötr RONIC varsayılanında RONIC her hücrede o hücrenin iskonto oranını izler.
- Analist RONIC'i değiştirdiyse tüm hücrelerde sabit kalır.
- Uç büyümenin iskontoya eşit veya büyük olduğu, ya da %4 tavanı aştığı hücreler boş bırakılır.

## Ters DCF — fiyatın ima ettiği büyüme

`implied_growth(projection, baseline, valuation, price=..., price_source=..., price_date=...)` soruyu tersine çevirir: Analistin girdiği hisse fiyatı, baz senaryonun diğer bütün varsayımları aynen korunarak yıllık **sabit** kaç gelir büyümesini ima ediyor? Sabit tutulan varsayımlar: marj yolu, vergi, satış / sermaye, iskonto, uç dönem, net borç ve hisse sayısı.

- **Fiyat girişi:** Fiyatı sistem indirmez. Analist fiyatı tarihi ve kaynağıyla girer.
- **Karşılaştırma:** Bulunan oran şirketin kendi yıllık büyüme geçmişiyle karşılaştırılır. Raporda şu bantlardan biri yazılır:
  - geçmişin en düşüğünün altında,
  - alt çeyreğin altında,
  - orta bant,
  - üst çeyreğin üstünde,
  - en yükseğin de üstünde.

  Böylece piyasa fiyatına gömülü beklentinin şirketin geçmişine göre ne kadar iddialı olduğu görülür.
- **Kök arama:** Mevcut `ters_dcf_v02` ile −%50 … +%100 aralığında yapılır. Tek kök doğrulanırsa sonuç verilir. Kök yoksa veya birden fazlaysa `NO_UNIQUE_SOLUTION` döner; bu, çözümsüzlüğün kanıtı değildir.
- **Tarih uyarıları:**
  - fiyat tarihi SEC bilgi tarihinden sonraysa (`PRICE_AFTER_SEC_AS_OF`), fiyat rapordaki SEC verisinde olmayan yeni bilgileri yansıtıyor olabilir;
  - iki tarih arasında 7 günden fazla fark varsa `PRICE_DATE_FAR_FROM_SEC_AS_OF`.
- **Sabit büyüme bir basitleştirmedir.** Sonuç piyasa beklentisinin bir yorumudur; alım / satım sinyali değildir.

Komut satırında `--price`, `--price-date`, `--price-source` birlikte verilir; bu kullanım hem `senaryo_degerleme.py` hem `sirket_arastirma_akisi.py` için geçerlidir. Web formunda da aynı üç alan vardır.

## Kullanım

```bash
python senaryo_degerleme.py --companyfacts CIK0000320193.json --as-of 2026-10-25 \
  --long-run-growth 0.03 --long-run-source "..." \
  --discount-rate 0.09 --discount-source "..." \
  --net-debt -50000000000 --net-debt-source "10-K: menkul kıymetler dahil net nakit, analist hesabı" \
  --out reports/aapl_degerleme.json
```

Tek komutluk araştırmada `--long-run-growth/--long-run-source` ile birlikte `--discount-rate/--discount-source` verilirse raporda "Senaryo değerlemesi" bölümü yer alır. Bu bölümde girdi kökenleri, senaryo değerleri, duyarlılık tablosu ve uyarılar bulunur.

## Sınırlar

- Deneysel v0.2 motorunun sınırları aynen geçerlidir (NOL süresi yok, SBC yalnız gider, uç dönem vergisi normalleştirilir; bkz. README).
- İskonto oranı tek bir sabit orandır; dönemsel sermaye maliyeti veya kaldıraç değişimi yoktur.
- Hisse başı değerler senaryo hesabıdır; **hedef fiyat, adil değer veya yatırım tavsiyesi değildir**. Sistem piyasa fiyatı indirmez; ters DCF yalnız analistin girdiği tarihli fiyatı kullanır.

## Testler

`tests/test_senaryo_degerleme.py` (15 test) ve `tests/test_v02_engine.py` içinde `marj_yolu` için 2 test. Kapsadıkları durumlar:
- girdi kökenleri, eksik hisse sayısı ve analist girdisinin doğrulanması,
- %4 uç büyüme tavanı ve projeksiyonun üretilemediği durum,
- her senaryonun doğrudan motor çalıştırmasıyla birebir aynı olması, faaliyet kârı yolunun eşleşmesi,
- duyarlılık tablosu: merkez ve köşe hücreler, geçersiz hücreler, nötr ve sabit RONIC,
- uyarılar, rapor bölümü, HTML karakter kaçışı ve CLI.
