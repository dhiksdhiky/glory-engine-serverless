"""
db_config.py — Shared Database Layer (SQLite / PostgreSQL)
===========================================================
Modul sentral yang menentukan engine berdasarkan TEST_MODE.
Semua modul lain HARUS import engine/session dari sini.
"""

import os
import logging
import traceback
import time
import random
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("DBConfig")

# ── Mode Detection ──────────────────────────────────────────
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

# ── Timezone Helper ─────────────────────────────────────────
import pytz
from datetime import datetime, date

JKT_TZ = pytz.timezone("Asia/Jakarta")

def today_jkt() -> date:
    return datetime.now(JKT_TZ).date()

def now_jkt() -> datetime:
    return datetime.now(JKT_TZ)

# ── Engine Creation ─────────────────────────────────────────
if TEST_MODE:
    SQLITE_PATH = os.getenv("SQLITE_PATH", "local_test.db")
    DATABASE_URL = f"sqlite:///{SQLITE_PATH}"
    engine = create_engine(DATABASE_URL, echo=False)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    logger.info(f"🧪 TEST MODE aktif — SQLite: {SQLITE_PATH}")
else:
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("❌ DATABASE_URL tidak ditemukan di .env! Set TEST_MODE=true untuk SQLite.")
    
    # Fix for SQLAlchemy 2.0 + Psycopg2
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

    # Inisialisasi Engine dengan Retry (Exponential Backoff)
    temp_engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
        pool_recycle=300,
        connect_args={"connect_timeout": 15}
    )

    max_retries = 6
    initial_delay = 2
    engine = None

    for attempt in range(max_retries):
        try:
            with temp_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ Database terhubung dan aktif.")
            engine = temp_engine
            break
        except OperationalError as e:
            if attempt == max_retries - 1:
                logger.error(f"❌ CRITICAL: Database gagal merespons setelah {max_retries} percobaan.")
                raise e
            
            wait_time = (initial_delay * (2 ** attempt)) + random.uniform(0, 1)
            logger.warning(f"⚠️ DB sedang tertidur/booting. Mencoba lagi {attempt+1}/{max_retries} dalam {wait_time:.2f}s...")
            time.sleep(wait_time)

    if not engine:
        raise ConnectionError("Gagal membangun koneksi ke database.")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_dialect() -> str:
    """Returns 'sqlite' or 'postgresql'."""
    return engine.dialect.name


def get_date_cutoff_sql(column: str, days: int = 30) -> str:
    """Generate dialect-compatible date interval SQL for cleanup queries."""
    if get_dialect() == "sqlite":
        return f"{column} < date('now', '-{days} days')"
    else:
        return f"{column} < CURRENT_DATE - INTERVAL '{days} days'"


def log_to_db(bot_name: str, error_level: str, error_message: str,
              ticker: str = None, exc_info: Exception = None):
    """Log error ke database. Fallback ke console jika DB gagal."""
    tb_str = None
    if exc_info:
        tb_str = "".join(traceback.format_exception(
            type(exc_info), exc_info, exc_info.__traceback__
        ))
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO bot_error_logs
                        (bot_name, error_level, ticker, error_message, traceback)
                    VALUES
                        (:bot_name, :error_level, :ticker, :error_message, :traceback)
                """), {
                    "bot_name": bot_name,
                    "error_level": error_level,
                    "ticker": ticker,
                    "error_message": str(error_message)[:255],
                    "traceback": tb_str
                })
    except Exception as e:
        logger.error(f"⚠️ Gagal log ke DB (fallback console): {e}")
        logger.error(f"  Original: [{error_level}] {bot_name} | {error_message}")


def setup_tables():
    """Buat semua tabel dengan DDL yang kompatibel dialect aktif."""
    dialect = get_dialect()
    logger.info(f"📦 Setup tabel database ({dialect})...")

    with engine.connect() as conn:
        with conn.begin():
            if dialect == "sqlite":
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS daftar_saham (
                        kode TEXT PRIMARY KEY,
                        no INTEGER,
                        nama_perusahaan TEXT NOT NULL,
                        tanggal_pencatatan DATE,
                        saham INTEGER,
                        papan_pencatatan TEXT,
                        tanggal_update DATE
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS harga_saham (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        tanggal DATE NOT NULL,
                        open REAL, high REAL, low REAL, close REAL,
                        volume INTEGER,
                        UNIQUE (ticker, tanggal)
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS open_positions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        entry_date DATE NOT NULL,
                        entry_price REAL NOT NULL,
                        quantity INTEGER NOT NULL,
                        current_trailing_stop REAL NOT NULL,
                        last_updated DATE NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS trade_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        entry_date DATE NOT NULL,
                        entry_price REAL NOT NULL,
                        exit_date DATE NOT NULL,
                        exit_price REAL NOT NULL,
                        quantity INTEGER NOT NULL,
                        profit_loss_percent REAL NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS broker_summary (
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
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS bot_error_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        bot_name TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        error_level TEXT NOT NULL,
                        ticker TEXT,
                        error_message TEXT NOT NULL,
                        traceback TEXT
                    )
                """))
            else:
                # PostgreSQL branch
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS daftar_saham (
                        kode VARCHAR(10) PRIMARY KEY,
                        no INTEGER,
                        nama_perusahaan VARCHAR(255) NOT NULL,
                        tanggal_pencatatan DATE,
                        saham BIGINT,
                        papan_pencatatan VARCHAR(50),
                        tanggal_update DATE
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS harga_saham (
                        id SERIAL PRIMARY KEY,
                        ticker VARCHAR(10) NOT NULL,
                        tanggal DATE NOT NULL,
                        open NUMERIC(20,4), high NUMERIC(20,4),
                        low NUMERIC(20,4), close NUMERIC(20,4),
                        volume BIGINT,
                        UNIQUE (ticker, tanggal)
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS open_positions (
                        id SERIAL PRIMARY KEY,
                        ticker VARCHAR(10) NOT NULL,
                        entry_date DATE NOT NULL,
                        entry_price FLOAT NOT NULL,
                        quantity INTEGER NOT NULL,
                        current_trailing_stop FLOAT NOT NULL,
                        last_updated DATE NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS trade_history (
                        id SERIAL PRIMARY KEY,
                        ticker VARCHAR(10) NOT NULL,
                        entry_date DATE NOT NULL,
                        entry_price FLOAT NOT NULL,
                        exit_date DATE NOT NULL,
                        exit_price FLOAT NOT NULL,
                        quantity INTEGER NOT NULL,
                        profit_loss_percent FLOAT NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS broker_summary (
                        id SERIAL PRIMARY KEY,
                        ticker VARCHAR(10) NOT NULL,
                        date DATE NOT NULL,
                        broker_code VARCHAR(5) NOT NULL,
                        buy_vol BIGINT DEFAULT 0,
                        buy_val FLOAT DEFAULT 0,
                        buy_avg FLOAT DEFAULT 0,
                        sell_vol BIGINT DEFAULT 0,
                        sell_val FLOAT DEFAULT 0,
                        sell_avg FLOAT DEFAULT 0,
                        net_vol BIGINT DEFAULT 0,
                        net_val FLOAT DEFAULT 0,
                        UNIQUE (ticker, date, broker_code)
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS bot_error_logs (
                        id SERIAL PRIMARY KEY,
                        bot_name VARCHAR(50) NOT NULL,
                        timestamp TIMESTAMPTZ DEFAULT NOW(),
                        error_level VARCHAR(20) NOT NULL,
                        ticker VARCHAR(10),
                        error_message VARCHAR(255) NOT NULL,
                        traceback TEXT
                    )
                """))
                
                # Indexes for Performance
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_broker_summary_ticker_date
                        ON broker_summary (ticker, date)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_harga_saham_ticker_date
                        ON harga_saham (ticker, tanggal)
                """))

    logger.info("✅ Semua tabel siap.")
