# Panduan Deployment ApexAI Trading Server

Dokumen ini berisi panduan langkah demi langkah untuk mendeploy aplikasi robot trading **ApexAI** ke server pribadi (VPS Linux Ubuntu/Debian, Docker, atau Windows Server).

---

## Opsi 1: Deploy Menggunakan Docker & Docker Compose (Paling Cepat & Mudah)

Jika server Anda sudah memiliki Docker:

1. **Upload folder proyek ini ke server Anda**:
   ```bash
   scp -r /path/to/trading user@ip_server:/opt/trading
   cd /opt/trading
   ```

2. **Jalankan container dengan Docker Compose**:
   ```bash
   docker-compose up -d --build
   ```

3. **Cek status container**:
   ```bash
   docker ps
   docker logs -f apexai_trading_robot
   ```

Aplikasi langsung aktif di `http://IP_SERVER_ANDA:8000`.

---

## Opsi 2: Deploy Manual di Linux VPS (Ubuntu / Debian)

### 1. Update Sistem & Pasang Python 3.11 / 3.12
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git
```

### 2. Pasang Dependencies
Masuk ke direktori proyek di VPS:
```bash
cd /opt/trading
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Buat Service Systemd (Agar Berjalan Otomatis 24/7 di Background)
Buat file service systemd:
```bash
sudo nano /etc/systemd/system/apexai.service
```

Isi dengan konfigurasi berikut:
```ini
[Unit]
Description=ApexAI Trading Robot Service
After=network.target

[Service]
User=root
WorkingDirectory=/opt/trading
ExecStart=/opt/trading/venv/bin/python server.py
Restart=always
RestartSec=5
Environment=HOST=0.0.0.0
Environment=PORT=8000

[Install]
WantedBy=multi-user.target
```

Aktifkan service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable apexai
sudo systemctl start apexai
sudo systemctl status apexai
```

---

## Opsi 3: Reverse Proxy dengan Nginx & SSL Gratis (HTTPS / Domain Sendiri)

Jika Anda memiliki domain sendiri (misal: `trading.domainanda.com`):

### 1. Pasang Nginx & Certbot
```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 2. Konfigurasi Nginx Reverse Proxy & WebSocket Support
Buat file konfigurasi:
```bash
sudo nano /etc/nginx/sites-available/trading
```

Isi dengan:
```nginx
server {
    server_name trading.domainanda.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

Aktifkan konfigurasi:
```bash
sudo ln -s /etc/nginx/sites-available/trading /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 3. Pasang SSL HTTPS Gratis (Certbot)
```bash
sudo certbot --nginx -d trading.domainanda.com
```

---

## Opsi 4: Deploy di Windows Server VPS

Jika Anda ingin menghubungkan robot langsung dengan **MetaTrader 5 broker lokal**:
1. Copy folder `trading` ke Windows Server Anda (misal `C:\trading`).
2. Pasang Python 3 dari python.org (pastikan opsi *"Add Python to PATH"* dicentang).
3. Buka Command Prompt / PowerShell di folder tersebut:
   ```cmd
   pip install -r requirements.txt
   pip install MetaTrader5
   ```
4. Pasang MetaTrader 5 menggunakan `mt5setup.exe`.
5. Jalankan:
   ```cmd
   run_production.bat
   ```
   Aplikasi akan berjalan langsung di port 8000.
