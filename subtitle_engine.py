"""
subtitle_engine.py
------------------
YouTube uslubida real-time subtitle engine.
- So'z o'z vaqtida chiqadi, keyingi so'z boshlangunicha ushlab turiladi
- requestAnimationFrame asosidagi precision engine (lag yo'q)
- Binary search bilan O(log n) tezlik
- Seek/pause/play xavfsiz
- Glassmorphism dizayn
"""

import streamlit as st
import base64
import os
from typing import List, Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY: Video base64 (cached)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def get_video_b64(video_path: str, cache_key: str = "") -> str:
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
    STT vaqtlari video davomiyligiga mos kelmasa avtomatik scale qiladi.
    """
    if not segments or video_duration <= 0:
        return segments

    # Timing lock qilingan bo'lsa (Muxlisa audio alignment) — scale tegmasin
    if segments and segments[0].get("__timing_locked__", False):
        return segments

    # Ikkinchi marta scale qilmaslik
    if segments and segments[0].get("__scaled__", False):
        return segments

    max_timestamp = max(s.get("end", 0) for s in segments)
    if max_timestamp <= 0:
        return segments

    diff_ratio = abs(video_duration - max_timestamp) / video_duration

    if 0.02 < diff_ratio < 0.35:
        scale = video_duration / max_timestamp
        if debug:
            st.warning(f"⚠️ Timing scale: {scale:.3f}x qo'llanilmoqda ({len(segments)} segment)")

        scaled = []
        for s in segments:
            scaled.append({
                **s,
                "start": round(s.get("start", 0) * scale, 3),
                "end":   round(s.get("end",   0) * scale, 3),
                "__scaled__":       True,
                "__scale_factor__": round(scale, 6),
            })
        return scaled

    return segments


# ─────────────────────────────────────────────────────────────────────────────
# MAIN: YouTube-style video player with precise subtitle engine
# ─────────────────────────────────────────────────────────────────────────────

def render_youtube_player(
    video_path: str,
    segments: List[Dict],
    start_time: float = 0.0,
    video_duration: float = 0.0,
    debug: bool = False,
    latency_offset: float = 0.0,
    seek_id: int = 0,
):
    """
    YouTube uslubidagi professional subtitle player.

    - Har bir so'z o'z vaqtida chiqadi
    - Gap bo'lsa (≤1.5s) — oldingi so'z keyingisigacha ushlab turiladi
    - Uzoq tanaffus (>1.5s) — subtitle yo'qoladi
    - requestAnimationFrame + binary search (O log n, lag yo'q)
    """

    if not video_path or not os.path.exists(video_path):
        st.error("❌ Media fayl topilmadi.")
        return

    if not segments:
        st.warning("⚠️ Segment ma'lumotlari topilmadi.")
        return

    start_time = max(0.0, float(start_time))

    # Auto-scale
    if video_duration > 0:
        segments = scale_timestamps(segments, video_duration, debug=debug)

    # AVI/MKV/MOV → mp4 (brauzer uchun mos format)
    try:
        from video_processor import ensure_browser_compatible
        video_path = ensure_browser_compatible(video_path)
    except Exception:
        pass  # Xato bo'lsa originalini ishlatamiz

    # Base64 encode (fayl o'zgarmasa keshdan olinadi, judayam tez)
    stat      = os.stat(video_path)
    cache_key = f"{video_path}:{stat.st_mtime_ns}:{stat.st_size}"
    video_b64 = get_video_b64(video_path, cache_key=cache_key)
    if not video_b64:
        st.error("❌ Video yuklab bo'lmadi.")
        return

    # MIME type
    ext       = os.path.splitext(video_path)[1].lower().lstrip(".")
    audio_exts = {"mp3", "wav", "m4a", "ogg", "flac"}
    is_audio   = ext in audio_exts
    tag        = "audio" if is_audio else "video"
    mime_map   = {
        "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
        "ogg": "audio/ogg",  "flac": "audio/flac",
        "mp4": "video/mp4",  "webm": "video/webm", "ogv": "video/ogg",
        "avi": "video/x-msvideo", "mov": "video/quicktime",
    }
    mime_type    = mime_map.get(ext, f"{'audio' if is_audio else 'video'}/{ext}")
    autoplay_attr = "autoplay muted playsinline"

    # Word span HTML
    word_spans = "\n".join([
        f'<span class="word" data-start="{s["start"]}" data-end="{s["end"]}" id="w{i}">'
        f'{s["text"]}</span>'
        for i, s in enumerate(segments)
    ])

    player_height = 300 if is_audio else 620

    html_code = f"""<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="seek_id" content="{seek_id}">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;700;900&display=swap');

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  html, body {{
    width: 100%; height: 100%;
    background: transparent;
    font-family: 'Inter', system-ui, sans-serif;
    overflow: hidden;
  }}

  /* ── Player wrapper ── */
  .player-wrap {{
    position: relative;
    width: 100%; height: 100%;
    background: #000;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 10px 40px rgba(0,0,0,0.6);
  }}

  {tag} {{
    width: 100%; height: 100%;
    object-fit: contain;
    background: #000;
    outline: none;
    display: block;
  }}

  /* ── Subtitle overlay ── */
  .sub-overlay {{
    position: absolute;
    bottom: 8%;
    left: 0; right: 0;
    display: flex;
    justify-content: center;
    align-items: flex-end;
    padding: 0 4%;
    z-index: 20;
    pointer-events: none;
  }}

  /* ── Caption box — modern dark glass ── */
  .caption-box {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: unset;
    padding: 6px 16px;
    background: rgba(0, 0, 0, 0.75);
    border-radius: 6px;
    pointer-events: none;
    
    opacity: 0;
    transition: opacity 0.1s;
  }}

  .caption-box.visible {{
    opacity: 1;
  }}

  /* ── Individual word ── */
  .word {{
    display: none;
    font-size: clamp(1.2rem, 3.5vw, 1.8rem);
    font-family: "Roboto", "Segoe UI", sans-serif;
    font-weight: 500;
    line-height: 1.3;
    color: #ffffff;
    text-shadow: none;
    text-transform: none;
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    
    /* Subtle pop for YouTube style */
    animation: wordPop 0.1s ease-out both;
  }}

  @keyframes wordPop {{
    0% {{ transform: scale(0.95); opacity: 0; }}
    100% {{ transform: scale(1); opacity: 1; }}
  }}

  .word.active {{
    display: inline-block;
    pointer-events: auto;
  }}

  .word:hover {{
    color: #ffd700;
    transform: scale(1.05);
  }}

  .subtitle-progress {{
    position: absolute;
    bottom: 0; left: 0;
    height: 4px;
    background: linear-gradient(90deg, #00d2ff, #3a7bd5);
    width: 0%;
    transition: width 0.1s linear;
    z-index: 30;
  }}

  /* ── Click-to-play overlay ── */
  .play-overlay {{
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0,0,0,0.5);
    z-index: 50;
    cursor: pointer;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s ease;
  }}
  .play-overlay.show {{
    opacity: 1;
    pointer-events: auto;
  }}
  .play-btn {{
    width: 80px; height: 80px;
    background: rgba(255,255,255,0.2);
    backdrop-filter: blur(10px);
    border: 2px solid rgba(255,255,255,0.4);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 2.5rem;
    color: #fff;
    transition: transform 0.2s ease, background 0.2s ease;
  }}
  .play-btn:hover {{ transform: scale(1.1); background: rgba(255,255,255,0.3); }}
</style>
</head>
<body>
<div class="player-wrap">
  <{tag} id="vid" controls playsinline preload="auto">
    <source src="data:{mime_type};base64,{video_b64}" type="{mime_type}">
  </{tag}>

  <div class="play-overlay" id="playOverlay">
    <div class="play-btn">▶</div>
  </div>

  <div class="sub-overlay">
    <div class="caption-box" id="cbox">
      {word_spans}
    </div>
  </div>

  <div class="subtitle-progress" id="prog"></div>
</div>

<script>
const vid = document.getElementById('vid');
const cbox = document.getElementById('cbox');
const overlay = document.getElementById('playOverlay');
const prog = document.getElementById('prog');
const words = Array.from(document.querySelectorAll('.word'));
const n = words.length;

const starts = new Float64Array(n);
const ends = new Float64Array(n);
words.forEach((w, i) => {{
  starts[i] = parseFloat(w.dataset.start);
  ends[i] = parseFloat(w.dataset.end);
}});

// Calculate effective ends (keep gapless if within 1.5s)
const MAX_GAP = 1.5;
const effEnds = new Float64Array(n);
for (let i = 0; i < n; i++) {{
  effEnds[i] = (i < n - 1 && (starts[i + 1] - ends[i]) <= MAX_GAP) ? starts[i + 1] : ends[i];
}}

const TARGET = {start_time};
let lastIdx = -1;
let rafId = null;

// Ensure we only attempt seeking once initially
let initialSeekDone = false;

function doSeekAndPlay() {{
  if (!initialSeekDone) {{
    vid.currentTime = TARGET;
    initialSeekDone = true;
  }}
  
  vid.muted = true; // Browser autoplay policies require muted initially
  const playPromise = vid.play();
  
  if (playPromise !== undefined) {{
    playPromise.then(() => {{
      overlay.classList.remove('show');
      // Attempt to unmute after successful play (might be blocked, but we try)
      vid.muted = false;
    }}).catch(error => {{
      console.warn("Autoplay prevented:", error);
      overlay.classList.add('show');
    }});
  }}
}}

// Play Overlay logic
overlay.addEventListener('click', () => {{
  overlay.classList.remove('show');
  vid.muted = false;
  if(Math.abs(vid.currentTime - TARGET) > 0.5 && TARGET > 0) {{
      vid.currentTime = TARGET;
  }}
  vid.play();
}});

// Core Engine Loop
function bisect(t) {{
  let lo = 0, hi = n - 1, idx = -1;
  while (lo <= hi) {{
    const mid = (lo + hi) >>> 1;
    if (starts[mid] <= t) {{ idx = mid; lo = mid + 1; }}
    else {{ hi = mid - 1; }}
  }}
  return idx;
}}

function renderLoop() {{
  const t = vid.currentTime;
  const idx = bisect(t);
  const active = (idx >= 0 && t < effEnds[idx]) ? idx : -1;

  if (vid.duration > 0) {{
    prog.style.width = (t / vid.duration * 100).toFixed(2) + '%';
  }}

  if (active !== lastIdx) {{
    if (lastIdx >= 0) {{
      words[lastIdx].style.display = 'none';
      words[lastIdx].classList.remove('active');
    }}
    if (active >= 0) {{
      const w = words[active];
      w.style.display = 'none';
      w.classList.remove('active');
      void w.offsetWidth; // force reflow for animation
      w.style.display = 'inline-block';
      w.classList.add('active');
      cbox.classList.add('visible');
    }} else {{
      cbox.classList.remove('visible');
    }}
    lastIdx = active;
  }}

  rafId = requestAnimationFrame(renderLoop);
}}

// Events
vid.addEventListener('loadedmetadata', () => {{
  doSeekAndPlay();
}}, {{once: true}});

vid.addEventListener('canplay', () => {{
  if (!initialSeekDone) doSeekAndPlay();
}}, {{once: true}});

vid.addEventListener('seeking', () => {{
  if (lastIdx >= 0) {{
    words[lastIdx].style.display = 'none';
    words[lastIdx].classList.remove('active');
  }}
  lastIdx = -1;
  cbox.classList.remove('visible');
}});

words.forEach(w => {{
  w.addEventListener('click', e => {{
    e.stopPropagation();
    vid.currentTime = parseFloat(w.dataset.start);
    vid.play().catch(() => {{}});
  }});
}});

// Start loop
if (vid.readyState >= 1) doSeekAndPlay();
rafId = requestAnimationFrame(renderLoop);
</script>
</body>
</html>"""

    try:
        st.iframe(html_code, height=player_height)
    except AttributeError:
        # Eski Streamlit versiyalari uchun fallback
        import streamlit.components.v1 as components
        components.html(html_code, height=player_height)
