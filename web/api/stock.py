import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from lib.database import SessionLocal
from lib.query_service import get_radar_hmb

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query_components = parse_qs(urlparse(self.path).query)
        action = query_components.get("action", [""])[0]
        
        db = SessionLocal()
        try:
            if action == "hmb":
                results = get_radar_hmb(db)
                data = [
                    {
                        "kode": r.kode,
                        "harga": float(r.harga),
                        "hmb": float(r.hmb),
                        "pct_diff": float(r.pct_diff),
                        "brokers": r.brokers
                    } for r in (results or [])
                ]
            else:
                data = {"message": "Gunakan ?action=hmb"}
                
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
