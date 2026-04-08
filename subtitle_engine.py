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
    if start_time > 0:
        start_time = max(0.0, start_time - 0.3)

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

    autoplay_attr = "autoplay" if start_time > 0 else ""

    # HTML/CSS/JS Component
    html_code = f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap');
        
        body {{
            margin: 0;
            padding: 0;
            background: transparent;
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
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 20px 50px rgba(0,0,0,0.5);
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
            top: 60%;
            left: 0;
            right: 0;
            text-align: center;
            z-index: 1000;
            pointer-events: none;
            display: flex;
            justify-content: center;
            padding: 0 20px;
            transform: translateY(-50%);
        }}

        .caption-box {{
            background: transparent;
            padding: 10px 20px;
            max-width: 90%;
            display: none;
            flex-wrap: wrap;
            justify-content: center;
            align-items: center;
            transition: all 0.1s ease;
        }}

        .word {{
            display: none;
            font-size: 2.5rem;
            color: rgba(255, 255, 255, 0.9);
            margin: 0 8px;
            font-weight: 800;
            cursor: pointer;
            pointer-events: auto;
            text-shadow: 2px 2px 0 #000, -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000;
            text-transform: uppercase;
        }}

        .word.active {{
            color: #ffd700;
            transform: scale(1.1);
            text-shadow: 0 0 20px rgba(255,215,0,0.8), 2px 2px 4px rgba(0,0,0,1);
            z-index: 10;
        }}

        @media (max-width: 768px) {{
            .word {{
                font-size: 1.8rem;
                margin: 0 4px;
            }}
        }}
    </style>

    <div class="player-container">
        <{tag} id="mainMedia" controls {autoplay_attr} crossorigin="anonymous" style="width:100%; height:100%;">
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
        const words = Array.from(document.querySelectorAll('.word'));
        const captionBox = document.getElementById('captionBox');

        media.addEventListener('loadedmetadata', () => {{
            media.currentTime = {start_time};
            if ({start_time} > 0) {{
                media.play().catch(e => console.log("Autoplay blocked:", e));
            }}
        }});
        
        if (media.readyState >= 1) {{
            media.currentTime = {start_time};
            if ({start_time} > 0) {{
                media.play().catch(e => console.log("Autoplay blocked:", e));
            }}
        }}

        function updateSubtitles() {{
            const ct = media.currentTime;
            let foundActive = false;

            words.forEach(w => {{
                const start = parseFloat(w.dataset.start);
                const end = parseFloat(w.dataset.end);
                
                // Active window slightly padded for smoothness
                if (ct >= start - 0.05 && ct <= end + 0.05) {{
                    w.style.display = 'inline-block';
                    w.classList.add('active');
                    foundActive = true;
                }} else {{
                    w.style.display = 'none';
                    w.classList.remove('active');
                }}
            }});
            
            captionBox.style.display = foundActive ? 'flex' : 'none';
            requestAnimationFrame(updateSubtitles);
        }}

        requestAnimationFrame(updateSubtitles);
        media.addEventListener('seeked', updateSubtitles);

        words.forEach(w => {{
            w.addEventListener('click', () => {{
                media.currentTime = parseFloat(w.dataset.start);
                media.play();
            }});
        }});
    </script>
    """
    
    st.components.v1.html(html_code, height=600 if tag=="video" else 250)
