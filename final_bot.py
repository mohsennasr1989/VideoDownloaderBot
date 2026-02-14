import os
import sys
import logging
import asyncio
import threading
import uuid  # برای تولید اسم فایل رندوم
from http.server import HTTPServer, SimpleHTTPRequestHandler
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- تنظیمات ---
TOKEN = os.getenv('BOT_TOKEN')
# آدرس دقیق اپلیکیشن خود را اینجا بگذارید (بدون اسلش آخر)
BASE_URL = os.getenv('BASE_URL', 'https://koyeb.app').rstrip('/')
PORT = int(os.getenv('PORT', 8000))

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.getcwd(), 'static')
os.makedirs(STATIC_DIR, exist_ok=True)

# --- سرور دانلود فایل ---
class FileHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        # هندل کردن Health Check برای زنده ماندن در Koyeb
        if self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            # دانلود فایل واقعی
            super().do_GET()

def start_web_server():
    server = HTTPServer(('0.0.0.0', PORT), FileHandler)
    print(f"✅ File Server running on port {PORT}")
    server.serve_forever()

# --- تنظیمات yt-dlp ---
def get_ydl_opts(download_mode=False, filename_id=None):
    opts = {
        'quiet': True,
        'nocheckcertificate': True,
        'source_address': '0.0.0.0', # اجازه استفاده از IPv6
        
        # --- استراتژی ضد تحریم (Embedded) ---
        # این کلاینت وانمود می‌کند ویدیو در یک سایت دیگر پخش می‌شود
        # و معمولاً حساسیت کمتری روی IP سرور دارد
        'extractor_args': {
            'youtube': {
                'player_client': ['web_embedded', 'web'],
                'player_skip': ['configs', 'webpage'],
            }
        },
    }
    
    if download_mode and filename_id:
        opts.update({
            'nopart': True,
            # اسم فایل را دقیقاً همان ID که ساختیم می‌گذاریم
            # این کار مشکل 404 و کاراکترهای عجیب را حل می‌کند
            'outtmpl': os.path.join(STATIC_DIR, f"{filename_id}.%(ext)s"),
            'format': 'best[ext=mp4]/best',
        })
    
    return opts

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ربات آماده است. لینک بفرست.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith("http"):
        await update.message.reply_text("ربات آماده است. لینک بفرست.")
        return


    msg = await update.message.reply_text("⏳ ...")
    
    try:
        # پاکسازی فایل‌های قدیمی
        for f in os.listdir(STATIC_DIR):
            try: os.remove(os.path.join(STATIC_DIR, f))
            except: pass

        ydl_opts = get_ydl_opts(download_mode=False)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            except Exception as e:
                # اگر Embedded جواب نداد، تلاش با iOS (بدون کوکی)
                logger.warning(f"Embedded failed: {e}. Trying iOS...")
                ydl_opts['extractor_args']['youtube']['player_client'] = ['ios']
                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                    info = await asyncio.to_thread(ydl2.extract_info, url, download=False)

            formats = [f for f in info.get('formats', []) if f.get('height')]
            unique_formats = []
            seen = set()
            for f in sorted(formats, key=lambda x: x.get('height', 0), reverse=True):
                h = f.get('height')
                # محدودیت 720p برای جلوگیری از پر شدن رم سرور و دانلود سریع‌تر
                if h and h <= 720 and h not in seen:
                    unique_formats.append(f)
                    seen.add(h)

            context.user_data['url'] = url
            context.user_data['formats'] = unique_formats
            # عنوان را فقط برای نمایش نگه می‌داریم، نه برای اسم فایل
            context.user_data['title'] = info.get('title', 'Video')
            context.user_data['uploader'] = info.get('uploader', 'Uploader')
            
            keyboard = []
            for i, f in enumerate(unique_formats[:5]): 
                keyboard.append([InlineKeyboardButton(f"📥 {f['height']}p", callback_data=f"dl_{i}")])
            
            await msg.edit_text(f"🎥 **{info.get('title')}**", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            
    except Exception as e:
        logger.error(str(e))
        error_msg = str(e)
        if "Sign in" in error_msg:
             await msg.edit_text("❌ خطا: گوگل آی‌پی سرور را مسدود کرده است. فعلاً راهی برای دانلود این ویدیو از سرور نیست.")
        else:
             await msg.edit_text(f"❌ خطا: {error_msg[:100]}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    idx = int(query.data.split('_')[1])
    try:
        fmt = context.user_data['formats'][idx]
        url = context.user_data['url']
        
        # تولید اسم فایل کاملاً تصادفی و امن (حل مشکل 404)
        file_id = str(uuid.uuid4())[:8]
        
        await query.edit_message_text(f"🚀 دانلود {fmt['height']}p...")
        
        # ارسال file_id به تنظیمات
        ydl_opts = get_ydl_opts(download_mode=True, filename_id=file_id)
        ydl_opts['format'] = f"{fmt['format_id']}+bestaudio/best"
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await asyncio.to_thread(ydl.download, [url])
            
        # ساخت لینک دانلود با اسم فایل رندوم
        filename = f"{file_id}.mp4"
        dl_link = f"{BASE_URL}/{filename}"
        
        await query.message.reply_text(
            f"✅ دانلود انجام شد!\n\n"
            f"\n"
            f"🔗 {context.user_data['title']} - {context.user_data['uploader']} ({dl_link})\n\n"
            f"⚠️ نکته: لینک برای دانلود مستقیم است.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(str(e))
        await query.message.reply_text("❌ خطا در دانلود.")

if __name__ == '__main__':
    server_thread = threading.Thread(target=start_web_server, daemon=True)
    server_thread.start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.run_polling()