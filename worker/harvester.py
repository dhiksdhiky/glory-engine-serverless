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
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db_config import (
    engine, SessionLocal, log_to_db,
    get_date_cutoff_sql, TEST_MODE,
    GAP_EXCLUDE_SQL, today_jkt, get_dialect
)
from scraper import BroksumScraper, SoftBlockError
from archiver import archive_and_delete_old_data
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
        broker_summary. Hanya ambil yang volume > 0 dan tidak terdaftar di harvester_gaps (attempts >= 3).
        """
        gap_threshold = today_jkt() - timedelta(days=30)
        query = text(f"""
            SELECT h.ticker, h.tanggal
            FROM harga_saham h
            JOIN daftar_saham ds ON h.ticker = ds.kode
            WHERE h.volume > 0
            AND NOT EXISTS (
                SELECT 1 FROM broker_summary b
                WHERE b.ticker = h.ticker AND b.date = h.tanggal
            )
            AND {GAP_EXCLUDE_SQL}
            ORDER BY h.tanggal ASC
            LIMIT :limit
        """)
        try:
            with SessionLocal() as db:
                results = db.execute(query, {
                    "limit": TARGET_LIMIT,
                    "gap_threshold": gap_threshold
                }).fetchall()
                return results
        except SQLAlchemyError as e:
            logger.error(f"❌ DB Error saat fetch targets: {e}")
            log_to_db("harvester", "CRITICAL", "Gagal fetch pending targets", exc_info=e)
            return []

    def record_gap(self, ticker: str, target_date, reason: str):
        """Catat gap terisolasi ke tabel harvester_gaps."""
        try:
            dialect = get_dialect()
            if dialect == "sqlite":
                sql = text("""
                    INSERT INTO harvester_gaps (ticker, date, reason, attempts, last_attempt)
                    VALUES (:ticker, :date, :reason, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT (ticker, date) DO UPDATE SET
                        attempts = harvester_gaps.attempts + 1,
                        last_attempt = CURRENT_TIMESTAMP,
                        reason = :reason
                """)
            else:
                sql = text("""
                    INSERT INTO harvester_gaps (ticker, date, reason, attempts, last_attempt)
                    VALUES (:ticker, :date, :reason, 1, NOW())
                    ON CONFLICT (ticker, date) DO UPDATE SET
                        attempts = harvester_gaps.attempts + 1,
                        last_attempt = NOW(),
                        reason = :reason
                """)
            with SessionLocal() as db:
                db.execute(sql, {"ticker": ticker, "date": target_date, "reason": reason})
                db.commit()
        except Exception as e:
            logger.warning(f"⚠️ Gagal catat gap ({ticker}, {target_date}): {e}")

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



    def run_batch(self) -> bool:
        """
        Eksekusi satu batch harvesting.
        Returns: True jika masih ada data pending, False jika sudah complete.
        """
        logger.info("═══════════════════════════════════════════")
        logger.info("  🕷️ HARVESTER BATCH DIMULAI")
        logger.info("═══════════════════════════════════════════")

        targets = self.get_pending_targets()
        total_targets = len(targets)

        if total_targets == 0:
            logger.info("✅ Tidak ada data pending. Database sudah up-to-date.")
            return False

        logger.info(f"📋 {total_targets} target ditemukan.")

        success_count = 0
        deferred_queue = []
        consecutive_failures = 0
        throttle_detected = False
        has_any_success = False

        # ── Fase Utama ──────────────────────────────────────
        for i, row in enumerate(targets):
            ticker, target_date = row[0], row[1]
            status = self.process_target(ticker, target_date)

            # Heartbeat ping for serverless DB (Keep-alive)
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception as e:
                logger.warning(f"⚠️ Heartbeat ping failed: {e}")

            if status == 'success':
                success_count += 1
                consecutive_failures = 0
                has_any_success = True
            else:
                consecutive_failures += 1
                if consecutive_failures >= 5:
                    logger.warning("🚨 IPOT-wide throttle/WAF terdeteksi (>=5 non-success berurutan). Skip gap marking & cooldown...")
                    throttle_detected = True

                if status == 'soft_block':
                    logger.warning(f"💤 Cooldown {COOLDOWN_SOFT_BLOCK}s (Soft-Block)...")
                    log_to_db("harvester", "WARNING", "Circuit Breaker aktif", ticker=ticker)
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
                    consecutive_failures = 0
                    has_any_success = True
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        throttle_detected = True

                    if status == 'soft_block':
                        logger.warning(f"💤 Cooldown {COOLDOWN_SOFT_BLOCK}s pada retry...")
                        time.sleep(COOLDOWN_SOFT_BLOCK)
                    else:
                        log_to_db("harvester", "WARNING", "Gagal setelah retry", ticker=ticker)

                    # F1: Catat gap HANYA jika bukan IPOT throttle dan run ini punya minimal 1 success!
                    if has_any_success and not throttle_detected:
                        self.record_gap(ticker, target_date, reason=status)

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

    last_archive_time = time.time()
    while True:
        try:
            has_more = harvester.run_batch()

            if not has_more:
                # S1: Panggil archiver saat drain tuntas (1x per siklus)
                try:
                    archive_and_delete_old_data()
                    last_archive_time = time.time()
                except Exception as e:
                    logger.error(f"❌ Archiver gagal saat drain selesai: {e}")

                if not daemon_mode:
                    logger.info("🏁 Semua data sudah sinkron. Auto-sync selesai.")
                    break
                
                logger.info(f"💤 Semua sinkron. Istirahat {REST_INTERVAL}s...")
                time.sleep(REST_INTERVAL)
            else:
                # S1: Fallback time-based jika drain menggantung > 4 jam
                if time.time() - last_archive_time > 4 * 3600:
                    try:
                        archive_and_delete_old_data()
                        last_archive_time = time.time()
                    except Exception as e:
                        logger.error(f"❌ Fallback archiver gagal: {e}")

                logger.info(f"⏳ Cooldown {COOLDOWN_BATCH}s sebelum batch berikutnya...")
                time.sleep(COOLDOWN_BATCH)

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
