"""
harvester.py — Broker Summary Harvester Orchestrator
======================================================
Mengatur batch scraping broker summary dari IndoPremier.
Bergantung pada data harga_saham yang sudah ada dari pipeline.

Error Handling:
  - Soft Block → Circuit Breaker: cooldown 10 menit, lalu lanjut
  - Hard Block → masuk retry queue
  - Network error → masuk retry queue
  - Retry Phase: ulang semua target yang gagal
  - TEST_MODE: limit 10 target, delay 2-5 detik
"""

import os
import sys
import io
import time
import random
import logging
import pandas as pd
import requests
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db_config import (
    engine, SessionLocal, log_to_db,
    get_date_cutoff_sql, TEST_MODE
)
from scraper import BroksumScraper, SoftBlockError
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("Harvester")

# ── Konfigurasi ─────────────────────────────────────────────
TARGET_LIMIT = 500 if not TEST_MODE else 10
DELAY_MIN = 7 if not TEST_MODE else 2
DELAY_MAX = 20 if not TEST_MODE else 5
COOLDOWN_SOFT_BLOCK = 600 if not TEST_MODE else 30  # 10 menit prod, 30s test
COOLDOWN_RETRY = 30 if not TEST_MODE else 5
COOLDOWN_BATCH = 120 if not TEST_MODE else 10
REST_INTERVAL = 60 * 60 * 3 if not TEST_MODE else 30  # 3 jam prod, 30s test

TELEGRAM_BOT_TOKEN = os.getenv("TELE_BOT_DHIKSDHIKY")
TELEGRAM_CHAT_ID = os.getenv("TELE_CHAT_ID_DHIKA")


class BatchHarvester:
    def __init__(self):
        self.scraper = BroksumScraper()

    def get_pending_targets(self) -> list:
        """
        Cari pasangan (ticker, tanggal) di harga_saham yang belum punya
        broker_summary. Hanya ambil yang volume > 0.
        """
        query = text("""
            SELECT h.ticker, h.tanggal
            FROM harga_saham h
            JOIN daftar_saham ds ON h.ticker = ds.kode
            WHERE h.volume > 0
            AND NOT EXISTS (
                SELECT 1 FROM broker_summary b
                WHERE b.ticker = h.ticker AND b.date = h.tanggal
            )
            ORDER BY h.tanggal DESC
            LIMIT :limit
        """)
        try:
            with SessionLocal() as db:
                results = db.execute(query, {"limit": TARGET_LIMIT}).fetchall()
                return results
        except SQLAlchemyError as e:
            logger.error(f"❌ DB Error saat fetch targets: {e}")
            log_to_db("harvester", "CRITICAL", "Gagal fetch pending targets", exc_info=e)
            return []

    def process_target(self, ticker: str, target_date) -> str:
        """
        Proses satu target scraping.
        Returns: 'success', 'soft_block', atau 'error'
        """
        try:
            # Handle string date dari SQLite
            if isinstance(target_date, str):
                from datetime import datetime as dt
                target_date = dt.strptime(target_date, "%Y-%m-%d").date()

            logger.info(f"🕷️ Scraping {ticker} [{target_date}]...")
            self.scraper.fetch_and_save(ticker, target_date)
            return 'success'
        except SoftBlockError as sbe:
            logger.error(f"🛑 CIRCUIT BREAKER: {sbe}")
            return 'soft_block'
        except Exception as e:
            logger.warning(f"⚠️ Gagal {ticker} [{target_date}]: {str(e)[:100]}")
            return 'error'

    def run_archiver(self):
        """
        Arsipkan data BrokSum > 2 tahun ke Telegram (setiap tanggal 1).
        Skip jika Telegram credentials tidak ada.
        """
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.info("📦 Archiver: Telegram credentials tidak ada, skip.")
            return

        now = datetime.now()
        if now.day != 1:
            logger.info(f"📅 Archiver standby (hari ini tgl {now.day}, dijadwalkan tgl 1).")
            return

        logger.info("📦 Memulai Archiver Bulanan (data > 30 hari)...")
        cutoff_sql = get_date_cutoff_sql("date", 30)

        try:
            with engine.connect() as conn:
                df = pd.read_sql(f"SELECT * FROM broker_summary WHERE {cutoff_sql}", conn)

            if df.empty:
                logger.info("✅ Tidak ada data usang untuk diarsipkan.")
                return

            total_rows = len(df)
            min_date = df['date'].min()
            max_date = df['date'].max()

            # Format date jika perlu (SQLite returns string)
            if isinstance(min_date, str):
                min_date_str = min_date.replace('-', '')
                max_date_str = max_date.replace('-', '')
            else:
                min_date_str = min_date.strftime('%Y%m%d')
                max_date_str = max_date.strftime('%Y%m%d')

            filename = f"Archive_BrokSum_{min_date_str}_to_{max_date_str}.xlsx"

            # Export ke Excel in-memory
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Archived_BrokSum')
            buffer.seek(0)

            # Kirim ke Telegram
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": (
                    f"🗄️ *Glory Auto-Archiver*\n"
                    f"Data BrokSum usang (> 30 Hari).\n"
                    f"Total: `{total_rows}` baris\n"
                    f"Rentang: `{min_date_str}` - `{max_date_str}`"
                ),
                "parse_mode": "Markdown"
            }
            files = {"document": (filename, buffer,
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

            response = requests.post(url, data=payload, files=files, timeout=60)
            if response.status_code == 200:
                with SessionLocal() as db:
                    db.execute(text(f"DELETE FROM broker_summary WHERE {cutoff_sql}"))
                    db.commit()
                logger.info(f"🗑️ {total_rows} baris data usang dihapus setelah arsip.")
            else:
                log_to_db("harvester_archiver", "ERROR",
                          f"Telegram HTTP {response.status_code}")

        except Exception as e:
            log_to_db("harvester_archiver", "ERROR", "Archiver gagal", exc_info=e)

    def run_batch(self) -> bool:
        """
        Eksekusi satu batch harvesting.
        Returns: True jika masih ada data pending, False jika sudah complete.
        """
        logger.info("═══════════════════════════════════════════")
        logger.info("  🕷️ HARVESTER BATCH DIMULAI")
        logger.info("═══════════════════════════════════════════")

        self.run_archiver()

        targets = self.get_pending_targets()
        total_targets = len(targets)

        if total_targets == 0:
            logger.info("✅ Tidak ada data pending. Database sudah up-to-date.")
            return False

        logger.info(f"📋 {total_targets} target ditemukan.")

        success_count = 0
        deferred_queue = []

        # ── Fase Utama ──────────────────────────────────────
        for i, row in enumerate(targets):
            ticker, target_date = row[0], row[1]
            status = self.process_target(ticker, target_date)

            # Heartbeat ping for serverless DB (Keep-alive)
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                # logger.debug("💓 DB Heartbeat: Ping sent.")
            except Exception as e:
                logger.warning(f"⚠️ Heartbeat ping failed: {e}")

            if status == 'success':
                success_count += 1
            elif status == 'soft_block':
                # ...
                logger.warning(f"💤 Cooldown {COOLDOWN_SOFT_BLOCK}s (Soft-Block)...")
                log_to_db("harvester", "WARNING",
                          "Circuit Breaker aktif", ticker=ticker)
                time.sleep(COOLDOWN_SOFT_BLOCK)
                deferred_queue.append((ticker, target_date))
                logger.info("🔄 Melanjutkan setelah cooldown.")
            else:
                deferred_queue.append((ticker, target_date))

            if i < total_targets - 1:
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        # ── Fase Retry ──────────────────────────────────────
        if deferred_queue:
            logger.info(
                f"🔄 Cooldown {COOLDOWN_RETRY}s sebelum retry "
                f"({len(deferred_queue)} target)..."
            )
            time.sleep(COOLDOWN_RETRY)

            for i, (ticker, target_date) in enumerate(deferred_queue):
                logger.info(f"🔁 [RETRY] {ticker} [{target_date}]...")
                status = self.process_target(ticker, target_date)

                if status == 'success':
                    success_count += 1
                elif status == 'soft_block':
                    logger.warning(f"💤 Cooldown {COOLDOWN_SOFT_BLOCK}s pada retry...")
                    time.sleep(COOLDOWN_SOFT_BLOCK)
                else:
                    log_to_db("harvester", "WARNING",
                              f"Gagal setelah retry", ticker=ticker)

                if i < len(deferred_queue) - 1:
                    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        logger.info("═══════════════════════════════════════════")
        logger.info(
            f"  🕷️ BATCH SELESAI | ✅ {success_count}/{total_targets}"
        )
        logger.info("═══════════════════════════════════════════")
        return True


def run_harvester(daemon_mode: bool = True):
    """
    Entry point harvester.
    - daemon_mode=True: loop terus sampai manual stop
    - daemon_mode=False: loop sampai semua data sinkron, lalu berhenti (Auto-Sync)
    """
    harvester = BatchHarvester()
    mode_str = "Daemon" if daemon_mode else "Auto-Sync"
    logger.info(f"🚀 Harvester Started (Mode: {mode_str})")

    while True:
        try:
            has_more = harvester.run_batch()

            if has_more:
                logger.info(f"⏳ Cooldown {COOLDOWN_BATCH}s sebelum batch berikutnya...")
                time.sleep(COOLDOWN_BATCH)
            else:
                if not daemon_mode:
                    logger.info("🏁 Semua data sudah sinkron. Auto-sync selesai.")
                    break
                
                logger.info(f"💤 Semua sinkron. Istirahat {REST_INTERVAL}s...")
                time.sleep(REST_INTERVAL)

        except KeyboardInterrupt:
            logger.info("🛑 Harvester dihentikan manual.")
            break
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            log_to_db("harvester", "CRITICAL", f"Crash: {e}")
            if not daemon_mode:
                break
            time.sleep(300)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    from db_config import setup_tables
    setup_tables()
    run_harvester(daemon_mode=True)
