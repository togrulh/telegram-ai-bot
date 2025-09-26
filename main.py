# main.py

import nest_asyncio
nest_asyncio.apply()

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from flask import Flask, request
import os
import yt_dlp
import ffmpeg

# Telegram bot token
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # Railway-də environment variable kimi təyin et

# Flask app
app = Flask(__name__)

# Komanda handler-ları
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salam! Bot işləyir.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sadəcə YouTube linkini göndərin və mp3/mp4 seçin.")

# Mesaj handler
async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    await update.message.reply_text("Yüklənir, zəhmət olmasa gözləyin...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        await update.message.reply_text(f"Yükləndi: {filename}")
    except Exception as e:
        await update.message.reply_text(f"Xəta baş verdi: {e}")

# Telegram bot run
def run_bot():
    application = ApplicationBuilder().token(TOKEN).build()

    # Handler-ları əlavə et
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_handler))

    # Botu polling ilə işə sal
    application.run_polling()

# Flask route (Health check və ya webhook üçün istifadə edilə bilər)
@app.route("/")
def index():
    return "Bot işləyir!"

# Railway üçün həm Flask, həm bot eyni prosesdə işləsin
if __name__ == "__main__":
    from threading import Thread

    # Botu ayrı thread-də işə sal
    bot_thread = Thread(target=run_bot)
    bot_thread.start()

    # Flask app
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
