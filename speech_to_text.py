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

            # 2. Whisper orqali vaqtlarni aniqlash
            # "base" model ba'zida 1 daqiqalik videoni 8 soniyada "tugadi" deb gallyutsinatsiya qilib yuboradi.
            # Shu sababli foydalanuvchi qaysi modelni tanlagan bo'lsa, xuddi o'sha model ishlatiladi!
            whisper_results = self._transcribe_whisper(audio_path)

            # 3. Muxlisa chunklari (esingizda bo'lsa API har 50s da bo'ladi) orqali yopishtiramiz
            aligned = []
            
            for m_chunk in results:
                if m_chunk.get("type") != "muxlisa_raw":
                    continue
                    
                text = m_chunk.get("text", "")
                words = [w.strip() for w in text.split() if w.strip()]
                if not words:
                    continue
                    
                # Muxlisa aniqlagan joriy blok yuki (masalan: 0s dan 50s gacha)
                c_start = m_chunk["start"]
                c_end = m_chunk["end"]
                
                # Shu oraliqdagi Whisper so'zlarini ajratib olamiz
                w_sub = [w for w in whisper_results if w["start"] >= c_start - 1.0 and w["start"] <= c_end + 1.0]
                
                m_count = len(words)
                w_count = len(w_sub)
                
                # Agar Whisper gallyutsinatsiya qilib hech narsa topmagan yoki erta to'xtab qolgan bo'lsa
                if w_count == 0:
                    # Xavfsizlik qatlami: oddiy vaqtga teng taqsimlash
                    # Hamma so'zni birdaniga 8 sekuntga otib yubormasligi uchun!
                    step = (c_end - c_start) / m_count if m_count > 0 else 0.4
                    for i, w in enumerate(words):
                        aligned.append({"start": round(c_start + i*step, 3), "end": round(c_start + (i+1)*step, 3), "text": w})
                else:
                    # Index proporsiyasi bilan Whisper VAD (jimjitlikka moslashib) ishlatamiz!
                    
                    # Agar Whisper faqat kichkina qismni (masalan 8 sekuntni) topgan-u, Muxlisa bloki 50sek bo'lsa:
                    # Biz uni vaqt bo'yicha to'g'irlaymiz
                    max_w_end = max(w["end"] for w in w_sub)
                    # 10 soniyadan ortiq muddat yo'qolgan bo'lsa -> Whisper adashgan
                    if (c_end - max_w_end) > 10.0 and m_count > w_count * 2:
                         step = (c_end - c_start) / m_count
                         for i, w in enumerate(words):
                             aligned.append({"start": round(c_start + i*step, 3), "end": round(c_start + (i+1)*step, 3), "text": w})
                         continue

                    grouped = {}
                    for i, w in enumerate(words):
                        w_idx = int((i / m_count) * w_count)
                        w_idx = min(w_idx, w_count - 1)
                        if w_idx not in grouped:
                            grouped[w_idx] = []
                        grouped[w_idx].append(w)
                        
                    for w_idx in sorted(grouped.keys()):
                        words_list = grouped[w_idx]
                        w_start = w_sub[w_idx]["start"]
                        w_end = w_sub[w_idx]["end"]
                        
                        c = len(words_list)
                        step = (w_end - w_start) / c if c > 0 else 0
                        
                        for idx, word in enumerate(words_list):
                            t_start = w_start + idx * step
                            t_end = w_start + (idx + 1) * step
                            aligned.append({
                                "start": round(t_start, 3),
                                "end": round(t_end, 3),
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
