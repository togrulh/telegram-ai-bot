import os
import json
import asyncio
from pathlib import Path
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)
import yt_dlp

# ----------------- TOKEN -----------------
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("⚠️ TOKEN environment variable not set!")

# ----------------- GLOBALS -----------------
user_language = {}
users_file = Path("users.json")
VIDEOS_PER_PAGE = 10
executor = ThreadPoolExecutor(max_workers=2)

# Load users
if users_file.exists():
    with open(users_file, "r") as f:
        users = json.load(f)
else:
    users = {}

# ----------------- MESSAGES -----------------
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
    "stats": {"az": "👥 İstifadəçilər: {users}\n🎵 Yükləmələr: {downloads}",
              "en": "👥 Users: {users}\n🎵 Downloads: {downloads}",
              "ru": "👥 Пользователи: {users}\n🎵 Загрузки: {downloads}"}
}

# ----------------- FLASK SERVER -----------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    Thread(target=lambda: app.run(host="0.0.0.0", port=port)).start()

# ----------------- USERS -----------------
def save_users():
    with open(users_file, "w") as f:
        json.dump(users, f, indent=4)

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

# ----------------- PROGRESS HOOK -----------------
def progress_hook_factory(chat_id, context, last_percent=[0]):
    def hook(d):
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            percent = int(downloaded / total * 100)
            if percent - last_percent[0] >= 10:
                asyncio.create_task(context.bot.send_message(chat_id=chat_id, text=f"⬇️ Downloading: {percent}%"))
                last_percent[0] = percent
    return hook

# ----------------- DOWNLOAD -----------------
 def download_video(chat_id, context, url, selected_format="mp3"):
    ydl_opts = {}
    if selected_format == "mp3":
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f"{chat_id}_%(title)s.%(ext)s",
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'}],
            'quiet': True,
            'noplaylist': True,
            'socket_timeout': 1200,
            'retries': 10,
        }
    else:
        ydl_opts = {'format': 'best', 'outtmpl': f"{chat_id}_%(title)s.%(ext)s"}

    def ytdlp_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if selected_format == "mp3":
                return Path(f"{chat_id}_{info['title']}.mp3")
            else:
                return Path(ydl.prepare_filename(info))

    # ThreadPoolExecutor ilə sync işləri async çağırış kimi işlət
    file_path = ThreadPoolExecutor().submit(ytdlp_download).result()

    # Faylı bot ilə göndər
    with open(file_path, "rb") as f:
        if selected_format == "mp3":
            context.bot.send_audio(chat_id=chat_id, audio=f)
        else:
            context.bot.send_video(chat_id=chat_id, video=f)

    file_path.unlink()

    increment_download(chat_id)

# ----------------- BOT HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    buttons = [
        [InlineKeyboardButton("🇦🇿 Azərbaycan", callback_data="lang_az")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")]
    ]
    await update.message.reply_text(MESSAGES["choose_lang"]["en"], reply_markup=InlineKeyboardMarkup(buttons))

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    lang = query.data.split("_")[1]
    user_language[chat_id] = lang
    add_user(chat_id, query.from_user.username, query.from_user.first_name)
    await query.message.reply_text(MESSAGES["start"][lang].format(first_name=query.from_user.first_name))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    lang = user_language.get(chat_id, "en")
    total_users = len(users)
    total_downloads = sum(u["downloads"] for u in users.values())
    await update.message.reply_text(MESSAGES["stats"][lang].format(users=total_users, downloads=total_downloads))

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if not users:
        await update.message.reply_text("⚠️ No users found.")
        return
    msg_lines = [f"{u.get('first_name','N/A')} (@{u.get('username','N/A')}) — Downloads: {u.get('downloads',0)}" for u in users.values()]
    await update.message.reply_text("\n".join(msg_lines))

# ----------------- RUN BOT -----------------
if __name__ == "__main__":
    keep_alive()  # Flask server
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("stats", stats))
    app_bot.add_handler(CommandHandler("users", users_list))
    app_bot.add_handler(CallbackQueryHandler(set_language, pattern=r"^lang_"))

    # Synchronous run_polling, async loop problemi çıxmır
    app_bot.run_polling()
