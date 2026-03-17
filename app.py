"""
app.py — Videodan O'zbek Tilidagi Matn va Audio Qidiruv Tizimi
============================================================
Muallif: AI Assistant
Texnologiyalar: Streamlit, faster-whisper, sentence-transformers, FAISS, moviepy
"""

import streamlit as st
import os
import json
import tempfile
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Ilovani Sozlash ---
st.set_page_config(
    page_title="🎬 Video AI Search",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
def init_state():
    defaults = {
        "stt_engine": None,
        "search_engine": None,
        "segments": [],
        "video_path": None,
        "video_name": None,
        "index_built": False,
        "processing": False,
        "play_timestamp": 0,
        "last_results": [],
        "engine_name": "",
        "video_duration": 0,
        "elevenlabs_key": os.environ.get("ELEVENLABS_API_KEY", ""),
        "whisper_model": "medium",
        "target_lang": "uz",
        "theme": "dark",
        "tts_engine": "Muxlisa",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ─────────────────────────────────────────────
# CUSTOM CSS — Premium Dynamic UI
# ─────────────────────────────────────────────
# Define colors based on session state theme
if st.session_state.theme == "light":
    bg_color = "#f8f7ff"         # Very faint violet-tinted white
    sec_bg_color = "#efebff"     # Soft premium lavender
    text_color = "#2d264d"       # Deep violet-tinted dark text
    glass_border = "rgba(124, 92, 191, 0.15)"
    primary_color = "#7c5cbf"
    accent_glow = "rgba(124, 92, 191, 0.12)"
    # Expanders (User preference)
    exp_bg = "#7c5cbf"           # Toq binafsha (Dark violet)
    exp_hover = "#9d80d8"        # Ochiq binafsha (Light violet)
    exp_text = "#ffffff"         # White text on dark headers
else:
    bg_color = "#0e1117"
    sec_bg_color = "#1a1c24"
    text_color = "#ffffff"
    glass_border = "rgba(255, 255, 255, 0.1)"
    primary_color = "#a371f7"
    accent_glow = "rgba(124, 92, 191, 0.3)"
    # Expanders (Dark mode defaults)
    exp_bg = "#1a1c24"
    exp_hover = "#252836"
    exp_text = "#ffffff"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600&display=swap');

:root {{
    --bg-color: {bg_color};
    --sec-bg-color: {sec_bg_color};
    --text-color: {text_color};
    --glass-border: {glass_border};
    --primary-color: {primary_color};
    --exp-bg: {exp_bg};
    --exp-hover: {exp_hover};
    --exp-text: {exp_text};
    --brand-gradient: linear-gradient(135deg, #7c5cbf 0%, #58a6ff 100%);
}}

/* ── Typography & Global ── */
html, body, [class*="css"] {{
    font-family: 'Outfit', 'Inter', sans-serif !important;
}}

.stApp {{
    background-color: var(--bg-color) !important;
    color: var(--text-color) !important;
    transition: all 0.5s ease;
}}

/* Ensure all markdown text respects the theme */
.stMarkdown p, .stMarkdown div, .stMarkdown span {{
    color: var(--text-color) !important;
}}

/* ── Streamlit Element Overrides ── */
header[data-testid="stHeader"], [data-testid="stHeader"] {{
    background-color: var(--bg-color) !important;
}}
header[data-testid="stHeader"] button, header[data-testid="stHeader"] a {{
    color: var(--primary-color) !important;
}}

/* ALL Expanders (Aggressive Fix) */
.streamlit-expanderHeader, 
[data-testid="stExpander"], 
.stExpander {{
    background-color: var(--exp-bg) !important;
    border-radius: 15px !important;
    border: 1px solid var(--glass-border) !important;
    margin-bottom: 0.5rem !important;
    transition: all 0.3s ease !important;
}}

.streamlit-expanderHeader:hover {{
    background-color: var(--exp-hover) !important;
    border-color: var(--primary-color) !important;
}}

.streamlit-expanderHeader p, 
.streamlit-expanderHeader span, 
.streamlit-expanderHeader div, 
.streamlit-expanderHeader svg {{
    color: var(--exp-text) !important;
    fill: var(--exp-text) !important;
    font-weight: 700 !important;
}}

.streamlit-expanderContent {{
    background-color: var(--bg-color) !important;
    color: var(--text-color) !important;
    border-radius: 0 0 15px 15px !important;
    border: 1px solid var(--glass-border) !important;
    border-top: none !important;
}}

/* Sidebar Elements */
[data-testid="stSidebar"] {{
    background-color: var(--sec-bg-color) !important;
    border-right: 1px solid var(--glass-border) !important;
}}
[data-testid="stSidebar"] .stMarkdown p {{
    color: var(--text-color) !important;
    font-weight: 600 !important;
}}

/* Selectboxes and Inputs */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
.stSelectbox div[data-baseweb="select"] {{
    background-color: var(--bg-color) !important;
    color: var(--text-color) !important;
    border-radius: 12px !important;
    border: 1px solid var(--glass-border) !important;
}}

/* Target the dropdown menu itself */
div[data-baseweb="menu"] {{
    background-color: var(--bg-color) !important;
    color: var(--text-color) !important;
    border: 1px solid var(--glass-border) !important;
}}
div[role="option"] {{
    color: var(--text-color) !important;
}}
div[role="option"]:hover {{
    background-color: var(--sec-bg-color) !important;
}}

/* Target Radio Buttons */
div[data-testid="stRadio"] > div {{
    background-color: transparent !important;
}}
div[data-testid="stRadio"] label {{
    color: var(--text-color) !important;
    background-color: var(--bg-color) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: 10px !important;
    padding: 8px 15px !important;
    margin-right: 10px !important;
}}

/* File Uploader (Corrected) */
[data-testid="stFileUploader"] {{
    padding: 0 !important;
    background-color: transparent !important;
}}
[data-testid="stFileUploader"] section {{
    background-color: var(--sec-bg-color) !important;
    border: 2px dashed var(--primary-color) !important;
    border-radius: 20px !important;
    padding: 1.5rem !important;
}}
[data-testid="stFileUploaderDropzone"] {{
    background-color: var(--bg-color) !important;
    border-radius: 15px !important;
}}
[data-testid="stFileUploader"] label,
[data-testid="stFileUploader"] p,
[data-testid="stFileUploader"] span,
[data-testid="stFileUploader"] small {{
    color: var(--text-color) !important;
    font-weight: 500 !important;
}}
[data-testid="stFileUploader"] button {{
    background-color: var(--primary-color) !important;
    color: white !important;
    border-radius: 12px !important;
}}

/* All Alert Overrides */
.stAlert {{
    background-color: var(--sec-bg-color) !important;
    color: var(--text-color) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: 15px !important;
}}
.stAlert svg {{ fill: var(--primary-color) !important; }}

/* ── Main Header ── */
.main-header {{
    text-align: center;
    padding: 3.5rem 0;
    margin-bottom: 2rem;
    background: radial-gradient(circle at center, {accent_glow} 0%, transparent 70%);
    border-radius: 30px;
}}
.main-header h1 {{
    font-size: 4rem !important;
    font-weight: 800 !important;
    background: linear-gradient(135deg, #7c5cbf 0%, #a371f7 30%, #58a6ff 70%, #7c5cbf 100%);
    background-size: 200% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: shine 4s linear infinite;
    letter-spacing: -3px;
    margin: 0 !important;
}}
.main-header p {{
    color: var(--text-color) !important;
    opacity: 0.7;
    font-size: 1.3rem;
    margin-top: 0.8rem;
    font-weight: 400;
}}

@keyframes shine {{
    to {{ background-position: 200% center; }}
}}

/* ── Info Banner (Welcome) ── */
.info-banner {{
    background: var(--sec-bg-color);
    border: 1px solid var(--glass-border);
    border-radius: 28px;
    padding: 3rem;
    text-align: center;
    margin: 2rem 0;
    box-shadow: 0 15px 45px rgba(124, 92, 191, 0.08);
}}
.info-banner h3 {{
    color: var(--primary-color) !important;
    font-weight: 800;
    font-size: 1.8rem !important;
    margin-bottom: 1rem !important;
}}
.info-banner p {{
    color: var(--text-color) !important;
    font-size: 1.1rem !important;
    opacity: 0.8;
}}

/* ── Premium Cards ── */
.result-card {{
    background: var(--sec-bg-color);
    border: 1px solid var(--glass-border);
    border-radius: 24px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    transition: all 0.4s ease;
    box-shadow: 0 8px 25px rgba(0,0,0,0.02);
}}
.result-card:hover {{
    border-color: var(--primary-color);
    transform: translateY(-8px);
    box-shadow: 0 20px 40px rgba(124, 92, 191, 0.12);
}}

/* ── Badges ── */
.score-badge {{
    padding: 0.5rem 1.2rem;
    border-radius: 50px;
    font-size: 0.8rem;
    font-weight: 800;
    text-transform: uppercase;
}}
.score-high {{ background: rgba(0, 200, 100, 0.1); color: #00c864; border: 1px solid rgba(0, 200, 100, 0.2); }}
.score-mid  {{ background: rgba(255, 165, 0, 0.1); color: #ffa500; border: 1px solid rgba(255, 165, 0, 0.2); }}
.score-low  {{ background: rgba(255, 69, 0, 0.1); color: #ff4500; border: 1px solid rgba(255, 69, 0, 0.2); }}

.time-badge {{
    background: rgba(124, 92, 191, 0.1);
    color: var(--primary-color);
    border: 1px solid rgba(124, 92, 191, 0.2);
    border-radius: 12px;
    padding: 0.4rem 0.8rem;
    font-weight: 800;
    font-size: 0.85rem;
}}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
    border-right: 1px solid var(--glass-border);
    background-color: var(--sec-bg-color) !important;
}}

[data-testid="stSidebar"] .stMarkdown p {{
    font-weight: 600;
    color: var(--text-color) !important;
}}

/* Buttons (Premium Glow) */
.stButton > button {{
    border-radius: 18px !important;
    background: var(--brand-gradient) !important;
    color: white !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
    padding: 0.7rem 2rem !important;
    border: none !important;
    transition: all 0.4s ease !important;
    box-shadow: 0 10px 25px rgba(124, 92, 191, 0.25) !important;
    width: 100%;
}}

.stButton > button:hover {{
    transform: translateY(-5px) !important;
    box-shadow: 0 15px 35px rgba(124, 92, 191, 0.4) !important;
}}

/* ── Animated Search Bar ── */
.stTextInput input {{
    border-radius: 18px !important;
    border: 1px solid var(--glass-border) !important;
    background: var(--bg-color) !important;
    color: var(--text-color) !important;
    padding: 0.8rem 1.2rem !important;
}}

.stTextInput input:focus {{
    border-color: var(--primary-color) !important;
    box-shadow: 0 0 15px rgba(124, 92, 191, 0.2) !important;
}}

/* --- Stats --- */
.stat-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.8rem;
    margin-top: 1rem;
}}
.stat-item {{
    background: var(--sec-bg-color);
    border: 1px solid var(--glass-border);
    border-radius: 15px;
    padding: 0.8rem;
    text-align: center;
}}
.stat-value {{ font-size: 1.2rem; font-weight: 800; color: var(--primary-color); }}
.stat-label {{ font-size: 0.7rem; color: var(--text-color); opacity: 0.6; text-transform: uppercase; margin-top: 0.2rem; }}

</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>🎬 Video AI Search</h1>
    <p>Videodan Matn va audio orqali aqlli qidiruv tizimi</p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SIDEBAR — Sozlamalar va Video yuklash
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Tizim Sozlamalari")
    st.markdown("---")

    # --- Til Tanlash ---
    with st.expander("🌐 Til va Hudud", expanded=True):
        lang_choice = st.selectbox(
            "Media tili:",
            ["O'zbekcha", "Russian", "English", "Turkish"],
            index=0
        )
        lang_map = {"O'zbekcha": "uz", "Russian": "ru", "English": "en", "Turkish": "tr"}
        st.session_state.target_lang = lang_map[lang_choice]

    # --- AI Engine sozlamalari ---
    with st.expander("🤖 AI Dvigatel", expanded=True):
        default_engine_idx = 0 if st.session_state.target_lang == "uz" else 1
        
        engine_choice = st.selectbox(
            "Transkripsiya modeli:",
            ["Muxlisa AI (Pro)", "Whisper (Asosiy)"],
            index=0 if st.session_state.target_lang == "uz" else 1,
            help="O'zbek tili uchun 'Muxlisa AI' tavsiya etiladi. Boshqa tillar uchun 'Asosiy' model ishonchliroq.",
        )

        if engine_choice == "Muxlisa AI (Pro)":
            st.success("🛰️ Muxlisa AI (National) faol. O'zbek tili bo'yicha mutaxassis model.")
        else:
            st.session_state.whisper_model = st.selectbox(
                "Whisper model hajmi:",
                ["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                index=["tiny", "base", "small", "medium", "large-v2", "large-v3"].index(
                    st.session_state.whisper_model
                ),
                help="Kattaroq model = aniqroq natija, lekin sekinroq",
            )
            st.info("💡 O'zbek tili uchun `medium` yoki `large-v2` tavsiya etiladi.")


    st.markdown("---")

    # --- Media Yuklash ---
    st.markdown("### 📹 Media Kiritish")
    
    tab_file, tab_mic = st.tabs(["📁 Fayl Yuklash", "🎙️ Ovoz Yozish"])
    
    with tab_file:
        uploaded_file = st.file_uploader(
            "Video yoki Audio yuboring:",
            type=["mp4", "mov", "avi", "mkv", "webm", "mp3", "wav", "m4a", "ogg", "flac"],
            help="Barcha asosiy video va audio formatlar qo'llab-quvvatlanadi",
            key="file_uploader"
        )
        
    with tab_mic:
        st.write("Telegram kabi ovoz yozib yuborish:")
        recorded_audio = st.audio_input("Ovoz yozish", key="mic_input")

    # Bitta faol mediani tanlash
    active_media = recorded_audio if recorded_audio else uploaded_file
    
    # O'zgaruvchilarni umumiy nomga o'tkazish
    uploaded_video = active_media  # Qo'yi qismlar buzilmasligi uchun

    if uploaded_video:
        # Faylni barqaror temp papkada saqlash
        temp_dir = tempfile.gettempdir()
        
        if recorded_audio:
            file_name = "voice_message.wav"
        else:
            file_name = uploaded_video.name
            
        temp_video_path = os.path.join(temp_dir, f"media_ai_{file_name}")

        # Agar fayl nomi o'zgargan bo'lsa yoki fayl mavjud bo'lmasa, qayta saqlaymiz
        if (
            st.session_state.video_name != file_name
            or not os.path.exists(temp_video_path)
            or os.path.getsize(temp_video_path) == 0
        ):
            uploaded_video.seek(0)
            with open(temp_video_path, "wb") as f:
                f.write(uploaded_video.read())

        # Yangi video yoki o'zgartirish holatida tasdiqlash tugmasi
        if st.session_state.video_path != temp_video_path:
            if st.button("🚀 Qayta Ishlash", use_container_width=True):
                st.session_state.video_path = temp_video_path
                st.session_state.video_name = file_name
                st.session_state.segments = []
                st.session_state.index_built = False
                st.session_state.last_results = []
                st.session_state.play_timestamp = 0
                st.session_state.processing = True
                st.rerun()

        elif st.session_state.index_built:
            st.success(f"✅ Tayyor: **{file_name}**")
            if st.session_state.segments:
                seg_count = len(st.session_state.segments)
                dur = st.session_state.video_duration
                m, s = divmod(int(dur), 60)
                st.write(f"Segmentlar: {seg_count}")
                st.write(f"Davomiylik: {m}:{s:02d}")

    st.markdown("---")
    col_l, col_d = st.columns(2)
    with col_l:
        if st.button("☀️ Light", use_container_width=True, key="light_btn"):
            st.session_state.theme = "light"
            st.rerun()
    with col_d:
        if st.button("🌙 Dark", use_container_width=True, key="dark_btn"):
            st.session_state.theme = "dark"
            st.rerun()

    st.markdown("""
    <div style="text-align:center; padding-top: 0.5rem;">
        <div style="color:#8b949e; font-size:0.75rem; font-weight: 500;">
            AI Qidiruv Tizimi
        </div>
        <div style="color:#7c5cbf; font-size:0.7rem; opacity: 0.5; margin-top: 0.3rem; letter-spacing: 0.5px; font-weight:700">
            V1.0.0 · AI SEARCH ENGINE
        </div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# VIDEO QAYTA ISHLASH
# ─────────────────────────────────────────────
if st.session_state.processing and st.session_state.video_path:
    st.session_state.processing = False
    video_path = st.session_state.video_path

    progress_container = st.container()
    with progress_container:
        st.markdown("### ⚙️ Qayta Ishlash Bosqichlari")
        progress_bar = st.progress(0)
        status_text = st.empty()

        # ── Qadam 1: Video ma'lumotlari ──
        status_text.markdown("**1/4** 📋 Video ma'lumotlari o'qilmoqda...")
        progress_bar.progress(10)
        from video_processor import get_video_info
        info = get_video_info(video_path)
        st.session_state.video_duration = info.get("duration_sec", 0)
        time.sleep(0.3)

        # ── Qadam 2: Audio ajratish ──
        status_text.markdown("**2/4** 🔊 Audio ajratilmoqda (Tezkor rejim)...")
        progress_bar.progress(25)
        from video_processor import extract_audio
        audio_path = extract_audio(video_path, format="mp3", sample_rate=16000)

        if not audio_path:
            st.error("❌ Audio ajratib bo'lmadi. Video fayldа audio trek mavjudligini tekshiring.")
            st.stop()

        progress_bar.progress(40)

        # ── Qadam 3: Nutqni matnga o'tkazish ──
        status_text.markdown("**3/4** 🧠 Nutq matnga o'tkazilmoqda ...")
        progress_bar.progress(45)

        from speech_to_text import SpeechToText
        stt = SpeechToText(
            whisper_model_size=st.session_state.whisper_model,
            language=st.session_state.target_lang,
            use_api=(engine_choice in ["Muxlisa AI (Pro)"]),
            elevenlabs_api_key=None,
            engine_name=engine_choice
        )
        st.session_state.stt_engine = stt
        st.session_state.engine_name = stt.get_engine_name()

        segments = stt.transcribe(audio_path)
        st.session_state.segments = segments

        # Temp audio faylni o'chirish
        from utils import cleanup_file
        cleanup_file(audio_path)

        progress_bar.progress(70)

        if not segments:
            st.warning("⚠️ Audio transkripsiya natijalari bo'sh. Boshqa model yoki fayl sinab ko'ring.")
            st.stop()

        # ── Qadam 4: Semantik indeks yaratish ──
        status_text.markdown(f"**4/4** 🔍 Semantik qidiruv indeksi yaratilmoqda ({len(segments)} segment)...")
        progress_bar.progress(80)

        from semantic_search import SemanticSearch
        search_engine = SemanticSearch()
        count = search_engine.add_transcripts(segments)
        st.session_state.search_engine = search_engine
        st.session_state.index_built = True

        progress_bar.progress(100)
        status_text.markdown(f"✅ **Tayyorlandi!** {count} segment indekslandi.")
        time.sleep(1)

    st.rerun()

# ─────────────────────────────────────────────
# ASOSIY QISM: Qidiruv va Natijalar
# ─────────────────────────────────────────────
if not st.session_state.index_built:
    # Xush kelibsiz sahifasi
    st.markdown("""
    <div class="info-banner">
        <div style="font-size: 3rem; margin-bottom: 1rem;">🚀</div>
        <h3>Boshlash uchun video yuklang</h3>
        <p style="opacity:0.8; font-size:1.1rem">Chap paneldan video faylni yuklang va "Videoni Qayta Ishlash" tugmasini bosing</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        <div class="result-card" style="text-align:center; animation-delay: 0.1s;">
            <div style="font-size:2.5rem; margin-bottom:1rem">📹</div>
            <div style="font-weight:700; font-size:1.1rem; margin-bottom:0.5rem">Video Yuklash</div>
            <div style="color:#8b949e; font-size:0.9rem">MP4, MOV, AVI kabi barcha formatlar</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="result-card" style="text-align:center; animation-delay: 0.2s;">
            <div style="font-size:2.5rem; margin-bottom:1rem">🧠</div>
            <div style="font-weight:700; font-size:1.1rem; margin-bottom:0.5rem">AI Tahlil</div>
            <div style="color:#8b949e; font-size:0.9rem">Whisper + Semantik mantiqiy tahlil</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="result-card" style="text-align:center; animation-delay: 0.3s;">
            <div style="font-size:2.5rem; margin-bottom:1rem">🔍</div>
            <div style="font-weight:700; font-size:1.1rem; margin-bottom:0.5rem">Tezkor Qidiruv</div>
            <div style="color:#8b949e; font-size:0.9rem">Matn yoki ovoz orqali natijalar</div>
        </div>
        """, unsafe_allow_html=True)

else:
    # ── Qidiruv va Video ──
    col_search, col_video = st.columns([1, 1], gap="large")

    # ─── QIDIRUV USTUNI ───
    with col_search:
        st.markdown("### 🔍 Qidiruv")

        # Engine ko'rsatkichi
        st.write(f"Robot: {st.session_state.engine_name}")
        st.markdown("")

        # Qidiruv rejimi
        search_mode = st.radio(
            "Qidiruv turi:",
            ["📝 Matn orqali", "🎤 Audio orqali"],
            horizontal=True,
        )
        st.markdown("")

        query_text = ""
        perform_search = False

        # ── Matn qidiruv ──
        if search_mode == "📝 Matn orqali":
            query_text = st.text_input(
                "So'rov kiriting:",
                placeholder="Misol: qush, mashina o'qitish...",
                key="text_query",
            )
            top_k = st.slider("Nechta natija ko'rsatilsin:", 1, 10, 3)

            if st.button("🔍 Qidirish", use_container_width=True, type="primary"):
                if query_text.strip():
                    perform_search = True
                else:
                    st.warning("⚠️ Qidiruv matni kiriting.")

        # ── Audio qidiruv ──
        else:
            st.info("🎤 Ovozli so'rovingizni yozing yoki audio fayl yuklang.")
            
            # Yangi: st.audio_input - Telegram kabi ovoz yozish uchun
            recorded_audio = st.audio_input("Ovozli qidiruv:")
            
            # Eski: fayl yuklash (fallback)
            uploaded_audio = st.file_uploader(
                "Yoki audio fayl yuklang:",
                type=["mp3", "wav", "ogg", "m4a"],
                key="audio_query_file",
            )
            
            top_k = st.slider("Nechta natija ko'rsatilsin:", 1, 10, 3, key="top_k_audio")

            # Qidiruv audio manbai (yo yozilgan, yo yuklangan)
            audio_source = recorded_audio or uploaded_audio

            if audio_source:
                if st.button("🔍 Audio orqali Qidirish", use_container_width=True, type="primary"):
                    with st.spinner("Audio tahlil qilinmoqda..."):
                        # Faylni saqlash
                        suffix = ".wav" if recorded_audio else f".{uploaded_audio.name.split('.')[-1]}"
                        tmp_f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                        tmp_f.write(audio_source.read())
                        tmp_f.close()

                        stt = st.session_state.stt_engine
                        if stt is None:
                            from speech_to_text import SpeechToText
                            stt = SpeechToText(
                                whisper_model_size=st.session_state.whisper_model,
                                language="uz",
                                elevenlabs_api_key=st.session_state.elevenlabs_key or None,
                            )
                            st.session_state.stt_engine = stt

                        q_segments = stt.transcribe(tmp_f.name)
                        from utils import cleanup_file
                        cleanup_file(tmp_f.name)

                        if q_segments:
                            query_text = " ".join(s["text"] for s in q_segments)
                            st.success(f"🎤 Tanilgan matn: *{query_text}*")
                            perform_search = True
                        else:
                            st.error("❌ Audioni matnga o'tkazib bo'lmadi.")

        # ── Natijalarni ko'rsatish ──
        if perform_search and query_text.strip():
            with st.spinner("Qidirilmoqda..."):
                # So'zma-so'z segmentlar uchun context_window qo'shish natijani o'qishni osonlashtiradi
                results = st.session_state.search_engine.search_with_context(
                    query_text.strip(), top_k=top_k, context_window=5
                )
            
            st.session_state.last_results = results
            
            # Agar kamida bitta natija bo'lsa, avtomatik birinchi natija vaqtiga o'tkazish
            if results and len(results) > 0:
                st.session_state.play_timestamp = float(results[0]["start"])
                st.rerun()

        if st.session_state.last_results:
            st.markdown(f"#### 📋 Natijalar — {len(st.session_state.last_results)} ta topildi")

            for i, res in enumerate(st.session_state.last_results):
                score = res["score"]
                from utils import format_time, score_to_percent, get_similarity_label, highlight_text
                label, _ = get_similarity_label(score)

                score_css = "score-high" if score >= 0.65 else ("score-mid" if score >= 0.4 else "score-low")
                start_fmt = format_time(res["start"])
                end_fmt = format_time(res["end"])

                # Contextual text bo'lsa uni ishlatamiz (so'zma-so'z qidiruvda readability uchun)
                display_text = res.get("context_text", res["text"])
                highlighted = highlight_text(display_text, query_text)

                st.markdown(f"""
                <div class="result-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.6rem">
                        <span style="color:#8b949e;font-size:0.85rem">№{i+1}</span>
                        <span class="score-badge {score_css}">{score_to_percent(score)} — {label}</span>
                    </div>
                    <div style="font-size:0.95rem;line-height:1.6;margin-bottom:0.7rem">{highlighted}</div>
                    <span class="time-badge">⏱ {start_fmt} → {end_fmt}</span>
                </div>
                """, unsafe_allow_html=True)

                if st.button(f"▶ {start_fmt} dan ijro etish", key=f"play_{i}_{start_fmt}"):
                    st.session_state.play_timestamp = float(res["start"])
                    st.rerun()

        elif st.session_state.last_results == [] and perform_search:
            st.markdown("""
            <div class="result-card" style="text-align:center;padding:2rem">
                <div style="font-size:2rem">🔍</div>
                <div style="color:#8b949e">Bu so'rov uchun natija topilmadi.</div>
                <div style="color:#444;font-size:0.85rem;margin-top:0.4rem">Boshqa kalit so'zlar bilan urinib ko'ring.</div>
            </div>
            """, unsafe_allow_html=True)

    # ─── MEDIA USTUNI ───
    with col_video:
        st.markdown("### 🎬 Media Player")

        if st.session_state.video_path and os.path.exists(st.session_state.video_path):
            start_time = st.session_state.get("play_timestamp", 0)
            
            # Subtitrlarni tayyorlash (agar mavjud bo'lsa)
            vtt_subs = None
            if st.session_state.get("segments"):
                from utils import segments_to_vtt
                vtt_text = segments_to_vtt(st.session_state.segments)
                # Streamlit v1.34+ expects a dictionary for labels or a direct string
                vtt_subs = {"Subtitrlar (AI)": vtt_text}

            try:
                ext = os.path.splitext(st.session_state.video_path)[1].lower()
                is_audio = ext in [".mp3", ".wav", ".m4a", ".ogg", ".flac"]
                
                if is_audio:
                    if st.session_state.segments:
                        from subtitle_engine import render_youtube_player
                        render_youtube_player(st.session_state.video_path, st.session_state.segments, start_time=start_time)
                    else:
                        st.audio(st.session_state.video_path, start_time=start_time)
                else:
                    if st.session_state.segments:
                        from subtitle_engine import render_youtube_player
                        render_youtube_player(st.session_state.video_path, st.session_state.segments, start_time=start_time)
                    else:
                        st.video(st.session_state.video_path, start_time=start_time)
            except Exception as e:
                st.error(f"Media yuklashda xato: {e}")

        # ── Transkript ──
        st.markdown("---")
        with st.expander("📜 To'liq Transkript", expanded=False):
            if st.session_state.segments:
                # SRT yuklab olish tugmasi
                from utils import segments_to_srt, segments_to_text
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    srt_content = segments_to_srt(st.session_state.segments)
                    st.download_button(
                        "⬇ SRT yuklab olish",
                        data=srt_content,
                        file_name="transkript.srt",
                        mime="text/plain",
                        use_container_width=True,
                    )
                with col_dl2:
                    txt_content = segments_to_text(st.session_state.segments)
                    st.download_button(
                        "⬇ TXT yuklab olish",
                        data=txt_content,
                        file_name="transkript.txt",
                        mime="text/plain",
                        use_container_width=True,
                    )
                
                # Word-level JSON export
                json_content = json.dumps(st.session_state.segments, indent=2, ensure_ascii=False)
                st.download_button(
                    "⬇ Word-level JSON (YouTube style)",
                    data=json_content,
                    file_name="word_timestamps.json",
                    mime="application/json",
                    use_container_width=True,
                )

                st.markdown("")
                from utils import format_time
                for seg in st.session_state.segments:
                    ts = format_time(seg["start"])
                    st.write(f"[{ts}] {seg['text']}")
            else:
                st.info("Transkript mavjud emas.")

        # Initialize tts_engine if not already in session state
        if "tts_engine" not in st.session_state:
            st.session_state.tts_engine = "ElevenLabs" # Default value

        st.markdown("### 🗣️ Matnni nutqqa aylantirish (TTS)")
        st.session_state.tts_engine = st.radio(
            "TTS Engine:",
            ["Muxlisa", "Whisper"],
            index=0 if st.session_state.tts_engine == "Muxlisa" else 1,
            help="Nutq generatsiya qilish uchun modelni tanlang."
        )

        tts_text = st.text_area("Nutq uchun matn:", placeholder="Bu yerga matn kiriting...")
        if st.button("🎙️ Nutq yaratish", use_container_width=True):
            if tts_text.strip():
                with st.spinner(f"{st.session_state.tts_engine} orqali generatsiya qilinmoqda..."):
                    from tts_engine import safe_tts
                    audio_data, tts_segments = safe_tts(tts_text.strip(), engine=st.session_state.tts_engine)
                    
                    if audio_data:
                        st.success("✅ Nutq va subtitrlar muvaffaqiyatli yaratildi!")
                        # Vaqtinchalik faylga saqlash (Streamlit player uchun)
                        tts_path = "tmp_tts.mp3"
                        with open(tts_path, "wb") as f:
                            f.write(audio_data)
                        
                        # Custom player bilan ko'rsatish
                        from subtitle_engine import render_youtube_player
                        render_youtube_player(tts_path, tts_segments)
                    else:
                        st.error("❌ Nutq yaratishda xato yuz berdi. Loglarni tekshiring.")
            else:
                st.warning("⚠️ Iltimos, matn kiriting.")
        
        st.markdown("---")
        st.markdown("### ℹ️ Ma'lumot")
        # ── Video statistika ──
        if st.session_state.segments:
            total_words = sum(len(s["text"].split()) for s in st.session_state.segments)
            dur = st.session_state.video_duration
            m, s_sec = divmod(int(dur), 60)

            st.write(f"Segmentlar: {len(st.session_state.segments)}")
            st.write(f"So'zlar: {total_words}")
            st.write(f"Davomiylik: {m}:{s_sec:02d}")
