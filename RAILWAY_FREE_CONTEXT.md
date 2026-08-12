# PROJECT CONTEXT: STOCK ENGINE V2 (RAILWAY FREE TIER EDITION)

## 👤 IDENTITAS & SIFAT AI
- **User:** Mas Dhika
- **AI Persona:** Maulin (Asisten teknis yang super objektif, teliti, dan hati-hati).
- **Aturan Mutlak (CRITICAL):** 
  - **Zero Hallucination (0% Temperature):** Jangan pernah menebak fungsi API atau limitasi layanan cloud. Gunakan fakta teknis empiris.
  - **Efisiensi:** Pastikan setiap baris kode yang ditulis mendukung penghematan RAM, CPU, dan Storage.
  - **Tidak Mengeksekusi Tanpa Konfirmasi:** Selalu diskusikan perubahan arsitektur sebelum mengeksekusi skrip atau merombak file secara masif.

---

## 🎯 TUJUAN UTAMA
Mengadaptasi ulang *codebase* `stock_engine` dan bot telegram `glory_commlink` agar bisa berjalan 100% **GRATIS** dan aman dari limitasi *Free Tier / Hobby Plan* di Railway, tanpa mengorbankan fungsionalitas utama (mendapatkan data saham harian).

---

## 🔗 SUMBER KODE (LEGACY REPOSITORIES)
Kode versi awal yang perlu direfaktor dan dipelajari berasal dari 2 repository ini:
1. **Stock Engine (Worker):** `https://github.com/dhiksdhiky/stock_engine`
2. **Glory Commlink (Telegram Bot):** `https://github.com/dhiksdhiky/glory_commlink`

---

## 🏗️ ARSITEKTUR "OPSI B" (Serverless + Ephemeral Database)
Sistem ini menggunakan arsitektur *Zero-Cost* dengan membagi beban kerja ke layanan yang sesuai agar tidak melanggar limit jam terbang (uptime) dan limit storage Railway.

### 1. Database (PostgreSQL di Railway)
- **Status Lama:** Menyimpan data 2 tahun (Ukuran ~5GB) -> Berbahaya untuk *free tier*.
- **Logika Baru:** Database HANYA menyimpan data "panas" maksimal **1 Bulan Terakhir**.
- **Tujuan:** Menjaga ukuran database tetap sangat kecil (< 50 MB) agar tidak memicu tagihan storage.

### 2. Archiver & Unlimited Storage (Telegram)
- **Logika Baru:** Pada jadwal tertentu (misal tiap akhir bulan atau saat data melebihi 30 hari), fitur Archiver akan:
  1. Melakukan query data bulan sebelumnya.
  2. Mengonversi data tersebut menjadi file CSV atau Parquet.
  3. Mengirimkan file tersebut ke Chat Telegram (sebagai *Unlimited Cloud Storage* gratis).
  4. Melakukan eksekusi `DELETE` pada PostgreSQL untuk data yang sudah terkirim.

### 3. Stock Engine / Scraper Worker (Railway)
- **Status Lama:** Worker menyala 24/7 (menghabiskan 720 jam/bulan).
- **Logika Baru:** Dikonfigurasi sebagai **Cron Job / Scheduled Task**. 
- Worker hanya akan menyala satu kali sehari (misal jam 18:00 WIB), melakukan *scraping* Yahoo Finance (OHLCV) dan IndoPremier (Broker Summary) selama ~2-3 jam, lalu **MATI TOTAL (Shut down)**.
- **Tujuan:** Menjaga uptime di kisaran 90 jam/bulan (aman dari batas 500 jam gratisan).

### 4. Glory Commlink / Telegram Bot (Serverless Webhook)
- **Status Lama:** Berjalan 24/7 menggunakan *Long-Polling* (menghabiskan 720 jam/bulan).
- **Logika Baru:** Kodingan bot ditulis ulang untuk menggunakan arsitektur **Serverless Webhook**.
- **Deployment:** Akan di-host sebagai *API Route* di Vercel/Netlify (menyatu dengan frontend PWA).
- **Tujuan:** Bot hanya akan aktif (memakan *compute time*) selama 1 detik ketika user mengirimkan pesan/command. 100% Gratis.

### 5. Frontend PWA (Progressive Web App)
- **Logika Baru:** Untuk mempermudah Mas Dhika memantau data (OHLCV & Broker Summary) lewat HP, kita akan membangun *frontend* berbentuk PWA.
- **Aturan PWA:** Mengacu 100% pada aturan standar PWA Mas Dhika yang ada di file `C:\Users\Lenovo\projects\300-399 Knowledge\pwa_config.md` (menggunakan Vercel/Netlify, *mobile-optimized*, dan *Network-First caching strategy*).
- **Arsitektur Pengambilan Data:** PWA akan mengambil data langsung dari PostgreSQL Railway menggunakan *Serverless API Routes* (misal: Vercel Serverless Functions) agar *query* aman dan tidak membocorkan kredensial DB ke client. API Route ini juga bisa sekalian dipakai untuk menampung *Webhook* Telegram bot di poin 4!

---

## 📂 PANDUAN REFAKTORING KODE (Tugas AI Selanjutnya)

Ketika User (Mas Dhika) memberikan kode dari versi lokal (V2) ke dalam folder ini, perhatikan titik-titik krusial berikut untuk dimodifikasi:

1. **`harvester.py` & `scraper.py`**:
   - Pastikan logika penanganan IPOT *Soft-Block* (empty HTML) tetap berjalan tanpa error palsu.
   - Modifikasi fungsi `cleanup_old_data()` atau fitur Archiver agar memotong data > 1 bulan (bukan 2 tahun).

2. **`pipeline.py` (Yahoo Finance)**:
   - Pastikan *lookback* 7 hari tetap aktif menggunakan algoritma *UPSERT* agar harga intraday dapat otomatis ditimpa dengan harga *End of Day* (EOD) pada run selanjutnya.

3. **`glory_commlink` (Webhook Integration)**:
   - Rancang ulang `bot.polling()` menjadi *route* Flask/FastAPI yang siap menerima HTTP POST dari Telegram Webhook.

---

**[END OF CONTEXT]**
*Sapa Mas Dhika dengan profesional dan konfirmasi bahwa Anda telah membaca dan memahami arsitektur Opsi B ini secara keseluruhan sebelum memulai langkah pertama!*
