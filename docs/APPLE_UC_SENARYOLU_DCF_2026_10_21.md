# Apple (AAPL) — 21 Ekim 2026 tarihli üç senaryolu deneysel DCF

**Durum:** İlk kaynaklı *stres testi* örneği. Şirket değerinin kesin tahmini, piyasa konsensüsü veya yatırım tavsiyesi değildir. Kod: [ornekler/apple_dcf_stres_pilotu_2026_10.py](../ornekler/apple_dcf_stres_pilotu_2026_10.py). Testler: [tests/test_apple_dcf_stres_pilotu.py](../tests/test_apple_dcf_stres_pilotu.py).

## Kaynak gerçekleri ve birbirinden farklı tarihler

| Veri | Tutar | Mali/veri tarihi | Birincil kaynak |
| --- | ---: | --- | --- |
| Konsolide net satış | 416,161 milyar USD | FY2025 / 27 Eylül 2025 | [Apple Form 10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm) |
| Faaliyet kârı (EBIT) | 133,050 milyar USD | FY2025 | Aynı 10-K |
| Nakit | 39,544 milyar USD | 27 Haziran 2026 | [Apple Form 10-Q](https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm) |
| Cari menkul kıymetler | 22,855 milyar USD | 27 Haziran 2026 | Aynı 10-Q |
| Cari olmayan menkul kıymetler | 84,118 milyar USD | 27 Haziran 2026 | Aynı 10-Q |
| Kısa vadeli borçlanma araçları | 1,997 milyar USD | 27 Haziran 2026 | Aynı 10-Q |
| Vadeli borç, kısa vadeli kısmı | 11,007 milyar USD | 27 Haziran 2026 | Aynı 10-Q |
| Vadeli borç, uzun vadeli kısmı | 71,340 milyar USD | 27 Haziran 2026 | Aynı 10-Q |
| Yaklaşık finansal net borç | **−62,173 milyar USD** | 27 Haziran 2026 | Yukarıdaki üç borç kalemi eksi nakit ve tüm menkul kıymetler |
| Ortaklık payı adedi | **14,594180 milyar adet** | 17 Temmuz 2026 | 10-Q kapak sayfası |
| Karşılaştırma fiyatı | **339,50 USD** | 20 Ekim 2026 *kapanış* | [Investing.com geçmiş fiyat](https://www.investing.com/equities/apple-computer-inc-historical-data) |

**Önemli veri kesiti sorunu:** FY2025 yıllık faaliyet sonuçları, FY2026 Q3 bilanço kalemleri, Temmuz 2026 hisse adedi ve Ekim 2026 piyasa kapanışı **aynı tarihli değildir**. FY2026 ilk dokuz ay verileri zaten kamuya açıklanmıştır; bu demonstrasyon bunları güncel bir TTM ciroya dönüştürmez. Üstelik FY2026 mali yılı 21 Ekim itibarıyla bitmiştir, ancak yıllık 10-K henüz açıklanmadı. Çıktılar **güncel şirket değerleme tavsiyesi değil**, motorun örnek senaryo hesabıdır.

Menkul kıymetlerin tümünü fazla nakit kabul etmek bir **model varsayımıdır**. SBC giderleşmesi EBIT içinde kabul edilmiştir; ileriye dönük yeni ihraç ve hisse geri alımları sayıya işlenmemiştir. Vergi oranı %21 varsayılmıştır (Apple'ın FY2025 gerçekleşen %15,6 efektif vergi oranıyla karıştırılmamalıdır).

## SEC 10-K: 2025 hisse değişimi ve Piotroski ayrımı

2025 Form 10-K, Note 10 (bin hisse): **15.116.786** yıl başı − **401.672** geri alım + **58.146** (çalışan vergisi sonrası net ihraç) = **14.773.260** yıl sonu.

- *Her türlü yeni hisse ihracı var mı?* **Evet** → lafzi «hiç yeni hisse ihracı yok» sinyali **0**.
- *Net dolaşımdaki pay adedi arttı mı?* **Hayır** → «net artış yok» vekil göstergesi **1**.
- *Dışarıdan sermaye toplamak amacıyla yeni ihraç mı?* 10-K'deki çalışan paylarının tanımıyla karıştırılmadan bağımsız sınıflama gerekir → **bilinmiyor**.

Dolayısıyla yöntem sürümü ve olay sınıflaması seçilmeden Piotroski kesin 7/9 ya da 8/9 diye dayatılamaz. Önceki sekiz göstergenin yedisi olumludur; dokuzuncunun nasıl tanımlandığına göre olası skor **7–8** kalır.

## Tamamen varsayımsal üç senaryo

| Senaryo | Yıllık beş yıllık gelir büyümesi | Hedef EBIT marjı | İskonto / WACC *varsayımı* | Uç büyüme | Hisse başı DCF | Uç değer / firma değeri |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Temkinli | %2 | %28 | %10,5 | %2 | **71,83 $** | %62 |
| Baz | %8 | %34 | %8,5 | %2,5 | **132,61 $** | %74 |
| İyimser | %15 | %37 | %7,5 | %3 | **242,28 $** | %82 |

Diğer varsayımlar: dönem sayısı beş, sabit yıllık büyüme, yıllık faaliyet marjı hedefe %30 yakınsıyor, yeniden yatırım = gelir farkı / satış-sermaye oranı (sırasıyla 2,5 / 3,0 / 3,5), uç dönem RONIC sırasıyla %10,5 / %10 / %12. Bunlar analist konsensüsü, Apple rehberliği, nesnel doğru WACC veya araştırmayla kanıtlanmış büyüme rakamları **değildir**.

### Ters DCF

20 Ekim 2026 kapanışı **339,50 $** kabul edilip baz senaryoda iskonto, terminal, marj ve yeniden yatırım varsayımları sabit tutulduğunda, aranan beş yıllık sabit yıllık gelir büyümesi yaklaşık **%34,53** oldu. Bu rakam **fiyata gömülü tek gerçek beklenti değildir**. Sonlu bir aralık tarandığı için tüm kökleri bulma garantisi de yoktur.

## Yerelde çalıştırma (ücretsiz)

Python 3.11+; ek paket yok. Repo kökünde:

```bash
python -m ornekler.apple_dcf_stres_pilotu_2026_10 --out apple_stres_sonuclari.json
python -m unittest discover -s tests -v
```

Bağımlılık olarak mevcut `degerleme_v02.py` ve `dogrulama/moduller_v02.py` gerekir. Yeni örneğe sekiz bağımsız test eklenmiştir; GitHub Actions'ın **başarı durumu ayrıca doğrulanmalıdır**.

**Öncelikli eksikler:** FY2026 üç aylık sonuçlarını gerçek TTM gelir, EBIT ve normalize SBC etkisiyle birleştirmek; hisse adedi tahminine geri alım ve çalışan paylarını katmak; net finansal borç ile gerçekten fazla nakdi ayırmak; sektör kaynaklı büyüme/iskonto varsayımlarını kanıtlandırmak; fiyat karşılaştırmasının aynı bilgi tarihinde olması.
