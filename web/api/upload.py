import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from lib.database import SessionLocal
from lib.sync_service import process_saham_excel

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        query_components = parse_qs(urlparse(self.path).query)
        filename = query_components.get("filename", ["unknown.xlsx"])[0]

        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self._send_error(400, "Empty payload")
            return

        file_bytes = self.rfile.read(content_length)

        if not SessionLocal:
            self._send_error(500, "DATABASE_URL environment variable is not set")
            return

        db = SessionLocal()
        try:
            metrics = process_saham_excel(db, file_bytes, filename)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success", 
                "message": "Bulk Replace Sukses",
                "data": metrics
            }).encode('utf-8'))
            
        except Exception as e:
            self._send_error(500, str(e))
        finally:
            db.close()

    def _send_error(self, code: int, message: str):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({'error': message}).encode('utf-8'))
