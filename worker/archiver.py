import os
import pandas as pd
import requests
import tempfile
import zipfile
import logging
from datetime import date, timedelta
from sqlalchemy import text

from db_config import engine, today_jkt, get_dialect, GAP_EXCLUDE_SQL

logger = logging.getLogger("Archiver")

TELEGRAM_BOT_TOKEN = os.environ.get("TELE_BOT_DHIKSDHIKY")
TELEGRAM_CHAT_ID = os.environ.get("TELE_CHAT_ID_DHIKA")


def _export_and_send_table(df: pd.DataFrame, table_name: str, month_str: str, is_force: bool) -> bool:
    """
    Ekspor dan kirim data satu tabel ke Telegram.
    Returns: True jika sukses (atau jika 0 baris), False jika gagal kirim.
    """
    if df.empty:
        logger.info(f"ℹ️ [{month_str}] Tabel {table_name} kosong (0 baris). Dianggap ok_sent.")
        return True

    # 1. Export awal ke Excel
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f'Archived_{table_name}')

    file_size = os.path.getsize(tmp_path)
    send_path = tmp_path
    filename = f"Archive_{table_name}_{month_str}.xlsx"
    mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # F8: Fail-safe kompresi CSV.ZIP jika ukuran > 40MB
    if file_size > 40 * 1024 * 1024:
        logger.info(f"📦 [{month_str}] {filename} ({file_size/1e6:.1f} MB) > 40MB. Konversi ke CSV.ZIP...")
        os.unlink(tmp_path)

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as zip_tmp:
            send_path = zip_tmp.name

        filename = f"Archive_{table_name}_{month_str}.csv.zip"
        mime_type = "application/zip"

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as csv_tmp:
            csv_path = csv_tmp.name
        df.to_csv(csv_path, index=False)

        with zipfile.ZipFile(send_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(csv_path, arcname=f"Archive_{table_name}_{month_str}.csv")
        os.unlink(csv_path)
        file_size = os.path.getsize(send_path)

    caption_mode = "Force-Close (Bypass 40d)" if is_force else "Smart Month End"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": (
            f"🗄️ *Glory Auto-Archiver*\n"
            f"Bulan: `{month_str}`\n"
            f"Tabel: `{table_name}`\n"
            f"Total: `{len(df)}` baris\n"
            f"Ukuran: `{file_size/1e6:.1f} MB`\n"
            f"Mode: {caption_mode}"
        ),
        "parse_mode": "Markdown"
    }

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(send_path, "rb") as f:
            files = {"document": (filename, f, mime_type)}
            response = requests.post(url, data=payload, files=files, timeout=300)

        os.unlink(send_path)
        if response.status_code == 200:
            logger.info(f"✅ [{month_str}] Berhasil arsipkan {filename} ke Telegram.")
            return True
        else:
            logger.error(f"❌ [{month_str}] Gagal kirim Telegram: HTTP {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ [{month_str}] Exception kirim Telegram: {e}")
        if os.path.exists(send_path):
            os.unlink(send_path)
        return False


def _mark_completed(month_str: str, status_str: str, dialect: str):
    """Menulis status completed ke tabel archive_status."""
    try:
        with engine.connect() as conn:
            with conn.begin():
                if dialect == "sqlite":
                    conn.execute(text("""
                        INSERT INTO archive_status (month, status, completed_at)
                        VALUES (:m, :st, CURRENT_TIMESTAMP)
                        ON CONFLICT(month) DO UPDATE SET status = :st, completed_at = CURRENT_TIMESTAMP
                    """), {"m": month_str, "st": status_str})
                else:
                    conn.execute(text("""
                        INSERT INTO archive_status (month, status, completed_at)
                        VALUES (:m, :st, NOW())
                        ON CONFLICT(month) DO UPDATE SET status = :st, completed_at = NOW()
                    """), {"m": month_str, "st": status_str})
    except Exception as e:
        logger.error(f"❌ Gagal update archive_status {month_str}: {e}")


def archive_and_delete_old_data():
    """
    Arsipkan data bulan lalu secara atomic per-bulan (OLDEST -> NEWEST).
    Hanya menghapus dan menandai COMPLETED jika KEDUA tabel (harga & broksum) sukses.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("📦 Archiver: Telegram credentials tidak ada, skip.")
        return False

    logger.info("📦 Memulai Smart Archiver Bulanan (Per-Bulan Atomic)...")
    today = today_jkt()
    current_month_start = today.replace(day=1)
    dialect = get_dialect()

    with engine.connect() as conn:
        # 1. Cari bulan kandidat < current_month yang ada datanya di DB
        if dialect == "sqlite":
            sql_months = """
                SELECT DISTINCT strftime('%Y-%m', tanggal) as m FROM harga_saham WHERE tanggal < :c
                UNION
                SELECT DISTINCT strftime('%Y-%m', date) as m FROM broker_summary WHERE date < :c
            """
        else:
            sql_months = """
                SELECT DISTINCT TO_CHAR(tanggal, 'YYYY-MM') as m FROM harga_saham WHERE tanggal < :c
                UNION
                SELECT DISTINCT TO_CHAR(date, 'YYYY-MM') as m FROM broker_summary WHERE date < :c
            """

        months_in_db = set(conn.execute(text(sql_months), {"c": current_month_start}).scalars().all())
        completed_months = set(conn.execute(
            text("SELECT month FROM archive_status WHERE status IN ('completed', 'completed_force')")
        ).scalars().all())

        # F6: Urutkan OLDEST -> NEWEST
        candidate_months = sorted([m for m in months_in_db if m and m not in completed_months])

        if not candidate_months:
            logger.info("ℹ️ Tidak ada bulan lampau yang perlu diarsipkan.")
            return True

        logger.info(f"📋 Bulan kandidat arsip (OLDEST -> NEWEST): {candidate_months}")

        for m in candidate_months:
            try:
                y, mo = map(int, m.split('-'))
                month_start = date(y, mo, 1)
                next_month_start = date(y + 1, 1, 1) if mo == 12 else date(y, mo + 1, 1)
                end_of_month = next_month_start - timedelta(days=1)
            except Exception as e:
                logger.error(f"❌ Format bulan invalid {m}: {e}")
                continue

            # F3: Gate evaluasi pending khusus bulan M
            gap_threshold = today - timedelta(days=30)
            gate_sql = text(f"""
                SELECT 1 FROM harga_saham h
                WHERE h.tanggal >= :month_start AND h.tanggal < :next_month_start
                AND h.volume > 0
                AND NOT EXISTS (
                    SELECT 1 FROM broker_summary b
                    WHERE b.ticker = h.ticker AND b.date = h.tanggal
                )
                AND {GAP_EXCLUDE_SQL}
                LIMIT 1
            """)
            has_pending = conn.execute(gate_sql, {
                "month_start": month_start,
                "next_month_start": next_month_start,
                "gap_threshold": gap_threshold
            }).scalar() is not None

            # G2: Force-close bypass jika sudah lewat 40 hari dari akhir bulan
            is_force = today > (end_of_month + timedelta(days=40))

            if has_pending and not is_force:
                logger.info(f"⏳ Bulan {m} masih memiliki target pending di Harvester. Skip arsip bulan ini.")
                continue

            # Ambil data kedua tabel
            df_h = pd.read_sql_query(
                text("SELECT * FROM harga_saham WHERE tanggal >= :s AND tanggal < :e"),
                conn, params={"s": month_start, "e": next_month_start}
            )
            # F5: Drop kolom 'id' pada broker_summary
            df_b = pd.read_sql_query(
                text("""
                    SELECT ticker, date, broker_code, buy_vol, buy_val, buy_avg,
                           sell_vol, sell_val, sell_avg, net_vol, net_val
                    FROM broker_summary
                    WHERE date >= :s AND date < :e
                """),
                conn, params={"s": month_start, "e": next_month_start}
            )

            # N3 & F4: Penanganan 0 baris per-tabel
            if df_h.empty and df_b.empty:
                logger.info(f"ℹ️ Bulan {m} kosong (0 baris di kedua tabel). Ditandai COMPLETED.")
                _mark_completed(m, "completed", dialect)
                continue

            ok_h = _export_and_send_table(df_h, "harga_saham", m, is_force)
            ok_b = _export_and_send_table(df_b, "broker_summary", m, is_force)

            # G4: Hanya jika KEDUA tabel sukses
            if ok_h and ok_b:
                with engine.connect() as del_conn:
                    with del_conn.begin():
                        del_conn.execute(
                            text("DELETE FROM harga_saham WHERE tanggal >= :s AND tanggal < :e"),
                            {"s": month_start, "e": next_month_start}
                        )
                        del_conn.execute(
                            text("DELETE FROM broker_summary WHERE date >= :s AND date < :e"),
                            {"s": month_start, "e": next_month_start}
                        )
                status_str = "completed_force" if is_force else "completed"
                _mark_completed(m, status_str, dialect)
                logger.info(f"🎉 Bulan {m} RESMI DITUTUP ({status_str}) & data dibersihkan!")
            else:
                logger.error(
                    f"⚠️ Gagal arsipkan bulan {m} (harga_ok={ok_h}, broksum_ok={ok_b}). "
                    f"Data TIDAK dihapus agar bisa di-retry pada run berikutnya."
                )

    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Standalone Archiver Process...")
    archive_and_delete_old_data()
    logger.info("Archiver Process Finished.")
