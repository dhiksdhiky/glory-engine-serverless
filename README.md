# 🚀 Glory Engine Serverless

**Glory Engine Serverless** adalah mesin otomatis pengumpul data pasar saham Indonesia (OHLCV & Broker Summary) yang dirancang dengan arsitektur 100% *Serverless* untuk beroperasi secara mandiri dan bebas biaya infrastruktur (*Zero-Cost*).

## 🏗️ Arsitektur Sistem

Proyek ini memisahkan beban kerja menjadi dua entitas utama (Monorepo):

### 1. `worker/` (Data Harvester & Archiver)
Berjalan secara otomatis via **GitHub Actions** setiap penutupan bursa. Bertugas:
- **Pipeline**: Memompa data *OHLCV* (Open, High, Low, Close, Volume) harian.
- **Harvester**: Menjalankan *Web Scraper* untuk data akumulasi/distribusi *Broker Summary*.
- **Smart Archiver**: Membersihkan dan mengarsipkan data bulan lalu ke Telegram secara pintar, menjaga database tetap ringan.

### 2. `web/` (API, PWA, & Telegram Bot)
Di-_deploy_ menggunakan layanan **Vercel** Serverless. Bertugas:
- **Webhook API**: Bertindak sebagai otak di balik Bot Telegram pintar pencari saham.
- **PWA Dashboard**: Antarmuka visual berupa *Heatmap Calendar* untuk memantau kelancaran sinkronisasi data harian secara langsung.

## 💾 Basis Data (Database)

Sistem menggunakan **PostgreSQL** terpusat (saat ini diletakkan di **Railway**) yang dirancang untuk sangat ramping. Berkat rutinitas pengarsipan bulanan, beban penyimpanan ditekan seminimal mungkin (hanya menampung *active month*), memastikan penggunaan *resources* aman dan tak pernah melewati batas *Free Tier*.

---
*Dibuat khusus untuk arsitektur serverless analitik saham. 🇮🇩*
