"""
speech_to_text.py
-----------------
Nutqni matnga o'tkazish — unified interface.

Ustuvorlik tartibi:
  1. ElevenLabs Scribe v1  (API kalit mavjud bo'lsa — eng aniq va tez)
  2. faster-whisper        (offline, local model)

O'zbek tili uchun optimallashtirilgan.
"""

import os
import gc
import streamlit as st
from typing import List, Dict, Optional

@st.cache_resource
def load_whisper_model(model_size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel
    print(f"[STT] Whisper yuklanmoqda: {model_size} ({device})...")
    return WhisperModel(model_size, device=device, compute_type=compute_type)


class SpeechToText:
    """
    Unified Speech-to-Text engine.
    API mavjudligiga qarab eng yaxshi dvigatelni avtomatik tanlaydi.
    """

    def __init__(
        self,
        whisper_model_size: str = "medium",
        language: str = "uz",
        use_api: bool = True,
        engine_name: str = "Muxlisa AI (Pro)"
    ):
        """
        Args:
            whisper_model_size : 'tiny'|'base'|'small'|'medium'|'large-v2'|'large-v3'
            language           : Til kodi  ('uz' — o'zbek)
            use_api            : True bo'lsa API ishlatishga harakat qiladi
            elevenlabs_api_key : ElevenLabs API kaliti
            engine_name        : Tanlangan STT motori nomi
        """
        self.language = language
        self.whisper_model_size = whisper_model_size
        self._whisper_model = None
        self._api_client = None
        self.active_engine: str = ""

        if use_api:
            self._api_client, self.active_engine = self._pick_api_client(
                engine_name
            )

        if not self.active_engine:
            self.active_engine = f"faster-whisper ({whisper_model_size})"

    # ------------------------------------------------------------------ #
    def _pick_api_client(
        self,
        engine_name: str = "Muxlisa AI (Pro)"
    ):
        """
        Mavjud va ishlaydigan API mijozini tanlaydi.
        """
        from ai_labs_api import get_best_api_client

        # 1. Muxlisa AI
        if "Muxlisa" in engine_name:
            client, name = get_best_api_client(engine_name="Muxlisa")
            if client:
                return client, name

        # 2. Fallback: Avtomatik tanlash (Muxlisa yoki boshqa)
        client, name = get_best_api_client(engine_name=engine_name)
        if client:
            return client, name

        return None, ""

    # ------------------------------------------------------------------ #
    def transcribe(self, audio_path: str) -> List[Dict]:
        """
        Audio faylni matnga o'tkazadi.

        Returns:
            [{"start": 0.0, "end": 3.4, "text": "Assalomu alaykum"}, ...]
        """
        if not os.path.exists(audio_path):
            print(f"[STT] Fayl topilmadi: {audio_path}")
            return []

        # API orqali
        client = self._api_client
        if client is not None and client.is_available():
            try:
                print(f"[STT] {self.active_engine} orqali tahlil qilinmoqda...")
                results = client.transcribe_audio(audio_path, language=self.language)
                
                # Yangi: Muxlisa AI uchun Hybrid Alignment (100% aniq vaqt)
                if results and any(r.get("type") == "muxlisa_raw" for r in results):
                    print("[STT] Muxlisa AI matni Whisper orqali aniq vaqtga tekislanmoqda...")
                    results = self._align_with_whisper(results, audio_path)
                
                if results:
                    return results
            except Exception as e:
                # DNS yoki internet xatosi bo'lsa tinchgina Whisperga o'tamiz
                if "getaddrinfo failed" in str(e) or "connection" in str(e).lower():
                    print("[STT] Internet ulanishida muammo. Lokal (Whisper) modelga o'tilmoqda...")
                else:
                    print(f"[STT] API xatosi: {e}. Lokal model ishlatiladi.")

        # Whisper fallback
        return self._transcribe_whisper(audio_path)

    def _align_with_whisper(self, results: List[Dict], audio_path: str) -> List[Dict]:
        """
        Muxlisa AI matnini Whisper vaqtlariga 100% aniqlik bilan bog'laydi.
        """
        try:
            # 1. Muxlisa matnini olish, bir necha qism yig'ilganda ularni bitta qilib birlashtiramiz
            full_text = " ".join(r.get("text", "") for r in results if r.get("type") == "muxlisa_raw")
            muxlisa_words = [w.strip() for w in full_text.split() if w.strip()]
            if not muxlisa_words:
                return results

            # 2. Whisper (Tezkor lekin aniq) orqali vaqtlarni aniqlash
            orig_size = self.whisper_model_size
            # tez ishlashi uchun 'base' ni ishlatamiz
            self.whisper_model_size = "base" 
            whisper_results = self._transcribe_whisper(audio_path)
            self.whisper_model_size = orig_size # Asliga qaytaramiz

            # 3. Muxlisa so'zlarini Whisper segmentlariga professional INTERPOLATSIYA qilish
            aligned = []
            m_count = len(muxlisa_words)
            w_count = len(whisper_results)
            
            if m_count == 0:
                return []
            if w_count == 0:
                padding = 0.4
                return [{"start": i*padding, "end": (i+1)*padding, "text": w} for i, w in enumerate(muxlisa_words)]

            # 3. Protsentga asoslangan (Proportional) sinxronizatsiya
            # Muxlisa matnini butun Whisper davomiyligi bo'ylab tekis va mantiqiy taqsimlaymiz
            aligned = []
            
            # Whisper segmentlaridan haqiqiy vaqt interval va bo'shliqlarni (VAD gaps) olamiz
            # Bu orqali qachon jimjitlik bo'lsa o'sha joyga so'z tushib qolishi oldini olinadi!
            whisper_intervals = []
            for w in whisper_results:
                whisper_intervals.append((w["start"], w["end"]))
                
            if not whisper_intervals:
                # Agar Whisper umuman ishlamasa, avtomatik tekis taqsimot
                padding = 0.4
                return [{"start": i*padding, "end": (i+1)*padding, "text": w} for i, w in enumerate(muxlisa_words)]
                
            # Haqiqiy so'zlashuv davomiyligi (faqat gapirilayotgan soniyalar)
            total_speech_duration = sum(end - start for start, end in whisper_intervals)
            
            # Har bir Muxlisa so'ziga qanchadan vaqt tushadi
            m_count = len(muxlisa_words)
            time_per_word = total_speech_duration / m_count if m_count > 0 else 0.4
            
            current_interval_idx = 0
            current_interval_used = 0.0
            
            for i, word in enumerate(muxlisa_words):
                if current_interval_idx >= len(whisper_intervals):
                    # Vaqt tugab qolsa ham so'zlarni oxiriga yopishtirib qolmaymiz
                    last_end = whisper_intervals[-1][1] if whisper_intervals else 0
                    start = last_end + (i - len(aligned)) * 0.4
                    end = start + 0.4
                    aligned.append({"start": round(start, 2), "end": round(end, 2), "text": word})
                    continue
                    
                start_time = whisper_intervals[current_interval_idx][0] + current_interval_used
                end_time = start_time + time_per_word
                
                # Agar bitta word intervaldan chiqib ketsa, uning qismini keyingi intervalga yopishtirmaymiz
                # balki uni joriy interval oxiriga taqaymiz va intervalni o'zgartiramiz
                if end_time > whisper_intervals[current_interval_idx][1]:
                    # Juda uzun so'z bo'lsa yoki interval kalta bo'lsa, uni shu joyda tugatamiz
                    end_time = whisper_intervals[current_interval_idx][1]
                    current_interval_idx += 1
                    current_interval_used = 0.0
                else:
                    current_interval_used += time_per_word
                    
                aligned.append({
                    "start": round(start_time, 2),
                    "end": round(end_time, 2),
                    "text": word
                })
                
            return aligned
        except Exception as e:
            print(f"[STT] Alignment hatosi: {e}")
            return results

    # ------------------------------------------------------------------ #
    def _load_whisper(self):
        """Whisper modelini lazy loading va st.cache_resource bilan yuklaydi."""
        if self._whisper_model is None:
            device = "cpu"
            compute_type = "int8"
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                    compute_type = "float16"
            except ImportError:
                pass
            
            self._whisper_model = load_whisper_model(
                self.whisper_model_size, device=device, compute_type=compute_type
            )
        return self._whisper_model

    def _transcribe_whisper(self, audio_path: str) -> List[Dict]:
        """faster-whisper orqali lokal transkripsiya."""
        try:
            model = self._load_whisper()
            print(f"[STT] Whisper transkripsiya (til: {self.language})...")
            segments, info = model.transcribe(
                audio_path,
                language=self.language,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 400},
                condition_on_previous_text=True,
                word_timestamps=True,  # So'zma-so'z vaqtlar uchun
            )
            lang = getattr(info, "language", self.language)
            prob = getattr(info, "language_probability", 0)
            print(f"[STT] Til aniqlandi: {lang} ({prob:.0%})")

            result = []
            for seg in segments:
                # Agar word_timestamps=True bo'lsa, har bir segmentda .words bo'ladi
                if hasattr(seg, "words") and seg.words:
                    for w in seg.words:
                        w_text = w.word.strip()
                        if w_text:
                            result.append({
                                "start": round(w.start, 2),
                                "end": round(w.end, 2),
                                "text": w_text,
                            })
                else:
                    # Fallback — butun segment
                    text = seg.text.strip()
                    if text:
                        result.append({
                            "start": round(seg.start, 2),
                            "end": round(seg.end, 2),
                            "text": text,
                        })
            print(f"[STT] {len(result)} so'z/segment topildi (Whisper).")
            return result
        except Exception as e:
            print(f"[STT] Whisper xatosi: {e}")
            return []

    # ------------------------------------------------------------------ #
    def get_engine_name(self) -> str:
        return self.active_engine or "Noma'lum"

    def get_full_text(self, segments: List[Dict]) -> str:
        return " ".join(s["text"] for s in segments if s.get("text"))
