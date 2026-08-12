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
        query_components = parse_qs(urlparse(self.path).query)
        action = query_components.get("action", ["harga"])[0]
        
        if not SessionLocal:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': "DATABASE_URL environment variable is not set"}).encode('utf-8'))
            return
            
        db = SessionLocal()
        try:
            start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
            
            if action == "harga":
                sql = text("""
                    SELECT tanggal, COUNT(*) as total
                    FROM harga_saham
                    WHERE tanggal >= :start_date
                    GROUP BY tanggal
                    ORDER BY tanggal ASC
                """)
                results = db.execute(sql, {"start_date": start_date}).fetchall()
                data = [
                    {
                        "date": r.tanggal,
                        "total": int(r.total)
                    } for r in results
                ]
            elif action == "broker":
                sql = text("""
                    SELECT date, COUNT(DISTINCT ticker) as total
                    FROM broker_summary
                    WHERE date >= :start_date
                    GROUP BY date
                    ORDER BY date ASC
                """)
                results = db.execute(sql, {"start_date": start_date}).fetchall()
                data = [
                    {
                        "date": r.date,
                        "total": int(r.total)
                    } for r in results
                ]
            else:
                data = {"message": "Gunakan ?action=harga atau ?action=broker"}
                
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
