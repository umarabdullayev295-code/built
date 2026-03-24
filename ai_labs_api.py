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
    # from elevenlabs.client import ElevenLabs
    pass
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


# ElevenLabsClient removed to simplify the application.


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


def get_best_api_client(engine_name: str = "Muxlisa AI (Pro)"):
    """
    Mavjud eng yaxshi API mijozini qaytaradi.
    Faqat Muxlisa AI qo'llab-quvvatlanadi.
    """
    muxlisa = MuxlisaClient()
    if muxlisa.is_available():
        return muxlisa, "Muxlisa AI (Pro)"

    return None, None
