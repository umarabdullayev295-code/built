"""
subtitle_engine.py
------------------
Professional real-time subtitle engine.
- YouTube Shorts / TikTok uslubida so'z-so'z yoki karaoke subtitr
- Avtomatik timestamp scale (video va audio davomiyliklari farqini to'g'rilash)
- 3 ta caption rejimi: 1-Word, Progressive, Karaoke
- requestAnimationFrame asosidagi real-time JS engine (lag yo'q)
- Debug rejim: video/audio/timestamp farqini ko'rsatadi
"""

import streamlit as st
import base64
import os
from typing import List, Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY: Video b64 encoding (keshlanadi — har safar qayta o'qilmaydi)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def get_video_b64(video_path: str, cache_key: str = "") -> str:
    """Video faylni base64 ko'rinishida o'qiydi va keshlaydi."""
    try:
        with open(video_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"[SubtitleEngine] b64 xato: {e}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# CORE: Timestamp auto-scaler
# ─────────────────────────────────────────────────────────────────────────────

def scale_timestamps(
    segments: List[Dict],
    video_duration: float,
    debug: bool = False,
) -> List[Dict]:
    """
    Subtitlelar juda tez yoki kech chiqsa bu funksiya vaqtlarni
    video davomiyligiga mos ravishda avtomatik miqyoslashtiradi (scale).

    Muammo sababi:
        Whisper yoki boshqa STT modeli audiodagi oxirgi so'zni
        video haqiqiy uzunligidan qisqa deb baholaydi.
        Masalan: 60s video lekin max_timestamp=8s → scale=60/8=7.5x

    Args:
        segments      : Word-level segment list [{start, end, text}, ...]
        video_duration: ffprobe orqali olingan haqiqiy video uzunligi (s)
        debug         : True bo'lsa Streamlit'da debug ma'lumotlarini chiqaradi

    Returns:
        Scale qilingan yoki o'zgarmagan segments
    """
    if not segments or video_duration <= 0:
        return segments

    # Muxlisa+audio alignment orqali "lock" qilingan timingga scale tegmasin.
    if segments and segments[0].get("__timing_locked__", False):
        return segments

    # Oldin scale qilingan bo'lsa, qayta scale qilmaymiz (double-scalingdan himoya)
    if segments and segments[0].get("__scaled__", False):
        return segments

    # Barcha so'zlardan maksimal vaqtni aniqlaymiz
    max_timestamp = max(s.get("end", 0) for s in segments)

    # Video va subtitr uzunliklari o'rtasidagi farq nisbati
    diff_ratio = abs(video_duration - max_timestamp) / video_duration
    
    # Subtitr va video davomiyligi sezilarli farq qilsa scale qilamiz.
    # Juda kichik farqni (2% gacha) o'zgartirmaymiz.
    if max_timestamp > 0 and 0.02 < diff_ratio < 0.35:
        scale = video_duration / max_timestamp

        if debug:
            st.warning(
                f"⚠️ **Timing noto'g'ri!** Scale koeffitsienti: **{scale:.3f}x**  \n"
                f"Barcha {len(segments)} ta so'z vaqtlari ozgina to'g'irlanmoqda..."
            )

        scaled = []
        for s in segments:
            scaled.append({
                **s,
                "start": round(s.get("start", 0) * scale, 3),
                "end": round(s.get("end", 0) * scale, 3),
                "__scaled__": True,
                "__scale_factor__": round(scale, 6),
            })

        if debug:
            st.success(f"✅ Scale muvaffaqiyatli: {scale:.3f}x qo'llanildi")

        return scaled

    if debug:
        st.success("✅ Timing aniq — (Katta siljish mavjud emas)")

    return segments


# ─────────────────────────────────────────────────────────────────────────────
# MAIN: Professional video player with real-time subtitle engine
# ─────────────────────────────────────────────────────────────────────────────

def render_youtube_player(
    video_path: str,
    segments: List[Dict],
    start_time: float = 0.0,
    video_duration: float = 0.0,
    debug: bool = False,
    latency_offset: float = 0.0
):
    """
    TikTok/YouTube Shorts uslubidagi professional subtitle player.

    Args:
        video_path    : MP4 fayl yo'li
        segments      : Word-level [{start, end, text}, ...] list
        start_time    : Videoni shu vaqtdan boshlash (qidiruv natijasida)
        video_duration: Video haqiqiy davomiyligi (scale uchun)
        debug         : Timing debug ma'lumotlarini ko'rsatish
    """

    # ── Fayl tekshiruvi ──
    if not video_path or not os.path.exists(video_path):
        st.error("❌ Media fayl topilmadi.")
        return

    if not segments:
        st.warning("⚠️ Subtitlelar uchun segment ma'lumotlari topilmadi.")
        return

    # Qidiruvdan bosilganda aynan topilgan vaqtdan boshlaymiz.
    if start_time > 0:
        start_time = max(0.0, float(start_time))

    # ── Timestamp auto-scale ──
    if video_duration > 0:
        segments = scale_timestamps(segments, video_duration, debug=debug)

    # ── Base64 encoding (cache bust: path bir xil bo'lsa ham yangi kontent yangilansin) ──
    stat = os.stat(video_path)
    cache_key = f"{video_path}:{stat.st_mtime_ns}:{stat.st_size}"
    video_b64 = get_video_b64(video_path, cache_key=cache_key)
    if not video_b64:
        st.error("❌ Video yuklab bo'lmadi.")
        return

    # ── MIME type ──
    ext = os.path.splitext(video_path)[1].lower().lstrip(".")
    audio_exts = {"mp3", "wav", "m4a", "ogg", "flac"}
    is_audio = ext in audio_exts
    tag = "audio" if is_audio else "video"
    mime_map = {"mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
                "ogg": "audio/ogg", "flac": "audio/flac",
                "mp4": "video/mp4", "webm": "video/webm", "ogv": "video/ogg"}
    mime_type = mime_map.get(ext, f"{'audio' if is_audio else 'video'}/{ext}")

    autoplay_attr = "autoplay" if start_time > 0 else ""

    # ── Subtitle span HTML ──
    word_spans = " ".join([
        f'<span class="word" data-start="{s["start"]}" data-end="{s["end"]}" id="w{i}">'
        f'{s["text"]}</span>'
        for i, s in enumerate(segments)
    ])

    # ─────────────────────────────────────────────────────────────────────────
    # HTML + CSS + JS
    # ─────────────────────────────────────────────────────────────────────────
    html_code = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;800;900&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: transparent;
    font-family: 'Inter', sans-serif;
    overflow: hidden;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
  }}

  .player-wrap {{
    position: relative;
    width: 100%;
    height: 100%;
    background: #000;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 16px 48px rgba(0,0,0,0.9);
  }}

  {tag} {{
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: #000;
    outline: none;
    display: block;
  }}

  /* ── Subtitle overlay ── */
  .sub-overlay {{
    position: absolute;
    bottom: 12%;
    left: 0; right: 0;
    display: flex;
    justify-content: center;
    align-items: flex-end;
    padding: 0 5%;
    z-index: 100;
    pointer-events: none;
  }}

  .caption-box {{
    background: rgba(0, 0, 0, 0.24);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 5px 10px;
    will-change: transform, opacity;
    max-width: 90%;
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    align-items: center;
    gap: 4px 10px;
    /* Fade in/out */
    opacity: 0;
    transform: translateY(12px);
    transition: opacity 0.18s ease-out, transform 0.18s ease-out;
    pointer-events: auto;
  }}

  .caption-box.show {{
    opacity: 1;
    transform: translateY(0);
  }}

  /* ── Individual word chip ── */
  .word {{
    display: none;
    font-size: clamp(1.25rem, 3.8vw, 2rem);
    font-weight: 900;
    color: rgba(255,255,255,0.96);
    letter-spacing: 0;
    text-shadow:
      0 1px 2px rgba(0,0,0,0.95),
      0 0 1px rgba(0,0,0,0.9);
    transition:
      color       0.05s ease-out,
      transform   0.07s cubic-bezier(0, 0, 0.2, 1);
  }}

  .word.active {{
    display: inline-block;
    color: #ffffff;
    transform: scale(1.03);
    text-shadow:
      0 1px 2px rgba(0,0,0,0.98),
      0 0 2px rgba(0,0,0,0.92);
  }}

  /* ── Mode switcher (top-right, appears on hover) ── */
  /* Mode bar removed as requested */

  .m-btn {{
    background: rgba(0,0,0,0.65);
    color: rgba(255,255,255,0.85);
    border: 1px solid rgba(255,255,255,0.22);
    padding: 5px 13px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 700;
    cursor: pointer;
    backdrop-filter: blur(4px);
    transition: background 0.15s, color 0.15s;
    letter-spacing: 0.04em;
  }}
  .m-btn.on {{ background: #FFD700; color: #111; border-color: #FFD700; }}

  @media (max-width: 600px) {{
    .word {{ font-size: 1.08rem; }}
    .caption-box {{ padding: 4px 8px; gap: 2px 5px; }}
    .sub-overlay {{ bottom: 10%; }}
  }}
</style>
</head>
<body>
<div class="player-wrap">

  <{tag} id="vid" controls {autoplay_attr} preload="auto">
    <source src="data:{mime_type};base64,{video_b64}" type="{mime_type}">
  </{tag}>

  <!-- No switcher -->

  <!-- Subtitle overlay -->
  <div class="sub-overlay">
    <div class="caption-box" id="cbox">
      {word_spans}
    </div>
  </div>

</div>

<script>
/* ══════════════════════════════════════════════════════════
   PROFESSIONAL REAL-TIME SUBTITLE ENGINE
   - requestAnimationFrame (no setInterval lag)
   - 3 modes: word-by-word | progressive | karaoke
   - seek/pause/play safe
══════════════════════════════════════════════════════════ */

const vid   = document.getElementById('vid');
const cbox  = document.getElementById('cbox');
const words = Array.from(document.querySelectorAll('.word'));
let mode    = 1;   // Forced to Word-by-word mode
const starts = words.map(w => parseFloat(w.dataset.start));
const ends = words.map(w => parseFloat(w.dataset.end));

/* ── Pre-compute phrase groups (burst gap > 0.9s → new phrase) ── */
const phrases = [];
let cur = [];
let maxTimestamp = 0;
// Global sync adjustment
const PERCEPTION_OFFSET = 0.015; 
const MANUAL_LATENCY    = {latency_offset}; 
const SYNC_DELAY        = 0.0 + MANUAL_LATENCY; 

words.forEach((w, idx) => {{
  const st = parseFloat(w.dataset.start);
  const end = parseFloat(w.dataset.end);
  if (end > maxTimestamp) maxTimestamp = end;

  const prevEnd = cur.length ? parseFloat(cur[cur.length-1].dataset.end) : 0;
  // Increase block size to 12 words, similar to a standard YouTube subtitle line
  if (idx > 0 && (st - prevEnd > 1.2 || cur.length >= 12)) {{
    phrases.push(cur);
    cur = [w];
  }} else {{
    cur.push(w);
  }}
}});
if (cur.length) phrases.push(cur);

/* ── Debug ── */
vid.addEventListener('loadedmetadata', () => {{
  console.log("----- SUBTITLE ENGINE DEBUG -----");
  console.log("Total Words:", words.length);
  console.log("Max Timestamp (subtitles):", maxTimestamp.toFixed(2));
  console.log("Video Duration (real):", vid.duration.toFixed(2));
  console.log("---------------------------------");
}});


/* ── Helpers ── */
function hideAll() {{
  words.forEach(w => {{
    w.style.display = 'none';
    w.classList.remove('active', 'passed');
  }});
}}

function findActiveGlobalIdx(ct) {{
  /* Strict timeline: word faqat o'z intervalida ko'rinadi */
  const t = ct - SYNC_DELAY;
  if (!starts.length) return -1;

  // Binary search: last index with start <= t
  let lo = 0;
  let hi = starts.length - 1;
  let idx = -1;
  while (lo <= hi) {{
    const mid = (lo + hi) >> 1;
    if (starts[mid] <= t) {{
      idx = mid;
      lo = mid + 1;
    }} else {{
      hi = mid - 1;
    }}
  }}
  if (idx < 0) return -1;

  // Minimal grace: erta/kechikishni kamaytirish uchun juda kichik buffer
  const ws = starts[idx] - PERCEPTION_OFFSET;
  const we = ends[idx] + 0.005;
  if (t >= ws && t <= we) return idx;
  return -1;
}}

/* ── Main render loop ── */
function render() {{
  const ct = vid.currentTime;
  const activeIdx = findActiveGlobalIdx(ct);
  hideAll();
  if (activeIdx < 0) {{
    cbox.classList.remove('show');
    requestAnimationFrame(render);
    return;
  }}
  cbox.classList.add('show');

  /* Only 1-Word display */
  words[activeIdx].style.display = 'inline-block';
  words[activeIdx].classList.add('active');

  requestAnimationFrame(render);
}}

/* ── Mode buttons ── */
/* Mode buttons removed */

/* ── Word click → seek ── */
words.forEach(w => {{
  w.addEventListener('click', () => {{
    vid.currentTime = parseFloat(w.dataset.start);
    vid.play();
  }});
}});

/* ── Autoplay / seek to start_time ── */
let hasInitialSeek = false;
function seekToStart() {{
  if (hasInitialSeek) return;
  if ({start_time} > 0) {{
    const target = {start_time};
    let attempts = 0;
    const maxAttempts = 12;

    const applySeek = () => {{
      attempts += 1;
      try {{
        vid.currentTime = target;
      }} catch (e) {{}}

      // 40ms aniqlik yetarli, aks holda yana urinib ko'ramiz
      if (Math.abs((vid.currentTime || 0) - target) <= 0.04 || attempts >= maxAttempts) {{
        hasInitialSeek = true;
        vid.play().catch(() => {{}});
        return;
      }}
      setTimeout(applySeek, 120);
    }};

    applySeek();
  }} else {{
    hasInitialSeek = true;
  }}
}}
vid.addEventListener('loadedmetadata', seekToStart, {{ once: true }});
vid.addEventListener('canplay', seekToStart, {{ once: true }});
if (vid.readyState >= 1) seekToStart();

/* ── Start render loop ── */
requestAnimationFrame(render);
</script>
</body>
</html>
"""

    st.components.v1.html(html_code, height=620 if not is_audio else 300)
