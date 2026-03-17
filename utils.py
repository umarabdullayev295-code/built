"""
utils.py
--------
Yordamchi funksiyalar moduli.
"""

import os
import shutil
import time
from typing import Optional, List, Dict


def format_time(seconds: float) -> str:
    """
    Soniyalarni MM:SS yoki HH:MM:SS formatiga o'tkazadi.
    
    Misol:
        format_time(75) -> "01:15"
        format_time(3723) -> "01:02:03"
    """
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_time_range(start: float, end: float) -> str:
    """Vaqt oralig'ini formatlaydi: '01:23 → 01:45'"""
    return f"{format_time(start)} → {format_time(end)}"


def cleanup_file(filepath: Optional[str]) -> bool:
    """
    Faylni o'chiradi.
    
    Returns:
        True — muvaffaqiyatli, False — xato
    """
    if not filepath:
        return False
    try:
        if os.path.isfile(filepath):
            os.remove(filepath)
            return True
        elif os.path.isdir(filepath):
            shutil.rmtree(filepath)
            return True
    except Exception as e:
        print(f"[Utils] Faylni o'chirishda xato ({filepath}): {e}")
    return False


def cleanup_files(*filepaths: str) -> None:
    """Bir nechta faylni o'chiradi."""
    for fp in filepaths:
        cleanup_file(fp)


def score_to_percent(score: float) -> str:
    """O'xshashlik ballini foizga o'tkazadi."""
    return f"{score * 100:.1f}%"


def score_to_stars(score: float) -> str:
    """O'xshashlik ballini yulduzchalar bilan ifodalaydi."""
    stars = int(round(score * 5))
    return "⭐" * stars + "☆" * (5 - stars)


def get_similarity_label(score: float) -> tuple:
    """
    O'xshashlik darajasiga mos yorliq va rangni qaytaradi.
    
    Returns:
        (label: str, color: str)
    """
    if score >= 0.85:
        return "Juda yuqori", "#00c853"
    elif score >= 0.65:
        return "Yuqori", "#64dd17"
    elif score >= 0.45:
        return "O'rtacha", "#ffd600"
    elif score >= 0.25:
        return "Past", "#ff6d00"
    else:
        return "Juda past", "#d50000"


def highlight_text(text: str, query: str) -> str:
    """
    Matndagi qidiruv so'zlarini ajratib ko'rsatadi (HTML formati).
    """
    if not query or not text:
        return text

    import re
    words = [w.strip() for w in query.split() if w.strip()]
    result = text
    for word in words:
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        result = pattern.sub(
            lambda m: f'<mark style="background:#ffe082;padding:0 2px;border-radius:3px">{m.group()}</mark>',
            result,
        )
    return result


def segments_to_srt(segments: List[Dict]) -> str:
    """
    Segmentlarni SRT (subtitle) formatiga o'tkazadi.
    """
    lines = []
    for i, seg in enumerate(segments, 1):
        start_srt = _seconds_to_srt_time(seg["start"])
        end_srt = _seconds_to_srt_time(seg["end"])
        lines.append(f"{i}\n{start_srt} --> {end_srt}\n{seg['text']}\n")
    return "\n".join(lines)


def _seconds_to_srt_time(seconds: float) -> str:
    """Soniyalarni SRT vaqt formatiga o'tkazadi: HH:MM:SS,mmm"""
    ms = int((seconds % 1) * 1000)
    total_sec = int(seconds)
    m, s = divmod(total_sec, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_vtt(segments: List[Dict]) -> str:
    """
    Segmentlarni WebVTT (subtitle) formatiga o'tkazadi.
    HTML5 / Streamlit video playerlar uchun kerak.
    """
    lines = ["WEBVTT\n"]
    for i, seg in enumerate(segments, 1):
        start_vtt = _seconds_to_vtt_time(seg["start"])
        end_vtt = _seconds_to_vtt_time(seg["end"])
        lines.append(f"{i}\n{start_vtt} --> {end_vtt}\n{seg['text']}\n")
    return "\n".join(lines)


def _seconds_to_vtt_time(seconds: float) -> str:
    """Soniyalarni VTT vaqt formatiga o'tkazadi: HH:MM:SS.mmm"""
    ms = int((seconds % 1) * 1000)
    total_sec = int(seconds)
    m, s = divmod(total_sec, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def segments_to_text(segments: List[Dict], include_timestamps: bool = True) -> str:
    """
    Segmentlarni o'qish uchun qulay matn formatiga o'tkazadi.
    """
    lines = []
    for seg in segments:
        if include_timestamps:
            ts = format_time_range(seg["start"], seg["end"])
            lines.append(f"[{ts}] {seg['text']}")
        else:
            lines.append(seg["text"])
    return "\n".join(lines)


def safe_filename(name: str, max_length: int = 50) -> str:
    """Fayl nomidan xavfli belgilarni olib tashlaydi."""
    import re
    safe = re.sub(r'[\\/:*?"<>|]', "_", name)
    return safe[:max_length]
