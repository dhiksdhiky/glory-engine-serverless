import re
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, text
from datetime import timedelta, date, datetime
from database import OpenPosition, HargaSaham, TradeHistory, Saham, BrokerSummary, engine

def _fmt_date(date_obj) -> str:
    return date_obj.strftime("%d/%m") if date_obj else "--/--"

def _fmt_price(val: float) -> str:
    if val >= 10000: return f"{val/1000:.1f}k"
    return f"{val:,.0f}"

def get_open_positions_split(db: Session) -> dict:
    positions = db.query(OpenPosition).all()
    if not positions:
        return {"new": "📁 *Portfolio Kosong*\nTidak ada posisi terbuka.", "all": None}

    processed_pos = []
    max_date = date.min
    for pos in positions:
        latest = db.query(HargaSaham).filter(HargaSaham.ticker == pos.ticker).order_by(desc(HargaSaham.tanggal)).first()
        current_price = latest.close if latest else pos.entry_price
        
        invested = pos.entry_price * pos.quantity
        floating_pct = ((current_price * pos.quantity - invested) / invested) * 100 if invested > 0 else 0
        
        pos.current_price = current_price
        pos.floating_pct = floating_pct
        processed_pos.append(pos)
        
        if pos.entry_date > max_date:
            max_date = pos.entry_date

    threshold_date = max_date - timedelta(days=5)
    new_signals = [p for p in processed_pos if p.entry_date >= threshold_date]
    new_signals.sort(key=lambda x: x.entry_date, reverse=True)

    msg_new = ["🆕 *Sinyal Baru (5 Hari Terakhir)*\n```text\nCODE |DATE |IN   |TS   |PNL%\n----------------------------"]
    if not new_signals:
        msg_new.append("Tidak ada entri baru dalam 5 hari.")
    else:
        for p in new_signals:
            code = f"{p.ticker:<4}"
            dt = f"{_fmt_date(p.entry_date):<5}"
            in_p = f"{_fmt_price(p.entry_price):>4}"
            ts_p = f"{_fmt_price(p.current_trailing_stop):>4}"
            pnl = f"{p.floating_pct:>+5.1f}"
            msg_new.append(f"{code} |{dt}|{in_p} |{ts_p} |{pnl}")
    msg_new.append("```")

    processed_pos.sort(key=lambda x: x.floating_pct, reverse=True)
    top_10 = processed_pos[:10]
    bottom_10 = processed_pos[-10:] if len(processed_pos) > 10 else []
    bottom_10 = [b for b in bottom_10 if b not in top_10]

    msg_all = ["🏆 *Top/Bottom 10 Floating PnL*\n```text\nCODE |LAST |IN   |TS   |PNL%\n----------------------------"]
    for p in top_10:
        code = f"{p.ticker:<4}"
        last_p = f"{_fmt_price(p.current_price):>4}"
        in_p = f"{_fmt_price(p.entry_price):>4}"
        ts_p = f"{_fmt_price(p.current_trailing_stop):>4}"
        pnl = f"{p.floating_pct:>+5.1f}"
        msg_all.append(f"{code} |{last_p} |{in_p} |{ts_p} |{pnl}")
        
    if bottom_10:
        msg_all.append("----------------------------")
        for p in bottom_10:
            code = f"{p.ticker:<4}"
            last_p = f"{_fmt_price(p.current_price):>4}"
            in_p = f"{_fmt_price(p.entry_price):>4}"
            ts_p = f"{_fmt_price(p.current_trailing_stop):>4}"
            pnl = f"{p.floating_pct:>+5.1f}"
            msg_all.append(f"{code} |{last_p} |{in_p} |{ts_p} |{pnl}")
    msg_all.append("```")

    return {"new": "\n".join(msg_new), "all": "\n".join(msg_all)}

def get_trade_history_summary(db: Session) -> str:
    winners = db.query(TradeHistory).order_by(desc(TradeHistory.profit_loss_percent)).limit(5).all()
    losers = db.query(TradeHistory).order_by(TradeHistory.profit_loss_percent).limit(5).all()

    if not winners and not losers:
        return "📁 *Riwayat Kosong*\nBelum ada transaksi tertutup."

    report_lines = ["🏆 *Trade History (Top/Bot 5)*\n```text\nCODE|IN   |OUT  |DIN  |DOUT |PNL%\n---------------------------------"]
    
    for h in winners + losers:
        if h in losers and len(winners) > 0 and h == losers[0]:
            report_lines.append("---------------------------------")
            
        code = f"{h.ticker:<4}"
        in_p = f"{_fmt_price(h.entry_price):>4}"
        out_p = f"{_fmt_price(h.exit_price):>4}"
        d_in = f"{_fmt_date(h.entry_date)}"
        d_out = f"{_fmt_date(h.exit_date)}"
        pnl = f"{h.profit_loss_percent:>+5.1f}"
        
        report_lines.append(f"{code}|{in_p} |{out_p} |{d_in}|{d_out}|{pnl}")

    report_lines.append("```")
    return "\n".join(report_lines)

def get_radar_hmb(db: Session):
    sql = text("""
        WITH JendelaWaktu AS (
            SELECT DISTINCT tanggal FROM harga_saham ORDER BY tanggal DESC LIMIT 20
        ),
        StatsBroker AS (
            SELECT ticker, broker_code, SUM(net_vol) AS total_net_vol,
                   SUM(buy_val) AS total_buy_val, SUM(buy_vol) AS total_buy_vol
            FROM broker_summary WHERE date IN (SELECT tanggal FROM JendelaWaktu)
            GROUP BY ticker, broker_code HAVING SUM(net_vol) > 0
        ),
        RankingBroker AS (
            SELECT *, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY total_net_vol DESC) as urutan
            FROM StatsBroker
        ),
        HMB_Final AS (
            SELECT ticker,
                   ROUND(CAST(SUM(total_buy_val) / NULLIF(SUM(total_buy_vol) * 100, 0) AS NUMERIC), 0) as hmb,
                   STRING_AGG(broker_code, ',') as top_brokers
            FROM RankingBroker WHERE urutan <= 3 GROUP BY ticker
        ),
        LatestMarketDate AS (
            SELECT MAX(tanggal) as max_tgl FROM harga_saham
        )
        SELECT h.ticker AS kode, h.close AS harga, f.hmb AS hmb,
               ROUND(CAST(((f.hmb - h.close) / h.close * 100) AS NUMERIC), 1) AS pct_diff,
               f.top_brokers AS brokers
        FROM harga_saham h
        JOIN HMB_Final f ON h.ticker = f.ticker
        JOIN LatestMarketDate l ON h.tanggal = l.max_tgl
        WHERE f.hmb >= (h.close * 0.97) AND h.volume > 10000
        ORDER BY pct_diff DESC LIMIT 20;
    """)
    return db.execute(sql).fetchall()

def get_ticker_analysis(db: Session, ticker: str) -> str:
    ticker = ticker.upper()
    saham = db.query(Saham).filter(Saham.kode == ticker).first()
    if not saham:
        return f"❌ *{ticker}* tidak ditemukan di database IDX."

    harga_terakhir = db.execute(text("SELECT tanggal, close FROM harga_saham WHERE ticker = :ticker ORDER BY tanggal DESC LIMIT 1"), {"ticker": ticker}).fetchone()
    if not harga_terakhir:
        return f"❌ *{ticker}* tidak memiliki data harga."
        
    tgl_last = harga_terakhir.tanggal.strftime('%Y-%m-%d')
    close_price = float(harga_terakhir.close)

    try:
        with engine.connect() as conn:
            # 1. HMB dan Top 5 Akumulator
            sql_acc = text("""
                SELECT broker_code, SUM(net_vol) as total_net_vol,
                       SUM(buy_val) / NULLIF(SUM(buy_vol) * 100, 0) as avg_price,
                       SUM(buy_val) as total_bval, SUM(buy_vol) as total_bvol
                FROM broker_summary
                WHERE ticker = :ticker AND date >= CURRENT_DATE - INTERVAL '20 days'
                GROUP BY broker_code
                HAVING SUM(net_vol) > 0
                ORDER BY total_net_vol DESC LIMIT 5
            """)
            df_acc = pd.read_sql(sql_acc, conn, params={"ticker": ticker})
            
            # 2. Historical Price (10 Hari)
            sql_hist = text("""
                SELECT 
                    tanggal, close, volume,
                    ROUND(((close - prev_close) / prev_close::numeric) * 100, 1) as chg_pct
                FROM (
                    SELECT 
                        tanggal, close, volume,
                        LAG(close) OVER (ORDER BY tanggal ASC) as prev_close
                    FROM harga_saham
                    WHERE ticker = :ticker
                ) sub
                ORDER BY tanggal DESC
                LIMIT 10
            """)
            df_hist = pd.read_sql(sql_hist, conn, params={"ticker": ticker})

        # Hitung HMB Price
        total_val = df_acc['total_bval'].sum() if not df_acc.empty else 0
        total_vol = df_acc['total_bvol'].sum() if not df_acc.empty else 0
        hmb_price = (total_val / (total_vol * 100)) if total_vol > 0 else 0
        
        risk_pct = ((hmb_price - close_price) / close_price * 100) if close_price > 0 else 0
        
        report = [
            f"*{ticker}* - {saham.nama_perusahaan}",
            f"{tgl_last}\n",
            f"Close Price : {close_price:,.0f}",
            f"Harga Modal : {hmb_price:,.0f} ({risk_pct:+.2f}%)\n",
            "📈 *TOP 5 AKUMULATOR (20 Hari)*",
            "```text",
            f"{'BRK':<3} │ {'NET LOT':>9} │ {'AVG PRICE':>9}",
            "────┼───────────┼──────────"
        ]
        
        for _, row in df_acc.iterrows():
            avg_p = int(row['avg_price']) if pd.notnull(row['avg_price']) else 0
            report.append(f"{row['broker_code']:<3} │ {int(row['total_net_vol']):>9,d} │ {avg_p:>9,d}")
        report.append("```")

        # Open Position
        pos = db.query(OpenPosition).filter(OpenPosition.ticker == ticker).first()
        if pos:
            report.append("\n[Open Position]")
            report.append(f"└ In: {pos.entry_price:,.0f} | TS: {pos.current_trailing_stop:,.0f} ({_fmt_date(pos.entry_date)})")

        # Closed Signal
        history = db.query(TradeHistory).filter(TradeHistory.ticker == ticker).order_by(desc(TradeHistory.exit_date)).limit(10).all()
        if history:
            report.append("\n🛒 *Closed Signal*")
            report.append("```text\nIN    |OUT   |DIN  |DOUT |PNL%\n--------------------------------")
            for h in history:
                in_p = f"{h.entry_price:,.0f}"
                out_p = f"{h.exit_price:,.0f}"
                d_in = _fmt_date(h.entry_date)
                d_out = _fmt_date(h.exit_date)
                pnl = f"{h.profit_loss_percent:>+5.1f}"
                report.append(f"{in_p:<5} |{out_p:<5} |{d_in}|{d_out}|{pnl}")
            report.append("```")

        # Historical Price
        if not df_hist.empty:
            report.append("\n📆 *HISTORICAL PRICE (10 Hari)*")
            report.append("```text")
            report.append(f"{'DATE':<5} │ {'CLOSE':>5} │ {'CHG%':>5} │ {'VOL (M)':>7}")
            report.append("──────┼───────┼───────┼────────")
            for _, row in df_hist.iterrows():
                dt_str = row['tanggal'].strftime('%d/%m') if pd.notnull(row['tanggal']) else "--/--"
                cl_p = int(row['close']) if pd.notnull(row['close']) else 0
                chg = f"{row['chg_pct']:+.1f}" if pd.notnull(row['chg_pct']) else "0.0"
                vol_m = (row['volume'] / 1_000_000) if pd.notnull(row['volume']) else 0
                report.append(f"{dt_str:<5} │ {cl_p:>5} │ {chg:>5} │ {vol_m:>7.1f}")
            report.append("```")

        return "\n".join(report)
    except Exception as e:
        return f"❌ *Error Analitik {ticker}:*\n`{str(e)}`"

def get_market_flow(days: int = 5) -> str:
    """Menghitung Top 5 Inflow dan Outflow seluruh market berdasarkan Net Value."""
    try:
        with engine.connect() as conn:
            inflow_sql = text("""
                SELECT ticker, SUM(net_val) as total_net_val
                FROM broker_summary
                WHERE date >= CURRENT_DATE - :days * INTERVAL '1 day'
                GROUP BY ticker
                HAVING SUM(net_val) > 0
                ORDER BY total_net_val DESC
                LIMIT 5
            """)
            df_in = pd.read_sql(inflow_sql, conn, params={"days": days})

            outflow_sql = text("""
                SELECT ticker, SUM(net_val) as total_net_val
                FROM broker_summary
                WHERE date >= CURRENT_DATE - :days * INTERVAL '1 day'
                GROUP BY ticker
                HAVING SUM(net_val) < 0
                ORDER BY total_net_val ASC
                LIMIT 5
            """)
            df_out = pd.read_sql(outflow_sql, conn, params={"days": days})

        msg = f"🌊 *MARKET FLOW*\nPeriode: {days} Hari Terakhir\n\n"
        
        msg += "🟢 *TOP 5 INFLOW (Net Value)*\n```text\n"
        msg += f"{'TICKER':<6} │ {'NET VAL (B)':>11}\n"
        msg += "───────┼────────────\n"
        for _, row in df_in.iterrows():
            val_b = row['total_net_val'] / 1_000_000_000
            msg += f"{row['ticker']:<6} │ {val_b:>11,.1f}\n"
        msg += "```\n"

        msg += "🔴 *TOP 5 OUTFLOW (Net Value)*\n```text\n"
        msg += f"{'TICKER':<6} │ {'NET VAL (B)':>11}\n"
        msg += "───────┼────────────\n"
        for _, row in df_out.iterrows():
            val_b = row['total_net_val'] / 1_000_000_000
            msg += f"{row['ticker']:<6} │ {val_b:>11,.1f}\n"
        msg += "```"

        return msg
    except Exception as e:
        return f"❌ Terjadi kesalahan query flow: {str(e)}"

def get_broker_profile(broker_code: str, days: int = 20) -> str:
    """Mendapatkan statistik Agregat, Akumulasi, dan Distribusi sebuah Broker."""
    try:
        with engine.connect() as conn:
            agg_sql = text("""
                SELECT 
                    SUM(buy_val) as t_buy, 
                    SUM(sell_val) as t_sell, 
                    SUM(net_val) as t_net
                FROM broker_summary
                WHERE broker_code = :brk AND date >= CURRENT_DATE - :days * INTERVAL '1 day'
            """)
            df_agg = pd.read_sql(agg_sql, conn, params={"brk": broker_code, "days": days})
            
            t_buy = (df_agg['t_buy'].iloc[0] or 0) / 1_000_000_000_000
            t_sell = (df_agg['t_sell'].iloc[0] or 0) / 1_000_000_000_000
            t_net = (df_agg['t_net'].iloc[0] or 0) / 1_000_000_000_000
            status = "AKUMULASI" if t_net > 0 else "DISTRIBUSI"

            acc_sql = text("""
                SELECT ticker, SUM(net_vol) as net_vol, SUM(net_val) as net_val
                FROM broker_summary
                WHERE broker_code = :brk AND date >= CURRENT_DATE - :days * INTERVAL '1 day'
                GROUP BY ticker HAVING SUM(net_val) > 0
                ORDER BY net_val DESC LIMIT 5
            """)
            df_acc = pd.read_sql(acc_sql, conn, params={"brk": broker_code, "days": days})

            dist_sql = text("""
                SELECT ticker, SUM(net_vol) as net_vol, SUM(net_val) as net_val
                FROM broker_summary
                WHERE broker_code = :brk AND date >= CURRENT_DATE - :days * INTERVAL '1 day'
                GROUP BY ticker HAVING SUM(net_val) < 0
                ORDER BY net_val ASC LIMIT 5
            """)
            df_dist = pd.read_sql(dist_sql, conn, params={"brk": broker_code, "days": days})

        msg = f"🏢 *{broker_code} - Profil Broker*\nPeriode: {days} Hari Terakhir\n\n"
        msg += f"📊 *AGREGAT TRANSAKSI (All Market)*\n"
        msg += f"Total Buy  : {t_buy:.1f} T\nTotal Sell : {t_sell:.1f} T\nNet Status : {t_net:+.1f} T ({status})\n\n"

        msg += "🟢 *TOP 5 AKUMULASI*\n```text\n"
        msg += f"{'TICKER':<6} │ {'NET VOL':>9} │ {'VAL (B)':>8}\n"
        msg += "───────┼───────────┼──────────\n"
        if not df_acc.empty:
            for _, row in df_acc.iterrows():
                val_b = row['net_val'] / 1_000_000_000
                msg += f"{row['ticker']:<6} │ {int(row['net_vol']):>9,d} │ {val_b:>8,.1f}\n"
        else:
            msg += "Data Kosong\n"
        msg += "```\n"

        msg += "🔴 *TOP 5 DISTRIBUSI*\n```text\n"
        msg += f"{'TICKER':<6} │ {'NET VOL':>9} │ {'VAL (B)':>8}\n"
        msg += "───────┼───────────┼──────────\n"
        if not df_dist.empty:
            for _, row in df_dist.iterrows():
                val_b = row['net_val'] / 1_000_000_000
                msg += f"{row['ticker']:<6} │ {int(row['net_vol']):>9,d} │ {val_b:>8,.1f}\n"
        else:
            msg += "Data Kosong\n"
        msg += "```"

        return msg
    except Exception as e:
        return f"❌ Terjadi kesalahan query broker: {str(e)}"

def get_market_info(db: Session) -> str:
    now = datetime.now()
    
    jml_saham = db.query(Saham).count()
    papan_stats = db.query(Saham.papan_pencatatan, func.count(Saham.kode)).group_by(Saham.papan_pencatatan).all()
    
    harga_meta = db.execute(text("SELECT COUNT(*), MAX(tanggal) FROM harga_saham")).fetchone()
    broksum_meta = db.execute(text("SELECT COUNT(*), MAX(date) FROM broker_summary")).fetchone()
    
    jml_open = db.query(OpenPosition).count()
    jml_hist = db.query(TradeHistory).count()
    
    err_data = db.execute(text("""
        SELECT bot_name, COUNT(*) 
        FROM bot_error_logs 
        WHERE timestamp >= NOW() - INTERVAL '48 HOURS' 
        GROUP BY bot_name
    """)).fetchall()
    
    err_dict = {row[0]: row[1] for row in err_data}
    err_harv = err_dict.get('harvester_core', 0) + err_dict.get('harvester_scraper', 0) + err_dict.get('harvester_archiver', 0)
    err_pipe = err_dict.get('pipeline', 0)
    err_bndr = err_dict.get('bandar_satu_scheduler', 0)

    tgl_h = harga_meta[1]
    tgl_b = broksum_meta[1]
    
    ind_harga = "🟢" if tgl_h and (now.date() - tgl_h).days <= 4 else "🔴"
    ind_broksum = "🟢" if tgl_b and (now.date() - tgl_b).days <= 4 else "🔴"
    
    str_tgl_h = tgl_h.strftime('%Y-%m-%d') if tgl_h else "N/A"
    str_tgl_b = tgl_b.strftime('%Y-%m-%d') if tgl_b else "N/A"

    report_lines = [
        "*Update database*",
        f"Waktu Server: {now.strftime('%Y-%m-%d %H:%M:%S')}\n",
        "💾 *STATUS DATABASE*",
        f"• Daftar Saham   : {jml_saham:,} Emiten Aktif",
        "Distribusi Papan:"
    ]
    
    for papan, count in papan_stats:
        papan_name = papan if papan else "Tidak Diketahui"
        report_lines.append(f"└ {papan_name}: {count}")
        
    report_lines.append(f"• Harga Saham    : {harga_meta[0]:,} Baris (Update: {str_tgl_h}) {ind_harga}")
    report_lines.append(f"• Broker Summary : {broksum_meta[0]:,} Baris (Update: {str_tgl_b}) {ind_broksum}\n")
    
    report_lines.append("🤖 *STATUS BOT (Bandar Satu)*")
    report_lines.append(f"• Posisi Terbuka : {jml_open} Saham")
    report_lines.append(f"• Trade History  : {jml_hist:,} Transaksi Tertutup\n")
    
    report_lines.append("⚠️ *ERROR LOGS (48 Jam Terakhir)*")
    
    if err_harv > 0:
        report_lines.append(f"• Harvester      : {err_harv} Warning 🟡 (/err\_harvester)")
    else:
        report_lines.append("• Harvester      : 0 Error 🟢")
        
    if err_pipe > 0:
        report_lines.append(f"• Pipeline       : {err_pipe} Warning 🟡 (/err\_pipeline)")
    else:
        report_lines.append("• Pipeline       : 0 Error 🟢")
        
    if err_bndr > 0:
        report_lines.append(f"• Bandar Satu    : {err_bndr} Warning 🟡 (/err\_bandar)")
    else:
        report_lines.append("• Bandar Satu    : 0 Error 🟢")

    return "\n".join(report_lines)

def execute_readonly_sql(db: Session, sql_query: str) -> str:
    query_upper = sql_query.upper()
    forbidden_keywords = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE', 
        'CREATE', 'GRANT', 'REVOKE', 'EXECUTE', 'MERGE', 'CALL', 'REPLACE'
    ]
    
    for word in forbidden_keywords:
        if re.search(rf'\b{word}\b', query_upper):
            return f"❌ *Akses Ditolak:*\nKueri terdeteksi mengandung perintah destruktif (`{word}`). Sandbox ini murni *Read-Only* (SELECT)."

    if not query_upper.strip().startswith('SELECT') and not query_upper.strip().startswith('WITH'):
        return "❌ *Sintaks Invalid:*\nKueri wajib diawali dengan klausa `SELECT` atau `WITH`."

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(sql_query), conn)

        if df.empty:
            return "✅ *Execute Success*\nQuery dieksekusi tanpa error (0 rows return)."

        total_rows = len(df)
        
        # Limitasi tampilan 20 baris
        if total_rows > 20:
            df_display = df.head(20)
            status_text = f"✅ *Execute Success* (Menampilkan 20 dari total {total_rows} baris)"
        else:
            df_display = df
            status_text = f"✅ *Execute Success* ({total_rows} baris)"

        result_text = df_display.to_string(index=False)
        
        if len(result_text) > 3800:
            result_text = result_text[:3800] + "\n...[Teks terpotong limit Telegram]"

        return f"{status_text}\n```text\n{result_text}\n```"
        
    except Exception as e:
        return f"❌ *Fatal Error Eksekusi:*\n`{str(e)}`"
