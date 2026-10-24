# INVEST_AI — Hızlı Başlangıç (Windows)

Genel bakış, modül listesi ve sınırlar için **[README.md](README.md)**, değişiklik geçmişi için **[CHANGELOG.md](CHANGELOG.md)**.

## Testleri çalıştırma
1. ZIP dosyasını bir klasöre çıkarın (Python 3.11+ gerekli, ek paket gerekmez).
2. `BASLAT_TESTLER.bat` dosyasına çift tıklayın. Sırasıyla şunları çalıştırır:
   - ana test paketi `tests/` (350 test),
   - dondurulmuş 0.1 kabul seti `dogrulama/kabul_testi.py` (17 vaka; rapor: `dogrulama/kabul_raporu.txt`),
   - kabul altyapısı + 0.2 deneysel modül testleri (2 + 7 test).
3. Sonda `TUM TESTLER GECTI` ya da hangi grubun başarısız olduğu yazılır.

## Dondurulmuş 0.1 dosyaları
- `dogrulama/KONVANSIYONLAR.md`: dondurulmuş 0.1 hesap sözleşmesi.
- `dogrulama/uretim_motoru.py`: bağımsız 0.1 üretim motoru (`referans_motor.py` dosyasını import etmez).
- `dogrulama/referans_motor.py`: karşılaştırma için saklanan referans uygulama.
- `dogrulama/motor_adaptoru.py`: kabul testini üretim motoruna bağlar.

## Kritik sınırlar
- 0.1, kaba sulandırma ve simetrik vergi konvansiyonlarını korur; gerçek şirket analizinde kullanmayın.
- 0.2 ters DCF kök araması tüm kökleri bulmayı garanti etmez.
- Finansal tavsiye değildir.
