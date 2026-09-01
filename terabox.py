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
    """Multi-Domain Terabox Link Resolver & High-Speed Stream Extraction Engine."""

    @staticmethod
    def extract_surl(url: str) -> Optional[str]:
        """Extracts the unique sharing code (surl) from ANY Terabox domain/link format."""
        if not url:
            return None
        
        url_clean = url.strip()
        parsed = urllib.parse.urlparse(url_clean)
        qs = urllib.parse.parse_qs(parsed.query)
        
        # 1. Query parameters: surl or shorturl or key
        for key in ["surl", "shorturl", "key"]:
            if key in qs and qs[key]:
                return qs[key][0].lstrip("1")

        # 2. Path formats: /s/1... or /s/...
        m = re.search(r"/s/([a-zA-Z0-9_\-]+)", url_clean)
        if m:
            return m.group(1).lstrip("1")
            
        # 3. Path with surl=
        m2 = re.search(r"surl=([a-zA-Z0-9_\-]+)", url_clean)
        if m2:
            return m2.group(1).lstrip("1")

        # 4. Raw alphanumeric share code
        m3 = re.search(r"\b(1[a-zA-Z0-9_-]{15,35}|[a-zA-Z0-9_-]{20,35})\b", url_clean)
        if m3:
            return m3.group(1).lstrip("1")

        return None

    @classmethod
    def get_stream_download_info(cls, url: str, cookie: str) -> Optional[List[TeraboxFile]]:
        surl = cls.extract_surl(url)
        if not surl:
            return None

        # 1. Multi-domain fallback to fetch file list
        mirror_domains = [
            "www.1024tera.com",
            "www.terabox.app",
            "www.1024terabox.com",
            "freeterabox.com",
            "nephobox.com",
            "4funbox.com",
            "mirrobox.com",
            "momerybox.com",
            "tibabox.com",
            "terafileshare.com"
        ]

        list_data = None
        for domain in mirror_domains:
            list_headers = {
                "User-Agent": USER_AGENT,
                "Referer": f"https://{domain}/sharing/link?surl={surl}",
                "Accept": "application/json, text/plain, */*"
            }
            list_url = f"https://{domain}/share/list?app_id=250528&shorturl={surl}&root=1"
            try:
                r_list = requests.get(list_url, headers=list_headers, timeout=8)
                resp_json = r_list.json()
                if resp_json.get("errno") == 0 and resp_json.get("list"):
                    list_data = resp_json
                    break
            except Exception:
                continue

        if not list_data or not list_data.get("list"):
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

        signb = None
        ts = None

        auth_endpoints = [
            "https://dm.1024terabox.com/api/home/info",
            "https://www.1024tera.com/api/home/info",
            "https://www.terabox.app/api/home/info"
        ]

        for auth_url in auth_endpoints:
            try:
                r_home = requests.get(auth_url, headers=auth_headers, timeout=10)
                home_json = r_home.json()
                if home_json.get("errno") == 0 and "data" in home_json:
                    home_data = home_json["data"]
                    signb = sign_download(home_data["sign3"], home_data["sign1"])
                    ts = home_data["timestamp"]
                    break
            except Exception:
                continue

        if not signb or not ts:
            return None

        # 3. For each file, extract video stream segments across all resolutions
        results = []
        qualities = ["M3U8_AUTO_1080", "M3U8_AUTO_720", "M3U8_AUTO_480", "M3U8_AUTO_360", "M3U8_AUTO_240"]
        streaming_hosts = ["dm.1024terabox.com", "www.1024tera.com", "www.terabox.app", "freeterabox.com"]

        for item in list_data["list"]:
            fs_id = item.get("fs_id")
            filename = item.get("server_filename", "video.mp4")
            size = int(item.get("size", 0))
            duration = int(item.get("duration", 0))
            thumb = (item.get("thumbs") or {}).get("url3") or (item.get("thumbs") or {}).get("url2") or (item.get("thumbs") or {}).get("url1")

            segment_urls = []
            final_st_url = ""

            for host in streaming_hosts:
                for q in qualities:
                    st_url = f"https://{host}/share/streaming?app_id=250528&web=1&channel=dubox&clienttype=0&type={q}&uk={uk}&shareid={share_id}&fid={fs_id}&surl={surl}&timestamp={ts}&sign={urllib.parse.quote(signb)}"
                    try:
                        r_st = requests.get(st_url, headers=auth_headers, timeout=8)
                        if "#EXTM3U" in r_st.text:
                            segment_urls = [line.strip() for line in r_st.text.split("\n") if line.strip().startswith("http")]
                            if segment_urls:
                                final_st_url = st_url
                                break
                    except Exception:
                        continue
                if segment_urls:
                    break

            if segment_urls:
                results.append(TeraboxFile(
                    file_name=filename,
                    download_url=final_st_url,
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

        raise ValueError("Could not extract video stream from this link. Link may be expired, private, or invalid.")
