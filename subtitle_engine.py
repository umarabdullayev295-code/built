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
            bottom: 12%;
            left: 0;
            right: 0;
            text-align: center;
            z-index: 1000;
            pointer-events: none;
            display: flex;
            justify-content: center;
            padding: 0 20px;
        }}

        .caption-box {{
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(8px);
            padding: 10px 20px;
            border-radius: 12px;
            max-width: 90%;
            display: none;
            flex-wrap: wrap;
            justify-content: center;
            align-items: center;
            border: 1px solid rgba(255,255,255,0.1);
            transition: all 0.3s ease;
        }}

        .word {{
            display: none;
            font-size: 1.3rem;
            color: rgba(255, 255, 255, 0.6);
            margin: 0 5px;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            font-weight: 600;
            cursor: pointer;
            pointer-events: auto;
            display: inline-block;
            opacity: 0;
            transform: translateY(5px);
        }}

        .word.visible {{
            opacity: 1;
            transform: translateY(0);
        }}

        .word.active {{
            color: #ffffff;
            font-weight: 900;
            transform: scale(1.2) translateY(-2px);
            text-shadow: 0 0 20px rgba(255,255,255,0.8), 
                         0 0 10px rgba(255,255,255,1),
                         2px 2px 4px rgba(0,0,0,0.8);
            z-index: 10;
        }}

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

        const phrases = [];
        let currentPhrase = [];
        
        words.forEach((w, index) => {{
            const start = parseFloat(w.dataset.start);
            const prevEnd = currentPhrase.length > 0 ? parseFloat(currentPhrase[currentPhrase.length-1].dataset.end) : 0;
            
            if (index > 0 && (start - prevEnd > 0.8 || currentPhrase.length >= 10)) {{
                phrases.push(currentPhrase);
                currentPhrase = [w];
            }} else {{
                currentPhrase.push(w);
            }}
        }});
        if (currentPhrase.length > 0) phrases.push(currentPhrase);

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
            let activePhrase = null;

            for (const phrase of phrases) {{
                const phraseStart = parseFloat(phrase[0].dataset.start);
                const phraseEnd = parseFloat(phrase[phrase.length-1].dataset.end);
                
                if (ct >= phraseStart - 0.2 && ct <= phraseEnd + 0.5) {{
                    activePhrase = phrase;
                    break;
                }}
            }}

            words.forEach(w => {{
                w.style.display = 'none';
                w.classList.remove('active', 'visible');
            }});
            
            if (activePhrase) {{
                captionBox.style.display = 'flex';
                activePhrase.forEach(w => {{
                    w.style.display = 'inline-block';
                    w.classList.add('visible');
                    
                    const start = parseFloat(w.dataset.start);
                    const end = parseFloat(w.dataset.end);
                    
                    if (ct >= start && ct <= end) {{
                        w.classList.add('active');
                    }}
                }});
            }} else {{
                captionBox.style.display = 'none';
            }}

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
