import nest_asyncio
nest_asyncio.apply()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import yt_dlp
from pathlib import Path
from flask import Flask
from threading import Thread
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os

# ----------------- TOKEN -----------------
TOKEN = os.getenv("TOKEN")  # Railway-də environment variable təyin et

user_selection = {}
pagination_data = {}
VIDEOS_PER_PAGE = 10
executor = ThreadPoolExecutor(max_workers=2)
user_language = {}

# ----------------- Mesajlar -----------------
MESSAGES = {
    "choose_lang": {"az": "Dil seçin:", "en": "Choose your language:", "ru": "Выберите язык:"},
    "start": {
        "az": "Salam {first_name}! 🎵\nMahnı adı / Müğənni adı göndərin...\nYouTube link / playlist göndərə bilərsiniz.",
        "en": "Hi {first_name}! 🎵\nSend me: Song name / Singer name\nYou can also send a YouTube link / playlist.",
        "ru": "Привет {first_name}! 🎵\nОтправь мне: Название песни / Имя исполнителя\nМожно также ссылку на YouTube / плейлист."
    },
    "searching": {"az": "🔎 YouTube-da axtarılır...", "en": "🔎 Searching on YouTube...", "ru": "🔎 Поиск на YouTube..."},
    "no_results": {"az": "⚠️ Nəticə tapılmadı.", "en": "⚠️ No results found.", "ru": "⚠️ Результаты не найдены."},
    "choose_format": {"az": "Formatı seçin:", "en": "Choose format:", "ru": "Выберите формат:"},
    "downloading": {"az": "⏳ {format} formatında yüklənir...", "en": "⏳ Downloading as {format}...", "ru": "⏳ Загрузка в формате {format}..."},
    "selected": {"az": "✅ Seçildi: {title}", "en": "✅ Selected: {title}", "ru": "✅ Выбрано: {title}"},
    "no_selection": {"az": "⚠️ Heç bir video seçilməyib.", "en": "⚠️ No videos selected.", "ru": "⚠️ Видео не выбрано."},
    "stats": {"az": "👥 İstifadəçilər: {users}\n🎵 Yükləmələr: {downloads}", "en": "👥 Users: {users}\n🎵 Downloads: {downloads}", "ru": "👥 Пользователи: {users}\n🎵 Загрузки: {downloads}"}
}

# ----------------- Flask server -----------------
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ----------------- User statistikası -----------------
USERS_FILE = Path("users.json")
if USERS_FILE.exists():
    with open(USERS_FILE, "r") as f:
        users = json.load(f)
else:
    users = {}

def add_user(chat_id, username, first_name):
    chat_id_str = str(chat_id)
    if chat_id_str not in users:
        users[chat_id_str] = {"username": username, "first_name": first_name, "downloads": 0}
        save_users()

def increment_download(chat_id):
    chat_id_str = str(chat_id)
    if chat_id_str in users:
        users[chat_id_str]["downloads"] += 1
        save_users()

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

# ----------------- Progress Hook -----------------
def progress_hook_factory(chat_id, context, last_percent=[0]):
    def hook(d):
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            percent = int(downloaded / total * 100)
            if percent - last_percent[0] >= 10:
                asyncio.run_coroutine_threadsafe(
                    context.bot.send_message(chat_id=chat_id, text=f"⬇️ Downloading: {percent}%"),
                    asyncio.get_event_loop())
                last_percent[0] = percent
    return hook

# ----------------- Asynchronous download -----------------
async def download_video_async(url, chat_id, context, selected_format):
    loop = asyncio.get_event_loop()
    ffmpeg_path = "/usr/bin/ffmpeg"  # Railway-də default path, dəyişə bilər

    if selected_format == "mp3":
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f"{chat_id}_%(title)s.%(ext)s",
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'}],
            'quiet': True,
            'noplaylist': True,
            'socket_timeout': 1200,
            'retries': 10,
            'progress_hooks': [progress_hook_factory(chat_id, context)],
            'ffmpeg_location': ffmpeg_path
        }

    def ytdlp_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if selected_format == "mp3":
                return Path(f"{chat_id}_{info['title']}.mp3")
            return Path(ydl.prepare_filename(info))

    file_name = await loop.run_in_executor(executor, ytdlp_download)

    with open(file_name, "rb") as f:
        if selected_format == "mp3":
            await context.bot.send_audio(chat_id=chat_id, audio=f)
        else:
            await context.bot.send_video(chat_id=chat_id, video=f)

    Path(file_name).unlink()

# ----------------- Bot funksiyaları -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    buttons = [
        [InlineKeyboardButton("🇦🇿 Azərbaycan", callback_data="lang_az")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")]
    ]
    await update.message.reply_text("Choose your language / Dil seçin / Выберите язык:",
                                    reply_markup=InlineKeyboardMarkup(buttons))

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    lang = query.data.split("_")[1]
    user_language[chat_id] = lang
    await query.answer()
    first_name = query.from_user.first_name
    add_user(chat_id, query.from_user.username, first_name)
    await query.message.reply_text(MESSAGES["start"][lang].format(first_name=first_name))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    lang = user_language.get(chat_id, "en")
    total_users = len(users)
    total_downloads = sum(user["downloads"] for user in users.values())
    msg = MESSAGES["stats"][lang].format(users=total_users, downloads=total_downloads)
    await update.message.reply_text(msg)

# ----------------- Run Bot -----------------
def run_bot():
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("stats", stats))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: asyncio.create_task(search_song(u,c))))
    app_bot.add_handler(CallbackQueryHandler(lambda u,c: asyncio.create_task(handle_selection(u,c))))
    print("✅ Bot is running...")
    app_bot.run_polling()

if __name__ == "__main__":
    keep_alive()
    run_bot()
