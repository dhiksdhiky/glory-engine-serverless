import os
import pandas as pd
import requests
import io
import logging
from datetime import datetime
from sqlalchemy import create_engine, text

logger = logging.getLogger("Archiver")

DB_URL = os.environ.get("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.environ.get("TELE_BOT_DHIKSDHIKY")
TELEGRAM_CHAT_ID = os.environ.get("TELE_CHAT_ID_DHIKA")

def archive_and_delete_old_data():
    """
    Arsipkan data (harga_saham, broker_summary) bulan lalu ke Telegram dalam format .xlsx.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("📦 Archiver: Telegram credentials tidak ada, skip.")
        return False
        
    if not DB_URL:
        logger.error("❌ Archiver: DATABASE_URL not set.")
        return False

    logger.info("📦 Memulai Smart Archiver Bulanan...")
    engine = create_engine(DB_URL)
    
    # Batas data: Ambil semua data sebelum tanggal 1 bulan ini
    today = datetime.now().date()
    cutoff_date = today.replace(day=1)
    
    tables = [("harga_saham", "tanggal"), ("broker_summary", "date")]
    
    with engine.connect() as conn:
        for table, date_col in tables:
            query = f"SELECT * FROM {table} WHERE {date_col} < '{cutoff_date}'"
            df = pd.read_sql_query(query, conn)
            
            if len(df) > 0:
                total_rows = len(df)
                min_date = df[date_col].min()
                max_date = df[date_col].max()
                
                if isinstance(min_date, str):
                    min_date_str = min_date.replace('-', '')
                    max_date_str = max_date.replace('-', '')
                else:
                    min_date_str = min_date.strftime('%Y%m%d')
                    max_date_str = max_date.strftime('%Y%m%d')

                # Export ke Excel in-memory
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name=f'Archived_{table}')
                buffer.seek(0)
                
                filename = f"Archive_{table}_{min_date_str}_to_{max_date_str}.xlsx"
                
                # Kirim ke Telegram
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": (
                        f"🗄️ *Glory Auto-Archiver*\n"
                        f"Tabel: `{table}`\n"
                        f"Total: `{total_rows}` baris\n"
                        f"Rentang: `{min_date_str}` - `{max_date_str}`\n"
                        f"Mode: Smart Month End"
                    ),
                    "parse_mode": "Markdown"
                }
                files = {"document": (filename, buffer,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                
                response = requests.post(url, data=payload, files=files, timeout=60)
                
                if response.status_code == 200:
                    logger.info(f"✅ Successfully archived {filename} to Telegram.")
                    with conn.begin():
                        delete_query = text(f"DELETE FROM {table} WHERE {date_col} < :cutoff_date")
                        conn.execute(delete_query, {"cutoff_date": cutoff_date})
                    logger.info(f"🗑️ Deleted {total_rows} rows from {table} (Date < {cutoff_date})")
                else:
                    logger.error(f"❌ Failed to archive: HTTP {response.status_code} - {response.text}")
            else:
                logger.info(f"✅ Tidak ada data usang untuk {table} sebelum {cutoff_date}.")

    engine.dispose()
    return True

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Standalone Archiver Process...")
    archive_and_delete_old_data()
    logger.info("Archiver Process Finished.")
