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
    """Vaqt oralig'ini formatlaydi: '01:23 - 01:45'"""
    return f"{format_time(start)} - {format_time(end)}"


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


def normalize_text_punctuation(text: str) -> str:
    """
    Matndagi tinish belgilarini to'g'ri joylashtiradi va ortiqcha bo'shliqlarni olib tashlaydi.
    Hamma tillar uchun ishlashga moslashadi, shu jumladan arabcha va lotin yozuvlarida.

    Misol:
        "Assalomu Alaykum ! Qadrli yurtdoshlar." -> "Assalomu Alaykum! Qadrli yurtdoshlar."
    """
    if not text:
        return text

    import re

    # Bir nechta bo'shliqlarni bitta bo'shliqga kamaytiramiz, lekin yangi satrni saqlaymiz
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Bo'shliqdan keyin tinish belgilarini olib tashlaymiz
    punctuation = r"\.,!\?;:،؟…，？！；：。"
    text = re.sub(rf"\s+([{punctuation}])", r"\1", text)

    # Agar tinish belgidan keyin darhol harf yoki raqam kelmasa, CJK yozuvida bo'lmasa, bo'shliq qo'yamiz
    cjk_range = r"\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff"
    text = re.sub(rf"([{punctuation}])([^\s{cjk_range}])", r"\1 \2", text)

    return text.strip()


def save_text_file(filepath: str, text: str, normalize: bool = True) -> bool:
    """
    Matnni tekst fayliga saqlaydi.

    Args:
        filepath: Saqlash uchun to'liq yo'l.
        text: Saqlanadigan matn.
        normalize: Ha bo'lsa, matnni tinish belgilarini to'g'rilaydi.

    Returns:
        True agar yozish muvaffaqiyatli bo'lsa, aks holda False.
    """
    if normalize:
        text = normalize_text_punctuation(text)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception as e:
        print(f"[Utils] Matnni saqlashda xato ({filepath}): {e}")
        return False


def score_to_percent(score: float) -> str:
    """O'xshashlik ballini foizga o'tkazadi."""
    return f"{score * 100:.1f}%"


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


def word_overlap_percent(query: str, text: str) -> float:
    """
    Query so'zlaridan qanchasi matnda uchraganini foizda qaytaradi.

    Misol:
        word_overlap_percent("kitob o'qish", "kitob javon") -> 50.0
    """
    if not query or not text:
        return 0.0
    import re

    def _tokenize(s: str):
        return set(
            re.sub(r"[.,!?\"';:()\[\]\-]", "", w).lower()
            for w in s.split()
            if len(w.strip()) > 1
        )

    query_words = _tokenize(query)
    text_words  = _tokenize(text)
    if not query_words:
        return 0.0
    matched = query_words & text_words
    return round(len(matched) / len(query_words) * 100, 1)


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


def segments_to_plain_text(segments: List[Dict]) -> str:
    """
    Segmentlarni faqat matn shaklida, vaqt belgilarisiz qaytaradi.
    Har bir segmentni bitta paragrafga birlashtiradi.
    """
    texts = []
    for seg in segments:
        text = seg.get("text", "")
        if text:
            texts.append(" ".join(text.split()))
    joined = " ".join(texts).strip()
    return normalize_text_punctuation(joined)
