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
        print(f"ERROR: Input video file not found at {video_path}", file=sys.stderr)
        return None

    # Diagnostic: Check if ffmpeg exists
    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        print("CRITICAL: ffmpeg not found in PATH via shutil.which!", file=sys.stderr)
        # Fix: Common absolute paths on Linux/Streamlit Cloud
        for path in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/avconv"]:
            if os.path.exists(path):
                ffmpeg_exe = path
                print(f"DEBUG: Found ffmpeg at {ffmpeg_exe}")
                break
    
    if not ffmpeg_exe:
        print("ERROR: ffmpeg is completely missing from the system environment.", file=sys.stderr)
        return None

    # Create a stable temp path
    temp_dir = tempfile.gettempdir()
    timestamp = int(time.time() * 1000)
    audio_output_path = os.path.join(temp_dir, f"audio_{timestamp}.{output_ext}")

    command = [
        ffmpeg_exe, 
        "-i", video_path, 
        "-vn", 
        "-acodec", "pcm_s16le" if output_ext == "wav" else "libmp3lame", 
        "-ar", "16000", 
        "-ac", "1", 
        audio_output_path, 
        "-y"
    ]

    try:
        print(f"DEBUG: Running command: {' '.join(command)}")
        # Note: We use capture_output=True to get stderr/stdout for logging on failure
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        if os.path.exists(audio_output_path) and os.path.getsize(audio_output_path) > 0:
            print(f"SUCCESS: Audio extracted to {audio_output_path} ({os.path.getsize(audio_output_path)} bytes)")
            return audio_output_path
        else:
            print(f"ERROR: ffmpeg finished but output file is missing or empty: {audio_output_path}", file=sys.stderr)
            return None

    except subprocess.CalledProcessError as e:
        print(f"FAILED: ffmpeg audio extraction failed with exit code {e.returncode}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"UNEXPECTED EXTRACTION ERROR: {str(e)}", file=sys.stderr)
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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
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
