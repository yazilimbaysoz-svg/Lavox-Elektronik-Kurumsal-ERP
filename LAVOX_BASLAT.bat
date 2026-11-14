@echo off
chcp 65001 >nul
title LAVOX Elektronik ERP - Baslatiliyor
echo ============================================
echo  LAVOX Elektronik ERP - Baslatiliyor
echo ============================================
echo.

cd /d "%~dp0"
echo [1/3] Veritabani ve yonetici hesabi kontrol ediliyor...
python backend\seed_data.py
if errorlevel 1 (
    echo HATA: Ilk kurulum basarisiz. Yonetici kurulum degiskenlerini kontrol edin.
    pause
    exit /b 1
)
echo [OK] Veritabani hazir.
echo.

echo [2/3] FastAPI sunucu 8010 portunda baslatiliyor...
echo Sunucu: http://127.0.0.1:8010
echo API dokumantasyonu production modunda kapali.
echo.
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
if errorlevel 1 (
    echo HATA: Sunucu baslatilamadi.
    pause
    exit /b 1
)
