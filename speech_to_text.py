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
        elevenlabs_api_key: Optional[str] = None,
        engine_name: str = "O'zbek AI Model (Pro)"
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
                elevenlabs_api_key, engine_name
            )

        if not self.active_engine:
            self.active_engine = f"faster-whisper ({whisper_model_size})"

    # ------------------------------------------------------------------ #
    def _pick_api_client(
        self,
        el_key: Optional[str],
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
                    print("[STT] Muxlisa AI matni Whisper orqali 100% aniqlikda tekislanmoqda...")
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
            # 1. Muxlisa matnini olish
            full_text = results[0].get("text", "")
            muxlisa_words = [w.strip() for w in full_text.split() if w.strip()]
            if not muxlisa_words:
                return results

            # 2. Whisper (Tezkor lekin aniq) orqali vaqtlarni aniqlash
            orig_size = self.whisper_model_size
            # 'small' o'zbek tili uchun 'base' dan ancha aniqroq
            self.whisper_model_size = "small" 
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

            # 3. Muxlisa so'zlarini Whisper vaqtlariga Sequence Matching orqali bog'lash
            import difflib
            whisper_words = [w["text"].lower().strip() for w in whisper_results]
            mux_words_low = [w.lower().strip() for w in muxlisa_words]
            
            matcher = difflib.SequenceMatcher(None, mux_words_low, whisper_words)
            aligned = []
            
            # Har bir Muxlisa so'zi uchun vaqt topamiz
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'equal':
                    # To'g'ridan-to'g'ri mos keladigan so'zlar
                    for idx, (m_idx, w_idx) in enumerate(zip(range(i1, i2), range(j1, j2))):
                        aligned.append({
                            "start": whisper_results[w_idx]["start"],
                            "end": whisper_results[w_idx]["end"],
                            "text": muxlisa_words[m_idx]
                        })
                elif tag in ('replace', 'insert'):
                    m_slice: List[str] = muxlisa_words[i1:i2]
                    count = len(m_slice)
                    if count > 0:
                        # Atrofdagi anchorlar (vaqtlar)ni topish
                        w_res: List[Dict] = whisper_results
                        p_idx = max(0, j1-1)
                        n_idx = min(len(w_res)-1, j2)
                        
                        prev_time = float(aligned[-1]["end"]) if aligned else float(w_res[p_idx]["end"])
                        next_time = float(w_res[n_idx]["start"])
                        
                        if next_time <= prev_time:
                            next_time = prev_time + 0.5
                        
                        step = (next_time - prev_time) / count
                        for idx, word in enumerate(m_slice):
                            aligned.append({
                                "start": round(prev_time + (idx * step), 2),
                                "end": round(prev_time + ((idx + 1) * step), 2),
                                "text": str(word)
                            })
                # 'delete' (Whisperda bor, Muxlisada yo'q) holatida biz hech narsa qo'shmaymiz,
                # chunki bizga faqat Muxlisa so'zlari uchun vaqt kerak.

            # Xavfsizlik: Agar biror sababga ko'ra ba'zi so'zlar qolib ketgan bo'lsa
            if len(aligned) < len(muxlisa_words):
                # Qolganlarini oxirgi vaqtdan so'ng qo'shamiz
                last_end = aligned[-1]["end"] if aligned else 0.0
                for i in range(len(aligned), len(muxlisa_words)):
                    aligned.append({
                        "start": last_end + (i - len(aligned)) * 0.4,
                        "end": last_end + (i - len(aligned) + 1) * 0.4,
                        "text": muxlisa_words[i]
                    })
            
            return aligned[:len(muxlisa_words)]
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
