import re
import json
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

def format_cookie_header(raw_cookie: str) -> str:
    """Formats any cookie input (raw string, json from Cookie-Editor, or single ndus) into a standard Cookie header."""
    if not raw_cookie:
        return ""
    raw = raw_cookie.strip()
    # If it's JSON from Cookie-Editor export: [{"name": "...", "value": "..."}, ...]
    if raw.startswith("[") or raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                cookies = [f"{c['name']}={c['value']}" for c in data if isinstance(c, dict) and "name" in c and "value" in c]
                return "; ".join(cookies)
            elif isinstance(data, dict):
                cookies = [f"{k}={v}" for k, v in data.items()]
                return "; ".join(cookies)
        except Exception:
            pass

    if "ndus=" not in raw and "=" not in raw:
        return f"ndus={raw}; lang=en"
    
    return raw

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
        """Extracts direct download link using Terabox session cookie."""
        if not cookie:
            return None
        
        cookie_header = format_cookie_header(cookie)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "User-Agent": USER_AGENT,
            "Cookie": cookie_header,
        }

        try:
            s = requests.Session()
            s.headers.update(headers)

            temp_req = s.get(url, timeout=20, allow_redirects=True)
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

            clean_surl = surl.lstrip("1")
            respo = temp_req.text

            js_token = cls._find_between(respo, 'fn%28%22', '%22%29')
            if not js_token:
                m_js = re.search(r'\"jsToken\":\"([a-fA-F0-9]+)\"', respo)
                if m_js:
                    js_token = m_js.group(1)

            domain = parsed_url.netloc or "www.1024tera.com"
            s.headers.update({"Referer": temp_req.url, "Host": domain})

            params = {
                "app_id": "250528",
                "web": "1",
                "channel": "dubox",
                "clienttype": "0",
                "jsToken": js_token,
                "page": "1",
                "num": "20",
                "by": "name",
                "order": "asc",
                "site_referer": temp_req.url,
                "shorturl": clean_surl,
                "root": "1",
            }

            list_resp = s.get(f"https://{domain}/share/list", params=params, timeout=20)
            data = list_resp.json()

            if data and data.get("errno") == 0 and "list" in data and len(data["list"]) > 0:
                files = []
                for item in data["list"]:
                    dlink = item.get("dlink")
                    # If dlink is directly available
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
                
                # If dlink is not in list, request from /share/download
                share_id = data.get("share_id")
                uk = data.get("uk")
                first_item = data["list"][0]
                fs_id = first_item.get("fs_id")

                dl_resp = s.post(f"https://{domain}/share/download", params={
                    "app_id": "250528", "web": "1", "channel": "dubox", "clienttype": "0", "jsToken": js_token
                }, data={
                    "product": "share", "nozip": "0", "primaryid": str(share_id), "uk": str(uk),
                    "fid_list": f"[{fs_id}]", "extra": "{}", "surl": clean_surl
                })
                dl_data = dl_resp.json()
                if dl_data.get("errno") == 0 and dl_data.get("dlink"):
                    thumb = first_item.get("thumbs", {}).get("url3") or first_item.get("thumbs", {}).get("url2")
                    return [TeraboxFile(
                        file_name=first_item.get("server_filename", "video.mp4"),
                        download_url=dl_data["dlink"],
                        size=int(first_item.get("size", 0)),
                        thumb_url=thumb,
                        fs_id=str(fs_id)
                    )]

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
        if TERABOX_COOKIE:
            files = await asyncio.to_thread(cls.extract_with_cookie, url, TERABOX_COOKIE)
            if files:
                return files

        async with aiohttp.ClientSession() as session:
            files = await cls.extract_via_public_apis(session, url)
            if files:
                return files

        raise ValueError("Could not extract download link. The link may be expired, private, or invalid.")
