import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from sqlalchemy import text
import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from lib.database import SessionLocal

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not SessionLocal:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': "DATABASE_URL environment variable is not set"}).encode('utf-8'))
            return
            
        db = SessionLocal()
        try:
            # 1. Total Emiten di Daftar Saham
            sql_saham = text("SELECT COUNT(*) as total, MAX(tanggal_update) as last_update FROM daftar_saham")
            saham_row = db.execute(sql_saham).fetchone()
            saham_total = int(saham_row.total) if saham_row and saham_row.total else 0
            saham_date = str(saham_row.last_update) if saham_row and saham_row.last_update else "N/A"

            # 2 & 3. Data Pipeline & History Harian (7 Hari Terakhir)
            # Kombinasi Harga (OHLCV) dan Broker dalam 1 query efisien.
            sql_history = text("""
                SELECT 
                    h.tanggal as date,
                    COUNT(DISTINCT h.ticker) as harga_total,
                    SUM(CASE WHEN h.volume > 0 THEN 1 ELSE 0 END) as target_harvester,
                    (SELECT COUNT(DISTINCT b.ticker) FROM broker_summary b WHERE b.date = h.tanggal) as broker_total
                FROM harga_saham h
                GROUP BY h.tanggal
                ORDER BY h.tanggal DESC
                LIMIT 7
            """)
            hist_rows = db.execute(sql_history).fetchall()
            
            history_data = []
            for r in hist_rows:
                history_data.append({
                    "date": str(r.date),
                    "ohlcv_scraped": int(r.harga_total) if r.harga_total else 0,
                    "target_harvester": int(r.target_harvester) if r.target_harvester else 0,
                    "broksum_synced": int(r.broker_total) if r.broker_total else 0
                })

            if history_data:
                pipeline_data = history_data[0] # Hari terakhir (paling atas)
            else:
                pipeline_data = {
                    "date": "N/A", "ohlcv_scraped": 0, 
                    "target_harvester": 0, "broksum_synced": 0
                }

            # 4. Recent Errors (48 jam terakhir)
            sql_errors = text("""
                SELECT bot_name, error_level, error_message, timestamp
                FROM bot_error_logs
                WHERE timestamp >= NOW() - INTERVAL '48 HOURS'
                ORDER BY timestamp DESC
                LIMIT 3
            """)
            error_rows = db.execute(sql_errors).fetchall()
            errors = []
            for r in error_rows:
                time_str = r.timestamp.strftime('%Y-%m-%d %H:%M') if hasattr(r.timestamp, 'strftime') else str(r.timestamp)
                errors.append({
                    "bot_name": str(r.bot_name),
                    "level": str(r.error_level),
                    "message": str(r.error_message),
                    "time": time_str
                })

            data = {
                "saham": {"total": saham_total, "last_update": saham_date},
                "pipeline": pipeline_data,
                "history": history_data,
                "errors": errors
            }

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "data": data}).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
        finally:
            db.close()
