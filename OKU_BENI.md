# YATIRIM AI — Bağımsız Değerleme Çekirdeği 0.1 + 0.2 Araştırma Modülleri

## Gerçek test sonuçları
- `dogrulama/uretim_motoru.py` bağımsız uygulanmıştır; `referans_motor.py` import etmez.
- 0.1 kabul seti: **17/17 GEÇTİ**.
- Kabul altyapısı birim testleri: **2/2 GEÇTİ**.
- 0.2 deneysel modül testleri: **7/7 GEÇTİ**.
- **0.2 bütünleşik değerleme motoru henüz tamamlanmadı ve bağımsız 0.2 kabul seti yok.**

## Windows
1. ZIP dosyasını klasöre çıkarın.
2. `BASLAT_TESTLER.bat` dosyasına çift tıklayın (Python 3 gerekli).
3. Sonuçları `dogrulama/kabul_raporu.txt` ve terminalde görün.

## Dosyalar
- `dogrulama/KONVANSIYONLAR.md`: Claude'un dondurulmuş 0.1 sözleşmesi.
- `dogrulama/uretim_motoru.py`: Yeni, bağımsız 0.1 üretim motoru.
- `dogrulama/motor_adaptoru.py`: Kabul testini yeni motora bağlar.
- `dogrulama/moduller_v02.py`: 0.2 deneysel kök bulucu, devreden zarar, marj yakınsaması, ROIIC.
- `dogrulama/test_moduller_v02.py`: 7 deneysel test.
- `dogrulama/referans_motor.py`: Claude'un referans uygulaması, karşılaştırma için saklandı.

## Kritik sınırlar
- `uretim_motoru.py` **0.1 sözleşmesine sadık kaldığından** 0.1'in kaba sulandırma ve simetrik vergi konvansiyonlarını hâlâ destekler. Gerçek şirket analizlerinde bunları kullanmayın.
- `moduller_v02.py` deneysel kök araması **tüm kökleri bulma garantisi vermez**; yakın çift kök/teğet kök testleri yalnız seçili vakalarda geçti.
- ROIIC tanısı bir dönem gecikmeli oran; gerçek sermaye verimliliği kanıtı değildir.
- Ücretsiz standart Python dışında kütüphane gerekmez.
- Gerçek şirket verisi, InvestingPro bağlantısı, otomatik haber ve üretim değerlemesi henüz yoktur.

## Metodolojik referanslar
- CFA Institute, Free Cash Flow Valuation (2026): https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/free-cash-flow-valuation
- Aswath Damodaran, Cash Flows: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/littlebook/cashflows.htm
- Aswath Damodaran, Terminal Value & Excess Returns: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/termvalueexreturns.htm