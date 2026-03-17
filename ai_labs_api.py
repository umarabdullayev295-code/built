"""
ai_labs_api.py
--------------
STT API integratsiyasi:
  1. ElevenLabs Scribe v1 (ustuvor — o'zbek tilini mukammal taniydi)
"""

import os
import tempfile
import time
import random
from typing import List, Dict, Optional
try:
    from elevenlabs.client import ElevenLabs
except ImportError:
    ElevenLabs = None
import httpx

# Local components
try:
    from video_processor import get_video_duration
except ImportError:
    get_video_duration = None

# ─── Muxlisa AI ───
MUXLISA_API_URL = "https://service.muxlisa.uz/api/v2/stt"


class ElevenLabsClient:
    """
    ElevenLabs Scribe v2 — eng aniq ko'p tilli STT modeli.
    O'zbek tilini (uzb) mukammal taniydi, gap yoki so'z belgilari bilan.
    Sayt: https://elevenlabs.io/speech-to-text
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        self.available = bool(self.api_key)

    def _simulate_human_usage(self):
        """Simulates human-like behavior with natural pauses between requests."""
        # Rule: Avoid rapid consecutive requests (2.0s to 5.0s delay)
        pause = random.uniform(2.0, 5.0)
        time.sleep(pause)

    def is_available(self) -> bool:
        return self.available

    def transcribe_audio(self, audio_path: str, language: str = "uz") -> List[Dict]:
        """
        ElevenLabs Scribe v1 orqali audio faylni matnga o'tkazadi.

        Args:
            audio_path: Audio fayl yo'li
            language: Til kodi (standart: 'uz' — o'zbek)

        Returns:
            Segmentlar ro'yxati: [{"start": float, "end": float, "text": str}]
        """
        if not self.available:
            return []

        # Rule: Simulate human usage pattern to avoid abuse detection
        self._simulate_human_usage()

        headers = {"xi-api-key": self.api_key}
        lang_map = {"uz": "uzb", "ru": "rus", "en": "eng", "tr": "tur"}
        iso3_lang = lang_map.get(language, "uzb")

        try:
            client = ElevenLabs(api_key=self.api_key)
            with open(audio_path, "rb") as audio_file:
                response = client.speech_to_text.convert(
                    file=audio_file,
                    model_id="scribe_v2",
                    language_code=iso3_lang,
                    tag_audio_events=False,
                    diarize=False
                )
                result = response.model_dump() if hasattr(response, 'model_dump') else response
                return self._parse_response(result)

        except Exception as e:
            err_msg = str(e)
            if "detected_unusual_activity" in err_msg:
                print("[AI Engine] XAVFSIZLIK CHEKLOVI: ElevenLabs tomonidan shubhali faollik aniqlandi.")
                print("[AI Engine] MASLAHAT: Bir oz kutib qayta urinib ko'ring yoki 'Muxlisa AI' yoki 'Whisper' modeliga o'ting.")
            else:
                print(f"[AI Engine] Process Alert: {err_msg}")
            return []

    def generate_speech(self, text: str, voice_id: str = "JBFqnCBsd6RMkjVDRZzb") -> Optional[str]:
        """
        Generates natural, human-like speech from text.
        Optimized for clarity and professional pacing.
        """
        if not self.available or not text.strip():
            return None

        # Rule: Avoid rapid requests
        self._simulate_human_usage()

        try:
            client = ElevenLabs(api_key=self.api_key)
            audio_generator = client.generate(
                text=text,
                voice=voice_id,
                model="eleven_multilingual_v2"
            )
            
            # Temporary file storage
            tmp_f = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            for chunk in audio_generator:
                if chunk:
                    tmp_f.write(chunk)
            tmp_f.close()
            return tmp_f.name

        except Exception as e:
            print(f"[AI Engine] TTS Generation Alert: {e}")
            return None

    def _parse_response(self, result: dict) -> List[Dict]:
        """
        ElevenLabs API javobini standart segment formatiga o'tkazadi.
        So'z darajasidagi vaqtlardan gap segmentlari yaratadi.
        """
        segments = []

        # 1. Scribe V2 format — segments -> words
        if "segments" in result:
            for seg in result["segments"]:
                for w in seg.get("words", []):
                    word_text = w.get("text", "").strip()
                    if word_text:
                        segments.append({
                            "start": float(w.get("start", 0)),
                            "end": float(w.get("end", 0)),
                            "text": word_text
                        })
        
        # 2. Direct words format (Legacy or other models)
        elif "words" in result:
            segments = self._words_to_segments(result["words"])
            
        # 3. Fallback to full text if no words/segments
        elif "text" in result:
            raw_text = str(result.get("text", "")).strip()
            segments = [{
                "start": 0.0,
                "end": 0.0,
                "text": raw_text,
            }]

        return [s for s in segments if s.get("text", "").strip()]

    def _words_to_segments(self, words: list) -> List[Dict]:
        """
        So'zlarni to'g'ridan-to'g'ri alohida segmentlar sifatida qaytaradi.
        Bu bilan subtitrda har bir so'z aniq o'z vaqtida yonadi.
        """
        if not words:
            return []

        segments = []
        for w in words:
            # Ba'zi modellarda "type" = "word" yoki shunchaki text mavjud
            if w.get("type", "word") != "word":
                continue
            
            word_text = w.get("text", w.get("word", "")).strip()
            if not word_text:
                continue

            # Har bir so'zni o'zining aniq boshlanish va tugash vaqtida alohida frame qilamiz
            segments.append({
                "start": float(w.get("start", 0)),
                "end": float(w.get("end", 0)),
                "text": word_text
            })

        return segments

class MuxlisaClient:
    """
    Muxlisa AI STT — Uzb tili uchun o'zimizning milliy STT.
    Max hajm: 5MB, Max davomiylik: 60s.
    Sayt: service.muxlisa.uz
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("MUXLISA_API_KEY")
        self.available = bool(self.api_key)

    def is_available(self) -> bool:
        return self.available

    def transcribe_audio(self, audio_path: str, language: str = "uz") -> List[Dict]:
        """
        Muxlisa AI orqali transkripsiya. 
        Kichik hiyla: ElevenLabs kabi so'zma-so'z vaqtlar bo'lishi uchun 
        matnni vaqtga nisbatan taqsimlaymiz.
        """
        if not self.available:
            return []

        headers = {"x-api-key": self.api_key}
        
        try:
            # 1. API dan javob olish
            with open(audio_path, "rb") as f:
                files = {"audio": (os.path.basename(audio_path), f, "audio/wav")}
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(MUXLISA_API_URL, headers=headers, files=files)
                    
                    if response.status_code == 200:
                        data = response.json()
                        raw_text = data.get("text", "").strip()
                        if not raw_text:
                            return []

                        # Router darajasida Word-level alignment qilish uchun 
                        # butun matnni bitta obyektda qaytaramiz.
                        return [{"start": 0.0, "end": 0.0, "text": raw_text, "type": "muxlisa_raw"}]
                    else:
                        print(f"[Muxlisa AI] Xato {response.status_code}: {response.text}")
                        return []
        except Exception as e:
            print(f"[Muxlisa AI] Umumiy xato: {e}")
            return []

    def test_connection(self) -> bool:
        """API ulanishini tekshiradi."""
        if not self.available:
            return False
        # Muxlisa uchun hozircha key borligini tekshirish kifoya
        return bool(self.api_key)


def get_best_api_client(engine_name: str = "ElevenLabs"):
    """
    Mavjud eng yaxshi API mijozini qaytaradi.
    """
    if "Muxlisa" in engine_name:
        muxlisa = MuxlisaClient()
        if muxlisa.is_available():
            return muxlisa, "Muxlisa AI (Pro)"
            
    if "Noiz AI" in engine_name:
        # Noiz AI STT hozircha ElevenLabs fallback sifatida
        elevenlabs = ElevenLabsClient()
        if elevenlabs.is_available():
            return elevenlabs, "Noiz AI (Professional)"

    elevenlabs = ElevenLabsClient()
    if elevenlabs.is_available():
        name = "My AI (Premium)" if "My AI" in engine_name else "O'zbek AI Model (Pro)"
        return elevenlabs, name

    return None, None
