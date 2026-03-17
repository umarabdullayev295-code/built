import streamlit as st
import base64
import os
import json
from typing import List, Dict

@st.cache_data(show_spinner=False)
def get_video_b64(video_path: str) -> str:
    """Video faylni base64 ko'rinishida o'qiydi va keshlaydi."""
    try:
        with open(video_path, "rb") as f:
            video_bytes = f.read()
            return base64.b64encode(video_bytes).decode('utf-8')
    except Exception as e:
        return ""

def render_youtube_player(video_path: str, segments: List[Dict], start_time: float = 0.0):
    """
    YouTube uslubidagi word-by-word subtitrli video player.
    Subtitrlar video tagida, real-vaqtda yonib turadi.
    """
    if not video_path or not os.path.exists(video_path):
        st.error("Media fayl topilmadi.")
        return

    # Video ma'lumotlarini b64 ga o'tkazish (keshlangan)
    video_b64 = get_video_b64(video_path)
    if not video_b64:
        st.error("Media yuklashda xato yuz berdi.")
        return

    # Ext ga qarab mime-type
    ext = os.path.splitext(video_path)[1].lower().replace('.', '')
    audio_exts = ['mp3', 'wav', 'm4a', 'ogg', 'flac']
    is_audio = ext in audio_exts
    
    mime_type = f"audio/{ext}" if is_audio else f"video/{ext}"
    if ext == 'mp3': mime_type = "audio/mpeg" # maxsus holat
    
    tag = "audio" if is_audio else "video"

    # HTML/CSS/JS Component
    html_code = f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
        
        body {{
            margin: 0;
            padding: 0;
            background: #000;
            font-family: 'Inter', sans-serif;
            overflow: hidden;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
        }}

        .player-container {{
            position: relative;
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            background: #000;
        }}

        {tag} {{
            width: 100%;
            height: 100%;
            object-fit: contain;
            background: #000;
            outline: none;
        }}

        .subtitle-overlay {{
            position: absolute;
            bottom: 15%;
            left: 0;
            right: 0;
            text-align: center;
            z-index: 1000;
            pointer-events: none;
            display: flex;
            justify-content: center;
        }}

        .caption-box {{
            background: rgba(8, 8, 8, 0.85); /* Deep dark background */
            padding: 6px 16px;
            border-radius: 4px;
            max-width: 80%;
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            align-items: center;
        }}

        .word {{
            display: none; /* Hidden by default */
            font-family: 'Roboto', 'Inter', sans-serif;
            font-size: 1.4rem;  /* Clearer size */
            color: #aaaaaa;     /* Dim gray for inactive words */
            margin: 0 4px;
            transition: color 0.15s ease;
            font-weight: 500;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
        }}

        .word.visible {{
            display: inline-block;
        }}

        .word.active {{
            display: inline-block;
            color: #ffffff;     /* Bright white for active word */
            font-weight: 700;
            /* text-decoration: underline; Optional YouTube auto-caption vibe */
        }}

        /* ── Mobile Responsiveness ── */
        @media (max-width: 768px) {{
            .subtitle-overlay {{
                bottom: 10%;
            }}
            .caption-box {{
                max-width: 95%;
                padding: 4px 10px;
            }}
            .word {{
                font-size: 1.0rem; /* Smaller font on mobile */
                margin: 0 2px;
            }}
        }}
    </style>

    <div class="player-container">
        <{tag} id="mainMedia" controls crossorigin="anonymous">
            <source src="data:{mime_type};base64,{video_b64}" type="{mime_type}">
        </{tag}>
        
        <div class="subtitle-overlay">
            <div class="caption-box" id="captionBox">
                {" ".join([f'<span class="word" data-start="{s["start"]}" data-end="{s["end"]}" id="word-{i}">{s["text"]}</span>' for i, s in enumerate(segments)])}
            </div>
        </div>
    </div>

    <script>
        const media = document.getElementById('mainMedia');
        const words = document.querySelectorAll('.word');
        const captionBox = document.getElementById('captionBox');

        media.addEventListener('loadedmetadata', () => {{
            media.currentTime = {start_time};
        }});
        
        if (media.readyState >= 1) {{
            media.currentTime = {start_time};
        }}

        let rafId = null;
        function updateSubtitles() {{
            const ct = media.currentTime;
            let currentActiveIndex = -1;

            // 1. Faol so'zni topish
            words.forEach((w, index) => {{
                const start = parseFloat(w.dataset.start);
                const end = parseFloat(w.dataset.end);

                if (ct >= start && ct <= end) {{
                    w.classList.add('active');
                    w.classList.add('visible');
                    currentActiveIndex = index;
                }} else {{
                    w.classList.remove('active');
                    w.classList.remove('visible');
                }}
            }});

            // 2. "Dona-dona" effekt: Atrofdagi so'zlarni ham ko'rsatish (xuddi YouTube line kabi)
            if (currentActiveIndex !== -1) {{
                // Hozirgi so'zdan oldingi 2 ta va keyingi 2 ta so'zni ko'rsatamiz (Kichikroq footprint)
                const startRange = Math.max(0, currentActiveIndex - 2);
                const endRange = Math.min(words.length - 1, currentActiveIndex + 2);
                
                for (let i = startRange; i <= endRange; i++) {{
                    words[i].classList.add('visible');
                }}
                captionBox.style.display = 'flex';
            }} else {{
                // Agar hech qanday so'z faol bo'lmasa va vaqt yaqin bo'lmasa, yashirish
                let anyVisible = false;
                words.forEach(w => {{
                    if (w.classList.contains('visible')) anyVisible = true;
                }});
                if (!anyVisible) captionBox.style.display = 'none';
            }}

            rafId = requestAnimationFrame(updateSubtitles);
        }}

        media.addEventListener('play', () => {{
            rafId = requestAnimationFrame(updateSubtitles);
        }});
        media.addEventListener('pause', () => {{
            cancelAnimationFrame(rafId);
        }});
        media.addEventListener('seeked', updateSubtitles);

        // Click to jump
        words.forEach(w => {{
            w.style.pointerEvents = 'auto'; // Re-enable pointer events for words
            w.addEventListener('click', () => {{
                media.currentTime = parseFloat(w.dataset.start);
                media.play();
            }});
        }});

        // Python'dan vaqt sovg'asi (agar kerak bo'lsa)
        // window.addEventListener('message', function(event) {{
        //     if (event.data.type === 'seek') {{
        //         media.currentTime = event.data.time;
        //         media.play();
        //     }}
        // }});
    </script>
    """
    
    st.components.v1.html(html_code, height=600 if tag=="video" else 250)
