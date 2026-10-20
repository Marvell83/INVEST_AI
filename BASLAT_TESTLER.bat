@echo off
chcp 65001 >nul
cd /d "%~dp0dogrulama"
python kabul_testi.py
if errorlevel 1 echo HATA: 0.1 kabul testi basarisiz!
python -m unittest test_dogrulama_seti test_moduller_v02 -v
pause