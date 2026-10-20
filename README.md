# INVEST_AI — Bağımsız Değerleme Çekirdeği

**Durum:** geliştirme ve doğrulama aşamasında. Bu depo, YATIRIM AI'nın yatırım araştırması platformu için geliştirilen ilk bağımsız değerleme çekirdeğini içerir.

## Amaç

InvestingPro ile seçilen şirketlere ait finansal verileri, sektör ve şirket araştırmalarından gelen kaynaklı varsayımları ve geleceğe dönük nakit akışı projeksiyonlarını kullanarak senaryolu DCF ve ters DCF değerlemesi yapmak. **Henüz InvestingPro entegrasyonu, otomatik haber takip sistemi veya gerçek şirketlere bağlı üretim uygulaması yoktur.**

## Modüller

- `dogrulama/uretim_motoru.py`: dondurulmuş 0.1 DCF ve ters DCF kurallarının bağımsız Python uygulaması.
- `dogrulama/moduller_v02.py`: deneysel vergi zarar devri, marj yakınsaması, marjinal getiri tanısı ve kök bulma işlevleri.
- `dogrulama/KONVANSIYONLAR.md`: dondurulmuş 0.1 hesap sözleşmesi.
- `dogrulama/kabul_testi.py`, `dogrulama/dogrulama_seti_v0_1.json`: 17 vakalık kabul altyapısı.
- `dogrulama/test_moduller_v02.py`: 7 deneysel modül testi.

## Windows

Python 3 kurulu bilgisayarda `BASLAT_TESTLER.bat` dosyasını çalıştırın.

## Test durumu

Kaynak ZIP'de raporlanan sonuçlar: **0.1 üretim motoru 17/17**, doğrulama altyapısı **2/2**, 0.2 deneysel modüller **7/7**. Tam entegre 0.2 motoru ve bağımsız 0.2 kabul seti **henüz yoktur**.

> Finansal tavsiye değildir. 0.1'in simetrik vergi ve kaba sulandırma yöntemleri gerçek şirket değerlemeleri için uygun değildir. 0.2 modüllerinin kök araması tüm kökleri bulmayı garanti etmez.


## Tahmin Defteri v0.1 (yeni)

`tahmin_defteri.py` yalnızca Python standart kütüphanesi ve SQLite kullanır. Kaynak gösterilerek kaydedilen tahminleri, daha sonra açıklanan gerçekleşen değerleri ve mutlak/imzalı tahmin hatalarını **ayrı, eklemeli kayıtlar** olarak saklar. Kayıtlar SQL tetikleyicileriyle güncelleme/silmeye karşı korunur. Bu, dosyaya erişen kötü niyetli birinin veritabanını değiştiremeyeceği anlamına gelmez; kriptografik değiştirilemezlik veya dış zaman damgası sağlamaz.

Çalıştırma: `python -m unittest discover -s tests -v`

Bu modül `degerleme_kaydi.py` aracılığıyla değerleme motorlarına bağlanmıştır. GitHub Actions koşusu henüz doğrulanmış değildir. Test girdileri sentetiktir. Değerlendirme şu anda mutlak hata ve imzalı hatadır; olasılık kalibrasyonu ve ölçeğe duyarlı skorlar daha sonra eklenecektir.


## DCF → Tahmin Defteri entegrasyonu

`degerleme_kaydi.py` dondurulmuş v0.1 `degerle()` ya da deneysel v0.2 `degerle_v02()` motorundan gelen yıllık gelir (`revenue`) ve serbest nakit akışı (`fcff`) tahminlerini SQLite'a kaydeder. Her kayıt şirketi, para birimini, tahmin yılını, kaynak listesini, varsayımları, model sürümünü ve hesaplanan özsermaye/hisse değerini içerir. Geçersiz değerleme kaydedilmez. Çok satırlı kayıtlarda dış SQLite işlemi kullanılır; ara aşamada hata olursa geri alma hedeflenir.

Örnek kullanım (yalnız sentetik test girdileri):

```python
from degerleme_kaydi import degerle_ve_kaydet
sonuc = degerle_ve_kaydet(
    db_path="tahminler.sqlite", company="DEMO", currency="USD",
    base_year=2026, inputs={
        "yillar": 3, "gelir_0": 100, "buyume": 0.1,
        "faaliyet_marji": 0.2, "satis_sermaye": 2,
        "vergi_orani": 0.2, "iskonto": 0.1,
        "uc_buyume": 0.02, "uc_roic": 0.12,
        "net_borc": 0, "hisse": 10, "sbc_yontemi": "gider"
    }, sources=["synthetic example"]
)
print(sonuc["durum"], sonuc["tahmin_kimlikleri"])
```

GitHub Actions: `.github/workflows/python-tests.yml`. Çalıştırma: `python -m unittest discover -s tests -v`. Test sonuçları GitHub Actions üzerinden kontrol edilmelidir; testlerin bu değişiklikle geçtiği henüz doğrulanmış değildir. v0.1 ekonomik sınırlamaları sürmektedir.

## v0.2 alpha — deterministik DCF + ters DCF

**Yeni:** `degerleme_v02.py` içinde `degerle_v02(inputs)` ve `ters_dcf_v02(inputs, price, lower, upper)` bulunur. v0.1'in sözleşmesi ve referans testleri değiştirilmemiştir.

v0.2 şu hesapları birlikte yapar: her yıl `gelir = onceki_gelir * (1 + buyume)`, faaliyet marjının belirtilen hedefe üstel yakınsaması, EBIT, önceki yıllardan devreden basitleştirilmiş vergi zararı (NOL), yeniden yatırım `gelir_farki / satis_sermaye`, FCFF, dönemsel bugünkü değer, normalleştirilmiş uç dönem vergisi ve RONIC üzerinden uç dönem yeniden yatırım. ROIIC için önceki yılın yeniden yatırımı kullanılır (tanı göstergesi).

Örnek (sentetik veri, finansal öneri değildir):

```python
from degerleme_v02 import degerle_v02, ters_dcf_v02
girdi = dict(yillar=3, gelir_0=100, buyume=.10,
    marj_0=.15, marj_hedef=.20, yakinlasma=.5,
    satis_sermaye=2, vergi_orani=.25, iskonto=.10,
    uc_buyume=.02, uc_roic=.12, hisse=10)
hesap = degerle_v02(girdi)
print(hesap["hisse_basi_deger"])
arama = ters_dcf_v02(girdi, price=hesap["hisse_basi_deger"], lower=.05, upper=.15)
print(arama["durum"], arama["ima_edilen_buyume"])
```

Tahmin Defteri'ne kaydetmek için `degerle_ve_kaydet(..., inputs=girdi, engine="v0.2")` kullanılır. Motor sürümü kayıtta saklanır.

**Sınırlamalar:** NOL'de süre bitimi, ülke kısıtları veya faiz vergi kalkanı modellenmez. SBC yalnız gider yaklaşımıdır; hisse sulandırması otomatik modellenmez. Marjın yıllık yakınsaması büyüme oranına açıkça bağlı değildir. Uç büyüme nominal para birimiyle uyumlu biçimde kullanıcı tarafından belirlenmelidir. Uç dönem vergisi normalleştirilir. Ters DCF araması sınırlı bir aralıktaki **aday kökleri** tarar: kök bulunamaması çözümsüzlüğün matematiksel kanıtı değildir.

Yerelde çalıştırılan v0.2 testleri: **16/16 başarılı**. Daha önceki v0.1 kabul testleri: **17/17** ve deneysel modül testleri: **7/7**. GitHub Actions'ın bu değişiklikler üzerindeki sonucu ayrıca kontrol edilmelidir. Bunlar ekonomik tahmin doğruluğu kanıtı değildir.



## SEC Company Facts — tarihli gerçek finansal veri altyapısı (yeni)

**Yeni modüller:** `sec_companyfacts.py` ve `sec_v02_bridge.py`. ABD SEC'nin Company Facts XBRL API'sinden yalnız USD birimindeki seçilmiş 10-K / 10-K/A yıllık muhasebe olguları alınır. Her satır açıklanma tarihi (`filed`), dönem başı/sonu (`start/end`), accession, XBRL kavramı ve kaynak URL'siyle korunur. `--as-of` filtresi, geçmiş bir analiz tarihinde henüz yayımlanmamış bilgilerle hesaplama yapılmasını engeller.

**DCF bağlantısı:** Son ortak tarihsel gelir ve EBIT kaydından `gelir_0` ve `marj_0` çıkarılır; büyüme, iskonto, hedef marj, terminal varsayımlar, hisse adedi ve net borç kaynakları kullanıcı tarafından belirtilmeden değerleme oluşturulmaz. CFO - CapEx, FCFF sanılmaz. Bu modül sadece SEC yıllık XBRL verisini kapsar; **InvestingPro, canlı fiyat, sektör araştırması veya otomatik yatırım önerisi içermez.**

[SEC kurulum, komutlar, sentetik örnek ve sınırlamalar](docs/SEC_INTEGRASYON.md)

Test komutu: `python -m unittest discover -s tests -v`. SEC modülleri için yerelde **20/20 sentetik test başarılı**. Gerçek şirket verileriyle kapsamlı kontrol ve GitHub Actions sonuç doğrulaması ayrıca gereklidir.


## SEC kaynak kalite kapısı ve v0.2 tahmin kaydı (20.10.2026)

Yeni, korunmalı veri akışı:

`SEC ham Company Facts` → `sec_gap_audit.py` (dönem/kaynak/çelişki) → `sec_v02_bridge.py` → `degerleme_v02.py` → `sec_reviewed_pipeline.py` → `tahmin_defteri.py`.

- 117 yerel SEC dosyasının yeniden denetiminde **86** şirket yalnızca ön incelemeyi geçti; **31** şirketin manuel kontrol gerektirdiği saptandı. Bunların **7** tanesinde birden fazla yıllık gelir etiketi arasında %5'ten büyük tutar ayrışması var.
- `sec_gap_audit.py`: kaynak ve mali yıl uyuşmazlığını ayrı raporlar; IFRS/eksik EBIT/pozitif olmayan geliri uydurma verilerle doldurmaz.
- `sec_reviewed_pipeline.py`: yalnız kaynak denetimini geçen ham SEC verilerinden deneysel v0.2 DCF üretip gelir, EBIT ve FCFF tahminlerini **kaynaklı, dönemli SQLite kayıtlarına** dönüştürür. Eski doğrudan `sec_v02_bridge.py` kullanımı **bu yeni denetim kapısını atlar**; yeni araştırmalarda korumalı akışı tercih edin.
- `sec_reviewed_cli.py`: bu akışı dosyalar üzerinden çalıştırır. Kullanıcı tüm gelecek varsayımları ve gelecekteki **mali yıl bitiş tarihlerini** verir; sistem bunları kendiliğinden tahmin etmez.
- Denetim, kaynak ve kullanım ayrıntısı: [docs/SEC_KAYNAK_DENETIMI_V02.md](docs/SEC_KAYNAK_DENETIMI_V02.md).

Test komutu: `python -m unittest discover -s tests -v`. Yerelde SEC modülleri için sentetik dosyalar ve SQLite uyumlu bir test adaptörüyle **38/38 test** geçmiştir. **GitHub üzerindeki gerçek tahmin defteriyle yeni CI sonucu henüz onaylanmamıştır**. Üretime hazır veya yatırım tavsiyesi değildir.


## SEC 10-K gelir etiketi mutabakatı — yedi araştırma adayı (2026-10-20)

Yedi şirketin resmî 10-K tablolarında konsolide gelir satırı araştırıldı ve yerel SEC Company Facts XBRL arşivinde **7/7 CIK / mali dönem / accession / tutar eşleşmesi** bulundu. Kanıtlar ve tutarlar: [SEC 7 gelir mutabakatı](docs/SEC_7_GELIR_MUTABAKATI.md); makine-okunur **onaylanmamış** adaylar: [evidence/sec_2026_revenue_review_candidates.json](evidence/sec_2026_revenue_review_candidates.json).

**Önemli:** Birincil kaynak araştırması, yetkili analistin imzaladığı muhasebe incelemesiyle aynı şey değildir. Aday JSON'un `status` alanı `proposed_requires_human_signoff` olduğu için sistem **bu 7 şirket için değerleme kilidini açmaz**. Kaynak okunup doğrulandıktan sonra `sec_revenue_reconciliation.py`, açıkça `approved` ve kaynak alanları dolu bir incelemeyi SEC XBRL verileriyle karşılaştırabilir.

`sec_reviewed_pipeline.analyze_and_record(..., revenue_review=...)` ve `sec_reviewed_cli.py --revenue-review approved_review.json` ile bu karar kayıt altına alınır. Yeni testler doğru onay, yanlış şirket, yanlış yıl, yanlış accession, yanlış tutar, sahte kaynak adresi ve eksik EBIT gibi durumları kapsar. Asıl GitHub CI sonucu ayrıca doğrulanmalıdır.

Veri sınırı: 117 şirketin ilk örnekleminde 86 aday daha önce teknik ön kontrolden geçiyordu; 7 kaynak açıklaması bulunsa bile **31 manuel inceleme gerektiren şirketin sayısı yetkili onay olmadan azaltılmaz**. Kalan 24 dosya başka veri sorunları yüzünden ayrıca incelenecek.
