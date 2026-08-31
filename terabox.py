import re
import json
import base64
import logging
import urllib.parse
from typing import Optional, List, Dict, Any
import asyncio
import aiohttp
import requests
from config import TERABOX_COOKIE

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"

def sign_download(s1: str, s2: str) -> str:
    """Computes RC4 stream cipher signature for Terabox streaming API."""
    p = bytearray(range(256))
    a = bytearray(len(p))
    for i in range(256):
        a[i] = ord(s1[i % len(s1)])
    j = 0
    for i in range(256):
        j = (j + p[i] + a[i]) % 256
        p[i], p[j] = p[j], p[i]
    result = bytearray()
    i = 0
    j = 0
    for q in range(len(s2)):
        i = (i + 1) % 256
        j = (j + p[i]) % 256
        p[i], p[j] = p[j], p[i]
        k = p[(p[i] + p[j]) % 256]
        result.append(ord(s2[q]) ^ k)
    return base64.b64encode(result).decode("utf-8")

class TeraboxFile:
    def __init__(self, file_name: str, download_url: str, size: int, thumb_url: Optional[str] = None, fs_id: Optional[str] = None, segment_urls: Optional[List[str]] = None, duration: int = 0):
        self.file_name = file_name
        self.download_url = download_url
        self.size = size
        self.thumb_url = thumb_url
        self.fs_id = fs_id
        self.segment_urls = segment_urls or []
        self.duration = duration

    def __repr__(self):
        return f"<TeraboxFile name='{self.file_name}' size={self.size} segments={len(self.segment_urls)}>"

class TeraboxExtractor:
    """High-Speed Terabox Link Resolver & Stream Extraction Engine."""

    @staticmethod
    def extract_surl(url: str) -> Optional[str]:
        if not url:
            return None
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "surl" in qs and qs["surl"]:
            return qs["surl"][0].lstrip("1")
        m = re.search(r"/s/([a-zA-Z0-9_\-]+)", url)
        if m:
            return m.group(1).lstrip("1")
        m2 = re.search(r"surl=([a-zA-Z0-9_\-]+)", url)
        if m2:
            return m2.group(1).lstrip("1")
        return None

    @classmethod
    def get_stream_download_info(cls, url: str, cookie: str) -> Optional[List[TeraboxFile]]:
        surl = cls.extract_surl(url)
        if not surl:
            return None

        # 1. Fetch file list from 1024tera.com
        list_headers = {
            "User-Agent": USER_AGENT,
            "Referer": f"https://www.1024tera.com/sharing/link?surl={surl}",
            "Accept": "application/json, text/plain, */*"
        }
        list_url = f"https://www.1024tera.com/share/list?app_id=250528&shorturl={surl}&root=1"
        try:
            r_list = requests.get(list_url, headers=list_headers, timeout=15)
            list_data = r_list.json()
        except Exception as e:
            logger.debug(f"List request failed: {e}")
            return None

        if list_data.get("errno") != 0 or not list_data.get("list"):
            return None

        share_id = list_data.get("share_id")
        uk = list_data.get("uk")
        
        # 2. Fetch Home Info with cookie for authentication tokens
        auth_cookie = cookie if "ndus=" in cookie else f"ndus={cookie}"
        auth_headers = {
            "User-Agent": USER_AGENT,
            "Cookie": auth_cookie,
            "Referer": "https://dm.1024terabox.com/"
        }

        try:
            r_home = requests.get("https://dm.1024terabox.com/api/home/info", headers=auth_headers, timeout=15)
            home_json = r_home.json()
            if home_json.get("errno") != 0 or "data" not in home_json:
                return None
            home_data = home_json["data"]
            signb = sign_download(home_data["sign3"], home_data["sign1"])
            ts = home_data["timestamp"]
        except Exception as e:
            logger.debug(f"Home info auth failed: {e}")
            return None

        # 3. For each file in the share list, extract video stream segments
        results = []
        qualities = ["M3U8_AUTO_1080", "M3U8_AUTO_720", "M3U8_AUTO_480", "M3U8_AUTO_360", "M3U8_AUTO_240"]

        for item in list_data["list"]:
            fs_id = item.get("fs_id")
            filename = item.get("server_filename", "video.mp4")
            size = int(item.get("size", 0))
            duration = int(item.get("duration", 0))
            thumb = (item.get("thumbs") or {}).get("url3") or (item.get("thumbs") or {}).get("url2")

            # Try streaming endpoints for this file
            segment_urls = []
            for q in qualities:
                st_url = f"https://dm.1024terabox.com/share/streaming?app_id=250528&web=1&channel=dubox&clienttype=0&type={q}&uk={uk}&shareid={share_id}&fid={fs_id}&surl={surl}&timestamp={ts}&sign={urllib.parse.quote(signb)}"
                try:
                    r_st = requests.get(st_url, headers=auth_headers, timeout=10)
                    if "#EXTM3U" in r_st.text:
                        segment_urls = [line.strip() for line in r_st.text.split("\n") if line.strip().startswith("http")]
                        if segment_urls:
                            break
                except Exception:
                    continue

            if segment_urls:
                results.append(TeraboxFile(
                    file_name=filename,
                    download_url=st_url,
                    size=size,
                    thumb_url=thumb,
                    fs_id=str(fs_id),
                    segment_urls=segment_urls,
                    duration=duration
                ))

        return results if results else None

    @classmethod
    async def get_download_info(cls, url: str) -> List[TeraboxFile]:
        cookie = TERABOX_COOKIE
        if not cookie:
            raise ValueError("Terabox cookie not configured in Heroku.")

        files = await asyncio.to_thread(cls.get_stream_download_info, url, cookie)
        if files:
            return files

        raise ValueError("Could not extract video stream. Link may be invalid, expired, or unsupported.")
