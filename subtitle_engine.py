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
def get_video_b64(video_path: str) -> str:
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

    # Barcha so'zlardan maksimal vaqtni aniqlaymiz
    max_timestamp = max(s.get("end", 0) for s in segments)

    # Video va subtitr uzunliklari o'rtasidagi farq nisbati
    diff_ratio = abs(video_duration - max_timestamp) / video_duration
    
    # Subtitrlar va video orasidagi farq 15% gacha bo'lsa scale qilamiz.
    if max_timestamp > 0 and 0.001 < diff_ratio < 0.15:
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

    # ── Pre-roll buffer (so'z boshlanishidan biroz oldin video starts) ──
    if start_time > 0:
        start_time = max(0.0, start_time - 0.3)

    # ── Timestamp auto-scale ──
    if video_duration > 0:
        segments = scale_timestamps(segments, video_duration, debug=debug)

    # ── Base64 encoding ──
    video_b64 = get_video_b64(video_path)
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
    bottom: 14%;
    left: 0; right: 0;
    display: flex;
    justify-content: center;
    align-items: flex-end;
    padding: 0 5%;
    z-index: 100;
    pointer-events: none;
  }}

  .caption-box {{
    background: rgba(0,0,0,0.62);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 14px 28px;
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
    font-size: clamp(1.4rem, 4vw, 2.6rem);
    font-weight: 800;
    color: rgba(255,255,255,0.55);
    letter-spacing: 0.03em;
    text-shadow: 1px 1px 6px rgba(0,0,0,0.9);
    cursor: pointer;
    transition:
      color       0.08s ease-out,
      transform   0.1s cubic-bezier(0.2, 0, 0.2, 1),
      text-shadow 0.08s ease-out;
  }}

  /* YouTube-style yellow highlight */
  .word.active {{
    display: inline-block;
    color: #ffcc00; 
    transform: scale(1.1);
    text-shadow: 
      0 0 12px rgba(255, 204, 0, 0.5),
      2px 2px 4px rgba(0,0,0,0.9);
    z-index: 10;
  }}

  .word.passed {{
    color: #ffffff;
    opacity: 1;
  }}

  /* ── Mode switcher (top-right, appears on hover) ── */
  .mode-bar {{
    position: absolute;
    top: 12px; right: 14px;
    display: flex; gap: 6px;
    z-index: 200;
    opacity: 0;
    transition: opacity 0.25s;
  }}
  .player-wrap:hover .mode-bar {{ opacity: 1; }}

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
    .word {{ font-size: 1.3rem; }}
    .caption-box {{ padding: 10px 16px; gap: 3px 7px; }}
    .sub-overlay {{ bottom: 10%; }}
  }}
</style>
</head>
<body>
<div class="player-wrap">

  <{tag} id="vid" controls {autoplay_attr} preload="auto">
    <source src="data:{mime_type};base64,{video_b64}" type="{mime_type}">
  </{tag}>

  <!-- Mode switcher -->
  <div class="mode-bar">
    <button class="m-btn"    data-mode="1">1-Word</button>
    <button class="m-btn"    data-mode="2">Progressive</button>
    <button class="m-btn on" data-mode="3">Karaoke</button>
  </div>

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
let mode    = 3;   // 1 = 1-Word  |  2 = Progressive  |  3 = Karaoke (YouTube style)

/* ── Pre-compute phrase groups (burst gap > 0.9s → new phrase) ── */
const phrases = [];
let cur = [];
let maxTimestamp = 0;
// Global sync adjustment
const PERCEPTION_OFFSET = 0.0; 
const MANUAL_LATENCY    = {latency_offset}; 
const SYNC_DELAY        = 0.05 + MANUAL_LATENCY; 

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

function findActivePhrase(ct) {{
  for (const ph of phrases) {{
    const ps = parseFloat(ph[0].dataset.start) - 0.2;
    const pe = parseFloat(ph[ph.length-1].dataset.end) + 0.1;
    if (ct >= ps && ct <= pe) return ph;
  }}
  return null;
}}

function findActiveIdx(phrase, ct) {{
  /* Returns index of the currently-spoken word within phrase (-1 if none) */
  for (let i = 0; i < phrase.length; i++) {{
    const rawSt = parseFloat(phrase[i].dataset.start);
    const rawEnd = parseFloat(phrase[i].dataset.end);
    const ws = rawSt + SYNC_DELAY;
    const we = rawEnd + SYNC_DELAY + 0.08; 
    if (ct >= ws && ct <= we) return i;
  }}
  /* If we're inside the phrase window but between two words, use last spoken */
  const ct2 = ct;
  let last = -1;
  for (let i = 0; i < phrase.length; i++) {{
    if (ct2 >= (parseFloat(phrase[i].dataset.start) - PERCEPTION_OFFSET)) last = i;
    else break;
  }}
  return last;
}}

/* ── Main render loop ── */
function render() {{
  const ct = vid.currentTime;
  const phrase = findActivePhrase(ct);

  if (!phrase) {{
    hideAll();
    cbox.classList.remove('show');
    requestAnimationFrame(render);
    return;
  }}

  const activeIdx = findActiveIdx(phrase, ct);
  hideAll();
  cbox.classList.add('show');

  if (mode === 1) {{
    /* ─ 1-Word: only the active word ─ */
    if (activeIdx >= 0) {{
      phrase[activeIdx].style.display = 'inline-block';
      phrase[activeIdx].classList.add('active');
    }}

  }} else if (mode === 2) {{
    /* ─ Progressive: words accumulate ─ */
    const limit = activeIdx >= 0 ? activeIdx : 0;
    phrase.forEach((w, i) => {{
      if (i <= limit) {{
        w.style.display = 'inline-block';
        if (i === limit) w.classList.add('active');
        else             w.classList.add('passed');
      }}
    }});

  }} else {{
    /* ─ Karaoke: full phrase, colour current ─ */
    phrase.forEach((w, i) => {{
      w.style.display = 'inline-block';
      if (i === activeIdx)     w.classList.add('active');
      else if (i < activeIdx)  w.classList.add('passed');
    }});
  }}

  requestAnimationFrame(render);
}}

/* ── Mode buttons ── */
document.querySelectorAll('.m-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.m-btn').forEach(b => b.classList.remove('on'));
    btn.classList.add('on');
    mode = parseInt(btn.dataset.mode);
  }});
}});

/* ── Word click → seek ── */
words.forEach(w => {{
  w.addEventListener('click', () => {{
    vid.currentTime = parseFloat(w.dataset.start);
    vid.play();
  }});
}});

/* ── Autoplay / seek to start_time ── */
function seekToStart() {{
  if ({start_time} > 0) {{
    vid.currentTime = {start_time};
    vid.play().catch(() => {{}});
  }}
}}
vid.addEventListener('loadedmetadata', seekToStart);
if (vid.readyState >= 1) seekToStart();

/* ── Start render loop ── */
requestAnimationFrame(render);
</script>
</body>
</html>
"""

    st.components.v1.html(html_code, height=620 if not is_audio else 300)
