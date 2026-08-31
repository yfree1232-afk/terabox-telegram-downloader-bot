import os
import time
import logging
import asyncio
import subprocess
import aiohttp
import aiofiles
from typing import Callable, Optional, List
from config import DOWNLOAD_DIR
from helpers import clean_filename, human_readable_size, format_time, get_progress_bar, clean_temp_files

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"

class Downloader:
    """Handles async streaming segment downloading and remuxing with live progress updates."""

    @staticmethod
    async def download_segments(
        segment_urls: List[str],
        filename: str,
        total_size: int = 0,
        progress_callback: Optional[Callable] = None
    ) -> str:
        safe_filename = clean_filename(filename)
        base_name, _ = os.path.splitext(safe_filename)
        raw_ts_path = os.path.join(DOWNLOAD_DIR, f"{int(time.time())}_{base_name}.ts")
        final_mp4_path = os.path.join(DOWNLOAD_DIR, f"{int(time.time())}_{base_name}.mp4")

        total_segments = len(segment_urls)
        downloaded_bytes = 0
        start_time = time.time()
        last_update_time = start_time

        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        timeout = aiohttp.ClientTimeout(total=3600, connect=20, sock_read=40)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with aiofiles.open(raw_ts_path, mode="wb") as f_out:
                for idx, seg_url in enumerate(segment_urls, 1):
                    async with session.get(seg_url, headers=headers) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            await f_out.write(content)
                            downloaded_bytes += len(content)

                    current_time = time.time()
                    if progress_callback and (current_time - last_update_time >= 3.0 or idx == total_segments):
                        elapsed = current_time - start_time
                        speed = downloaded_bytes / elapsed if elapsed > 0 else 0
                        pct = (idx / total_segments) * 100
                        remaining_segs = total_segments - idx
                        time_per_seg = elapsed / idx if idx > 0 else 0
                        eta = remaining_segs * time_per_seg

                        text = (
                            f"📥 **Downloading Terabox Stream...**\n\n"
                            f"📁 **File:** `{safe_filename}`\n"
                            f"📊 **Progress:** {get_progress_bar(pct)}\n"
                            f"📦 **Segments:** `{idx}/{total_segments}`\n"
                            f"💾 **Downloaded:** `{human_readable_size(downloaded_bytes)}`\n"
                            f"⚡ **Speed:** `{human_readable_size(int(speed))}/s`\n"
                            f"⏱️ **ETA:** `{format_time(eta)}`"
                        )
                        try:
                            await progress_callback(text)
                        except Exception:
                            pass
                        last_update_time = current_time

        # Remux raw .ts to playable .mp4 with ffmpeg
        if progress_callback:
            try:
                await progress_callback("⚙️ **Remuxing Video Stream to MP4...**\n*Almost ready to upload!*")
            except Exception:
                pass

        cmd = [
            "ffmpeg",
            "-y",
            "-i", raw_ts_path,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            final_mp4_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        # Cleanup raw ts file
        clean_temp_files(raw_ts_path)

        if os.path.exists(final_mp4_path) and os.path.getsize(final_mp4_path) > 0:
            return os.path.abspath(final_mp4_path)

        # If remux failed, return raw ts file if it exists
        if os.path.exists(raw_ts_path):
            return os.path.abspath(raw_ts_path)

        raise Exception("Failed to generate playable MP4 file from video stream.")
