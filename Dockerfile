# استفاده از ایمیج آماده که هم پایتون داره هم Node.js
FROM nikolaik/python-nodejs:python3.10-nodejs20

# نصب FFmpeg (برای چسباندن صدا و تصویر)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# کپی و نصب نیازمندی‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی بقیه فایل‌ها
COPY . .

# دستور اجرا
CMD ["python", "main_bot.py"]