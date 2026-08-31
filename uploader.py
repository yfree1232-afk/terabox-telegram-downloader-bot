import os
import time
import logging
import asyncio
import subprocess
from typing import Optional, Tuple
from pyrogram import Client
from pyrogram.types import Message
from helpers import human_readable_size, format_time, get_progress_bar, clean_temp_files

logger = logging.getLogger(__name__)

def get_video_metadata(video_path: str) -> Tuple[int, int, int]:
    """
    Extracts video duration (seconds), width, and height using ffprobe.
    Returns (duration, width, height).
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration:stream=width,height",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
        
        width = 1280
        height = 720
        duration = 0

        # ffprobe outputs width, height, and duration
        if len(lines) >= 3:
            try:
                width = int(lines[0])
                height = int(lines[1])
                duration = int(float(lines[2]))
            except ValueError:
                pass
        elif len(lines) >= 1:
            try:
                duration = int(float(lines[-1]))
            except ValueError:
                pass

        return duration, width, height
    except Exception as e:
        logger.debug(f"ffprobe extraction failed: {e}")
        return 0, 1280, 720

def generate_thumbnail(video_path: str, output_thumb_path: str, timestamp_sec: int = 2) -> Optional[str]:
    """Generates a JPEG thumbnail from the video file at a given timestamp using ffmpeg."""
    try:
        cmd = [
            "ffmpeg",
            "-ss", str(timestamp_sec),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            "-y",
            output_thumb_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if res.returncode == 0 and os.path.exists(output_thumb_path):
            return output_thumb_path
    except Exception as e:
        logger.debug(f"ffmpeg thumbnail generation failed: {e}")
    return None

class TelegramUploader:
    """Handles streaming upload of videos / documents to Telegram with live progress updates."""

    @staticmethod
    async def upload_video_file(
        client: Client,
        chat_id: int,
        file_path: str,
        status_msg: Message,
        caption: str = "",
        custom_thumb_path: Optional[str] = None,
        reply_to_message_id: Optional[int] = None
    ) -> Message:
        """Uploads video file to Telegram with streamable attributes and live upload progress."""
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        
        # Extract metadata
        duration, width, height = get_video_metadata(file_path)
        
        # Generate thumbnail if not provided
        generated_thumb = None
        thumb_to_use = custom_thumb_path
        if not thumb_to_use:
            thumb_path = f"{file_path}.jpg"
            generated_thumb = generate_thumbnail(file_path, thumb_path, timestamp_sec=min(3, max(1, duration // 2)))
            thumb_to_use = generated_thumb

        start_time = time.time()
        last_update_time = [start_time]

        async def upload_progress(current: int, total: int):
            now = time.time()
            if now - last_update_time[0] >= 3.5:
                last_update_time[0] = now
                elapsed = now - start_time
                speed = current / elapsed if elapsed > 0 else 0
                remaining = total - current if total > current else 0
                eta = remaining / speed if speed > 0 else 0
                pct = (current / total * 100) if total > 0 else 0

                text = (
                    f"📤 **Uploading Video to Telegram...**\n\n"
                    f"📁 **File:** `{filename}`\n"
                    f"📊 **Progress:** {get_progress_bar(pct)}\n"
                    f"💾 **Uploaded:** `{human_readable_size(current)}` / `{human_readable_size(total)}`\n"
                    f"⚡ **Speed:** `{human_readable_size(int(speed))}/s`\n"
                    f"⏱️ **ETA:** `{format_time(eta)}`"
                )
                try:
                    await status_msg.edit_text(text)
                except Exception:
                    pass

        try:
            # Send as streamable video
            sent_msg = await client.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=caption,
                duration=duration,
                width=width,
                height=height,
                thumb=thumb_to_use if (thumb_to_use and os.path.exists(thumb_to_use)) else None,
                supports_streaming=True,
                reply_to_message_id=reply_to_message_id,
                progress=upload_progress
            )
            return sent_msg
        finally:
            # Clean up generated thumbnail
            if generated_thumb:
                clean_temp_files(generated_thumb)
