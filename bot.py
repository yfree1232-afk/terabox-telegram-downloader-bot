import os
import sys
import time
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

import config
from helpers import (
    extract_terabox_url,
    human_readable_size,
    clean_temp_files,
    get_system_stats
)
from terabox import TeraboxExtractor
from downloader import Downloader
from uploader import TelegramUploader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("TeraboxBot")

# Validate required environment variables
if not config.BOT_TOKEN or not config.API_ID or not config.API_HASH:
    logger.error("BOT_TOKEN, API_ID, and API_HASH must be configured in environment variables or config.py!")
    print("\n[ERROR] Missing Credentials! Please set BOT_TOKEN, API_ID, and API_HASH in .env or Heroku Config Vars.\n")
    # We do not sys.exit() immediately here so that imports for testing work, but bot start will check it.

app = Client(
    "terabox_downloader_bot",
    api_id=config.API_ID if config.API_ID else 12345,
    api_hash=config.API_HASH if config.API_HASH else "placeholder_hash",
    bot_token=config.BOT_TOKEN
)

BOT_START_TIME = time.time()

# ----------------- COMMAND HANDLERS ----------------- #

@app.on_message(filters.command(["start"]))
async def start_command(client: Client, message: Message):
    user_name = message.from_user.first_name if message.from_user else "User"
    welcome_text = (
        f"👋 **Namaste {user_name}! Welcome to Terabox Video Downloader Bot** 🚀\n\n"
        f"Mujhe koi bhi **Terabox Video Link** bhejiye, main seedhe video file download karke Telegram par bhej dunga! 🎬\n\n"
        f"✨ **Features:**\n"
        f"• ⚡ Fast High-Speed Video Streaming\n"
        f"• 📊 Real-time Download & Upload Progress Bar\n"
        f"• 📁 2 GB tak ki Large Files Support\n"
        f"• 🎬 Direct Streamable Video with Thumbnail\n\n"
        f"💡 *Bas link bhejiye aur magic dekhiye!*"
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Help", callback_data="help_menu"),
            InlineKeyboardButton("📊 Bot Status", callback_data="status_menu")
        ]
    ])
    await message.reply_text(welcome_text, reply_markup=buttons, disable_web_page_preview=True)

@app.on_message(filters.command(["help"]))
async def help_command(client: Client, message: Message):
    help_text = (
        "📖 **Terabox Downloader Bot - Help Guide**\n\n"
        "1️⃣ **Step 1:** Terabox app ya website se video link copy karein.\n"
        "2️⃣ **Step 2:** Link ko is bot ko chat me paste karke send karein.\n"
        "3️⃣ **Step 3:** Bot link ko analyze karke download & upload karega.\n\n"
        "🌐 **Supported Domains:**\n"
        "`terabox.com`, `teraboxapp.com`, `1024tera.com`, `terasharelink.com`, `nephobox.com`, `4funbox.com`, `mirrobox.com`, `freeterabox.com`\n\n"
        "⚠️ *Maximum File Limit: 2 GB*"
    )
    await message.reply_text(help_text, disable_web_page_preview=True)

@app.on_message(filters.command(["status", "ping"]))
async def status_command(client: Client, message: Message):
    stats = get_system_stats()
    uptime_sec = int(time.time() - BOT_START_TIME)
    h, rem = divmod(uptime_sec, 3600)
    m, s = divmod(rem, 60)
    uptime_str = f"{h}h {m}m {s}s"

    status_text = (
        "🤖 **Bot System Status**\n\n"
        f"⏱️ **Uptime:** `{uptime_str}`\n"
        f"💻 **CPU Usage:** `{stats['cpu']}`\n"
        f"🧠 **RAM:** `{stats['ram_used']}` / `{stats['ram_total']}` (`{stats['ram_pct']}`)\n"
        f"💽 **Disk Free:** `{stats['disk_free']}` / `{stats['disk_total']}`\n"
        f"🚀 **Bot Status:** `Online & Operational`"
    )
    await message.reply_text(status_text)

# ----------------- CALLBACK QUERY HANDLER ----------------- #

@app.on_callback_query()
async def callback_handler(client: Client, query):
    data = query.data
    if data == "help_menu":
        help_text = (
            "📖 **Terabox Downloader Bot - Help Guide**\n\n"
            "1️⃣ Terabox video ka link copy karein.\n"
            "2️⃣ Is bot ko link send karein.\n"
            "3️⃣ Bot high speed me direct video file bhej dega.\n\n"
            "Supported links: `terabox.com`, `1024tera.com`, `freeterabox.com` etc."
        )
        await query.message.edit_text(
            help_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_start")]])
        )
    elif data == "status_menu":
        stats = get_system_stats()
        status_text = (
            f"📊 **System Status:**\n\n"
            f"💻 CPU: `{stats['cpu']}` | RAM: `{stats['ram_pct']}`\n"
            f"💽 Disk Free: `{stats['disk_free']}`\n"
            f"⚡ Server: `Heroku Cloud Dyno`"
        )
        await query.message.edit_text(
            status_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_start")]])
        )
    elif data == "back_start":
        await start_command(client, query.message)
    await query.answer()

# ----------------- LINK PROCESSOR HANDLER ----------------- #

@app.on_message(filters.text & ~filters.command(["start", "help", "status", "ping"]))
async def process_terabox_link(client: Client, message: Message):
    text = message.text.strip()
    terabox_url = extract_terabox_url(text)

    if not terabox_url:
        # Ignore messages that aren't terabox links (or gently inform if private chat)
        if message.chat.type.name == "PRIVATE":
            await message.reply_text(
                "❌ **Invalid Terabox Link!**\n\nKripya valid Terabox video link bhejiye (e.g. `https://teraboxapp.com/s/...`).",
                quote=True
            )
        return

    status_msg = await message.reply_text("🔎 **Analyzing Terabox Link...**\n*Extracting direct download stream...*", quote=True)
    downloaded_files = []

    try:
        # 1. Extract download info from Terabox link
        files = await TeraboxExtractor.get_download_info(terabox_url)

        if not files:
            await status_msg.edit_text("❌ **Error:** No downloadable files found in this link.")
            return

        total_files = len(files)
        for index, file_info in enumerate(files, start=1):
            file_name = file_info.file_name
            file_size = file_info.size
            dlink = file_info.download_url

            # Check file size limit
            if file_size > config.MAX_FILE_SIZE:
                await status_msg.edit_text(
                    f"⚠️ **File Too Large!**\n\n"
                    f"📁 **File:** `{file_name}`\n"
                    f"💾 **Size:** `{human_readable_size(file_size)}`\n"
                    f"Bot limit: `{human_readable_size(config.MAX_FILE_SIZE)}`"
                )
                continue

            prefix = f"[{index}/{total_files}] " if total_files > 1 else ""
            await status_msg.edit_text(f"🚀 {prefix}**Connecting to Terabox server...**\n📁 `{file_name}` (`{human_readable_size(file_size)}`)")

            # Progress callback for downloader
            async def progress_update(prog_text: str):
                try:
                    await status_msg.edit_text(f"{prefix}{prog_text}")
                except FloodWait as fw:
                    await asyncio.sleep(fw.value)
                except Exception:
                    pass

            # 2. Download file chunk-by-chunk to disk
            file_path = await Downloader.download_file(
                download_url=dlink,
                filename=file_name,
                total_size=file_size,
                progress_callback=progress_update
            )
            downloaded_files.append(file_path)

            # 3. Upload video to user
            await status_msg.edit_text(f"📤 {prefix}**Uploading video to Telegram...**\n📁 `{file_name}`")
            caption = (
                f"🎬 **{file_name}**\n\n"
                f"💾 **Size:** `{human_readable_size(os.path.getsize(file_path))}`\n"
                f"🤖 **Downloaded via:** @{(await client.get_me()).username}"
            )

            await TelegramUploader.upload_video_file(
                client=client,
                chat_id=message.chat.id,
                file_path=file_path,
                status_msg=status_msg,
                caption=caption,
                reply_to_message_id=message.id
            )

            # Clean downloaded file immediately after upload to save Heroku disk space
            clean_temp_files(file_path)
            downloaded_files.remove(file_path)

        # Final cleanup confirmation
        await status_msg.delete()

    except Exception as e:
        logger.exception(f"Processing failed for URL {terabox_url}: {e}")
        error_msg = str(e)
        if "Could not extract" in error_msg:
            err_text = "❌ **Failed to resolve Terabox link!**\nLink might be expired, private, or temporarily unreachable."
        else:
            err_text = f"❌ **Error while processing:** `{error_msg}`"
        try:
            await status_msg.edit_text(err_text)
        except Exception:
            pass

    finally:
        # Guarantee all residual files are purged
        if downloaded_files:
            clean_temp_files(*downloaded_files)

# ----------------- BOT START ----------------- #

if __name__ == "__main__":
    print("==============================================")
    print("      TERABOX DOWNLOADER TELEGRAM BOT         ")
    print("==============================================")
    if not config.BOT_TOKEN or not config.API_ID or not config.API_HASH:
        print("[CRITICAL] Please configure API_ID, API_HASH, and BOT_TOKEN before running!")
        sys.exit(1)

    print("[INFO] Starting Bot Client...")
    app.run()
