"""Chap panel: tema, sozlamalar, media yuklash — barcha sahifalar uchun umumiy."""
import gc
import os
import tempfile
import time

import streamlit as st


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## ⚙️ Tizim Sozlamalari")
        st.markdown("---")

        with st.expander("🌐 Til va Hudud", expanded=True):
            lang_choice = st.selectbox(
                "Media tili:",
                ["O'zbekcha", "Russian", "English", "Turkish"],
                index=0,
            )
            lang_map = {"O'zbekcha": "uz", "Russian": "ru", "English": "en", "Turkish": "tr"}
            st.session_state.target_lang = lang_map[lang_choice]

        with st.expander("🤖 AI Dvigatel", expanded=True):
            if st.session_state.target_lang == "uz":
                if "engine_label_ui" not in st.session_state:
                    st.session_state.engine_label_ui = (
                        "Whisper (Asosiy)"
                        if "Whisper" in st.session_state.get("engine_choice", "")
                        else "UzbekPro"
                    )

                engine_label = st.selectbox(
                    "Transkripsiya modeli:",
                    ["UzbekPro", "Whisper (Asosiy)"],
                    index=0 if st.session_state.engine_label_ui == "UzbekPro" else 1,
                    key="engine_label_ui",
                    help="O'zbek tili uchun 'UzbekPro' tavsiya etiladi (60s gacha).",
                )
                engine_choice = (
                    "Muxlisa AI (Uzbek Pro)"
                    if engine_label == "UzbekPro"
                    else "Whisper (Asosiy)"
                )
            else:
                engine_label = "Whisper (Asosiy)"
                engine_choice = "Whisper (Asosiy)"
                st.info(f"💡 {lang_choice} tili uchun Whisper qo'llaniladi.")

            st.session_state["engine_choice"] = engine_choice

            if engine_label == "UzbekPro":
                st.success("🛰️ UzbekPro faol.")
                st.warning("⚠️ UzbekPro rejimi uchun media davomiyligi 60s gacha.")
            else:
                st.session_state["whisper_model"] = st.selectbox(
                    "Whisper model hajmi:",
                    ["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                    index=1,
                )
                st.info("💡 O'zbek tili uchun `medium` yoki `large-v2` tavsiya etiladi.")

        st.markdown("---")

        st.markdown("### 📹 Media Kiritish")

        tab_file, tab_mic = st.tabs(["📁 Fayl Yuklash", "🎙️ Ovoz Yozish"])

        with tab_file:
            uploaded_file = st.file_uploader(
                "Video yoki Audio yuboring:",
                type=["mp4", "mov", "avi", "mkv", "webm", "mp3", "wav", "m4a", "ogg", "flac"],
                help="Barcha asosiy video va audio formatlar qo'llab-quvvatlanadi",
                key="file_uploader",
            )

        with tab_mic:
            st.write("Telegram kabi ovoz yozib yuborish:")
            recorded_audio = st.audio_input("Ovoz yozish", key="mic_input")

        active_media = recorded_audio if recorded_audio else uploaded_file
        uploaded_video = active_media

        if uploaded_video:
            temp_dir = tempfile.gettempdir()

            if recorded_audio:
                file_name = "voice_message.wav"
            else:
                file_name = uploaded_video.name

            temp_video_path = os.path.join(temp_dir, f"media_ai_{file_name}")

            if st.button("🚀 Qayta Ishlash", use_container_width=True):
                prev_video_path = st.session_state.get("video_path")

                # Har safar qayta ishlashda yuklangan media faylni qayta yozamiz.
                # Bu bir xil nomli yangi fayl yuklanganda ham to'g'ri ishlashini ta'minlaydi.
                uploaded_video.seek(0)
                with open(temp_video_path, "wb") as f:
                    while True:
                        chunk = uploaded_video.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                gc.collect()

                # Streamlit Cloud (1GB RAM) uchun agressiv tozalash:
                # oldingi natijalar, keshlangan resurslar va temp videoni bo'shatamiz.
                try:
                    if prev_video_path and prev_video_path != temp_video_path and os.path.exists(prev_video_path):
                        os.remove(prev_video_path)
                except Exception:
                    pass

                st.session_state.search_engine = None
                st.session_state.stt_engine = None
                st.session_state.segments = []
                st.session_state.last_results = []
                st.session_state.engine_name = ""
                st.session_state.video_duration = 0
                st.session_state.index_built = False

                # Model/embedding cache'lari RAM'ni ushlab qolmasligi uchun
                st.cache_data.clear()
                st.cache_resource.clear()

                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass

                gc.collect()

                # Faqat UzbekPro rejimida 60s limitni tekshiramiz.
                if "Muxlisa" in st.session_state.get("engine_choice", ""):
                    try:
                        from video_processor import get_video_info
                        info = get_video_info(temp_video_path)
                        dur = float(info.get("duration_sec", 0) or 0)
                        if dur > 60.0:
                            st.error("❌ UzbekPro rejimida media davomiyligi 60 sekunddan oshmasligi kerak.")
                            return
                    except Exception:
                        st.warning("⚠️ Davomiylikni tekshirib bo'lmadi. UzbekPro uchun 60s limitni hisobga oling.")

                st.session_state.video_path = temp_video_path
                st.session_state.video_name = file_name
                st.session_state.play_timestamp = 0
                st.session_state.processing = True
                st.rerun()

            if st.session_state.index_built and st.session_state.video_path == temp_video_path:
                st.success(f"✅ Tayyor: **{file_name}**")
                if st.session_state.segments:
                    seg_count = len(st.session_state.segments)
                    dur = st.session_state.video_duration
                    m, s = divmod(int(dur), 60)
                    st.write(f"Segmentlar: {seg_count}")
                    st.write(f"Davomiylik: {m}:{s:02d}")

        st.markdown("---")
        if st.button(
            "🗑️ Cache va RAMni tozalash",
            use_container_width=True,
            help="Barcha yuklangan modellar va vaqtinchalik xotirani tozalaydi",
        ):
            st.cache_resource.clear()
            st.cache_data.clear()
            gc.collect()
            st.success("✅ Xotira tozalandi!")
            time.sleep(1)
            st.rerun()

        st.markdown(
            """
            <div style="text-align:center; padding-top: 0.5rem;">
                <div style="color:var(--muted-text); font-size:0.75rem; font-weight:500;">
                    AI Qidiruv Tizimi
                </div>
                <div style="color:var(--primary-color); font-size:0.7rem; opacity:0.7; margin-top:0.3rem; letter-spacing:0.5px; font-weight:700;">
                    V1.0.0 · AI SEARCH ENGINE
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
        theme_menu = st.selectbox(
            "Tema",
            ["🌙 Qorong'u", "☀️ Yorug'"],
            index=0 if st.session_state.theme == "dark" else 1,
            key="theme_bottom_menu",
        )
        desired_theme = "dark" if theme_menu.startswith("🌙") else "light"
        if desired_theme != st.session_state.theme:
            st.session_state.theme = desired_theme
            st.query_params["set_theme"] = desired_theme
            st.rerun()
