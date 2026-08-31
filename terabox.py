import re
import logging
import aiohttp
from typing import Optional, Dict, Any, List
from config import TERABOX_COOKIE

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

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
    def extract_surl(url: str) -> Optional[str]:
        """Extracts the surl key from Terabox link."""
        match = re.search(r"[?&]surl=([a-zA-Z0-9_\-]+)", url)
        if match:
            surl = match.group(1)
            return surl if surl.startswith("1") else "1" + surl
        
        match_path = re.search(r"/s/([a-zA-Z0-9_\-]+)", url)
        if match_path:
            surl = match_path.group(1)
            return surl if surl.startswith("1") else "1" + surl
        
        return None

    @classmethod
    async def resolve_url_redirect(cls, session: aiohttp.ClientSession, url: str) -> str:
        """Resolves any redirects (e.g. shortlinks) to the final canonical URL."""
        headers = {"User-Agent": USER_AGENT}
        try:
            async with session.head(url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return str(resp.url)
        except Exception:
            return url

    @classmethod
    async def extract_via_official_api(cls, session: aiohttp.ClientSession, surl: str) -> Optional[List[TeraboxFile]]:
        """Extracts direct download links using Terabox official web API."""
        clean_surl = surl.lstrip("1")
        api_url = f"https://www.terabox.app/share/list?app_id=250528&shorturl={clean_surl}&root=1"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": f"https://www.terabox.app/sharing/link?surl={clean_surl}",
            "Accept": "application/json, text/plain, */*",
        }
        if TERABOX_COOKIE:
            headers["Cookie"] = f"ndus={TERABOX_COOKIE}"

        try:
            async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data.get("errno") == 0 and "list" in data:
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
            logger.debug(f"Official API extraction error: {e}")
        return None

    @classmethod
    async def extract_via_fast_proxies(cls, session: aiohttp.ClientSession, original_url: str) -> Optional[List[TeraboxFile]]:
        """Fallback fast public API resolvers for Terabox."""
        # List of reliable public fast bypass APIs
        resolvers = [
            {
                "url": "https://terabox-dl.qtcloud.workers.dev/api/get-info",
                "method": "POST",
                "json": {"url": original_url}
            },
            {
                "url": f"https://yt-api-terabox.vercel.app/api?url={original_url}",
                "method": "GET"
            },
            {
                "url": f"https://teradl-api.dapuntaratya.com/generate_file?url={original_url}",
                "method": "GET"
            },
            {
                "url": f"https://api.syndication.workers.dev/terabox?url={original_url}",
                "method": "GET"
            }
        ]

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

        for resolver in resolvers:
            try:
                if resolver.get("method") == "POST":
                    async with session.post(resolver["url"], json=resolver.get("json"), headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            parsed = cls._parse_resolver_data(data)
                            if parsed:
                                return parsed
                else:
                    async with session.get(resolver["url"], headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            parsed = cls._parse_resolver_data(data)
                            if parsed:
                                return parsed
            except Exception as e:
                logger.debug(f"Resolver {resolver['url']} failed: {e}")
                continue

        return None

    @staticmethod
    def _parse_resolver_data(data: Any) -> Optional[List[TeraboxFile]]:
        """Parses various JSON response schemas from fallback APIs."""
        if not data or not isinstance(data, dict):
            return None

        # Case 1: Standard list format { "list": [ { "filename": "...", "download_link": "...", "size": ... } ] }
        file_list = data.get("list") or data.get("files") or data.get("data")
        if isinstance(file_list, list) and len(file_list) > 0:
            results = []
            for f in file_list:
                if isinstance(f, dict):
                    name = f.get("server_filename") or f.get("filename") or f.get("name") or "video.mp4"
                    dlink = f.get("dlink") or f.get("download_link") or f.get("url") or f.get("direct_link")
                    size = int(f.get("size") or f.get("file_size") or 0)
                    thumb = f.get("thumb") or f.get("thumbnail") or (f.get("thumbs") or {}).get("url3")
                    if dlink:
                        results.append(TeraboxFile(name, dlink, size, thumb, str(f.get("fs_id", ""))))
            if results:
                return results

        # Case 2: Single object format { "file_name": "...", "download_url": "...", "size": ... }
        name = data.get("server_filename") or data.get("filename") or data.get("name") or data.get("file_name")
        dlink = data.get("dlink") or data.get("download_link") or data.get("url") or data.get("direct_link") or data.get("downloadUrl")
        size = int(data.get("size") or data.get("file_size") or 0)
        thumb = data.get("thumb") or data.get("thumbnail")

        if dlink:
            return [TeraboxFile(name or "video.mp4", dlink, size, thumb)]

        return None

    @classmethod
    async def get_download_info(cls, url: str) -> List[TeraboxFile]:
        """Resolves the Terabox link and returns extracted TeraboxFile objects."""
        async with aiohttp.ClientSession() as session:
            # 1. Resolve redirect to canonical URL
            final_url = await cls.resolve_url_redirect(session, url)
            surl = cls.extract_surl(final_url) or cls.extract_surl(url)

            # 2. Try Official API extraction
            if surl:
                files = await cls.extract_via_official_api(session, surl)
                if files:
                    return files

            # 3. Fallback to fast public API extractors
            files = await cls.extract_via_fast_proxies(session, final_url)
            if files:
                return files

            # 4. Fallback with original URL if final_url differed
            if final_url != url:
                files = await cls.extract_via_fast_proxies(session, url)
                if files:
                    return files

        raise ValueError("Could not extract direct download link from this Terabox URL. Link may be expired, password-protected, or invalid.")
