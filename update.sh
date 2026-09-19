#!/bin/bash
# =============================================================================
# Script Auto-Update ApexAI Trading Bot di Server Linux
# =============================================================================

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo "========================================================"
echo "  🔄 Memulai Update ApexAI Trading Bot pada Server Linux"
echo "========================================================"
echo ""

# 1. Tarik pembaruan kode dari Git
echo "[1/3] Menarik kode terbaru dari Git..."
git fetch --all
git reset --hard origin/main || git pull origin main

# 2. Cek apakah berjalan dengan Docker atau Native Linux
if [ -f "docker-compose.yml" ] && command -v docker &> /dev/null && docker ps -a | grep -q "apexai"; then
    echo ""
    echo "[2/3] Mendeteksi deployment via Docker Compose..."
    echo "      Membangun ulang container dengan kode terbaru..."
    docker compose up -d --build || docker-compose up -d --build
    echo ""
    echo "[3/3] Memeriksa status container..."
    docker ps | grep apexai || true
else
    echo ""
    echo "[2/3] Mendeteksi deployment Native Linux (Systemd / Python Venv)..."
    if [ -d "venv" ]; then
        source venv/bin/activate
        pip install -r requirements.txt
    fi

    if systemctl is-active --quiet apexai 2>/dev/null; then
        echo "      Me-restart systemd service apexai..."
        sudo systemctl restart apexai
        sudo systemctl status apexai --no-pager
    else
        echo "      Catatan: Service apexai belum terdaftar di systemd."
    fi
fi

echo ""
echo "========================================================"
echo "  ✅ Pembaruan Selesai! Server berjalan dengan kode terbaru."
echo "========================================================"
