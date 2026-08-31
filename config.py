import os
from dotenv import load_dotenv

# Load .env file if present (useful for local development)
load_dotenv()

# Telegram API Credentials
# Get API_ID and API_HASH from https://my.telegram.org
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")

# Telegram Bot Token from @BotFather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Optional Terabox Session Cookie (ndus) for authenticated & higher download speeds
# Leave blank if you don't have one; bot uses fallback fast APIs
TERABOX_COOKIE = os.environ.get("TERABOX_COOKIE", "").strip()

# Maximum allowed file size to download (in bytes) - Default: 2 GB
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", str(2 * 1024 * 1024 * 1024)))  # 2 GB

# Download directory
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads")

# Bot Owner / Admin ID (Optional, for admin commands)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Log Channel ID (Optional, format: -100xxxxxxxxxx)
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0")) if os.environ.get("LOG_CHANNEL") else None

# Chunk size for streaming downloads (Default: 4MB chunks)
CHUNK_SIZE = 4 * 1024 * 1024

# Ensure downloads directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
