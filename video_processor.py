"""
video_processor.py
------------------
Videodan audio ajratib olish moduli.
moviepy kutubxonasi yordamida ishlaydi.
WAV formatida saqlash tavsiya etiladi (yuqori sifat).
"""

import os
import uuid
import tempfile
import gc
from typing import Optional, Tuple


def extract_audio(
    video_path: str,
    output_dir: Optional[str] = None,
    format: str = "wav",
    sample_rate: int = 16000,
) -> Optional[str]:
    """
    Video fayldan audio ajratib oladi.

    Args:
        video_path: Video fayl to'liq yo'li
        output_dir: Audio saqlanadigan papka (None bo'lsa tempdir ishlatiladi)
        format: Audio format ('wav' yoki 'mp3')
        sample_rate: Namuna chastotasi Hz da (Whisper uchun 16000 tavsiya)

    Returns:
        Audio fayl yo'li yoki None (xato bo'lsa)
    """
    if not os.path.exists(video_path):
        print(f"[VideoProcessor] Fayl topilmadi: {video_path}")
        return None

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="video_ai_")
    else:
        os.makedirs(output_dir, exist_ok=True)

    audio_filename = f"{uuid.uuid4().hex}.{format}"
    audio_path = os.path.join(output_dir, audio_filename)

    try:
        from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_audio
        import subprocess

        # Check if ffmpeg is available
        import shutil
        if not shutil.which("ffmpeg"):
            print("[VideoProcessor] ERROR: ffmpeg NOT FOUND in system path!")
            return None

        # Video yoki faqat audio fayl ekanligini aniqlash
        ext = os.path.splitext(video_path)[1].lower()
        if ext in [".mp3", ".wav", ".flac", ".ogg", ".m4a"]:
            # To'g'ridan-to'g'ri audio fayl bo'lsa, ffmpeg orqali konvertatsiya
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-ac", "1", "-ar", str(sample_rate)
            ]
            if format == "mp3":
                cmd.extend(["-codec:a", "libmp3lame", "-b:a", "64k"])
            cmd.append(audio_path)
        import sys
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[VideoProcessor] Ffmpeg Error (Code {result.returncode}):\n{result.stderr}", file=sys.stderr)
            return None

        print(f"[VideoProcessor] Audio successfully extracted: {audio_path}")
        gc.collect()
        return audio_path

    except ImportError:
        print("[VideoProcessor] moviepy o'rnatilmagan. Quyidagi buyruqni bajaring:")
        print("  pip install moviepy")
        return None
    except Exception as e:
        print(f"[VideoProcessor] Audio ajratishda xato: {e}")
        return None


def get_video_duration(video_path: str) -> Optional[float]:
    """
    Media (video yoki audio) faylning umumiy davomiyligini soniyalarda qaytaradi.
    """
    try:
        ext = os.path.splitext(video_path)[1].lower()
        is_audio = ext in [".mp3", ".wav", ".m4a", ".ogg", ".flac"]
        
        if is_audio:
            from moviepy.editor import AudioFileClip
            with AudioFileClip(video_path) as clip:
                return float(clip.duration)
        else:
            try:
                from moviepy.video.io.VideoFileClip import VideoFileClip
            except ImportError:
                from moviepy.editor import VideoFileClip
            
            with VideoFileClip(video_path) as clip:
                return float(clip.duration)
    except Exception as e:
        print(f"[VideoProcessor] Davomiylikni olishda xato: {e}")
        return None


def get_video_info(video_path: str) -> dict:
    """
    Video haqida asosiy ma'lumotlarni qaytaradi.
    """
    info = {
        "path": video_path,
        "filename": os.path.basename(video_path),
        "size_mb": 0.0,
        "duration_sec": 0.0,
        "has_audio": False,
    }

    if os.path.exists(video_path):
        info["size_mb"] = round(os.path.getsize(video_path) / (1024 * 1024), 2)

    try:
        ext = os.path.splitext(video_path)[1].lower()
        is_audio = ext in [".mp3", ".wav", ".m4a", ".ogg", ".flac"]

        if is_audio:
            from moviepy.editor import AudioFileClip
            with AudioFileClip(video_path) as clip:
                info["duration_sec"] = round(float(clip.duration), 2)
                info["has_audio"] = True
                info["fps"] = 0
                info["size"] = (0, 0)
        else:
            try:
                from moviepy.video.io.VideoFileClip import VideoFileClip
            except ImportError:
                from moviepy.editor import VideoFileClip
            
            with VideoFileClip(video_path) as clip:
                info["duration_sec"] = round(float(clip.duration), 2)
                info["has_audio"] = bool(clip.audio is not None)
                info["fps"] = round(float(getattr(clip, "fps", 0)), 2)
                info["size"] = getattr(clip, "size", (0, 0))
    except Exception as e:
        print(f"[VideoProcessor] Media ma'lumotida xato: {e}")

    return info
