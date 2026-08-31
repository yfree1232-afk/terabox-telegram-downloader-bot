import re
import logging
import aiohttp
import urllib.parse
from typing import Optional, Dict, Any, List
from config import TERABOX_COOKIE

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

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
        """Extracts the surl key from any Terabox link format."""
        if not url:
            return None
        
        # Format: ?surl=... or &surl=...
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "surl" in qs and qs["surl"]:
            surl = qs["surl"][0]
            return surl if surl.startswith("1") else "1" + surl
        
        # Format: /s/1... or /s/...
        match_path = re.search(r"/s/([a-zA-Z0-9_\-]+)", url)
        if match_path:
            surl = match_path.group(1)
            return surl if surl.startswith("1") else "1" + surl
        
        # Search anywhere in path for surl
        match_general = re.search(r"surl=([a-zA-Z0-9_\-]+)", url)
        if match_general:
            surl = match_general.group(1)
            return surl if surl.startswith("1") else "1" + surl

        return None

    @classmethod
    async def resolve_url_redirect(cls, session: aiohttp.ClientSession, url: str) -> str:
        """Resolves redirects to get the full final target URL."""
        headers = {"User-Agent": USER_AGENT}
        try:
            async with session.get(url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return str(resp.url)
        except Exception:
            return url

    @classmethod
    async def extract_via_official_api(cls, session: aiohttp.ClientSession, surl: str) -> Optional[List[TeraboxFile]]:
        """Extracts direct download links using Terabox web APIs."""
        clean_surl = surl.lstrip("1")
        domains = ["www.terabox.app", "www.1024tera.com", "www.terabox.com"]

        for domain in domains:
            api_url = f"https://{domain}/share/list?app_id=250528&shorturl={clean_surl}&root=1"
            headers = {
                "User-Agent": USER_AGENT,
                "Referer": f"https://{domain}/sharing/link?surl={clean_surl}",
                "Accept": "application/json, text/plain, */*",
            }
            if TERABOX_COOKIE:
                headers["Cookie"] = f"ndus={TERABOX_COOKIE}"

            try:
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
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
                logger.debug(f"Official API ({domain}) error: {e}")
                continue
        return None

    @classmethod
    async def extract_via_fast_proxies(cls, session: aiohttp.ClientSession, original_url: str) -> Optional[List[TeraboxFile]]:
        """Fallback fast public API resolvers for Terabox."""
        encoded_url = urllib.parse.quote(original_url, safe="")
        
        resolvers = [
            {
                "url": "https://terabox-dl.qtcloud.workers.dev/api/get-info",
                "method": "POST",
                "json": {"url": original_url}
            },
            {
                "url": "https://terabox.hnn.workers.dev/api/get-info",
                "method": "POST",
                "json": {"url": original_url}
            },
            {
                "url": f"https://yt-api-terabox.vercel.app/api?url={encoded_url}",
                "method": "GET"
            },
            {
                "url": f"https://teradl-api.dapuntaratya.com/generate_file?url={encoded_url}",
                "method": "GET"
            },
            {
                "url": f"https://terabox.astad.co/api/terabox?url={encoded_url}",
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
                    async with session.post(resolver["url"], json=resolver.get("json"), headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            parsed = cls._parse_resolver_data(data)
                            if parsed:
                                return parsed
                else:
                    async with session.get(resolver["url"], headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            parsed = cls._parse_resolver_data(data)
                            if parsed:
                                return parsed
            except Exception as e:
                logger.debug(f"Resolver {resolver['url']} notice: {e}")
                continue

        return None

    @staticmethod
    def _parse_resolver_data(data: Any) -> Optional[List[TeraboxFile]]:
        """Parses various JSON response schemas from fallback APIs."""
        if not data:
            return None

        # If data is a list
        if isinstance(data, list) and len(data) > 0:
            results = []
            for f in data:
                if isinstance(f, dict):
                    name = f.get("server_filename") or f.get("filename") or f.get("name") or f.get("file_name") or "video.mp4"
                    dlink = f.get("dlink") or f.get("download_link") or f.get("url") or f.get("direct_link") or f.get("downloadUrl")
                    size = int(f.get("size") or f.get("file_size") or 0)
                    thumb = f.get("thumb") or f.get("thumbnail") or (f.get("thumbs") or {}).get("url3")
                    if dlink:
                        results.append(TeraboxFile(name, dlink, size, thumb, str(f.get("fs_id", ""))))
            if results:
                return results

        if not isinstance(data, dict):
            return None

        # Case 1: Nested files array { "list": [...] } or { "data": [...] }
        file_list = data.get("list") or data.get("files") or data.get("data") or data.get("result")
        if isinstance(file_list, list) and len(file_list) > 0:
            results = []
            for f in file_list:
                if isinstance(f, dict):
                    name = f.get("server_filename") or f.get("filename") or f.get("name") or f.get("file_name") or "video.mp4"
                    dlink = f.get("dlink") or f.get("download_link") or f.get("url") or f.get("direct_link") or f.get("downloadUrl")
                    size = int(f.get("size") or f.get("file_size") or 0)
                    thumb = f.get("thumb") or f.get("thumbnail") or (f.get("thumbs") or {}).get("url3")
                    if dlink:
                        results.append(TeraboxFile(name, dlink, size, thumb, str(f.get("fs_id", ""))))
            if results:
                return results

        # Case 2: Single object format { "file_name": "...", "download_url": "...", "size": ... }
        name = data.get("server_filename") or data.get("filename") or data.get("name") or data.get("file_name") or data.get("title")
        dlink = data.get("dlink") or data.get("download_link") or data.get("url") or data.get("direct_link") or data.get("downloadUrl") or data.get("download")
        size = int(data.get("size") or data.get("file_size") or 0)
        thumb = data.get("thumb") or data.get("thumbnail")

        if dlink and isinstance(dlink, str) and dlink.startswith("http"):
            return [TeraboxFile(name or "video.mp4", dlink, size, thumb)]

        return None

    @classmethod
    async def get_download_info(cls, url: str) -> List[TeraboxFile]:
        """Resolves the Terabox link and returns extracted TeraboxFile objects."""
        clean_url = url.strip()
        async with aiohttp.ClientSession() as session:
            # 1. Resolve redirect to final canonical URL
            final_url = await cls.resolve_url_redirect(session, clean_url)
            
            # Extract surl from both final_url and original clean_url
            surl = cls.extract_surl(final_url) or cls.extract_surl(clean_url)

            # 2. Try Web APIs with surl
            if surl:
                files = await cls.extract_via_official_api(session, surl)
                if files:
                    return files

            # 3. Try fast API extractors with clean_url
            files = await cls.extract_via_fast_proxies(session, clean_url)
            if files:
                return files

            # 4. Try fast API extractors with final_url
            if final_url != clean_url:
                files = await cls.extract_via_fast_proxies(session, final_url)
                if files:
                    return files

            # 5. If surl is present, construct canonical sharing link and try
            if surl:
                canonical_link = f"https://www.terabox.app/sharing/link?surl={surl.lstrip('1')}"
                files = await cls.extract_via_fast_proxies(session, canonical_link)
                if files:
                    return files

        raise ValueError("Could not extract direct download link from this Terabox URL. Link may be expired, password-protected, or invalid.")
