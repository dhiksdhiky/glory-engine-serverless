# 🕯️ CANDLIFY + GLORY ENGINE: UNIFIED IDX SUPER-PWA BLUEPRINT

Dokumen ini merangkum cetak biru (*architecture blueprint*) untuk menggabungkan **Candlify** (Advanced Candlestick Charting & TA) dengan **Glory Engine Serverless** (IDX Harvester, Bandarmologi, & Archiver) menjadi satu platform analitik saham tunggal yang ramping (*lean*), bertenaga, dan 100% beroperasi di atas infrastruktur *Zero-Cost* (Neon Serverless PostgreSQL + Vercel + GitHub Actions).

---

## 🎯 1. Filosofi Desain: "Lean, Essential, & Bandar-Powered"

### Masalah Candlify Versi Lama
* **Overkill Geometric Patterns:** Deteksi segitiga, double bottom, cup & handle via regresi linear matematis menghasilkan terlalu banyak *false breakout* dan membuat kanvas mobile penuh garis ruwet.
* **Canggung di Layar Mobile:** Drawing tools kompleks (Fibonacci, parallel channel, ray line) sulit dioperasikan via sentuhan jari.
* **Ketergantungan Eksternal:** Mengambil data dari TradingView Scanner API eksternal yang rentan *rate-limiting*.
* **Buta Terhadap Bandar:** Candlestick murni tanpa konteks broker summary sering terjebak *bull trap*.

### Solusi Arsitektur Baru
* **Penyederhanaan Ekstrem (3 Tab Utama Saja):** Screener, Chart & Bandar Analyzer, dan Trading Journal.
* **Bandarmologi Overlay:** Mengintegrasikan garis **HMB (Harga Modal Bandar)** dan sub-pane **Net Flow Bandar (Akumulasi vs Distribusi)** langsung di bawah candlestick KLineCharts.
* **Database Tunggal (Neon PostgreSQL):** Seluruh data harga, broker summary, master emiten, dan trading plans disatukan dalam satu basis data.

---

## 🏗️ 2. Arsitektur Komponen Terpadu

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        UNIFIED PWA FRONTEND                            │
│                 (Vanilla JS + KLineCharts v9 + CSS Glass)              │
├───────────────────┬────────────────────────────┬───────────────────────┤
│ Tab 1: SCREENER   │ Tab 2: CHART & BANDAR      │ Tab 3: JOURNAL & PLAN │
│ - Akumulasi Diam2 │ - Candlestick Multi-TF     │ - Form Entry, SL, TP  │
│ - Breakout Valid  │ - Level SnR (S1, S2, R1, R2│ - Win/Loss Tracking   │
│ - Big Inflow      │ - Garis HMB (Harga Bandar) │ - Realized PnL        │
│                   │ - Sub-pane: Net Buy/Sell   │                       │
└───────────────────┴─────────────┬──────────────┴───────────────────────┘
                                  │ HTTP Fetch
┌─────────────────────────────────▼──────────────────────────────────────┐
│                    VERCEL SERVERLESS API (Python)                      │
│  - /api/stock.py    : Health, metadata, & scanner feed                 │
│  - /api/history.py  : Candlestick OHLCV feed (baca dari Neon)          │
│  - /api/bandar.py   : Agregasi Broker Summary & kalkulasi HMB          │
│  - /api/journal.py  : CRUD Trading Plans & Portofolio                  │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │ TCP / PgBouncer Pooler
┌─────────────────────────────────▼──────────────────────────────────────┐
│                     NEON SERVERLESS POSTGRESQL                         │
│  - daftar_saham     : Master emiten IDX (955 emiten)                   │
│  - harga_saham      : OHLCV harian (Rolling 2 Bulan)                   │
│  - broker_summary   : Akumulasi/Distribusi per broker (Rolling 2 Bulan)│
│  - trading_plans    : Catatan trading & watchlist pengguna             │
│  - archive_status   : Tracking status arsip bulanan                    │
│  - harvester_gaps   : Monitoring suspensi/emiten kosong                │
└─────────────────────────────────▲──────────────────────────────────────┘
                                  │ Bulk UPSERT (Malam Hari)
┌─────────────────────────────────┴──────────────────────────────────────┐
│                    GITHUB ACTIONS CRON WORKER                          │
│  - Pipeline         : Tarik OHLCV harian (yfinance)                    │
│  - Harvester        : Tarik Broker Summary (IndoPremier)               │
│  - Smart Archiver   : Ekspor bulan N-2 ke Telegram & Delete dari Neon  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 💾 3. Strategi Retensi Data: Rolling 2-Month Window

Untuk memastikan indikator Bandarmologi (HMB) di Candlify selalu memiliki data historis minimal **20–30 hari bursa** (bahkan saat pergantian tanggal 1 awal bulan), aturan pembersihan data diubah dari 1 bulan menjadi **Rolling 2 Bulan**:

$$\text{Database Active Window} = \text{Bulan Berjalan } (M) + \text{Bulan Sebelumnya } (M-1)$$

* **Bulan $M$ (Berjalan):** Data terus diisi setiap penutupan bursa.
* **Bulan $M-1$ (Lalu):** Dipertahankan penuh agar analisa HMB dan tren 20 hari tetap presisi.
* **Bulan $M-2$:** Begitu pergantian bulan baru, data bulan $M-2$ diekspor menjadi file Excel/ZIP, dikirimkan ke Telegram Mas Dhika, lalu dihapus dari Neon.

### Evaluasi Kapasitas Neon Free Tier (500 MB Storage)
| Tabel | Estimasi Baris (2 Bulan) | Ukuran Data + Index |
| :--- | :--- | :--- |
| `harga_saham` | ~42.000 baris | ~5 MB |
| `broker_summary` | ~440.000 baris | ~55 MB |
| `daftar_saham` | 955 baris | ~1 MB |
| `trading_plans` | ~1.000 baris | ~1 MB |
| `bot_error_logs` & `harvester_gaps` | ~5.000 baris | ~4 MB |
| **Total Penyimpanan Aktif** | **~490.000 baris** | **~66 MB** |

> 🟢 **Hasil:** Kapasitas 500 MB Neon **hanya terpakai ~13%**. Sisa 87% kuota storage masih sangat lega.

---

## ⏱️ 4. Evaluasi Komputasi Harvester & Neon Free Tier (100 Jam)

* **Durasi Pipeline:** ~10 menit per hari bursa.
* **Durasi Harvester (Scraping IPOT):** ~2,5 jam per hari bursa (akibat delay anti-WAF 7–20 detik).
* **Hari Bursa per Bulan:** ~22 hari kerja (Weekend 0 jam).
* **Total Jam Compute Worker:** $22 \times 2{,}6\text{ jam} \approx \mathbf{57{,}2\text{ jam/bulan}}$.
* **Akses PWA Pengguna:** ~**4 – 6 jam/bulan** (Auto-suspend Neon aktif setelah 5 menit idle).
* 👉 **Total Konsumsi Sebulan: ~62 – 64 jam CU-hours** (dari batas **100 jam gratis**).

> 🟢 **Hasil:** Masih memiliki cadangan aman ~36 jam untuk mengatasi retry queue atau circuit breaker.

---

## 🚀 5. Roadmap Tahapan Eksekusi

### Fase 1: Penyesuaian Archiver (Rolling 2-Month)
1. Modifikasi fungsi `archive_and_delete_old_data()` di `worker/archiver.py` agar batas potong data (*cutoff*) adalah $M-2$ (bukan $M-1$).
2. Memastikan `get_backfill_floor()` di `worker/db_config.py` sinkron dengan status bulan $M-2$.

### Fase 2: Pembuatan Tabel & API Journaling
1. Membuat tabel `trading_plans` di database Neon.
2. Membangun endpoint `/api/journal.py` di Vercel untuk menggantikan ketergantungan Supabase client di Candlify.

### Fase 3: Integrasi KLineCharts dengan Database Neon
1. Memindahkan aset `klinecharts.min.js` dan CSS Candlify ke dalam direktori PWA Glory Engine (`web/public/`).
2. Menghubungkan endpoint candlestick Candlify agar langsung membaca data lokal tabel `harga_saham` di Neon.
3. Menambahkan kalkulasi HMB (Harga Modal Bandar) dan sub-pane Net Flow Broker di bawah candlestick.

### Fase 4: Finalisasi UI/UX PWA Ramping
1. Menyusun navigasi 3 tab mobile: **Screener**, **Chart & Bandar**, **Journal**.
2. Uji coba fungsionalitas PWA (Add to Home Screen, Service Worker offline caching).
