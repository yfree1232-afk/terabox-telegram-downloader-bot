import os
import time
import logging
import aiohttp
import aiofiles
from typing import Callable, Optional
from config import CHUNK_SIZE, TERABOX_COOKIE, DOWNLOAD_DIR
from helpers import clean_filename, human_readable_size, format_time, get_progress_bar

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

class Downloader:
    """Handles async streaming file downloads with throttled real-time progress callbacks."""

    @staticmethod
    async def download_file(
        download_url: str,
        filename: str,
        total_size: int = 0,
        progress_callback: Optional[Callable] = None,
        custom_headers: Optional[dict] = None
    ) -> str:
        """
        Downloads a file chunk-by-chunk and updates the progress callback periodically.
        Returns the absolute local path to the downloaded file.
        """
        safe_filename = clean_filename(filename)
        destination_path = os.path.join(DOWNLOAD_DIR, f"{int(time.time())}_{safe_filename}")

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Connection": "keep-alive",
        }
        if custom_headers:
            headers.update(custom_headers)
        if TERABOX_COOKIE and "Cookie" not in headers:
            headers["Cookie"] = f"ndus={TERABOX_COOKIE}"

        timeout = aiohttp.ClientTimeout(total=3600, connect=30, sock_read=60)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(download_url, headers=headers, allow_redirects=True) as response:
                if response.status not in (200, 206):
                    raise Exception(f"Server returned HTTP status code {response.status}")

                content_len = response.headers.get("Content-Length")
                if content_len and content_len.isdigit():
                    total_size = int(content_len)

                downloaded_bytes = 0
                start_time = time.time()
                last_update_time = start_time

                async with aiofiles.open(destination_path, mode="wb") as f:
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        if not chunk:
                            break
                        await f.write(chunk)
                        downloaded_bytes += len(chunk)

                        current_time = time.time()
                        # Throttle progress updates to every 3.5 seconds
                        if progress_callback and (current_time - last_update_time >= 3.5):
                            elapsed = current_time - start_time
                            speed = downloaded_bytes / elapsed if elapsed > 0 else 0
                            remaining_bytes = total_size - downloaded_bytes if total_size > downloaded_bytes else 0
                            eta = remaining_bytes / speed if speed > 0 else 0
                            percentage = (downloaded_bytes / total_size * 100) if total_size > 0 else 0

                            text = (
                                f"📥 **Downloading Video from Terabox...**\n\n"
                                f"📁 **File:** `{safe_filename}`\n"
                                f"📊 **Progress:** {get_progress_bar(percentage)}\n"
                                f"💾 **Size:** `{human_readable_size(downloaded_bytes)}` / `{human_readable_size(total_size)}`\n"
                                f"⚡ **Speed:** `{human_readable_size(int(speed))}/s`\n"
                                f"⏱️ **ETA:** `{format_time(eta)}`"
                            )

                            try:
                                await progress_callback(text)
                            except Exception as e:
                                logger.debug(f"Progress callback error: {e}")

                            last_update_time = current_time

        return os.path.abspath(destination_path)
