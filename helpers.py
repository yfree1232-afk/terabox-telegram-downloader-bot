import os
import re
import shutil
import psutil
import requests

# All recognized domains, subdomains & alias keywords for Terabox
TERABOX_DOMAINS = [
    "terabox", "1024tera", "nephobox", "4funbox", "mirrobox", 
    "momerybox", "tibabox", "freeterabox", "terashare", "terafileshare",
    "teraboxlink", "teraboxshare", "1024terabox", "terasharefile",
    "teraboxapp", "terafiles", "teraboxdrive", "teraboxurl", "teraboxcdn",
    "teradownloader", "dubox", "tera-box", "terabox.fun", "terashare.link",
    "terashare.com", "terabox.link", "terabox.online"
]

def extract_terabox_url(text: str) -> str | None:
    """
    Extracts any Terabox link from user text across all known domains, 
    mirror links, shortlinks, or raw surl share codes.
    """
    if not text:
        return None
    
    clean_text = text.strip()
    
    # 1. Check for any full URL containing Terabox domains
    matches = re.findall(r"https?://[^\s<>\"']+", clean_text)
    for url in matches:
        url_lower = url.lower()
        if any(domain in url_lower for domain in TERABOX_DOMAINS):
            return url.strip()
            
    # 2. Check if a shortlink/redirect was sent
    for url in matches:
        try:
            resp = requests.head(url, allow_redirects=True, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            final_url = resp.url.lower()
            if any(domain in final_url for domain in TERABOX_DOMAINS) or "surl=" in final_url or "/s/" in final_url:
                return resp.url
        except Exception:
            pass

    # 3. Check if a raw surl / share code was sent directly (e.g. 1JbdsCwLyjufpcwEmbyIg6Q)
    surl_match = re.search(r"\b(1[a-zA-Z0-9_-]{15,35}|[a-zA-Z0-9_-]{20,35})\b", clean_text)
    if surl_match:
        return f"https://www.1024tera.com/sharing/link?surl={surl_match.group(1)}"

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
