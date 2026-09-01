"""
scraper.py — IndoPremier Broker Summary Scraper
=================================================
Scrape data broker summary dari indopremier.com,
parse HTML, dan upsert ke database.

Error Handling:
  - Hard Block (WAF): tabel HTML hilang → raise Exception
  - Soft Block: tabel ada tapi kosong → raise SoftBlockError (trigger circuit breaker)
  - Network timeout: retry 3x dengan backoff 2s/4s/8s
  - Invalid broker code: skip baris, tidak crash
  - DB constraint violation: on_conflict_do_update (upsert)
"""

import re
import logging
import requests
from bs4 import BeautifulSoup
from sqlalchemy import text
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.retry import Retry

from db_config import engine, SessionLocal, get_dialect, TEST_MODE
from models import BrokerSummary

logger = logging.getLogger("Scraper")


class SoftBlockError(Exception):
    """Dipicu saat server IPOT mengembalikan tabel kosong (rate-limiting)."""
    pass


class BroksumScraper:
    def __init__(self):
        self.base_url = "https://www.indopremier.com/module/saham/include/data-brokersummary.php"
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

        # Retry strategy: 3x untuk HTTP 429/5xx
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            backoff_factor=2  # 2s → 4s → 8s
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _convert_to_float(self, value_str: str) -> float:
        """Parse angka dengan suffix K/M/B/T dan hilangkan titik ribuan format ID."""
        if not value_str or value_str.strip() in ('', '-'):
            return 0.0
            
        clean = value_str.strip().upper()
        # Jika nilai dari web IndoPremier pakai format Indonesia (contoh "1,5B"), kita ganti koma jadi titik desimal.
        clean = clean.replace(',', '.')
        
        try:
            multipliers = {'T': 1e12, 'B': 1e9, 'M': 1e6, 'K': 1e3}
            for suffix, mult in multipliers.items():
                if suffix in clean:
                    return float(clean.replace(suffix, '')) * mult
            
            # Jika tidak ada suffix (contoh "1.000" lot), maka titik adalah pemisah ribuan, bukan desimal.
            clean = clean.replace('.', '')
            return float(clean)
        except ValueError:
            return 0.0

    def _clean_broker_code(self, code: str) -> str | None:
        """Bersihkan kode broker menjadi 2 huruf uppercase."""
        if not code:
            return None
        clean = re.sub(r'[^A-Z]', '', code.strip().upper())
        return clean[:2] if clean else None

    def _do_upsert(self, db, data_to_insert: list):
        """Dialect-aware upsert untuk broker_summary."""
        if not data_to_insert:
            return

        dialect = get_dialect()
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            from sqlalchemy.dialects.postgresql import insert as dialect_insert

        stmt = dialect_insert(BrokerSummary).values(data_to_insert)
        stmt = stmt.on_conflict_do_update(
            index_elements=['ticker', 'date', 'broker_code'],
            set_={
                'buy_vol': stmt.excluded.buy_vol,
                'buy_val': stmt.excluded.buy_val,
                'buy_avg': stmt.excluded.buy_avg,
                'sell_vol': stmt.excluded.sell_vol,
                'sell_val': stmt.excluded.sell_val,
                'sell_avg': stmt.excluded.sell_avg,
                'net_vol': stmt.excluded.net_vol,
                'net_val': stmt.excluded.net_val,
            }
        )
        db.execute(stmt)
        db.commit()

    def fetch_and_save(self, ticker: str, date_obj):
        """
        Scrape broker summary untuk 1 ticker + 1 tanggal, lalu simpan ke DB.

        Raises:
            SoftBlockError: jika server mengembalikan tabel kosong
            Exception: jika tabel HTML tidak ditemukan (hard block)
        """
        db = SessionLocal()
        ticker_clean = ticker.upper().strip()

        try:
            date_fmt = date_obj.strftime('%m/%d/%Y')
            params = {
                'code': ticker_clean,
                'start': date_fmt,
                'end': date_fmt,
                'fd': 'all',
                'board': 'all'
            }
            headers = {
                'User-Agent': self.ua,
                'Referer': 'https://www.indopremier.com/',
                'Accept': '*/*',
                'X-Requested-With': 'XMLHttpRequest'
            }

            response = self.session.get(
                self.base_url, params=params, headers=headers, timeout=15
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', class_='table-summary')

            # ── HARD BLOCK: Tabel HTML tidak ada ────────────
            if not table:
                raise Exception(
                    "Tabel HTML tidak ditemukan (Hard Block WAF / Timeout IPOT)"
                )

            # ── SOFT BLOCK: Tabel ada tapi kosong ───────────
            is_empty = False
            if not table.tbody:
                is_empty = True
            else:
                rows = table.tbody.find_all('tr')
                if not rows:
                    is_empty = True
                else:
                    first_cols = rows[0].find_all('td')
                    if len(first_cols) > 0:
                        first_buyer = first_cols[0].text.strip()
                        if not first_buyer or first_buyer == '-':
                            is_empty = True

            if is_empty:
                raise SoftBlockError(
                    "Soft-Block: HTML valid tapi data kosong (rate-limited oleh IPOT)"
                )

            # ── PARSE DATA ──────────────────────────────────
            broker_map = {}
            rows = table.tbody.find_all('tr')

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 9:
                    continue

                # Sisi Buyer (kolom 0-2)
                b_code = self._clean_broker_code(cols[0].text)
                if b_code:
                    if b_code not in broker_map:
                        broker_map[b_code] = {
                            'buy_lot': 0, 'buy_val': 0,
                            'sell_lot': 0, 'sell_val': 0
                        }
                    broker_map[b_code]['buy_lot'] += self._convert_to_float(cols[1].text)
                    broker_map[b_code]['buy_val'] += self._convert_to_float(cols[2].text)

                # Sisi Seller (kolom 5-7)
                s_code = self._clean_broker_code(cols[5].text)
                if s_code:
                    if s_code not in broker_map:
                        broker_map[s_code] = {
                            'buy_lot': 0, 'buy_val': 0,
                            'sell_lot': 0, 'sell_val': 0
                        }
                    broker_map[s_code]['sell_lot'] += self._convert_to_float(cols[6].text)
                    broker_map[s_code]['sell_val'] += self._convert_to_float(cols[7].text)

            # ── PREPARE INSERT ──────────────────────────────
            data_to_insert = []
            for code, vals in broker_map.items():
                b_lot = int(round(vals['buy_lot']))
                b_val = int(round(vals['buy_val']))
                s_lot = int(round(vals['sell_lot']))
                s_val = int(round(vals['sell_val']))

                buy_avg = (vals['buy_val'] / (vals['buy_lot'] * 100)) if vals['buy_lot'] > 0 else 0
                sell_avg = (vals['sell_val'] / (vals['sell_lot'] * 100)) if vals['sell_lot'] > 0 else 0

                data_to_insert.append({
                    'ticker': ticker_clean,
                    'date': date_obj,
                    'broker_code': code,
                    'buy_vol': b_lot,
                    'buy_val': b_val,
                    'buy_avg': float(buy_avg),
                    'sell_vol': s_lot,
                    'sell_val': s_val,
                    'sell_avg': float(sell_avg),
                    'net_vol': b_lot - s_lot,
                    'net_val': b_val - s_val,
                })

            if data_to_insert:
                self._do_upsert(db, data_to_insert)
                logger.info(
                    f"✅ [{ticker_clean}] {date_obj} → {len(data_to_insert)} broker records saved."
                )

        except SoftBlockError:
            db.rollback()
            raise  # Propagate ke harvester untuk circuit breaker
        except Exception:
            db.rollback()
            raise  # Propagate ke harvester untuk retry logic
        finally:
            db.close()
