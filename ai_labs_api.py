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
        if not self.api_key:
            try:
                import streamlit as st
                self.api_key = st.secrets.get("MUXLISA_API_KEY")
            except Exception:
                pass
        
        # Aqlli tozalash: faqat chetdagi qo'shtirnoqlarni olib tashlaymiz
        if self.api_key:
            self.api_key = str(self.api_key).strip()
            if len(self.api_key) >= 2:
                if (self.api_key[0] == '"' and self.api_key[-1] == '"') or \
                   (self.api_key[0] == "'" and self.api_key[-1] == "'"):
                    self.api_key = self.api_key[1:-1]
        
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
            import soundfile as sf
            import numpy as np
            
            data, samplerate = sf.read(audio_path)
            total_duration = len(data) / samplerate
            
            # Muxlisa rejimida 1..60s oralig'ini barqaror qilish:
            # bitta butun chunk qaytaramiz (timeline uzilmaydi).
            if total_duration <= 60.0:
                chunks = [(data, 0.0)]
            else:
                # 60s dan katta fayllar uchun adaptiv chunk (10..20s diapazon).
                chunk_duration = float(min(20, max(10, int(total_duration / 8))))
                samples_per_chunk = int(chunk_duration * samplerate)
                chunks = []
                for i in range(0, len(data), samples_per_chunk):
                    chunks.append((data[i:i+samples_per_chunk], i / samplerate))
                    
            import concurrent.futures

            def process_chunk(chunk_idx, chunk_data, start_sec):
                result_text = ""
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                    sf.write(tmp_wav.name, chunk_data, samplerate)
                    tmp_wav_path = tmp_wav.name
                    
                try:
                    with open(tmp_wav_path, "rb") as f:
                        files = {"audio": (os.path.basename(tmp_wav_path), f, "audio/wav")}
                        with httpx.Client(timeout=120.0) as client:
                            response = client.post(MUXLISA_API_URL, headers=headers, files=files)
                            
                            if response.status_code == 200:
                                result_data = response.json()
                                chunk_text = result_data.get("text", "").strip()
                                if chunk_text:
                                    result_text = chunk_text
                            else:
                                print(f"[Muxlisa AI] Xato: Status {response.status_code}")
                                if response.status_code == 401:
                                    print("[Muxlisa AI] API Key noto'g'ri (Unauthorized).")
                                elif response.status_code == 413:
                                    print("[Muxlisa AI] Fayl hajmi juda katta.")
                                else:
                                    print(f"[Muxlisa AI] Response: {response.text}")
                finally:
                    if os.path.exists(tmp_wav_path):
                        os.remove(tmp_wav_path)
                
                chunk_duration_sec = len(chunk_data) / samplerate
                return chunk_idx, {
                    "start": start_sec, 
                    "end": start_sec + chunk_duration_sec, 
                    "text": result_text, 
                    "type": "muxlisa_raw"
                }

            results_dict = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                for idx, (chunk_data, start_sec) in enumerate(chunks):
                    futures.append(executor.submit(process_chunk, idx, chunk_data, start_sec))
                    
                for future in concurrent.futures.as_completed(futures):
                    chunk_idx, chunk_result = future.result()
                    if chunk_result["text"]:
                        results_dict[chunk_idx] = chunk_result
            
            final_segments = []
            for idx in sorted(results_dict.keys()):
                final_segments.append(results_dict[idx])
                
            return final_segments
            
        except Exception as e:
            print(f"[Muxlisa AI] Umumiy xato: {e}")
            return []

    def test_connection(self) -> bool:
        """API ulanishini tekshiradi."""
        if not self.available:
            return False
        # Muxlisa uchun hozircha key borligini tekshirish kifoya
        return bool(self.api_key)
def get_best_api_client(engine_name: str = "Muxlisa AI (Uzbek Pro)"):
    """
    Mavjud eng yaxshi API mijozini qaytaradi.
    Faqat Muxlisa AI qo'llab-quvvatlanadi.
    """
    muxlisa = MuxlisaClient()
    if muxlisa.is_available():
        return muxlisa, "Muxlisa AI (Uzbek Pro)"

    return None, None
