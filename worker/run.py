"""
run.py — Main Orchestrator (Sequential: Pipeline → Harvester)
===============================================================
Entry point utama. Menjalankan Pipeline OHLCV terlebih dahulu,
lalu Harvester BrokSum. Semua dalam SATU proses Python (hemat RAM).

Usage:
  python run.py                  # Single run (pipeline + 1 batch harvester)
  python run.py --daemon         # Daemon mode (harvester loop terus)
  python run.py --pipeline-only  # Hanya pipeline
  python run.py --harvester-only # Hanya harvester
"""

import sys
import logging
from datetime import datetime

from db_config import setup_tables, TEST_MODE

# ── Setup Logging ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Orchestrator")


def main():
    start_time = datetime.now()

    # Parse arguments
    args = set(sys.argv[1:])
    daemon_mode = "--daemon" in args
    pipeline_only = "--pipeline-only" in args
    harvester_only = "--harvester-only" in args

    mode_str = "🧪 TEST MODE (SQLite)" if TEST_MODE else "🚀 PRODUCTION (PostgreSQL)"
    logger.info("╔═══════════════════════════════════════════╗")
    logger.info("║     STOCK ENGINE v2 — Unified Runner      ║")
    logger.info("╚═══════════════════════════════════════════╝")
    logger.info(f"  Mode: {mode_str}")
    logger.info(f"  Daemon: {'Ya' if daemon_mode else 'Tidak'}")
    logger.info("")

    # ── Step 1: Setup Database ──────────────────────────────
    try:
        setup_tables()
    except Exception as e:
        logger.error(f"❌ FATAL: Gagal setup database: {e}")
        sys.exit(1)

    # ── Step 2: Pipeline OHLCV ──────────────────────────────
    pipeline_success = True
    if not harvester_only:
        try:
            from pipeline import run_pipeline
            pipeline_success = run_pipeline()
        except Exception as e:
            logger.error(f"❌ Pipeline crash: {e}")
            pipeline_success = False

    # ── Step 3: Harvester BrokSum ───────────────────────────
    harvester_success = True
    if not pipeline_only:
        try:
            from harvester import run_harvester
            run_harvester(daemon_mode=daemon_mode)
        except Exception as e:
            logger.error(f"❌ Harvester crash: {e}")
            harvester_success = False

    # ── Step 4: Final Archiver Guarantee ────────────────────
    if not daemon_mode:
        try:
            from archiver import archive_and_delete_old_data
            archive_and_delete_old_data()
        except Exception as e:
            logger.error(f"❌ Final Archiver gagal: {e}")

    if not pipeline_success:
        logger.error("⚠️ Peringatan: Pipeline sempat gagal sebelumnya (lihat log di atas).")

    # ── Summary ─────────────────────────────────────────────
    duration = datetime.now() - start_time
    logger.info("")
    logger.info("╔═══════════════════════════════════════════╗")
    logger.info(f"║  🏁 SELESAI — Durasi: {str(duration).split('.')[0]:>17s}  ║")
    logger.info("╚═══════════════════════════════════════════╝")
    
    if not pipeline_success or (not pipeline_only and not harvester_success):
        sys.exit(1)


if __name__ == "__main__":
    main()
