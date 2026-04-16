"""
video_processor.py
------------------
Videodan audio ajratib olish moduli.
ffmpeg yordamida ishlaydi.
WAV formatida saqlash tavsiya etiladi (Whisper uchun eng barqaror).
"""

import os
import sys
import tempfile
import time
import shutil
import uuid
import gc
import subprocess
from typing import Optional, List, Dict, Tuple

_SUBPROCESS_TEXT_KWARGS = {
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
}


def _safe_text(msg: str) -> str:
    txt = str(msg)
    enc = getattr(sys.stderr, "encoding", None) or "utf-8"
    try:
        txt.encode(enc, errors="strict")
        return txt
    except Exception:
        return txt.encode(enc, errors="replace").decode(enc, errors="replace")


def _log(msg: str) -> None:
    print(_safe_text(msg))


def _log_err(msg: str) -> None:
    print(_safe_text(msg), file=sys.stderr)

def extract_audio(video_path: str, output_ext: str = "wav") -> Optional[str]:
    """
    Video fayldan audio ajratib oladi.

    Args:
        video_path: Video fayl to'liq yo'li
        output_ext: Audio format ('wav' yoki 'mp3')

    Returns:
        Audio fayl yo'li yoki None (xato bo'lsa)
    """
    if not os.path.exists(video_path):
        _log_err(f"ERROR: Input video file not found at {video_path}")
        return None

    # Diagnostic: Check if ffmpeg exists
    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        _log_err("CRITICAL: ffmpeg not found in PATH via shutil.which!")
        # Fix: Common absolute paths on Linux/Streamlit Cloud
        for path in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/avconv"]:
            if os.path.exists(path):
                ffmpeg_exe = path
                _log(f"DEBUG: Found ffmpeg at {ffmpeg_exe}")
                break
    
    if not ffmpeg_exe:
        _log_err("ERROR: ffmpeg is completely missing from the system environment.")
        return None

    # Create a stable temp path
    temp_dir = tempfile.gettempdir()
    timestamp = int(time.time() * 1000)
    audio_output_path = os.path.join(temp_dir, f"audio_{timestamp}.{output_ext}")

    command = [
        ffmpeg_exe, 
        "-nostdin",
        "-hide_banner",
        "-i", video_path, 
        "-vn", 
        "-acodec", "pcm_s16le" if output_ext == "wav" else "libmp3lame", 
        "-ar", "16000", 
        "-ac", "1", 
        audio_output_path, 
        "-y"
    ]

    try:
        _log(f"DEBUG: Running command: {' '.join(command)}")
        # Note: We use capture_output=True to get stderr/stdout for logging on failure
        result = subprocess.run(command, capture_output=True, check=True, **_SUBPROCESS_TEXT_KWARGS)
        
        if os.path.exists(audio_output_path) and os.path.getsize(audio_output_path) > 0:
            _log(f"SUCCESS: Audio extracted to {audio_output_path} ({os.path.getsize(audio_output_path)} bytes)")
            return audio_output_path
        else:
            _log_err(f"ERROR: ffmpeg finished but output file is missing or empty: {audio_output_path}")
            return None

    except subprocess.CalledProcessError as e:
        _log(f"FAILED: ffmpeg audio extraction failed with exit code {e.returncode}")
        _log(f"STDOUT: {e.stdout}")
        _log_err(f"STDERR: {e.stderr}")
        return None
    except Exception as e:
        _log_err(f"UNEXPECTED EXTRACTION ERROR: {str(e)}")
        return None

def get_video_duration(video_path: str) -> Optional[float]:
    """
    Media (video yoki audio) faylning umumiy davomiyligini soniyalarda qaytaradi.
    FFmpeg orqali olish tavsiya etiladi (moviepy dan ko'ra yengilroq).
    """
    try:
        ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"
        # ffprobe is part of ffmpeg suite
        ffprobe_exe = shutil.which("ffprobe") or "ffprobe"
        
        cmd = [
            ffprobe_exe, 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, check=True, **_SUBPROCESS_TEXT_KWARGS)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[VideoProcessor] Davomiylikni olishda xato: {e}")
        return 0.0

def get_video_info(video_path: str) -> dict:
    """
    Video haqida asosiy ma'lumotlarni qaytaradi.
    """
    return {
        "path": video_path,
        "filename": os.path.basename(video_path),
        "duration_sec": get_video_duration(video_path)
    }
