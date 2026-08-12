import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from sqlalchemy import text

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
            if action == "harga":
                sql = text("""
                    SELECT h.ticker, d.nama_perusahaan, h.close, h.volume,
                           ROUND(CAST(((h.close - prev.close) / NULLIF(prev.close, 0)) * 100 AS numeric), 2) as chg_pct
                    FROM harga_saham h
                    JOIN daftar_saham d ON h.ticker = d.kode
                    LEFT JOIN (
                        SELECT ticker, close 
                        FROM harga_saham 
                        WHERE tanggal = (SELECT DISTINCT tanggal FROM harga_saham ORDER BY tanggal DESC OFFSET 1 LIMIT 1)
                    ) prev ON h.ticker = prev.ticker
                    WHERE h.tanggal = (SELECT MAX(tanggal) FROM harga_saham)
                    ORDER BY h.volume DESC
                    LIMIT 50
                """)
                results = db.execute(sql).fetchall()
                data = [
                    {
                        "kode": r.ticker,
                        "nama": r.nama_perusahaan,
                        "harga": float(r.close) if r.close else 0,
                        "volume": int(r.volume) if r.volume else 0,
                        "chg_pct": float(r.chg_pct) if r.chg_pct else 0
                    } for r in results
                ]
            elif action == "broker":
                sql = text("""
                    SELECT broker_code, SUM(net_vol) as total_net_vol, SUM(net_val) as total_net_val
                    FROM broker_summary
                    WHERE date = (SELECT MAX(date) FROM broker_summary)
                    GROUP BY broker_code
                    ORDER BY ABS(SUM(net_val)) DESC
                    LIMIT 20
                """)
                results = db.execute(sql).fetchall()
                data = [
                    {
                        "broker": r.broker_code,
                        "net_vol": int(r.total_net_vol) if r.total_net_vol else 0,
                        "net_val": float(r.total_net_val) if r.total_net_val else 0
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
