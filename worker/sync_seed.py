"""
sync_seed.py — Seed Local SQLite dari Railway PostgreSQL
==========================================================
Tarik data sampel dari Railway untuk testing lokal.
Jalankan SEKALI sebelum run.py agar SQLite punya data awal.

Usage:
  python sync_seed.py              # Default: 50 ticker, 500 harga
  python sync_seed.py --full       # Semua ticker, 2000 harga
"""

import os
import sys
import sqlite3
import logging
import pandas as pd

# Fix for Windows console emoji encoding
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("SyncSeed")


def sync():
    load_dotenv()
    pg_url = os.getenv("DATABASE_URL")
    sqlite_path = os.getenv("SQLITE_PATH", "local_test.db")
    full_mode = "--full" in sys.argv

    if not pg_url or "sqlite" in pg_url:
        logger.error("❌ DATABASE_URL harus PostgreSQL (bukan SQLite)!")
        logger.info("💡 Pastikan .env punya DATABASE_URL=postgresql://...")
        return

    logger.info("📡 Koneksi ke Railway PostgreSQL...")
    try:
        pg_engine = create_engine(pg_url)
        # Test koneksi
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Koneksi Railway berhasil.")
    except Exception as e:
        logger.error(f"❌ Gagal koneksi ke Railway: {e}")
        return

    # ── Tarik Data ──────────────────────────────────────────
    try:
        # 1. Daftar Saham (semua)
        logger.info("📥 Menarik daftar_saham...")
        df_saham = pd.read_sql("SELECT kode, nama_perusahaan AS nama FROM daftar_saham", pg_url)
        logger.info(f"   → {len(df_saham)} saham")

        # 2. Harga Saham (sampel atau full)
        limit_harga = 2000 if full_mode else 500
        ticker_limit = "" if full_mode else "LIMIT 50"

        # Ambil ticker terpopuler (yang punya data terbanyak)
        logger.info(f"📥 Menarik harga saham (limit {limit_harga})...")
        query_harga = f"""
            SELECT * FROM harga_saham
            WHERE ticker IN (
                SELECT ticker FROM harga_saham
                GROUP BY ticker ORDER BY COUNT(*) DESC {ticker_limit}
            )
            ORDER BY tanggal DESC
            LIMIT {limit_harga}
        """
        df_harga = pd.read_sql(query_harga, pg_url)
        logger.info(f"   → {len(df_harga)} baris harga ({df_harga['ticker'].nunique()} ticker)")

        # 3. Broker Summary (sampel terkini)
        logger.info("📥 Menarik broker_summary terbaru (sampel 1000)...")
        df_broksum = pd.read_sql(
            "SELECT * FROM broker_summary ORDER BY date DESC LIMIT 1000",
            pg_url
        )
        logger.info(f"   → {len(df_broksum)} baris broksum")

    except Exception as e:
        logger.error(f"❌ Gagal tarik data dari Railway: {e}")
        return

    # ── Simpan ke SQLite ────────────────────────────────────
    logger.info(f"💾 Menulis ke {sqlite_path}...")
    try:
        conn = sqlite3.connect(sqlite_path)
        cursor = conn.cursor()

        # Buat tabel dengan constraint yang benar
        cursor.executescript("""
            DROP TABLE IF EXISTS daftar_saham;
            CREATE TABLE daftar_saham (
                kode TEXT PRIMARY KEY,
                nama TEXT
            );

            DROP TABLE IF EXISTS harga_saham;
            CREATE TABLE harga_saham (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                tanggal DATE NOT NULL,
                open REAL, high REAL, low REAL, close REAL,
                volume INTEGER,
                UNIQUE (ticker, tanggal)
            );

            DROP TABLE IF EXISTS broker_summary;
            CREATE TABLE broker_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date DATE NOT NULL,
                broker_code TEXT NOT NULL,
                buy_vol INTEGER DEFAULT 0,
                buy_val REAL DEFAULT 0,
                buy_avg REAL DEFAULT 0,
                sell_vol INTEGER DEFAULT 0,
                sell_val REAL DEFAULT 0,
                sell_avg REAL DEFAULT 0,
                net_vol INTEGER DEFAULT 0,
                net_val REAL DEFAULT 0,
                UNIQUE (ticker, date, broker_code)
            );

            DROP TABLE IF EXISTS bot_error_logs;
            CREATE TABLE bot_error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_name TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                error_level TEXT NOT NULL,
                ticker TEXT,
                error_message TEXT NOT NULL,
                traceback TEXT
            );
        """)

        # Insert data (tanpa kolom id agar AUTOINCREMENT bekerja)
        cols_saham = ['kode', 'nama']
        df_saham[cols_saham].to_sql("daftar_saham", conn, if_exists="append", index=False)

        cols_harga = ['ticker', 'tanggal', 'open', 'high', 'low', 'close', 'volume']
        if 'id' in df_harga.columns:
            df_harga[cols_harga].to_sql("harga_saham", conn, if_exists="append", index=False)
        else:
            df_harga.to_sql("harga_saham", conn, if_exists="append", index=False)

        cols_broksum = ['ticker', 'date', 'broker_code', 'buy_vol', 'buy_val',
                        'buy_avg', 'sell_vol', 'sell_val', 'sell_avg', 'net_vol', 'net_val']
        if 'id' in df_broksum.columns:
            df_broksum[cols_broksum].to_sql("broker_summary", conn, if_exists="append", index=False)
        else:
            df_broksum.to_sql("broker_summary", conn, if_exists="append", index=False)

        conn.close()

        # Verifikasi
        conn2 = sqlite3.connect(sqlite_path)
        counts = {}
        for tbl in ['daftar_saham', 'harga_saham', 'broker_summary']:
            counts[tbl] = conn2.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        conn2.close()

        logger.info("")
        logger.info("╔═══════════════════════════════════════════╗")
        logger.info("║       ✨ SEED SELESAI — Mini Railway!      ║")
        logger.info("╠═══════════════════════════════════════════╣")
        logger.info(f"║  daftar_saham  : {counts['daftar_saham']:>8,} rows          ║")
        logger.info(f"║  harga_saham   : {counts['harga_saham']:>8,} rows          ║")
        logger.info(f"║  broker_summary: {counts['broker_summary']:>8,} rows          ║")
        logger.info("╚═══════════════════════════════════════════╝")
        logger.info(f"📁 File: {os.path.abspath(sqlite_path)}")
        logger.info("💡 Sekarang jalankan: python run.py")

    except Exception as e:
        logger.error(f"❌ Gagal menulis ke SQLite: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    sync()
