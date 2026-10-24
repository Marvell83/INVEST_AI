@echo off
chcp 65001 >nul
cd /d "%~dp0"
set HATA=0
echo === Ana test paketi (tests/) ===
python -m unittest discover -s tests
if errorlevel 1 (echo HATA: ana test paketi basarisiz! & set HATA=1)
cd /d "%~dp0dogrulama"
echo === Dondurulmus 0.1 kabul testi ===
python kabul_testi.py
if errorlevel 1 (echo HATA: 0.1 kabul testi basarisiz! & set HATA=1)
echo === Kabul altyapisi ve 0.2 deneysel moduller ===
python -m unittest test_dogrulama_seti test_moduller_v02 -v
if errorlevel 1 (echo HATA: dogrulama birim testleri basarisiz! & set HATA=1)
if %HATA%==0 (echo TUM TESTLER GECTI) else (echo EN AZ BIR TEST GRUBU BASARISIZ)
pause
