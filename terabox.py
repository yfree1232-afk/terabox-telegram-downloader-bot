import re
import logging
import asyncio
import aiohttp
import urllib.parse
from typing import Optional, Dict, Any, List
import requests
from config import TERABOX_COOKIE

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"

class TeraboxFile:
    def __init__(self, file_name: str, download_url: str, size: int, thumb_url: Optional[str] = None, fs_id: Optional[str] = None):
        self.file_name = file_name
        self.download_url = download_url
        self.size = size
        self.thumb_url = thumb_url
        self.fs_id = fs_id

    def __repr__(self):
        return f"<TeraboxFile name='{self.file_name}' size={self.size}>"

class TeraboxExtractor:
    """Multi-Engine Terabox Link Resolver & Direct Download Link Extractor."""

    @staticmethod
    def _find_between(s: str, start: str, end: str) -> str:
        start_index = s.find(start)
        if start_index == -1:
            return ""
        start_index += len(start)
        end_index = s.find(end, start_index)
        if end_index == -1:
            return ""
        return s[start_index:end_index]

    @classmethod
    def extract_with_cookie(cls, url: str, cookie: str) -> Optional[List[TeraboxFile]]:
        """Extracts direct download link using Terabox session cookie (ndus)."""
        if not cookie:
            return None
        
        cookie_val = cookie if "ndus=" in cookie else f"ndus={cookie}"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Host": "www.terabox.app",
            "User-Agent": USER_AGENT,
            "Cookie": cookie_val,
        }

        try:
            # First request to get canonical URL
            temp_req = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
            if not temp_req.ok:
                return None

            parsed_url = urllib.parse.urlparse(temp_req.url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            surl = None
            if "surl" in query_params:
                surl = query_params["surl"][0]
            else:
                m = re.search(r"/s/([a-zA-Z0-9_\-]+)", temp_req.url)
                if m:
                    surl = m.group(1).lstrip("1")

            if not surl:
                return None

            # Second request to scrape jsToken, dp-logid, bdstoken
            req2 = requests.get(temp_req.url, headers=headers, timeout=20)
            respo = req2.text

            js_token = cls._find_between(respo, 'fn%28%22', '%22%29')
            if not js_token:
                m_js = re.search(r'\"jsToken\":\"([a-fA-F0-9]+)\"', respo)
                if m_js:
                    js_token = m_js.group(1)

            logid = cls._find_between(respo, 'dp-logid=', '&') or "9097091044853808108"
            
            clean_surl = surl.lstrip("1")
            params = {
                "app_id": "250528",
                "web": "1",
                "channel": "dubox",
                "clienttype": "0",
                "jsToken": js_token,
                "dp-logid": logid,
                "page": "1",
                "num": "20",
                "by": "name",
                "order": "asc",
                "site_referer": temp_req.url,
                "shorturl": clean_surl,
                "root": "1,",
            }

            list_resp = requests.get("https://www.terabox.app/share/list", headers=headers, params=params, timeout=20)
            data = list_resp.json()

            if data and data.get("errno") == 0 and "list" in data and len(data["list"]) > 0:
                files = []
                for item in data["list"]:
                    dlink = item.get("dlink")
                    if dlink:
                        thumb = item.get("thumbs", {}).get("url3") or item.get("thumbs", {}).get("url2") or item.get("thumbs", {}).get("url1")
                        files.append(TeraboxFile(
                            file_name=item.get("server_filename", "video.mp4"),
                            download_url=dlink,
                            size=int(item.get("size", 0)),
                            thumb_url=thumb,
                            fs_id=str(item.get("fs_id", ""))
                        ))
                if files:
                    return files
        except Exception as e:
            logger.debug(f"Cookie extraction failed: {e}")
            return None

        return None

    @classmethod
    async def extract_via_public_apis(cls, session: aiohttp.ClientSession, url: str) -> Optional[List[TeraboxFile]]:
        """Tries various public mirror APIs."""
        clean_url = url.strip()
        encoded = urllib.parse.quote(clean_url, safe="")
        
        endpoints = [
            f"https://terabox-dl.qtcloud.workers.dev/api/get-info",
            f"https://terabox.hnn.workers.dev/api/get-info",
            f"https://teradl-api.dapuntaratya.com/generate_file?url={encoded}",
            f"https://yt-api-terabox.vercel.app/api?url={encoded}"
        ]

        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

        for ep in endpoints:
            try:
                if "/api/get-info" in ep:
                    async with session.post(ep, json={"url": clean_url}, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data:
                                dlink = data.get("download_link") or data.get("dlink") or data.get("url")
                                if dlink:
                                    name = data.get("file_name") or data.get("filename") or "video.mp4"
                                    size = int(data.get("size") or data.get("size_bytes") or 0)
                                    return [TeraboxFile(name, dlink, size, data.get("thumbnail"))]
                else:
                    async with session.get(ep, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data:
                                dlink = data.get("download_link") or data.get("dlink") or data.get("url")
                                if dlink:
                                    name = data.get("file_name") or data.get("filename") or "video.mp4"
                                    size = int(data.get("size") or data.get("size_bytes") or 0)
                                    return [TeraboxFile(name, dlink, size, data.get("thumbnail"))]
            except Exception:
                continue
        return None

    @classmethod
    async def get_download_info(cls, url: str) -> List[TeraboxFile]:
        """Resolves the Terabox link and returns extracted TeraboxFile objects."""
        # 1. Try extraction with TERABOX_COOKIE if configured
        if TERABOX_COOKIE:
            files = await asyncio.to_thread(cls.extract_with_cookie, url, TERABOX_COOKIE)
            if files:
                return files

        # 2. Try Public Mirror APIs
        async with aiohttp.ClientSession() as session:
            files = await cls.extract_via_public_apis(session, url)
            if files:
                return files

        # 3. If cookie wasn't provided, explain how to set TERABOX_COOKIE
        if not TERABOX_COOKIE:
            raise ValueError(
                "Terabox ke anti-bot protection ko bypass karne ke liye **TERABOX_COOKIE (ndus)** zaroori hai.\n\n"
                "📌 **Cookie Kaise Set Karein:**\n"
                "1. Browser me [terabox.app](https://www.terabox.app) par login karein.\n"
                "2. `F12` (Inspect) -> `Application` -> `Cookies` -> `ndus` ki value copy karein.\n"
                "3. Heroku me `TERABOX_COOKIE` config var me paste kar dein."
            )

        raise ValueError("Could not extract download link. The link may be expired, private, or invalid.")
