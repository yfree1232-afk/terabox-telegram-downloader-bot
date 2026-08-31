import os
import re
import shutil
import psutil

# Recognized domains / keywords for Terabox links
TERABOX_DOMAINS = [
    "terabox", "1024tera", "nephobox", "4funbox", "mirrobox", 
    "momerybox", "tibabox", "freeterabox", "terashare", "terafileshare",
    "teraboxlink", "teraboxshare", "1024terabox"
]

def extract_terabox_url(text: str) -> str | None:
    """
    Extracts the full complete Terabox URL from user text without truncating query parameters.
    """
    if not text:
        return None
    
    # Find any full URL in the text
    matches = re.findall(r"https?://[^\s<>\"']+", text.strip())
    for url in matches:
        url_lower = url.lower()
        if any(domain in url_lower for domain in TERABOX_DOMAINS):
            return url.strip()
            
    # Check if a raw surl or shortlink was sent without http
    surl_match = re.search(r"\b(1[a-zA-Z0-9_-]{15,35}|[a-zA-Z0-9_-]{20,35})\b", text.strip())
    if surl_match:
        return f"https://www.terabox.app/sharing/link?surl={surl_match.group(1)}"

    return None

def human_readable_size(size_bytes: int) -> str:
    """Converts bytes to human readable format (KB, MB, GB)."""
    if not size_bytes or size_bytes < 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"

def format_time(seconds: float | int) -> str:
    """Converts seconds to HH:MM:SS or MM:SS format."""
    if not seconds or seconds < 0:
        return "00s"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}h {minutes:02d}m {secs:02d}s"
    if minutes > 0:
        return f"{minutes:02d}m {secs:02d}s"
    return f"{secs:02d}s"

def get_progress_bar(percentage: float, length: int = 10) -> str:
    """Generates a text-based progress bar."""
    percentage = max(0.0, min(100.0, percentage))
    filled_len = int(length * percentage // 100)
    bar = "█" * filled_len + "░" * (length - filled_len)
    return f"[{bar}] {percentage:.1f}%"

def clean_filename(filename: str) -> str:
    """Removes unsupported characters from filenames."""
    if not filename:
        return "terabox_video.mp4"
    clean = re.sub(r'[\\/*?:"<>|]', "", filename)
    clean = clean.strip().replace(" ", "_")
    if not clean:
        return "terabox_video.mp4"
    return clean

def clean_temp_files(*paths):
    """Safely removes temporary files or folders from disk."""
    for path in paths:
        if path and os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
            except Exception:
                pass

def get_system_stats() -> dict:
    """Returns CPU, RAM, and Disk space stats for status command."""
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = shutil.disk_usage(".")
    return {
        "cpu": f"{cpu}%",
        "ram_used": human_readable_size(ram.used),
        "ram_total": human_readable_size(ram.total),
        "ram_pct": f"{ram.percent}%",
        "disk_free": human_readable_size(disk.free),
        "disk_total": human_readable_size(disk.total)
    }
