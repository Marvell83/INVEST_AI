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
