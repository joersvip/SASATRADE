@echo off
title ApexAI Production Engine (Live Trading)
cls
echo =========================================================================
echo    APEXAI ROBOT TRADING ENGINE - PRODUCTION MODE
echo    Pasar Aktif: Forex, Crypto, Saham
echo =========================================================================
echo.
echo [1/3] Memeriksa environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python tidak ditemukan. Mohon pastikan Python 3 terpasang.
    pause
    exit /b 1
)

echo [2/3] Memastikan folder data dan logs...
if not exist "logs" mkdir logs
if not exist "data" mkdir data

echo [3/3] Menjalankan server produksi di http://localhost:8000 ...
echo Tekan CTRL+C untuk mematikan server.
echo.
python server.py
pause
