FROM python:3.10-slim

# نصب Node.js نسخه 20 (حیاتی برای یوتیوب)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# دستور اجرا
CMD ["python", "main_bot.py"]