import os
import sys
import logging
import asyncio
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- تنظیمات ---
TOKEN = os.getenv('BOT_TOKEN')
BASE_URL = os.getenv('BASE_URL', 'https://google.com') 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- بررسی‌های اولیه (Fail Fast) ---
print("\n" + "!"*50)
print("🚀 STARTING FINAL BOT V3.0")

# 1. بررسی وجود Node.js
node_check = os.system("node -v")
if node_check != 0:
    print("❌ CRITICAL: Node.js is NOT installed!")
else:
    print("✅ Node.js is ready.")

# 2. بررسی فایل کوکی
COOKIE_FILE = 'youtube_cookies.txt'
if not os.path.exists(COOKIE_FILE):
    print(f"❌ CRITICAL: Cookie file '{COOKIE_FILE}' NOT found!")
    # فایل خالی می‌سازیم که ربات کرش نکند، ولی دانلود یوتیوب کار نخواهد کرد
    with open(COOKIE_FILE, 'w') as f: f.write("# Netscape HTTP Cookie File\n")
else:
    print(f"✅ Cookie file found: {os.path.abspath(COOKIE_FILE)}")
    # چک کردن فرمت فایل
    with open(COOKIE_FILE, 'r') as f:
        first_line = f.readline()
        if "Netscape" not in first_line and "#" not in first_line:
            print("⚠️ WARNING: Cookie file format might be wrong! Must be Netscape format.")

print("!"*50 + "\n")

if not TOKEN:
    sys.exit("❌ FATAL: BOT_TOKEN is missing.")

STATIC_PATH = os.path.join(os.getcwd(), 'static')
os.makedirs(STATIC_PATH, exist_ok=True)

# --- تنظیمات پیشرفته yt-dlp ---
def get_ydl_opts(download_mode=False):
    opts = {
        'quiet': True,
        'nocheckcertificate': True,
        'cookiefile': COOKIE_FILE,
        
        # --- حیاتی‌ترین بخش برای Koyeb ---
        'source_address': '0.0.0.0',  # اجبار به استفاده از IPv4 (حل مشکل بلاک یوتیوب)
        'force_ipv4': True,
        
        # استفاده از کلاینت اندروید (پایدارترین حالت)
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'player_skip': ['js', 'configs', 'webpage'],
            }
        },
    }
    
    if download_mode:
        opts.update({
            'nopart': False,
            'merge_output_format': 'mp4',
        })
    
    return opts

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ربات نهایی آماده است. لینک بده!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith("http"): return

    msg = await update.message.reply_text("⏳ در حال بررسی (Force IPv4)...")
    
    try:
        # مرحله اول: گرفتن اطلاعات
        ydl_opts = get_ydl_opts(download_mode=False)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            formats = [f for f in info.get('formats', []) if f.get('height')]
            unique_formats = []
            seen = set()
            # سورت کردن و حذف تکراری‌ها
            for f in sorted(formats, key=lambda x: x['height'] if x['height'] else 0, reverse=True):
                h = f['height']
                if h and h not in seen:
                    unique_formats.append(f)
                    seen.add(h)

            context.user_data['url'] = url
            context.user_data['formats'] = unique_formats
            context.user_data['title'] = info.get('title', 'video')
            
            keyboard = []
            for i, f in enumerate(unique_formats[:5]): # فقط 5 کیفیت اول
                keyboard.append([InlineKeyboardButton(f"📥 {f['height']}p", callback_data=f"dl_{i}")])
            
            await msg.edit_text(f"🎥 **{info.get('title')}**\n\nکیفیت را انتخاب کن:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            
    except Exception as e:
        error = str(e)
        logger.error(error)
        if "Sign in" in error:
            await msg.edit_text("❌ خطا: فایل کوکی منقضی شده یا نامعتبر است.")
        elif "n challenge" in error:
            await msg.edit_text("❌ خطا: مشکل JS هنوز پابرجاست (عجیب است!).")
        else:
            await msg.edit_text(f"❌ خطا: {error[:200]}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    idx = int(query.data.split('_')[1])
    fmt = context.user_data['formats'][idx]
    url = context.user_data['url']
    
    await query.edit_message_text(f"🚀 در حال دانلود {fmt['height']}p...")
    
    safe_title = "".join([c for c in context.user_data.get('title', 'vid') if c.isalnum()])[:15]
    filename = f"{safe_title}_{fmt['height']}p.mp4"
    output_path = os.path.join(STATIC_PATH, filename)

    try:
        ydl_opts = get_ydl_opts(download_mode=True)
        ydl_opts['format'] = f"{fmt['format_id']}+bestaudio/best"
        ydl_opts['outtmpl'] = output_path
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await asyncio.to_thread(ydl.download, [url])
            
        dl_link = f"{BASE_URL}/{filename}"
        await query.message.reply_text(f"✅ دانلود تکمیل شد!\n\n🔗 [لینک دانلود]({dl_link})", parse_mode='Markdown')
        
    except Exception as e:
        await query.message.reply_text(f"❌ خطا در دانلود نهایی: {str(e)}")

if __name__ == '__main__':
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.run_polling()