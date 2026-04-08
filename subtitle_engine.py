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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;800;900&display=swap');
        
        body {{
            margin: 0; padding: 0; background: transparent;
            font-family: 'Inter', sans-serif; overflow: hidden;
            display: flex; justify-content: center; align-items: center;
            height: 100vh;
        }}

        .player-container {{
            position: relative; width: 100%; height: 100%;
            display: flex; flex-direction: column; background: #000;
            border-radius: 12px; overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.8);
        }}

        {tag} {{
            width: 100%; height: 100%; object-fit: contain;
            background: #000; outline: none;
        }}

        .subtitle-overlay {{
            position: absolute; bottom: 15%; left: 0; right: 0;
            text-align: center; z-index: 1000; pointer-events: none;
            display: flex; justify-content: center; padding: 0 20px;
        }}

        .caption-box {{
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(4px);
            padding: 15px 30px;
            border-radius: 16px;
            max-width: 85%;
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            align-items: center;
            transition: all 0.2s ease-in-out;
            opacity: 0;
            transform: translateY(20px);
        }}
        
        .caption-box.visible {{
            opacity: 1;
            transform: translateY(0);
        }}

        .word {{
            display: none;
            font-size: 2.4rem;
            color: rgba(255, 255, 255, 0.6);
            margin: 0 6px;
            font-weight: 800;
            cursor: pointer; pointer-events: auto;
            text-transform: uppercase;
            text-shadow: 2px 2px 4px rgba(0,0,0,1);
            transition: color 0.15s ease-out, transform 0.15s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }}

        .word.active {{
            color: #FFD700; 
            transform: scale(1.15) translateY(-2px);
            text-shadow: 0 0 15px rgba(255,215,0,0.6), 2px 2px 4px rgba(0,0,0,1);
            opacity: 1;
        }}
        
        /* Modern UI controls for Subtitle Modes */
        .mode-selector {{
            position: absolute; top: 15px; right: 20px;
            z-index: 1001; display: flex; gap: 8px;
            opacity: 0.2; transition: opacity 0.3s;
        }}
        .player-container:hover .mode-selector {{
            opacity: 1;
        }}
        .mode-btn {{
            background: rgba(0,0,0,0.6); color: white; border: 1px solid rgba(255,255,255,0.2);
            padding: 6px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600;
            cursor: pointer; backdrop-filter: blur(4px);
        }}
        .mode-btn.active {{ background: #FFD700; color: #000; border: none; }}

        @media (max-width: 768px) {{
            .word {{ font-size: 1.5rem; margin: 0 3px; }}
            .caption-box {{ padding: 10px 15px; }}
            .subtitle-overlay {{ bottom: 10%; }}
        }}
    </style>

    <div class="player-container">
        <{tag} id="mainMedia" controls {autoplay_attr} crossorigin="anonymous">
            <source src="data:{mime_type};base64,{video_b64}" type="{mime_type}">
        </{tag}>
        
        <div class="mode-selector">
            <button class="mode-btn active" data-mode="1">1-Word</button>
            <button class="mode-btn" data-mode="2">Progressive</button>
            <button class="mode-btn" data-mode="3">Karaoke</button>
        </div>

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
        let currentMode = 1; // 1 = Word-by-word, 2 = Progressive, 3 = Karaoke
        
        // Setup chunking for words into phrases (Sentences)
        const phrases = [];
        let currentPhrase = [];
        words.forEach((w, index) => {{
            const start = parseFloat(w.dataset.start);
            const prevEnd = currentPhrase.length > 0 ? parseFloat(currentPhrase[currentPhrase.length-1].dataset.end) : 0;
            if (index > 0 && (start - prevEnd > 0.8 || currentPhrase.length >= 7)) {{
                phrases.push(currentPhrase);
                currentPhrase = [w];
            }} else {{
                currentPhrase.push(w);
            }}
        }});
        if (currentPhrase.length > 0) phrases.push(currentPhrase);

        // Subtitle Update Engine
        function updateSubtitles() {{
            const ct = media.currentTime;
            let activePhrase = null;
            let activeWordIndexInPhrase = -1;
            let activeWordGlobalIndex = -1;

            // 1. Find the current active phrase
            for (const phrase of phrases) {{
                const pStart = parseFloat(phrase[0].dataset.start) - 0.1;
                const pEnd = parseFloat(phrase[phrase.length-1].dataset.end) + 0.3;
                if (ct >= pStart && ct <= pEnd) {{
                    activePhrase = phrase;
                    break;
                }}
            }}

            // Hide all words initially to reset state
            words.forEach(w => {{ 
                w.style.display = 'none'; 
                w.classList.remove('active'); 
                w.style.color = 'rgba(255, 255, 255, 0.6)';
            }});

            if (activePhrase) {{
                captionBox.classList.add('visible');
                
                // Find exactly which word is active within the phrase
                activePhrase.forEach((w, i) => {{
                    // offset fix native to Whisper
                    const start = parseFloat(w.dataset.start);
                    const end = parseFloat(w.dataset.end) + 0.1;
                    if (ct >= start && ct <= end) {{
                        activeWordIndexInPhrase = i;
                    }}
                }});
                
                // Render modes
                if (currentMode === 1) {{
                    // WORD-BY-WORD (TikTok single focus)
                    activePhrase.forEach((w, i) => {{
                        if (i === activeWordIndexInPhrase) {{
                            w.style.display = 'inline-block';
                            w.style.color = '#FFD700';
                            w.classList.add('active');
                        }}
                    }});
                }} 
                else if (currentMode === 2) {{
                    // PROGRESSIVE (Accumulating words)
                    activePhrase.forEach((w, i) => {{
                        if (activeWordIndexInPhrase !== -1 && i <= activeWordIndexInPhrase) {{
                            w.style.display = 'inline-block';
                            w.style.color = '#FFF'; 
                            if (i === activeWordIndexInPhrase) {{
                                w.classList.add('active');
                            }}
                        }}
                    }});
                }} 
                else if (currentMode === 3) {{
                    // KARAOKE (Full phrase, highlight current)
                    activePhrase.forEach((w, i) => {{
                        w.style.display = 'inline-block';
                        w.style.color = 'rgba(255, 255, 255, 0.6)';
                        if (i === activeWordIndexInPhrase) {{
                            w.classList.add('active');
                        }} else if (activeWordIndexInPhrase !== -1 && i < activeWordIndexInPhrase) {{
                            w.style.color = '#FFF'; // Passed words become white
                        }}
                    }});
                }}
            }} else {{
                captionBox.classList.remove('visible');
            }}
            
            requestAnimationFrame(updateSubtitles);
        }}

        // Mode Toggler UI
        const modeBtns = document.querySelectorAll('.mode-btn');
        modeBtns.forEach(btn => {{
            btn.addEventListener('click', (e) => {{
                modeBtns.forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                currentMode = parseInt(e.target.dataset.mode);
            }});
        }});

        // Run
        requestAnimationFrame(updateSubtitles);
        
        // Autoplay logic if requested
        media.addEventListener('loadedmetadata', () => {{
            if ({start_time} > 0) {{
                media.currentTime = {start_time};
                media.play().catch(e => console.log(e));
            }}
        }});
        if (media.readyState >= 1 && {start_time} > 0) {{
            media.currentTime = {start_time};
            media.play().catch(e => console.log(e));
        }}

        // Seek sync
        words.forEach(w => {{
            w.addEventListener('click', () => {{
                media.currentTime = parseFloat(w.dataset.start);
                media.play();
            }});
        }});
    </script>
    """
    
    st.components.v1.html(html_code, height=600 if tag=="video" else 300)
