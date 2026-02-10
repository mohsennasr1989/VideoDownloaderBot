import os
import logging
import asyncio
import yt_dlp
import shutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- تنظیمات ---
TOKEN = TOKEN = os.getenv('BOT_TOKEN')
# آدرس سایت شما در PythonAnywhere (مثلاً http://mohsen.pythonanywhere.com)
BASE_URL = os.getenv('BASE_URL', 'http://localhost') 
# مسیر پوشه استاتیک روی سرور
STATIC_PATH = os.path.join(os.getcwd(), 'static')

if not os.path.exists(STATIC_PATH):
    os.makedirs(STATIC_PATH)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 سلام محسن جان! لینک ویدیو رو بفرست.\nفایل‌ها در پوشه استاتیک ذخیره میشن و لینک مستقیم میگیری.")

async def clear_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پاکسازی تمام فایل‌های دانلود شده قبلی"""
    try:
        for filename in os.listdir(STATIC_PATH):
            file_path = os.path.join(STATIC_PATH, filename)
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
        await update.message.reply_text("✅ تمام فایل‌های قبلی با موفقیت پاک شدند.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در پاکسازی: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith("http"): return

    status_msg = await update.message.reply_text("🔍 در حال تحلیل لینک...")
    
    ydl_opts = {'nocheckcertificate': True, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            formats = [f for f in info.get('formats', []) if f.get('height') is not None]
            
            unique_formats = []
            seen = set()
            for f in sorted(formats, key=lambda x: x['height'], reverse=True):
                if f['height'] not in seen:
                    unique_formats.append(f)
                    seen.add(f['height'])

            context.user_data['url'] = url
            context.user_data['formats'] = unique_formats
            
            keyboard = [[InlineKeyboardButton(f"🎬 {f['height']}p ({f['ext']})", callback_data=f"idx_{i}")] 
                        for i, f in enumerate(unique_formats[:8])]
            
            await status_msg.edit_text(f"🎬 {info.get('title')[:50]}\nکیفیت را انتخاب کنید:", 
                                     reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await status_msg.edit_text(f"❌ خطا: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    idx = int(query.data.split('_')[1])
    selected = context.user_data['formats'][idx]
    url = context.user_data['url']
    
    # ایجاد نام فایل یکتا برای جلوگیری از تداخل
    file_id = query.id
    safe_name = f"video_{file_id}.mp4"
    output_path = os.path.join(STATIC_PATH, safe_name)

    await query.edit_message_text(f"🚀 شروع دانلود {selected['height']}p...\nفایل‌های موقت پس از تکمیل حذف می‌شوند.")

    ydl_opts = {
        'format': f"{selected['format_id']}+bestaudio/best",
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'nocheckcertificate': True,
        'nopart': False, # اجازه استفاده از فایل‌های .part برای پایداری
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await asyncio.to_thread(ydl.download, [url])
        
        # تولید لینک مستقیم
        download_link = f"{BASE_URL}/static/{safe_name}"
        await query.message.reply_text(
            f"✅ دانلود با موفقیت انجام شد!\n\n🔗 لینک دانلود مستقیم (تا قبل از پاکسازی معتبر است):\n{download_link}\n\n"
            f"🗑 برای پاکسازی سرور از دستور /clear استفاده کنید."
        )
    except Exception as e:
        await query.message.reply_text(f"❌ خطا در دانلود: {str(e)}")

if __name__ == '__main__':
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear_files))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.run_polling()