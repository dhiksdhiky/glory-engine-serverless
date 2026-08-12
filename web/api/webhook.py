import os
import sys
import json
import asyncio
from http.server import BaseHTTPRequestHandler
import re
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from sqlalchemy import text

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from lib.database import SessionLocal
from lib.sync_service import process_saham_excel
from lib.query_service import (
    get_open_positions_split, 
    get_trade_history_summary, 
    get_ticker_analysis, 
    get_market_info,
    execute_readonly_sql,
    get_radar_hmb,
    get_broker_profile,
    get_market_flow
)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELE_BOT_DHIKSDHIKY")
TELEGRAM_CHAT_ID = os.getenv("TELE_CHAT_ID_DHIKA")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Environment variables Telegram tidak diset.")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def post_init_callback(application: Application):
    startup_msg = (
        "🤖 *Glory Comm-Link [ONLINE]*\n\n"
        "Sistem Pusat Rekapitulasi & Komando telah aktif.\n"
        "Status Infrastruktur: Normal 🟢\n\n"
        "*Menu Analitik & Konfigurasi:*\n"
        "🔹 `/hmb` - Radar Harga Modal Bandar (HMB) Top 20\n"
        "🔹 `/flow [hari]` - Market Inflow/Outflow (Default: 5)\n"
        "🔹 `/open` - Portofolio Aktif (Sinyal Baru & Top/Bot 10)\n"
        "🔹 `/history` - Histori Trade Tertutup (Top/Bot 5)\n"
        "🔹 `/[KODE]` - (Cth: `/BBCA`) Profil & Rekam Jejak Detail\n"
        "🔹 `/[BROKER] [hari]` - (Cth: `/AK 20`) Analitik Profil Broker\n"
        "🔹 `/info` - Ringkasan Database & Status Worker\n"
        "🔹 `/sql [query]` - Konsol eksekusi Raw SQL (Read-Only)\n"
        "🔹 `/update` - Masuk mode siaga Sinkronisasi Excel IDX\n"
    )
    try:
        await application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=startup_msg, parse_mode='Markdown')
        logger.info("Startup notification sent.")
    except Exception as e:
        logger.error(f"Gagal mengirim notifikasi startup: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
    await post_init_callback(context.application)

async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
    context.user_data['awaiting_excel'] = True
    await update.message.reply_text("🟢 *Mode Siaga Update Aktif*\nSilakan kirim dokumen `.xlsx`.", parse_mode='Markdown')

async def sql_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengeksekusi Raw SQL langsung dari baris command."""
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
    
    raw_query = " ".join(context.args).strip()
    
    if not raw_query:
        await update.message.reply_text(
            "⚠️ *Penggunaan Salah*\n"
            "Gunakan format satu baris:\n"
            "`/sql SELECT ticker, close FROM harga_saham LIMIT 5;`", 
            parse_mode='Markdown'
        )
        return

    status_msg = await update.message.reply_text("⏳ Memproses kueri SQL...")
    db = SessionLocal()
    try:
        result_msg = execute_readonly_sql(db, raw_query)
        await status_msg.edit_text(result_msg, parse_mode='Markdown')
    except Exception as e:
        await status_msg.edit_text(f"❌ *Kesalahan Database:*\n`{str(e)}`", parse_mode='Markdown')
    finally:
        db.close()

async def flow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
    try:
        days = int(context.args[0]) if context.args else 5
    except ValueError:
        await update.message.reply_text("⚠️ Argumen hari harus berupa angka. Contoh: `/flow 10`", parse_mode='Markdown')
        return
    
    try:
        report = get_market_flow(days)
        await update.message.reply_text(report, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: `{str(e)}`", parse_mode='Markdown')

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
    db = SessionLocal()
    try:
        reports = get_open_positions_split(db)
        await update.message.reply_text(reports["new"], parse_mode='Markdown')
        if reports["all"]:
            await update.message.reply_text(reports["all"], parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: `{str(e)}`", parse_mode='Markdown')
    finally:
        db.close()

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
    db = SessionLocal()
    try:
        report = get_trade_history_summary(db)
        await update.message.reply_text(report, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: `{str(e)}`", parse_mode='Markdown')
    finally:
        db.close()

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
    db = SessionLocal()
    try:
        report = get_market_info(db)
        await update.message.reply_text(report, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: `{str(e)}`", parse_mode='Markdown')
    finally:
        db.close()

async def hmb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
    db = SessionLocal()
    try:
        results = get_radar_hmb(db)
        if not results:
            await update.message.reply_text("Data belum mencukupi untuk radar HMB.")
            return

        tgl_akhir = db.execute(text("SELECT MAX(tanggal) FROM harga_saham")).scalar()
        
        msg = "🎯 *Radar Harga Modal Bandar (HMB) - 20 hari*\n"
        msg += "Filter: HMB > Harga (Maks -3%), Vol > 10K\n"
        msg += f"Tanggal: {tgl_akhir.strftime('%Y-%m-%d') if tgl_akhir else 'N/A'}\n\n"
        msg += "```text\n"
        msg += "KODE │ HARGA │   HMB │ RISK% │ TOP BRK\n"
        msg += "─────┼───────┼───────┼───────┼────────\n"
        
        for r in results:
            msg += f"{r.kode:<4} │ {r.harga:>5,.0f} │ {r.hmb:>5,.0f} │ {r.pct_diff:>+5.1f} │ {r.brokers}\n"
        
        msg += "```"
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
    finally:
        db.close()

def err_check_generator(bot_filter):
    async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
        db = SessionLocal()
        try:
            sql = text(f"""
                SELECT timestamp, error_level, ticker, error_message 
                FROM bot_error_logs 
                WHERE bot_name LIKE :bot_filter AND timestamp >= NOW() - INTERVAL '48 HOURS'
                ORDER BY timestamp DESC LIMIT 5
            """)
            errors = db.execute(sql, {"bot_filter": f"%{bot_filter}%"}).fetchall()
            
            if not errors:
                await update.message.reply_text(f"✅ Tidak ada error log terbaru untuk {bot_filter}.")
                return
                
            msg = f"⚠️ *Log Error Terbaru ({bot_filter.upper()})*\n\n"
            for e in errors:
                t_str = e.timestamp.strftime('%H:%M:%S')
                tkr = f"[{e.ticker}] " if e.ticker else ""
                msg += f"• `{t_str}` | {e.error_level} {tkr}\n`{e.error_message}`\n\n"
                
            await update.message.reply_text(msg, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        finally:
            db.close()
    return check_command

err_harvester_cmd = err_check_generator('harvester')
err_pipeline_cmd = err_check_generator('pipeline')
err_bandar_cmd = err_check_generator('bandar_satu')

async def dynamic_ticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani request 4 Karakter (Saham) atau 2 Karakter (Broker)"""
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
    
    text_input = update.message.text
    command_parts = text_input.split()
    command_str = command_parts[0].split('@')[0][1:].upper()
    
    # Deteksi 4 Karakter -> Analitik Saham
    if re.match(r'^[A-Z]{4}$', command_str):
        db = SessionLocal()
        try:
            report = get_ticker_analysis(db, command_str)
            await update.message.reply_text(report, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Error Analitik {command_str}: `{str(e)}`", parse_mode='Markdown')
        finally:
            db.close()
        return

    # Deteksi 2 Karakter -> Profil Broker
    if re.match(r'^[A-Z]{2}$', command_str):
        days = 20
        if len(command_parts) > 1 and command_parts[1].isdigit():
            days = int(command_parts[1])
            
        try:
            report = get_broker_profile(command_str, days)
            await update.message.reply_text(report, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Error Profil Broker {command_str}: `{str(e)}`", parse_mode='Markdown')
        return

    await update.message.reply_text("❌ Perintah tidak dikenal. (Gunakan 4 huruf untuk saham atau 2 huruf untuk broker)")

async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Dikosongkan karena mode interaktif raw text SQL dihapus
    return

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID): return
    if not context.user_data.get('awaiting_excel', False):
        await update.message.reply_text("⚠️ Akses ditolak. Kirim `/update` terlebih dahulu.")
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith('.xlsx'):
        await update.message.reply_text("❌ Format ditolak. Kirim ekstensi .xlsx.")
        return

    status_msg = await update.message.reply_text("⏳ Memproses Bulk Insert...")
    try:
        telegram_file = await context.bot.get_file(doc.file_id)
        file_bytes = await telegram_file.download_as_bytearray()
        db = SessionLocal()
        try:
            metrics = process_saham_excel(db, bytes(file_bytes), doc.file_name)
            await status_msg.edit_text(f"✅ *Bulk Replace Sukses*\n📅 `{metrics['tanggal_update']}`\n📊 Total: `{metrics['total_active']}`", parse_mode='Markdown')
            context.user_data['awaiting_excel'] = False
        finally:
            db.close()
    except Exception as e:
        await status_msg.edit_text(f"❌ *Error:*\n`{str(e)}`", parse_mode='Markdown')
        context.user_data['awaiting_excel'] = False

# Inisialisasi PTB Application (Global stateless singleton untuk webhook)
app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("update", update_command))
app.add_handler(CommandHandler("open", open_command))
app.add_handler(CommandHandler("history", history_command))
app.add_handler(CommandHandler("info", info_command))
app.add_handler(CommandHandler("sql", sql_command))
app.add_handler(CommandHandler("hmb", hmb_command))
app.add_handler(CommandHandler("flow", flow_command))

app.add_handler(CommandHandler("err_harvester", err_harvester_cmd))
app.add_handler(CommandHandler("err_pipeline", err_pipeline_cmd))
app.add_handler(CommandHandler("err_bandar", err_bandar_cmd))

app.add_handler(MessageHandler(filters.COMMAND, dynamic_ticker_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_handler))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

# Vercel Handler Class
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            update_data = json.loads(post_data.decode('utf-8'))
            update = Update.de_json(update_data, app.bot)
            
            # Initialize & process update within single event loop (Vercel max 10s execution)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def handle_update():
                try:
                    await app.initialize()
                except RuntimeError:
                    pass # Already initialized in Vercel warm container
                
                await app.process_update(update)
                
                # Await pending background tasks before returning HTTP 200
                # because Vercel freezes the container immediately after return.
                pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                if pending:
                    await asyncio.wait(pending)
            
            loop.run_until_complete(handle_update())
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        except Exception as e:
            logger.error(f"Error processing update: {e}")
            self.send_response(500)
            self.end_headers()
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Glory Comm-Link Vercel Webhook is online.')
