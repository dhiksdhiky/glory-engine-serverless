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
            import datetime as dt
            today = dt.date.today()
            first_day = today.replace(day=1)
            # Menentukan tanggal 1 bulan depannya
            if today.month == 12:
                next_month_first_day = today.replace(year=today.year+1, month=1, day=1)
            else:
                next_month_first_day = today.replace(month=today.month+1, day=1)

            sql_history = text("""
                SELECT 
                    h.tanggal as date,
                    COUNT(DISTINCT h.ticker) as harga_total,
                    SUM(CASE WHEN h.volume > 0 THEN 1 ELSE 0 END) as target_harvester,
                    (SELECT COUNT(DISTINCT b.ticker) FROM broker_summary b WHERE b.date = h.tanggal) as broker_total
                FROM harga_saham h
                WHERE h.tanggal >= :first_day AND h.tanggal < :next_month_first_day
                GROUP BY h.tanggal
                ORDER BY h.tanggal ASC
            """)
            hist_rows = db.execute(sql_history, {"first_day": first_day, "next_month_first_day": next_month_first_day}).fetchall()
            
            history_data = []
            for r in hist_rows:
                history_data.append({
                    "date": str(r.date),
                    "ohlcv_scraped": int(r.harga_total) if r.harga_total else 0,
                    "target_harvester": int(r.target_harvester) if r.target_harvester else 0,
                    "broksum_synced": int(r.broker_total) if r.broker_total else 0
                })

            if history_data:
                pipeline_data = history_data[-1] # Hari terakhir (paling bawah/terbaru)
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

            # 5. Archive Status & DB Stats
            try:
                sql_archive = text("""
                    SELECT month, status, completed_at 
                    FROM archive_status 
                    ORDER BY month DESC 
                    LIMIT 5
                """)
                archive_rows = db.execute(sql_archive).fetchall()
                archive_list = []
                for r in archive_rows:
                    dt_str = r.completed_at.strftime('%Y-%m-%d %H:%M') if hasattr(r.completed_at, 'strftime') and r.completed_at else str(r.completed_at)
                    archive_list.append({
                        "month": str(r.month),
                        "status": str(r.status),
                        "completed_at": dt_str
                    })

                sql_stats = text("""
                    SELECT 
                        (SELECT COUNT(*) FROM harga_saham) as total_harga,
                        (SELECT COUNT(*) FROM broker_summary) as total_broksum,
                        (SELECT MIN(tanggal) FROM harga_saham) as min_date,
                        (SELECT MAX(tanggal) FROM harga_saham) as max_date
                """)
                stats_row = db.execute(sql_stats).fetchone()
                db_stats = {
                    "total_harga": int(stats_row.total_harga) if stats_row and stats_row.total_harga else 0,
                    "total_broksum": int(stats_row.total_broksum) if stats_row and stats_row.total_broksum else 0,
                    "min_date": str(stats_row.min_date) if stats_row and stats_row.min_date else "N/A",
                    "max_date": str(stats_row.max_date) if stats_row and stats_row.max_date else "N/A"
                }
            except Exception as e:
                archive_list = []
                db_stats = {"total_harga": 0, "total_broksum": 0, "min_date": "N/A", "max_date": "N/A"}

            # 6. Harvester Gaps (Suspended / Empty Emiten)
            try:
                sql_gaps = text("""
                    SELECT ticker, date, reason, attempts, last_attempt 
                    FROM harvester_gaps 
                    ORDER BY date DESC, attempts DESC 
                    LIMIT 15
                """)
                gap_rows = db.execute(sql_gaps).fetchall()
                gap_list = []
                for r in gap_rows:
                    dt_str = r.last_attempt.strftime('%Y-%m-%d %H:%M') if hasattr(r.last_attempt, 'strftime') and r.last_attempt else str(r.last_attempt)
                    gap_list.append({
                        "ticker": str(r.ticker),
                        "date": str(r.date),
                        "reason": str(r.reason),
                        "attempts": int(r.attempts) if r.attempts else 1,
                        "last_attempt": dt_str
                    })
            except Exception as e:
                gap_list = []

            data = {
                "saham": {"total": saham_total, "last_update": saham_date},
                "pipeline": pipeline_data,
                "history": history_data,
                "errors": errors,
                "archive": {
                    "history": archive_list,
                    "stats": db_stats
                },
                "gaps": gap_list
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
