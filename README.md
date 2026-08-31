# 🚀 Terabox Video Downloader Telegram Bot (Heroku Ready)

Ek powerful, fast aur reliable Telegram Bot jo kisi bhi **Terabox Video Link** ko process karke direct Telegram par high-speed streamable video file (up to 2GB) bhejta hai.

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

---

## ✨ Features

- ⚡ **High Speed Streaming**: Direct video file generation.
- 📁 **Large File Support**: **Pyrogram MTProto** ke zariye 2 GB tak ki files upload hoti hain (Telegram HTTP Bot API ki 50MB limit bypass).
- 📊 **Real-time Live Progress Bar**: Download aur upload dono ke dauran speed (`MB/s`), percentage (`%`), aur `ETA` live update hota hai.
- 🎬 **Streamable Video Output**: `ffmpeg` se automatic thumbnail, duration, aur aspect ratio extract karke as video send karta hai taaki direct Telegram player me play ho sake.
- 🧹 **Auto-Cleanup**: Download hone aur user ko send hone ke baad Heroku disk space automatically clean ho jaata hai.
- 🌐 **All Terabox Domains Supported**: `terabox.com`, `teraboxapp.com`, `1024tera.com`, `terabox.app`, `freeterabox.com`, `nephobox.com`, `4funbox.com`, `mirrobox.com`, etc.

---

## 🛠️ Requirements & Setup

Aapko sirf 3 credentials chahiye:
1. **`BOT_TOKEN`**: Telegram par [@BotFather](https://t.me/BotFather) ke pass jaakar `/newbot` banayein aur Token copy karein.
2. **`API_ID` & `API_HASH`**: [my.telegram.org](https://my.telegram.org) par login karke **API Development Tools** se apna `API_ID` aur `API_HASH` lein.
3. *(Optional)* **`TERABOX_COOKIE`**: Agar aapke paas Terabox premium/normal account ka `ndus` cookie hai toh bypass aur bhi fast hota hai (Cookie lene ke liye: Terabox website par login karein -> `F12` Developer Tools -> `Application` -> `Cookies` -> `ndus` ki value copy karein).

---

## 🚀 Heroku Par Deploy Kaise Karein (Step-by-Step)

### Option 1: 1-Click Heroku Deploy (Sabse Aasan Tarika)

1. Is project ko apne **GitHub** account par push karein.
2. Upar diye gaye **"Deploy to Heroku"** button par click karein ya yeh URL open karein:
   ```
   https://heroku.com/deploy?template=https://github.com/<YOUR-GITHUB-USERNAME>/<REPO-NAME>
   ```
3. Apna `BOT_TOKEN`, `API_ID`, aur `API_HASH` daalein.
4. **Deploy App** par click karein!
5. Deployment complete hone ke baad Heroku dashboard me **Resources** tab me jaakar **worker** dyno ko **ON** karein.

---

### Option 2: Heroku CLI Se Deploy Karna

```bash
# 1. Heroku login karein
heroku login

# 2. Nayi Heroku app create karein
heroku create your-terabox-bot-name

# 3. Buildpacks add karein (Python + FFmpeg)
heroku buildpacks:add heroku/python
heroku buildpacks:add https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest.git

# 4. Environment Variables (Config Vars) set karein
heroku config:set API_ID=12345678
heroku config:set API_HASH="your_api_hash_here"
heroku config:set BOT_TOKEN="your_bot_token_here"

# 5. Code deploy karein
git init
git add .
git commit -m "Deploy Terabox Downloader Bot"
git push heroku master

# 6. Worker dyno start karein
heroku ps:scale worker=1
```

---

## 💻 Local Machine Par Run Kaise Karein

```bash
# 1. Repository clone karein / folder me jayein
cd terabox-downloader-bot

# 2. Virtual Environment banayein (Optional)
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. Dependencies install karein
pip install -r requirements.txt

# 4. .env file banayein
cp .env.example .env
# .env file me apna BOT_TOKEN, API_ID, API_HASH fill karein

# 5. Bot run karein
python bot.py
```

---

## 🤖 Bot Commands

| Command | Kaam |
|---|---|
| `/start` | Bot ko start karega aur welcome menu dikhayega |
| `/help` | Detailed help & usage guide |
| `/status` | Server CPU, RAM, Disk Space aur Uptime dikhayega |

---

## 📂 Project Structure

```
terabox-downloader-bot/
├── bot.py            # Main Telegram Bot Logic & Handlers
├── config.py         # App Configuration & Environment Variables
├── terabox.py        # Terabox Link Resolver & Direct Video Stream Extractor
├── downloader.py     # Chunked Streaming Downloader with Progress Bar
├── uploader.py       # Pyrogram MTProto Video Uploader with Thumbnail & Metadata
├── helpers.py        # Progress Bar, Time, File Size & Cleanup Utilities
├── Procfile          # Heroku Process Declaration (worker: python bot.py)
├── runtime.txt       # Python Runtime Version
├── requirements.txt  # Python Libraries
├── app.json          # Heroku 1-Click Deploy Template
├── .env.example      # Environment variables template
└── README.md         # Documentation
```
