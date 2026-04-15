"""
video_processor.py
------------------
Videodan audio ajratib olish moduli.
ffmpeg yordamida ishlaydi.
WAV formatida saqlash tavsiya etiladi (Whisper uchun eng barqaror).
"""

import os
import re
import sys
import tempfile
import time
import shutil
import subprocess
from typing import List, Optional

# So'nggi audio ajratish xatosi (UI da ko'rsatish uchun)
LAST_AUDIO_EXTRACT_DIAGNOSTIC: Optional[str] = None

# ffmpeg -i stderr dan: Stream #0:1(und): Audio: ...
_FFMPEG_AUDIO_STREAM_RE = re.compile(
    r"Stream\s+#0:(\d+)(?:\([^)]*\))?:\s*Audio:",
    re.IGNORECASE,
)


def _ffprobe_audio_stream_indices(video_path: str) -> List[int]:
    """Fayldagi barcha audio oqimlarining global indekslari (0, 1, 2, ...)."""
    ffprobe = _resolve_ffprobe_exe()
    if not ffprobe:
        return []
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        video_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not (r.stdout or "").strip():
        return []
    out: List[int] = []
    for line in (r.stdout or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(int(line))
        except ValueError:
            continue
    return out


def _ffmpeg_stderr_audio_indices(video_path: str, ffmpeg_exe: str) -> List[int]:
    """ffprobe bo'lmasa, ffmpeg -i chiqishidan audio oqim indekslarini olish."""
    try:
        r = subprocess.run(
            [ffmpeg_exe, "-nostdin", "-hide_banner", "-i", video_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    return [int(m.group(1)) for m in _FFMPEG_AUDIO_STREAM_RE.finditer(r.stderr or "")]


def _audio_map_candidates(video_path: str, ffmpeg_exe: str) -> List[Optional[str]]:
    """
    Urinish tartibi: aniq oqim indekslari, keyin 0:a:0..2, oxirida avtomatik tanlash (None).
    """
    seen = set()
    ordered: List[Optional[str]] = []

    def add(m: Optional[str]) -> None:
        if m in seen:
            return
        seen.add(m)
        ordered.append(m)

    for idx in _ffprobe_audio_stream_indices(video_path):
        add(f"0:{idx}")
    for idx in _ffmpeg_stderr_audio_indices(video_path, ffmpeg_exe):
        add(f"0:{idx}")
    for i in range(4):
        add(f"0:a:{i}")
    add(None)
    return ordered


def _run_ffmpeg_extract(
    ffmpeg_exe: str,
    video_path: str,
    audio_output_path: str,
    output_ext: str,
    map_arg: Optional[str],
) -> subprocess.CompletedProcess:
    acodec = "pcm_s16le" if output_ext == "wav" else "libmp3lame"
    cmd: List[str] = [
        ffmpeg_exe,
        "-nostdin",
        "-hide_banner",
        "-err_detect",
        "ignore_err",
        "-i",
        video_path,
        "-vn",
    ]
    if map_arg:
        cmd.extend(["-map", map_arg])
    cmd.extend(
        [
            "-acodec",
            acodec,
            "-ar",
            "16000",
            "-ac",
            "1",
            audio_output_path,
            "-y",
        ]
    )
    return subprocess.run(cmd, capture_output=True, text=True)


def _resolve_ffmpeg_exe() -> Optional[str]:
    """Tizim PATH, standart Linux yo'llar, so'ng imageio-ffmpeg (Windows uchun)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    for path in ("/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/avconv"):
        if os.path.isfile(path):
            return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        print(f"[video_processor] imageio-ffmpeg orqali ffmpeg topilmadi: {e}", file=sys.stderr)
    return None


def _resolve_ffprobe_exe() -> Optional[str]:
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    ffmpeg_exe = _resolve_ffmpeg_exe()
    if not ffmpeg_exe:
        return None
    d = os.path.dirname(ffmpeg_exe)
    for name in ("ffprobe", "ffprobe.exe"):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def extract_audio(video_path: str, output_ext: str = "wav") -> Optional[str]:
    """
    Video fayldan audio ajratib oladi.

    Args:
        video_path: Video fayl to'liq yo'li
        output_ext: Audio format ('wav' yoki 'mp3')

    Returns:
        Audio fayl yo'li yoki None (xato bo'lsa)
    """
    global LAST_AUDIO_EXTRACT_DIAGNOSTIC
    LAST_AUDIO_EXTRACT_DIAGNOSTIC = None

    if not os.path.exists(video_path):
        print(f"ERROR: Input video file not found at {video_path}", file=sys.stderr)
        LAST_AUDIO_EXTRACT_DIAGNOSTIC = f"Kirish fayli topilmadi: {video_path}"
        return None

    ffmpeg_exe = _resolve_ffmpeg_exe()
    if not ffmpeg_exe:
        print("ERROR: ffmpeg is completely missing from the system environment.", file=sys.stderr)
        LAST_AUDIO_EXTRACT_DIAGNOSTIC = (
            "ffmpeg topilmadi. `pip install imageio-ffmpeg` yoki https://ffmpeg.org/download.html "
            "orqali o'rnating va PATH ga qo'shing."
        )
        return None

    # Create a stable temp path
    temp_dir = tempfile.gettempdir()
    timestamp = int(time.time() * 1000)
    audio_output_path = os.path.join(temp_dir, f"audio_{timestamp}.{output_ext}")

    candidates = _audio_map_candidates(video_path, ffmpeg_exe)
    last_stderr = ""

    try:
        for map_arg in candidates:
            label = map_arg if map_arg else "(avtomatik tanlash)"
            print(f"DEBUG: Audio ajratish, -map {label}")
            result = _run_ffmpeg_extract(
                ffmpeg_exe, video_path, audio_output_path, output_ext, map_arg
            )
            if result.returncode != 0:
                last_stderr = (result.stderr or result.stdout or "").strip() or last_stderr
                continue
            if os.path.exists(audio_output_path) and os.path.getsize(audio_output_path) > 0:
                print(
                    f"SUCCESS: Audio extracted to {audio_output_path} "
                    f"({os.path.getsize(audio_output_path)} bytes), map={label}"
                )
                return audio_output_path
            last_stderr = "ffmpeg 0 kod bilan tugadi, lekin chiqish fayli bo'sh."

        print(f"FAILED: barcha -map strategiyalari yiqildi. Oxirgi stderr: {last_stderr[:500]}", file=sys.stderr)
        LAST_AUDIO_EXTRACT_DIAGNOSTIC = last_stderr or "Audio ajratilmadi (barcha urinishlar muvaffaqiyatsiz)."
        return None

    except Exception as e:
        print(f"UNEXPECTED EXTRACTION ERROR: {str(e)}", file=sys.stderr)
        LAST_AUDIO_EXTRACT_DIAGNOSTIC = str(e)
        return None

def get_video_duration(video_path: str) -> Optional[float]:
    """
    Media (video yoki audio) faylning umumiy davomiyligini soniyalarda qaytaradi.
    FFmpeg orqali olish tavsiya etiladi (moviepy dan ko'ra yengilroq).
    """
    try:
        ffprobe_exe = _resolve_ffprobe_exe()
        if ffprobe_exe:
            cmd = [
                ffprobe_exe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            out = result.stdout.strip()
            if out and out != "N/A":
                return float(out)

        ffmpeg_exe = _resolve_ffmpeg_exe()
        if ffmpeg_exe:
            r = subprocess.run(
                [ffmpeg_exe, "-nostdin", "-hide_banner", "-i", video_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr or "")
            if m:
                h, mi, s = m.groups()
                return int(h) * 3600 + int(mi) * 60 + float(s)
        return 0.0
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
