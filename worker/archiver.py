import os
import psycopg2
import pandas as pd
import requests
from datetime import datetime, timedelta
import io

DB_URL = os.environ.get("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") # Chat/Channel ID untuk arsip

def send_document_to_telegram(filename, file_content):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram Token/Chat ID not found.")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    files = {'document': (filename, file_content)}
    data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f"Archive: {filename}"}
    
    response = requests.post(url, files=files, data=data)
    if response.status_code == 200:
        print(f"Successfully archived {filename} to Telegram.")
        return True
    else:
        print(f"Failed to archive: {response.text}")
        return False

def archive_and_delete_old_data():
    if not DB_URL:
        print("DATABASE_URL not set.")
        return
        
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    # Batas data yang disimpan di database adalah 30 hari terakhir
    cutoff_date = datetime.now().date() - timedelta(days=30)
    
    tables = ["stocks_daily", "broker_summary"]
    
    for table in tables:
        # 1. Ekstrak data lama
        query = f"SELECT * FROM {table} WHERE date < %s"
        df = pd.read_sql_query(query, conn, params=(cutoff_date,))
        
        if len(df) > 0:
            # 2. Convert ke CSV in-memory
            csv_buffer = io.BytesIO()
            df.to_csv(csv_buffer, index=False)
            csv_buffer.seek(0)
            
            filename = f"{table}_archive_until_{cutoff_date}.csv"
            
            # 3. Kirim ke Telegram
            success = send_document_to_telegram(filename, csv_buffer)
            
            # 4. Hapus dari PostgreSQL JIKA berhasil dikirim (aman)
            if success:
                delete_query = f"DELETE FROM {table} WHERE date < %s"
                cur.execute(delete_query, (cutoff_date,))
                conn.commit()
                print(f"Deleted {len(df)} rows from {table} (Date < {cutoff_date})")
        else:
            print(f"No old data to archive for {table}.")
            
    cur.close()
    conn.close()

if __name__ == "__main__":
    print("Starting Archiver Process...")
    archive_and_delete_old_data()
    print("Archiver Process Finished.")
