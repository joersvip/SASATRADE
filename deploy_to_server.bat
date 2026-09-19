@echo off
title Kirim Update ApexAI ke Server Linux
cls
echo =========================================================================
echo    APEXAI - SINKRONISASI KODE KE SERVER LINUX (1-KLIK)
echo =========================================================================
echo.

:: SILAKAN SESUAIKAN DENGAN IP & USER SERVER LINUX ANDA:
set SERVER_USER=root
set SERVER_IP=IP_SERVER_LINUX_ANDA
set SERVER_PATH=/opt/trading

echo Target Server: %SERVER_USER%@%SERVER_IP%:%SERVER_PATH%
echo.

echo [1/3] Mengirim folder backend dan public...
scp -r backend public %SERVER_USER%@%SERVER_IP%:%SERVER_PATH%/

echo.
echo [2/3] Mengirim server.py, update.sh, dan requirements.txt...
scp server.py update.sh requirements.txt docker-compose.yml Dockerfile %SERVER_USER%@%SERVER_IP%:%SERVER_PATH%/

echo.
echo [3/3] Menjalankan update script di server...
ssh %SERVER_USER%@%SERVER_IP% "bash %SERVER_PATH%/update.sh"

echo.
echo =========================================================================
echo  [SELESAI] Semua perubahan berhasil diterapkan di server Linux Anda!
echo =========================================================================
pause
