@echo off
chcp 65001 >nul
cd /d "%~dp0dogrulama"
python kabul_testi.py
if errorlevel 1 (
  echo HATA: 0.1 kabul testi basarisiz!
  pause
  exit /b 1
)
python -m unittest test_moduller_v02 -v
if errorlevel 1 (
  echo HATA: 0.2 pilot modulleri testi basarisiz!
  pause
  exit /b 1
)
pause
