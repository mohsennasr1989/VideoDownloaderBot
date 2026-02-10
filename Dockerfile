FROM python:3.10-slim

# نصب ffmpeg برای میکس کردن صدا و تصویر
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# اجرای ربات
CMD ["python", "test_tlgrm_bot.py"]