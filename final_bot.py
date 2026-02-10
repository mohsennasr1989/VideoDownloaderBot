import os
import sys
import logging
import asyncio
import threading
import shutil
from http.server import HTTPServer, SimpleHTTPRequestHandler
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- تنظیمات ---
TOKEN = os.getenv('BOT_TOKEN')
# نکته: آدرس اپلیکیشن در کویب را اینجا بگذارید (بدون اسلش آخر)
# مثال: https://my-bot-name.koyeb.app
BASE_URL = os.getenv('BASE_URL', 'https://google.com') 
PORT = int(os.getenv('PORT', 8000))

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# مسیر ذخیره فایل‌ها
STATIC_DIR = os.path.join(os.getcwd(), 'static')
os.makedirs(STATIC_DIR, exist_ok=True)

# --- سرور وب واقعی (برای دانلود فایل) ---
class RealFileHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # ریشه سرور را پوشه static قرار می‌دهیم
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        # اگر درخواست Health Check بود
        if self.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return
        
        # در غیر این صورت فایل را دانلود کن
        return super().do_GET()

def start_web_server():
    # سرور را روی پورت 8000 اجرا می‌کنیم
    server = HTTPServer(('0.0.0.0', PORT), RealFileHandler)
    print(f"✅ File Server & Health Check running on port {PORT}")
    print(f"📂 Serving files from: {STATIC_DIR}")
    server.serve_forever()

# --- تنظیمات yt-dlp (بدون کوکی) ---
def get_ydl_opts(download_mode=False):
    opts = {
        'quiet': True,
        'nocheckcertificate': True,
        # کوکی را حذف کردیم چون باعث بلاک شدن می‌شود
        'source_address': '0.0.0.0', 
        
        # اجازه به IPv6 (حیاتی برای عبور از تحریم یوتیوب در دیتاسنتر)
        'force_ipv4': False,
        
        # کلاینت اندروید بدون کوکی معمولا بهتر جواب می‌دهد
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'player_skip': ['configs', 'webpage'],
            }
        },
    }
    
    if download_mode:
        opts.update({
            'nopart': True, # دانلود یک‌تکه برای جلوگیری از فایل‌های ناقص
            'outtmpl': '%(title)s.%(ext)s',
            # محدود کردن کیفیت برای جلوگیری از کرش کردن سرور (OOM)
            'format': 'best[ext=mp4]/best',
        })
    
    return opts

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ربات آماده است! (نسخه پایدار)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith("http"): return

    msg = await update.message.reply_text("⏳ در حال بررسی...")
    
    try:
        # پاکسازی فایل‌های قدیمی برای آزاد کردن فضا
        clean_static_folder()

        ydl_opts = get_ydl_opts(download_mode=False)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            except Exception as e:
                # اگر باز هم ارور داد، تلاش با کلاینت iOS
                logger.warning(f"First attempt failed: {e}. Trying iOS fallback...")
                ydl_opts['extractor_args']['youtube']['player_client'] = ['ios']
                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                    info = await asyncio.to_thread(ydl2.extract_info, url, download=False)

            # استخراج فرمت‌ها
            formats = info.get('formats', [])
            # فیلتر کردن فرمت‌های خیلی حجیم که سرور را می‌کشند
            valid_formats = []
            seen_heights = set()
            
            for f in sorted(formats, key=lambda x: x.get('height', 0) or 0, reverse=True):
                h = f.get('height')
                # فقط کیفیت‌های زیر 1080 را پیشنهاد بده (سرور رایگان کشش 4K ندارد)
                if h and h <= 1080 and h not in seen_heights:
                    valid_formats.append(f)
                    seen_heights.add(h)

            context.user_data['url'] = url
            context.user_data['formats'] = valid_formats
            context.user_data['title'] = info.get('title', 'video')
            
            keyboard = []
            for i, f in enumerate(valid_formats[:5]): 
                keyboard.append([InlineKeyboardButton(f"📥 {f['height']}p (MP4)", callback_data=f"dl_{i}")])
            
            await msg.edit_text(f"🎥 **{info.get('title')}**\n\nکیفیت را انتخاب کن:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            
    except Exception as e:
        logger.error(str(e))
        await msg.edit_text(f"❌ خطا: {str(e)[:200]}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    idx = int(query.data.split('_')[1])
    try:
        fmt = context.user_data['formats'][idx]
        url = context.user_data['url']
        original_title = context.user_data.get('title', 'video')
        
        await query.edit_message_text(f"🚀 در حال دانلود {fmt['height']}p...\n(ممکن است کمی طول بکشد)")
        
        # ایمن‌سازی نام فایل
        safe_title = "".join([c for c in original_title if c.isalnum() or c in [' ', '-', '_']]).strip()[:50]
        filename = f"{safe_title}_{fmt['height']}p.mp4"
        output_path = os.path.join(STATIC_DIR, filename)

        ydl_opts = get_ydl_opts(download_mode=True)
        # دانلود فرمت انتخاب شده + تبدیل صدا اگر لازم بود
        ydl_opts['format'] = f"{fmt['format_id']}+bestaudio/best"
        ydl_opts['outtmpl'] = output_path
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await asyncio.to_thread(ydl.download, [url])
            
        # ساخت لینک دانلود
        # اگر BASE_URL ست نشده باشد، لینک لوکال بی معنی است اما برای تست می‌گذاریم
        dl_link = f"{BASE_URL}/{filename}"
        
        await query.message.reply_text(
            f"✅ **دانلود تکمیل شد!**\n\n"
            f"📂 نام فایل: {filename}\n"
            f"🔗 [برای دانلود کلیک کنید]({dl_link})\n\n"
            f"⚠️ لینک تا دقایقی دیگر منقضی می‌شود.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(str(e))
        await query.message.reply_text(f"❌ خطا در دانلود: {str(e)}")

def clean_static_folder():
    """پاک کردن فایل‌های قدیمی برای جلوگیری از پر شدن دیسک"""
    try:
        for filename in os.listdir(STATIC_DIR):
            file_path = os.path.join(STATIC_DIR, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
    except Exception as e:
        logger.error(f"Error cleaning static folder: {e}")

if __name__ == '__main__':
    # اجرای وب‌سرور در ترد جداگانه
    server_thread = threading.Thread(target=start_web_server, daemon=True)
    server_thread.start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.run_polling()