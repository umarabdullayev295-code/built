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
import gc
from pathlib import Path
from dotenv import load_dotenv

from ui_styles import init_state, apply_theme_from_query_params, inject_global_styles
from ui_sidebar import render_sidebar

# Qidiruv natijasiga sakraganda so'zni "kesib yubormaslik" uchun
# biroz oldindan boshlaymiz.
SEEK_PREROLL_SEC = 0.35

# Load environment variables
load_dotenv()

# --- Ilovani Sozlash ---
st.set_page_config(
    page_title="Asosiy qidiruv · Video AI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_state()
apply_theme_from_query_params()
inject_global_styles()

# ─────────────────────────────────────────────
# (CSS ui_styles.py da — universal + responsive)
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown(f"""
<div class="main-header">
    <h1>🎬 Video AI Search</h1>
    <p>Videodan matn va audio orqali aqlli qidiruv</p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SIDEBAR (umumiy modul)
# ─────────────────────────────────────────────
render_sidebar()

# ─────────────────────────────────────────────
# VIDEO QAYTA ISHLASH
# ─────────────────────────────────────────────
if st.session_state.processing and st.session_state.video_path:
    st.session_state.processing = False
    video_path = st.session_state.video_path

    with st.spinner("⏳ Qayta ishlanmoqda, biroz kuting..."):
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
            from video_processor import extract_audio, LAST_AUDIO_EXTRACT_DIAGNOSTIC
            audio_path = extract_audio(video_path, output_ext="wav")

            if not audio_path:
                st.error("❌ Audio ajratib bo'lmadi. Video faylda audio oqimi bor-yo‘qligini tekshiring (yoki ffmpeg o‘rnatilganligini).")
                if LAST_AUDIO_EXTRACT_DIAGNOSTIC:
                    with st.expander("Texnik tafsilot (ffmpeg)"):
                        st.code(LAST_AUDIO_EXTRACT_DIAGNOSTIC[:4000], language="text")
                st.stop()

            progress_bar.progress(40)

            # ── Qadam 3: Nutqni matnga o'tkazish ──
            status_text.markdown("**3/4** 🧠 Nutq matnga o'tkazilmoqda ...")
            progress_bar.progress(45)

            from speech_to_text import SpeechToText
            engine_choice = st.session_state.get("engine_choice", "Whisper (Asosiy)")
            stt = SpeechToText(
                whisper_model_size=st.session_state.get("whisper_model", "base"),
                language=st.session_state.target_lang,
                use_api=("Muxlisa" in engine_choice),
                engine_name=engine_choice,
            )
            st.session_state.stt_engine = stt
            st.session_state.engine_name = stt.get_engine_name()
            segments = stt.transcribe(audio_path)
            
            # Qat'iy global autoscale: Barcha modullar (SRT, semantic_search, player) uchun 
            # faqat moslashtirilgan mukammal time o'zlashtiriladi!
            if segments and st.session_state.video_duration > 0:
                from subtitle_engine import scale_timestamps
                segments = scale_timestamps(segments, st.session_state.video_duration, debug=False)
                
            st.session_state.segments = segments
            # Temp audio faylni o'chirish
            from utils import cleanup_file
            cleanup_file(audio_path)

            progress_bar.progress(70)

            if not segments:
                st.warning("⚠️ Audio transkripsiya natijalari bo'sh. Boshqa model yoki fayl sinab ko'ring.")
                st.stop()
            
            st.toast("✅ Transkripsiya muvaffaqiyatli yakunlandi!", icon="🎯")

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
            st.toast(f"✅ {count} ta segment tahlil qilindi!", icon="🚀")
            
            # Tugatgandan so'ng xotirani tozalash
            gc.collect()
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
            <div style="color:var(--muted-text); font-size:0.9rem">MP4, MOV, AVI kabi barcha formatlar</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="result-card" style="text-align:center; animation-delay: 0.2s;">
            <div style="font-size:2.5rem; margin-bottom:1rem">🧠</div>
            <div style="font-weight:700; font-size:1.1rem; margin-bottom:0.5rem">AI Tahlil</div>
            <div style="color:var(--muted-text); font-size:0.9rem">Whisper + Semantik mantiqiy tahlil</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="result-card" style="text-align:center; animation-delay: 0.3s;">
            <div style="font-size:2.5rem; margin-bottom:1rem">🔍</div>
            <div style="font-weight:700; font-size:1.1rem; margin-bottom:0.5rem">Tezkor Qidiruv</div>
            <div style="color:var(--muted-text); font-size:0.9rem">Matn yoki ovoz orqali natijalar</div>
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
                                whisper_model_size=st.session_state.get("whisper_model", "base"),
                                language="uz",
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
                st.session_state.play_timestamp = max(
                    0.0, float(results[0]["start"]) - SEEK_PREROLL_SEC
                )
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
                        <span style="color:var(--muted-text);font-size:0.85rem">№{i+1}</span>
                        <span class="score-badge {score_css}">{score_to_percent(score)} — {label}</span>
                    </div>
                    <div style="font-size:0.95rem;line-height:1.6;margin-bottom:0.7rem">{highlighted}</div>
                    <span class="time-badge">⏱ {start_fmt} → {end_fmt}</span>
                </div>
                """, unsafe_allow_html=True)

                if st.button(f"▶ {start_fmt} dan ijro etish", key=f"play_{i}_{start_fmt}"):
                    st.session_state.play_timestamp = max(
                        0.0, float(res["start"]) - SEEK_PREROLL_SEC
                    )
                    st.rerun()

        elif st.session_state.last_results == [] and perform_search:
            st.markdown("""
            <div class="result-card" style="text-align:center;padding:2rem">
                <div style="font-size:2rem">🔍</div>
                <div style="color:var(--muted-text)">Bu so'rov uchun natija topilmadi.</div>
                <div style="color:var(--text-color);opacity:0.82;font-size:0.85rem;margin-top:0.4rem">Boshqa kalit so'zlar bilan urinib ko'ring.</div>
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
                        render_youtube_player(
                            st.session_state.video_path, 
                            st.session_state.segments, 
                            start_time=start_time,
                            video_duration=st.session_state.get('video_duration', 0.0),
                            debug=False,
                            latency_offset=0.0,
                        )
                    else:
                        st.audio(st.session_state.video_path, start_time=start_time)
                else:
                    if st.session_state.segments:
                        from subtitle_engine import render_youtube_player
                        render_youtube_player(
                            st.session_state.video_path, 
                            st.session_state.segments, 
                            start_time=start_time,
                            video_duration=st.session_state.get('video_duration', 0.0),
                            debug=False,
                            latency_offset=0.0,
                        )
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
