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
            background: rgba(0, 0, 0, 0.7); /* YouTube-style semi-transparent black */
            padding: 8px 20px;
            border-radius: 4px;
            max-width: 90%;
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            align-items: center;
            min-height: 2em;
        }}

        .word {{
            display: inline-block;
            font-family: 'Roboto', 'Inter', sans-serif;
            font-size: 1.6rem;
            color: rgba(255, 255, 255, 0.4); /* Dim white for context */
            margin: 0 5px;
            transition: all 0.1s ease;
            font-weight: 500;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
            opacity: 0; /* Initially hidden */
            transform: translateY(5px);
        }}

        .word.visible {{
            opacity: 1;
            transform: translateY(0);
        }}

        .word.active {{
            color: #ffffff;
            font-weight: 700;
            transform: scale(1.1);
            text-shadow: 0 0 10px rgba(255,255,255,0.5);
        }}

        /* ── Mobile Responsiveness ── */
        @media (max-width: 768px) {{
            .subtitle-overlay {{
                bottom: 12%;
            }}
            .caption-box {{
                max-width: 95%;
                padding: 6px 12px;
            }}
            .word {{
                font-size: 1.1rem;
                margin: 0 3px;
            }}
        }}
    </style>

    <div class="player-container">
        <{tag} id="mainMedia" controls crossorigin="anonymous" style="width:100%; height:100%;">
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

        function updateSubtitles() {{
            const ct = media.currentTime;
            
            words.forEach((w, index) => {{
                const start = parseFloat(w.dataset.start);
                const end = parseFloat(w.dataset.end);

                // Word is ACTIVE if current time is within its bounds
                if (ct >= start && ct <= end) {{
                    w.classList.add('active');
                    w.classList.add('visible');
                    w.style.display = 'inline-block';
                }} else if (ct > end) {{
                    // Word has passed - keep visible but not active
                    w.classList.remove('active');
                    w.classList.add('visible');
                    // Hide words that are too old (e.g., more than 4 seconds ago)
                    if (ct - end > 4.0) {{
                        w.style.display = 'none';
                    }} else {{
                        w.style.display = 'inline-block';
                    }}
                }} else if (ct < start) {{
                    // Word is in the future
                    w.classList.remove('active');
                    w.classList.remove('visible');
                    w.style.display = 'none';
                }}
            }});

            requestAnimationFrame(updateSubtitles);
        }}

        // Start the loop
        requestAnimationFrame(updateSubtitles);

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
