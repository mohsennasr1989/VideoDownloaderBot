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

# تنظیم لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- تست حیاتی اجرا ---
print("\n" + "#"*50)
print("🚀 SYSTEM REBOOT: EXECUTION STARTED SUCCESSFULLY")
print(f"📂 Current Directory: {os.getcwd()}")
print(f"🍪 Looking for cookies at: {os.path.join(os.getcwd(), 'youtube_cookies.txt')}")
print("#"*50 + "\n")

if not TOKEN:
    print("❌ CRITICAL ERROR: BOT_TOKEN is missing!")
    sys.exit(1)

STATIC_PATH = os.path.join(os.getcwd(), 'static')
if not os.path.exists(STATIC_PATH):
    os.makedirs(STATIC_PATH)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ربات با سیستم جدید آماده است! لینک بفرست.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith("http"): return

    msg = await update.message.reply_text("🔍 در حال آنالیز لینک...")
    
    # تنظیمات استخراج اطلاعات
    ydl_opts = {
        'quiet': True,
        'nocheckcertificate': True,
        'cookiefile': 'youtube_cookies.txt', # بازگشت به کوکی
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            formats = [f for f in info.get('formats', []) if f.get('height')]
            
            unique_formats = []
            seen = set()
            for f in sorted(formats, key=lambda x: x['height'], reverse=True):
                if f['height'] not in seen:
                    unique_formats.append(f)
                    seen.add(f['height'])

            context.user_data['url'] = url
            context.user_data['formats'] = unique_formats
            
            keyboard = [[InlineKeyboardButton(f"🎬 {f['height']}p", callback_data=f"idx_{i}")] 
                        for i, f in enumerate(unique_formats[:6])]
            
            await msg.edit_text(f"🎬 {info.get('title')}\nکیفیت را انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))
            
    except Exception as e:
        await msg.edit_text(f"❌ خطا: {str(e)}")
        print(f"ERROR: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    idx = int(query.data.split('_')[1])
    fmt = context.user_data['formats'][idx]
    url = context.user_data['url']
    
    await query.edit_message_text(f"🚀 شروع دانلود {fmt['height']}p...")
    
    filename = f"vid_{query.id}.mp4"
    output_path = os.path.join(STATIC_PATH, filename)

    ydl_opts = {
        'format': f"{fmt['format_id']}+bestaudio/best",
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'nocheckcertificate': True,
        'cookiefile': 'youtube_cookies.txt', # استفاده از کوکی
        'nopart': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await asyncio.to_thread(ydl.download, [url])
        
        dl_link = f"{BASE_URL}/{filename}"
        await query.message.reply_text(f"✅ دانلود شد:\n{dl_link}")
        
    except Exception as e:
        await query.message.reply_text(f"❌ خطا در دانلود: {e}")

if __name__ == '__main__':
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.run_polling()