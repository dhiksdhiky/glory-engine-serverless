# 🚀 Glory Engine Serverless (Stock Engine V2)

Arsitektur "Opsi B" yang 100% didesain untuk kebal dari limitasi **Free Tier** dengan memisahkan *Worker* (Pumping/Scraping Data) dan *Frontend/API* (Commlink Telegram & PWA).

## 🏗 Arsitektur Monorepo

Project ini menggunakan arsitektur Monorepo yang memisahkan eksekusi antara Vercel dan Railway.

### 1. 🚄 `worker/` (Railway - Worker & Database)
Folder ini di-_deploy_ di **Railway** menggunakan fitur **Cron Job**. 
Tugasnya adalah memompa data secara periodik dan langsung mati (*graceful exit*) saat selesai agar tidak menyedot kuota bulanan Free Tier (500 jam).
- **`pipeline.py`**: Mengunduh dan membersihkan data OHLCV via *yfinance*.
- **`harvester.py` & `scraper.py`**: Menjalankan *IPOT Web Scraper* untuk data *Broker Summary* (Dilengkapi dengan WAF *Circuit Breaker*).
- **`archiver.py`**: Fitur otomatis pembersihan data PostgreSQL lebih dari 30 hari.

### 2. 🚀 `web/` (Vercel - Serverless Webhook & PWA)
Folder ini di-_deploy_ di **Vercel** sebagai fungsi Serverless (Maks 10 detik per request, kebal polling Telegram limit).
- **`/api/webhook.py`**: Entrypoint Serverless yang bertindak sebagai bot Telegram (*webhook*).
- **`/api/stock.py`**: Entrypoint untuk Frontend PWA.
- **`/lib/`**: Kumpulan modul berat (*SQLAlchemy*, query analitik seperti Inflow/Outflow dan HMB) milik Glory Commlink.
- **`/public/`**: Frontend Progressive Web App (PWA) dengan *Service Worker* & *Manifest*.

---

## ⚙️ Panduan Deployment

### Variabel Environment (.env)
Baik Vercel maupun Railway membutuhkan 3 Variabel wajib ini:
- `DATABASE_URL`: URI PostgreSQL dari Railway. (Wajib menggunakan prefix `postgresql://`).
- `TELE_BOT_DHIKSDHIKY`: Token Bot Telegram dari BotFather.
- `TELE_CHAT_ID_DHIKA`: Chat ID Anda untuk filter autorisasi perintah.

### Deploy Worker (Railway)
1. Hubungkan repo ke Railway, buat *New Project*.
2. Setup *PostgreSQL*.
3. Edit **Root Directory** dari repo ini menjadi `/worker`.
4. Di bagian **Settings > Cron**, jadwalkan kapan worker berjalan (Misal: `0 16 * * 1-5` untuk hari kerja jam 4 sore).
5. Masukkan variabel environment.

### Deploy Webhook & PWA (Vercel)
1. Hubungkan repo ke Vercel.
2. Edit **Root Directory** menjadi `web`.
3. Masukkan variabel environment.
4. Klik **Deploy**.
5. Setelah Vercel memberikan domain (contoh: `https://glory-engine.vercel.app`), aktifkan Webhook Telegram dengan URL berikut di *Browser*:
   `https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://glory-engine.vercel.app/api/webhook`

---

*Dibuat khusus untuk arsitektur serverless Opsi B persahaman duniawi. 🇮🇩*
