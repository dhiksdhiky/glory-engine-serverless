"""
pipeline.py — OHLCV Price Data Fetcher
========================================
Mengambil data harga saham harian dari yfinance,
forward-fill berdasarkan kalender IHSG, dan bulk upsert ke database.

Error Handling:
  - DB connection fail → log + exit
  - yfinance timeout → skip ticker, lanjut ke berikutnya
  - IHSG calendar empty → abort pipeline
  - Bulk insert fail → log critical error
  - TEST_MODE: limit 10 ticker, 60 hari, delay minimal
"""

import os
import sys
import traceback
import logging
import time
import pandas as pd
import yfinance as yf
from datetime import datetime, date, timedelta

import pytz
from sqlalchemy import text

from db_config import engine, log_to_db, get_dialect, get_date_cutoff_sql, TEST_MODE

logger = logging.getLogger("Pipeline")

# ── Konfigurasi ─────────────────────────────────────────────
BATCH_SIZE = 50 if not TEST_MODE else 10
BATCH_SLEEP = 30 if not TEST_MODE else 5
TICKER_SLEEP = 0.5 if not TEST_MODE else 0.2
LOOKBACK_DAYS = 365 * 2 if not TEST_MODE else 60
TICKER_LIMIT = None if not TEST_MODE else 10  # None = semua ticker
JKT_TZ = pytz.timezone('Asia/Jakarta')


def get_tickers() -> list:
    """Ambil daftar ticker dari database. Fallback ke CSV jika kosong (TEST_MODE)."""
    tickers = []
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT kode FROM daftar_saham"))
            for row in result:
                tickers.append(row[0].strip())
    except Exception as e:
        logger.warning(f"⚠️ Gagal baca daftar_saham dari DB: {e}")

    # Fallback: load dari CSV jika tabel kosong
    if not tickers:
        csv_path = os.path.join(os.path.dirname(__file__), "daftar_saham.csv")
        if os.path.exists(csv_path):
            logger.info("📄 Fallback: Membaca ticker dari daftar_saham.csv...")
            df = pd.read_csv(csv_path, sep=";")
            tickers = df["Kode"].str.strip().tolist()

            # Auto-seed ke database agar harvester bisa JOIN
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        for kode in tickers:
                            nama = df.loc[df["Kode"].str.strip() == kode, "Nama Perusahaan"].values
                            nama_str = nama[0] if len(nama) > 0 else ""
                            conn.execute(text(
                                "INSERT OR IGNORE INTO daftar_saham (kode, nama_perusahaan) "
                                "VALUES (:kode, :nama)"
                            ) if get_dialect() == "sqlite" else text(
                                "INSERT INTO daftar_saham (kode, nama_perusahaan) "
                                "VALUES (:kode, :nama) ON CONFLICT (kode) DO NOTHING"
                            ), {"kode": kode, "nama": nama_str})
                logger.info(f"✅ {len(tickers)} ticker di-seed ke daftar_saham.")
            except Exception as e:
                logger.error(f"⚠️ Gagal seed daftar_saham: {e}")
        else:
            logger.error("❌ Tidak ada ticker sama sekali! Jalankan sync_seed.py dulu.")
            return []

    if not tickers:
        logger.error("❌ Daftar ticker kosong setelah semua fallback.")
        return []

    # Limit untuk TEST_MODE
    if TICKER_LIMIT:
        tickers = tickers[:TICKER_LIMIT]
        logger.info(f"🧪 TEST MODE: Dibatasi {TICKER_LIMIT} ticker.")

    logger.info(f"📋 Total {len(tickers)} ticker dimuat.")
    return tickers


def get_master_calendar(start_date: date, end_date: date) -> pd.DatetimeIndex:
    """Unduh kalender bursa IHSG (^JKSE) sebagai acuan hari trading."""
    logger.info("📅 Mengunduh Kalender Bursa (IHSG/^JKSE)...")
    try:
        ihsg = yf.download('^JKSE', start=start_date, end=end_date, progress=False)
        if ihsg.empty:
            raise ValueError("Data IHSG kosong dari yfinance.")
        logger.info(f"📅 Kalender bursa dimuat: {len(ihsg)} hari trading.")
        return ihsg.index
    except Exception as e:
        logger.error(f"❌ Gagal unduh kalender IHSG: {e}")
        raise


def cleanup_old_data():
    """Hapus data harga >30 hari untuk menghemat storage."""
    try:
        cutoff_sql = get_date_cutoff_sql("tanggal", 30)
        with engine.connect() as conn:
            with conn.begin():
                result = conn.execute(text(f"DELETE FROM harga_saham WHERE {cutoff_sql}"))
                logger.info(f"🧹 Cleanup: {result.rowcount} baris data lama dihapus.")
    except Exception as e:
        logger.warning(f"⚠️ Cleanup gagal (non-fatal): {e}")


def run_pipeline():
    """
    Proses utama Pipeline OHLCV:
    1. Ambil daftar ticker
    2. Unduh kalender IHSG
    3. Loop per ticker: download, forward-fill, kumpulkan
    4. Bulk upsert ke database
    5. Cleanup data lama
    """
    logger.info("═══════════════════════════════════════════")
    logger.info("  📈 PIPELINE OHLCV DIMULAI")
    logger.info("═══════════════════════════════════════════")

    tickers = get_tickers()
    if not tickers:
        logger.error("❌ Pipeline dibatalkan: tidak ada ticker.")
        return False

    total_tickers = len(tickers)

    # ── Cek data terakhir per ticker ────────────────────────
    last_update_dates = {}
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT ticker, MAX(tanggal) as max_tanggal FROM harga_saham GROUP BY ticker"
            ))
            for row in result:
                last_update_dates[row[0]] = row[1]
    except Exception as e:
        logger.warning(f"⚠️ Gagal baca last dates (fresh start): {e}")

    # ── Setup waktu ─────────────────────────────────────────
    now_jkt = datetime.now(JKT_TZ)
    api_end_date = now_jkt.date() + timedelta(days=1)
    min_date = now_jkt.date() - timedelta(days=30)  # Ambil maksimal 30 hari ke belakang agar pergantian bulan tidak terpotong

    try:
        master_calendar = get_master_calendar(min_date, api_end_date)
    except Exception:
        log_to_db("pipeline", "CRITICAL", "Gagal muat Master Calendar IHSG")
        return False

    # ── Loop Ekstraksi ──────────────────────────────────────
    all_data = []
    success_count = 0
    skip_count = 0
    error_count = 0

    for i, ticker_code in enumerate(tickers, 1):
        ticker_yf = f"{ticker_code}.JK"
        try:
            last_date = last_update_dates.get(ticker_code)

            # Jika sudah ada data, ambil dari 5 hari sebelum data terakhir
            if last_date:
                # Handle string date dari SQLite
                if isinstance(last_date, str):
                    last_date = datetime.strptime(last_date, "%Y-%m-%d").date()
                start_dt = max(last_date - timedelta(days=5), min_date)
            else:
                start_dt = min_date

            data_raw = yf.download(
                ticker_yf, start=start_dt, end=api_end_date,
                progress=False, auto_adjust=False
            )

            if data_raw.empty:
                logger.warning(f"({i}/{total_tickers}) ⚠️ {ticker_code}: Data kosong dari yfinance.")
                skip_count += 1
                continue

            # Handle MultiIndex columns dari yfinance
            if isinstance(data_raw.columns, pd.MultiIndex):
                try:
                    data_raw.columns = data_raw.columns.droplevel('Ticker')
                except Exception:
                    data_raw.columns = data_raw.columns.droplevel(1)

            # Forward-fill berdasarkan kalender IHSG
            mask = (master_calendar.date >= start_dt) & (master_calendar.date <= now_jkt.date())
            local_calendar = master_calendar[mask]
            data_reindexed = data_raw.reindex(local_calendar)
            data_reindexed[['Open', 'High', 'Low', 'Close']] = \
                data_reindexed[['Open', 'High', 'Low', 'Close']].ffill()
            data_reindexed['Volume'] = data_reindexed['Volume'].fillna(0)
            data_reindexed.dropna(subset=['Close'], inplace=True)

            if data_reindexed.empty:
                skip_count += 1
                continue

            rows_count = len(data_reindexed)
            data_clean = pd.DataFrame({
                'ticker': ticker_code,
                'tanggal': data_reindexed.index.date,
                'open': data_reindexed['Open'].values,
                'high': data_reindexed['High'].values,
                'low': data_reindexed['Low'].values,
                'close': data_reindexed['Close'].values,
                'volume': data_reindexed['Volume'].values
            })
            all_data.extend(data_clean.to_dict(orient='records'))

            logger.info(
                f"({i}/{total_tickers}) ✅ {ticker_code} | {rows_count} baris | "
                f"{data_clean['tanggal'].min()} → {data_clean['tanggal'].max()}"
            )
            success_count += 1

        except Exception as e:
            logger.error(f"({i}/{total_tickers}) ❌ {ticker_code}: {str(e)[:120]}")
            error_count += 1

        time.sleep(TICKER_SLEEP)
        if i % BATCH_SIZE == 0 and i < total_tickers:
            # Heartbeat ping for serverless DB (Keep-alive)
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info("💓 DB Heartbeat: Ping sent (keep-alive).")
            except Exception as e:
                logger.warning(f"⚠️ Heartbeat ping failed: {e}")

            logger.info(f"💤 Batch cooldown {BATCH_SLEEP}s...")
            time.sleep(BATCH_SLEEP)

    # ── Bulk UPSERT ─────────────────────────────────────────
    if all_data:
        total_rows = len(all_data)
        logger.info(f"💾 Bulk UPSERT {total_rows} baris ke database...")
        try:
            with engine.connect() as conn:
                with conn.begin():
                    upsert_sql = text("""
                        INSERT INTO harga_saham (ticker, tanggal, open, high, low, close, volume)
                        VALUES (:ticker, :tanggal, :open, :high, :low, :close, :volume)
                        ON CONFLICT (ticker, tanggal) DO UPDATE SET
                            open = EXCLUDED.open, high = EXCLUDED.high,
                            low = EXCLUDED.low, close = EXCLUDED.close,
                            volume = EXCLUDED.volume
                    """)
                    conn.execute(upsert_sql, all_data)
            logger.info(f"✅ Bulk UPSERT berhasil ({total_rows} baris).")
        except Exception as e:
            logger.error(f"❌ CRITICAL: Bulk UPSERT gagal: {e}")
            log_to_db("pipeline", "CRITICAL", f"Bulk UPSERT gagal: {e}")
            return False
    else:
        logger.warning("⚠️ Tidak ada data untuk di-insert.")

    # ── Cleanup ─────────────────────────────────────────────
    cleanup_old_data()

    logger.info("═══════════════════════════════════════════")
    logger.info(f"  📈 PIPELINE SELESAI | ✅ {success_count} | ⚠️ {skip_count} skip | ❌ {error_count} error")
    logger.info("═══════════════════════════════════════════")
    return True


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    from db_config import setup_tables
    setup_tables()
    run_pipeline()
