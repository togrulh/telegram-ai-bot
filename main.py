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

# ----------------- TOKEN -----------------
TOKEN = "8416226783:AAEumHkVQ_I_83AShwr3IfJbhRniDTUZLmU"

user_selection = {}
pagination_data = {}
VIDEOS_PER_PAGE = 10
executor = ThreadPoolExecutor(max_workers=2)

user_language = {}  # chat_id -> lang

# ----------------- Mesajlar -----------------
MESSAGES = {
    "choose_lang": {
        "az": "Dil seçin:",
        "en": "Choose your language:",
        "ru": "Выберите язык:"
    },
    "start": {
        "az": "Salam {first_name}! 🎵\nMahnı adı / Müğənni adı göndərin...\nYouTube link / playlist göndərə bilərsiniz.",
        "en": "Hi {first_name}! 🎵\nSend me: Song name / Singer name\nYou can also send a YouTube link / playlist.",
        "ru": "Привет {first_name}! 🎵\nОтправь мне: Название песни / Имя исполнителя\nМожно также ссылку на YouTube / плейлист."
    },
    "searching": {
        "az": "🔎 YouTube-da axtarılır...",
        "en": "🔎 Searching on YouTube...",
        "ru": "🔎 Поиск на YouTube..."
    },
    "no_results": {
        "az": "⚠️ Nəticə tapılmadı.",
        "en": "⚠️ No results found.",
        "ru": "⚠️ Результаты не найдены."
    },
    "choose_format": {
        "az": "Formatı seçin:",
        "en": "Choose format:",
        "ru": "Выберите формат:"
    },
    "downloading": {
        "az": "⏳ {format} formatında yüklənir...",
        "en": "⏳ Downloading as {format}...",
        "ru": "⏳ Загрузка в формате {format}..."
    },
    "selected": {
        "az": "✅ Seçildi: {title}",
        "en": "✅ Selected: {title}",
        "ru": "✅ Выбрано: {title}"
    },
    "no_selection": {
        "az": "⚠️ Heç bir video seçilməyib.",
        "en": "⚠️ No videos selected.",
        "ru": "⚠️ Видео не выбрано."
    },
    "stats": {
        "az": "👥 İstifadəçilər: {users}\n🎵 Yükləmələr: {downloads}",
        "en": "👥 Users: {users}\n🎵 Downloads: {downloads}",
        "ru": "👥 Пользователи: {users}\n🎵 Загрузки: {downloads}"
    },
    "no_users": {
        "az": "👥 Hələ heç bir istifadəçi yoxdur.",
        "en": "👥 No users yet.",
        "ru": "👥 Пока нет пользователей."
    }
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
        users[chat_id_str] = {
            "username": username,
            "first_name": first_name,
            "downloads": 0
        }
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
                    context.bot.send_message(
                        chat_id=chat_id, text=f"⬇️ Downloading: {percent}%"),
                    asyncio.get_event_loop())
                last_percent[0] = percent
    return hook

# ----------------- Asynchronous download -----------------
async def download_video_async(url, chat_id, context, selected_format):
    loop = asyncio.get_event_loop()

    if selected_format == "mp3":
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f"{chat_id}_%(title)s.%(ext)s",
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128'
            }],
            'quiet': True,
            'noplaylist': True,
            'socket_timeout': 1200,
            'retries': 10,
            'progress_hooks': [progress_hook_factory(chat_id, context)]
        }

    def ytdlp_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if selected_format == "mp3":
                file_name = Path(f"{chat_id}_{info['title']}.mp3")
            else:
                file_name = Path(ydl.prepare_filename(info))
        return file_name

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
    lang = query.data.split("_")[1]  # az/en/ru
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

# ----------------- Search funksiyası -----------------
async def search_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    lang = user_language.get(chat_id, "en")
    query = update.message.text
    await update.message.reply_text(MESSAGES["searching"][lang])

    is_link = query.startswith("http://") or query.startswith("https://")
    if is_link:
        ydl_opts = {'quiet': True, 'extract_flat': False}
    else:
        ydl_opts = {'quiet': True, 'skip_download': True, 'default_search': 'ytsearch50', 'extract_flat': 'in_playlist'}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(query, download=False)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")
        return

    if not results:
        await update.message.reply_text(MESSAGES["no_results"][lang])
        return

    entries = results.get('entries', [])
    if not entries and 'title' in results:
        entries = [results]
    if not entries:
        await update.message.reply_text(MESSAGES["no_results"][lang])
        return

    for entry in entries:
        entry['url'] = entry.get('url') or entry.get('webpage_url')

    user_selection[chat_id] = []
    pagination_data[chat_id] = {"entries": entries, "page": 0}
    await send_video_buttons(update, chat_id, entries, 0, lang)

async def send_video_buttons(update, chat_id, entries, page, lang):
    start = page * VIDEOS_PER_PAGE
    end = start + VIDEOS_PER_PAGE
    buttons = [[InlineKeyboardButton(entry['title'], callback_data=f"video_{start+i}")] for i, entry in enumerate(entries[start:end])]

    nav_buttons = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page_{page-1}"))
    if end < len(entries):
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}"))
    nav_buttons.append(InlineKeyboardButton("✅ Complete selection", callback_data="done"))
    buttons.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await update.callback_query.edit_message_text("✅ Select videos:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("✅ Results found, select videos:", reply_markup=reply_markup)

# ----------------- Selection -----------------
async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    lang = user_language.get(chat_id, "en")
    data = query.data

    if data.startswith("lang_"):
        await set_language(update, context)
        return

    # VIDEO PAGE CALLBACKS
    if data.startswith("page_"):
        if chat_id not in pagination_data:
            await query.message.reply_text("⚠️ No video data found.")
            return
        new_page = int(data.split("_")[1])
        pagination_data[chat_id]["page"] = new_page
        await send_video_buttons(update, chat_id, pagination_data[chat_id]["entries"], new_page, lang)
        return

    if data.startswith("video_"):
        if chat_id not in pagination_data:
            await query.message.reply_text("⚠️ No video data found.")
            return
        index = int(data.split("_")[1])
        entry = pagination_data[chat_id]["entries"][index]
        url = entry.get('url')
        title = entry.get('title', 'No Title')
        if chat_id not in user_selection:
            user_selection[chat_id] = []
        if url not in user_selection[chat_id]:
            user_selection[chat_id].append(url)
        await query.message.reply_text(MESSAGES["selected"][lang].format(title=title))
        return

    # FORMAT CALLBACKS
    if data == "done":
        urls = user_selection.get(chat_id, [])
        if not urls:
            await query.message.reply_text(MESSAGES["no_selection"][lang])
            return
        format_buttons = [[InlineKeyboardButton("🎵 MP3", callback_data="format_mp3")]]
        await query.message.reply_text(MESSAGES["choose_format"][lang], reply_markup=InlineKeyboardMarkup(format_buttons))
        return

    if data.startswith("format_"):
        selected_format = data.split("_")[1]
        await query.message.reply_text(MESSAGES["downloading"][lang].format(format=selected_format.upper()))
        urls = user_selection.get(chat_id, [])
        if not urls:
            await query.message.reply_text(MESSAGES["no_selection"][lang])
            return
        for url in urls:
            try:
                await download_video_async(url, chat_id, context, selected_format)
                increment_download(chat_id)
            except Exception as e:
                await query.message.reply_text(f"⚠️ Error: {e}")
        user_selection[chat_id] = []

# ----------------- Run -----------------
def run_bot():
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("stats", stats))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_song))
    app_bot.add_handler(CallbackQueryHandler(handle_selection))
    print("✅ Bot is running...")
    app_bot.run_polling()

if __name__ == "__main__":
    keep_alive()
    run_bot()
