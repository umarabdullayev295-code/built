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
from pathlib import Path
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv

_APP_DIR = Path(__file__).resolve().parent


def _load_dotenv_here() -> None:
    """Loyiha ildizidagi .env (Streamlit ishchi katalogi har xil bo'lishi mumkin)."""
    load_dotenv(_APP_DIR / ".env", override=True)


def _strip_key(raw: Optional[str]) -> str:
    if raw is None:
        return ""
    s = str(raw).strip().replace("\ufeff", "")
    # Windows CRLF va qo'shimcha separatorlar
    s = s.splitlines()[0].strip() if s else ""
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1].strip()
    return s


def _muxlisa_transcription_text(result_data: Any) -> str:
    """Muxlisa STT javobidagi matnni turli JSON shakllaridan ajratadi."""
    if result_data is None:
        return ""
    if isinstance(result_data, str):
        return result_data.strip()
    if isinstance(result_data, list):
        parts: List[str] = []
        for item in result_data:
            if isinstance(item, dict):
                t = item.get("text") or item.get("transcript") or item.get("transcription")
                if t:
                    parts.append(str(t).strip())
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return " ".join(parts).strip()
    if isinstance(result_data, dict):
        direct = (
            result_data.get("text")
            or result_data.get("transcription")
            or result_data.get("transcript")
        )
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        for nested_key in ("result", "data", "response"):
            nested = result_data.get(nested_key)
            inner = _muxlisa_transcription_text(nested)
            if inner:
                return inner
    return ""


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
        # Streamlit Cloud uchun asosiy manba: st.secrets.
        # Lokal fallback: explicit api_key -> .env/os.environ.
        self.api_key = api_key
        self._key_source = "explicit"
        if not self.api_key:
            try:
                import streamlit as st
                self.api_key = st.secrets.get("MUXLISA_API_KEY") or st.secrets.get(
                    "MUXLISA_AI_API_KEY"
                )
                if self.api_key:
                    self._key_source = "st.secrets"
            except Exception:
                pass
        if not self.api_key:
            _load_dotenv_here()
            self.api_key = os.environ.get("MUXLISA_API_KEY") or os.environ.get(
                "MUXLISA_AI_API_KEY"
            )
            if self.api_key:
                self._key_source = "env"

        self.api_key = _strip_key(self.api_key or "")
        self.available = bool(self.api_key)
        if self.available:
            print(f"[Muxlisa AI] API key source: {self._key_source}, len={len(self.api_key)}")
        else:
            print("[Muxlisa AI] API key topilmadi (st.secrets/env).")

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
            # Stereo yoki ko'p kanalli WAV — MUXLISA uchun odatda mono kutiladi
            if hasattr(data, "ndim") and data.ndim > 1:
                data = np.mean(data, axis=1)
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
                        payload = f.read()
                    with httpx.Client(timeout=120.0) as client:
                        for field_name in ("audio", "file", "media"):
                            for attempt in range(1, 4):
                                files = {
                                    field_name: (
                                        os.path.basename(tmp_wav_path),
                                        payload,
                                        "audio/wav",
                                    )
                                }
                                try:
                                    response = client.post(
                                        MUXLISA_API_URL,
                                        headers=headers,
                                        files=files,
                                    )
                                except Exception as e:
                                    if attempt == 3:
                                        print(f"[Muxlisa AI] So'rov xatosi ({field_name}): {e}")
                                    else:
                                        time.sleep(0.5 * attempt + random.uniform(0.0, 0.2))
                                    continue

                                if response.status_code == 200:
                                    try:
                                        result_data = response.json()
                                    except Exception:
                                        result_data = {}

                                    chunk_text = _muxlisa_transcription_text(result_data)
                                    if (
                                        not chunk_text
                                        and isinstance(result_data, dict)
                                        and len(str(result_data)) < 800
                                    ):
                                        ks = (
                                            list(result_data.keys())
                                            if result_data
                                            else []
                                        )
                                        print(f"[Muxlisa AI] 200 javob kalitlari: {ks}")
                                    if chunk_text:
                                        result_text = chunk_text
                                        break
                                else:
                                    if attempt == 3:
                                        print(
                                            f"[Muxlisa AI] Xato: status={response.status_code}, field={field_name}"
                                        )
                                        if response.status_code == 401:
                                            print(
                                                "[Muxlisa AI] API key noto'g'ri yoki ruxsat yo'q."
                                            )
                                        elif response.status_code == 413:
                                            print("[Muxlisa AI] Chunk hajmi juda katta.")
                                        else:
                                            print(f"[Muxlisa AI] Response: {response.text[:500]}")
                                    else:
                                        time.sleep(0.5 * attempt + random.uniform(0.0, 0.2))
                            if result_text:
                                break
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
        return bool(self.api_key)


# ─── Gladia AI (Ko'p tilli STT) ───
GLADIA_UPLOAD_URL      = "https://api.gladia.io/v2/upload"
GLADIA_TRANSCRIBE_URL  = "https://api.gladia.io/v2/pre-recorded"


class GladiaClient:
    """
    Gladia AI STT — Ko'p tilli, so'z darajasida vaqtlar bilan.
    10 soat/oy bepul. Ko'p tilli qo'llab-quvvatlaydi.
    """

    LANG_MAP = {
        "uz": "uz", "ru": "ru", "en": "en", "tr": "tr",
        "ar": "ar", "de": "de", "fr": "fr", "es": "es",
        "zh": "zh", "ja": "ja", "auto": None,
    }

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self._key_source = "explicit"

        if not self.api_key:
            try:
                import streamlit as st
                self.api_key = (
                    st.secrets.get("GLADIA_API_KEY") or
                    st.secrets.get("GLADIA_AI_API_KEY")
                )
                if self.api_key:
                    self._key_source = "st.secrets"
            except Exception:
                pass

        if not self.api_key:
            _load_dotenv_here()
            self.api_key = (
                os.environ.get("GLADIA_API_KEY") or
                os.environ.get("GLADIA_AI_API_KEY")
            )
            if self.api_key:
                self._key_source = "env"

        self.api_key   = _strip_key(self.api_key or "")
        self.available = bool(self.api_key)

        if self.available:
            print(f"[Gladia] API key source: {self._key_source}, len={len(self.api_key)}")
        else:
            print("[Gladia] API key topilmadi.")

    def is_available(self) -> bool:
        return self.available

    def transcribe_audio(self, audio_path: str, language: str = "auto") -> List[Dict]:
        """
        Gladia v2 orqali transkripsiya:
        1. Faylni yuklash → audio_url olish
        2. Transkripsiya boshlash → job_id
        3. Natijani kutish (polling)
        4. So'z darajasida segmentlarni qaytarish
        """
        if not self.available:
            return []

        headers = {"x-gladia-key": self.api_key}

        # 1. Audio yuklash
        try:
            ext = os.path.splitext(audio_path)[1].lower().lstrip(".")
            mime_map = {
                "wav": "audio/wav", "mp3": "audio/mpeg",
                "m4a": "audio/mp4", "ogg": "audio/ogg",
                "flac": "audio/flac", "webm": "audio/webm",
            }
            mime = mime_map.get(ext, "audio/wav")

            with open(audio_path, "rb") as f:
                files = {"audio": (os.path.basename(audio_path), f, mime)}
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(GLADIA_UPLOAD_URL, headers=headers, files=files)

            if resp.status_code != 200:
                print(f"[Gladia] Upload xato: {resp.status_code} — {resp.text[:300]}")
                return []

            audio_url = resp.json().get("audio_url")
            if not audio_url:
                print(f"[Gladia] audio_url topilmadi: {resp.json()}")
                return []

            print(f"[Gladia] Yuklandi: {audio_url[:60]}...")

        except Exception as e:
            print(f"[Gladia] Upload exception: {e}")
            return []

        # 2. Transkripsiya boshlash
        try:
            gladia_lang = self.LANG_MAP.get(language)
            payload: Dict[str, Any] = {
                "audio_url": audio_url,
                "word_timestamps": True,
                "diarization": False,
            }
            if gladia_lang:
                payload["language_config"] = {"languages": [gladia_lang]}
            # Agar "auto" — language_config yo'q → Gladia o'zi aniqlasin

            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    GLADIA_TRANSCRIBE_URL,
                    headers={**headers, "Content-Type": "application/json"},
                    json=payload,
                )

            if resp.status_code not in (200, 201):
                print(f"[Gladia] Transcribe xato: {resp.status_code} — {resp.text[:300]}")
                return []

            job_id = resp.json().get("id")
            if not job_id:
                print(f"[Gladia] job_id topilmadi: {resp.json()}")
                return []

            print(f"[Gladia] Job boshlandi: {job_id}")

        except Exception as e:
            print(f"[Gladia] Transcribe exception: {e}")
            return []

        # 3. Natijani polling bilan kutish
        poll_url = f"{GLADIA_TRANSCRIBE_URL}/{job_id}"
        max_polls = 60      # max 2 daqiqa (60 × 2s)
        for attempt in range(max_polls):
            time.sleep(2.0)
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(poll_url, headers=headers)

                if resp.status_code != 200:
                    print(f"[Gladia] Poll xato: {resp.status_code}")
                    continue

                data = resp.json()
                status = data.get("status", "")

                if status == "done":
                    print(f"[Gladia] Transkripsiya tayyor ({attempt+1} polling).")
                    return self._parse_result(data)

                elif status == "error":
                    print(f"[Gladia] Transkripsiya xato: {data}")
                    return []

                # "queued" yoki "processing" — davom et
                print(f"[Gladia] Status: {status} ({attempt+1}/{max_polls})")

            except Exception as e:
                print(f"[Gladia] Polling exception: {e}")

        print("[Gladia] Timeout: natija 2 daqiqada kelmadi.")
        return []

    def _parse_result(self, data: Dict) -> List[Dict]:
        """
        Gladia javobidan word-level segmentlar yaratadi.
        """
        segments: List[Dict] = []
        try:
            transcription = data.get("result", {}).get("transcription", {})
            utterances    = transcription.get("utterances") or []

            for utt in utterances:
                words = utt.get("words") or []
                if words:
                    # So'z darajasida (word-level)
                    for w in words:
                        word_text = str(w.get("word") or "").strip()
                        if not word_text:
                            continue
                        segments.append({
                            "start": round(float(w.get("start", 0.0)), 3),
                            "end":   round(float(w.get("end",   0.0)), 3),
                            "text":  word_text,
                            "__timing_source__": "gladia_word",
                        })
                else:
                    # Fallback — utterance darajasida
                    utt_text = str(utt.get("text") or "").strip()
                    if utt_text:
                        segments.append({
                            "start": round(float(utt.get("start", 0.0)), 3),
                            "end":   round(float(utt.get("end",   0.0)), 3),
                            "text":  utt_text,
                            "__timing_source__": "gladia_utterance",
                        })

            if not segments:
                # Oxirgi fallback — full_transcript
                full = transcription.get("full_transcript", "")
                if full.strip():
                    segments.append({
                        "start": 0.0, "end": 1.0,
                        "text": full.strip(),
                        "__timing_source__": "gladia_full",
                    })

            print(f"[Gladia] {len(segments)} segment tahlil qilindi.")
        except Exception as e:
            print(f"[Gladia] Parse xato: {e}")

        return segments


def get_best_api_client(engine_name: str = "Muxlisa AI (Uzbek Pro)", language: str = "uz"):
    """
    Mavjud va ishlaydigan eng yaxshi API mijozini qaytaradi.
    - O'zbek tili: Muxlisa AI (ustuvor) → Gladia → None
    - Boshqa tillar: Gladia (agar mavjud)
    """
    # O'zbek tili uchun Muxlisa ustuvor
    if language == "uz" and "Muxlisa" in engine_name:
        muxlisa = MuxlisaClient()
        if muxlisa.is_available():
            return muxlisa, "Muxlisa AI (Uzbek Pro)"

    # Gladia — barcha tillar uchun
    gladia = GladiaClient()
    if gladia.is_available():
        return gladia, "Gladia AI (Multilingual)"

    # AssemblyAI fallback
    aai = AssemblyAIClient()
    if aai.is_available():
        return aai, "AssemblyAI (Multilingual)"

    # Muxlisa oxirgi fallback
    muxlisa = MuxlisaClient()
    if muxlisa.is_available():
        return muxlisa, "Muxlisa AI (Uzbek Pro)"

    return None, None


# ─── AssemblyAI (Ko'p tilli STT) ───
ASSEMBLYAI_UPLOAD_URL     = "https://api.assemblyai.com/v2/upload"
ASSEMBLYAI_TRANSCRIPT_URL = "https://api.assemblyai.com/v2/transcript"

# AssemblyAI qo'llab-quvvatlaydigan tillar (lang_code)
_AAI_LANG_MAP = {
    "en": "en", "ru": "ru", "tr": "tr", "fr": "fr",
    "de": "de", "es": "es", "it": "it", "pt": "pt",
    "nl": "nl", "hi": "hi", "ja": "ja", "ko": "ko",
    "zh": "zh", "ar": "ar", "uk": "uk", "uz": None,  # uz yo'q → auto
    "auto": None,
}


class AssemblyAIClient:
    """
    AssemblyAI STT — Ko'p tilli, so'z darajasida vaqtlar.
    100 soat/oy bepul. Real-time va pre-recorded.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self._key_source = "explicit"

        if not self.api_key:
            try:
                import streamlit as st
                self.api_key = (
                    st.secrets.get("ASSEMBLYAI_API_KEY") or
                    st.secrets.get("ASSEMBLY_AI_API_KEY")
                )
                if self.api_key:
                    self._key_source = "st.secrets"
            except Exception:
                pass

        if not self.api_key:
            _load_dotenv_here()
            self.api_key = (
                os.environ.get("ASSEMBLYAI_API_KEY") or
                os.environ.get("ASSEMBLY_AI_API_KEY")
            )
            if self.api_key:
                self._key_source = "env"

        self.api_key   = _strip_key(self.api_key or "")
        self.available = bool(self.api_key)

        if self.available:
            print(f"[AssemblyAI] API key source: {self._key_source}, len={len(self.api_key)}")
        else:
            print("[AssemblyAI] API key topilmadi.")

    def is_available(self) -> bool:
        return self.available

    def transcribe_audio(self, audio_path: str, language: str = "auto") -> List[Dict]:
        """
        AssemblyAI v2 orqali transkripsiya:
        1. Audio yuklash → upload_url
        2. Transkripsiya boshlash → id
        3. Polling → natija
        4. Word-level segmentlar qaytarish
        """
        if not self.available:
            return []

        headers = {
            "authorization": self.api_key,
            "content-type": "application/json",
        }

        # 1. Audio yuklash
        try:
            with open(audio_path, "rb") as f:
                audio_data = f.read()

            upload_headers = {"authorization": self.api_key}
            with httpx.Client(timeout=180.0) as client:
                resp = client.post(
                    ASSEMBLYAI_UPLOAD_URL,
                    headers=upload_headers,
                    content=audio_data,
                )

            if resp.status_code != 200:
                print(f"[AssemblyAI] Upload xato: {resp.status_code} — {resp.text[:300]}")
                return []

            upload_url = resp.json().get("upload_url")
            if not upload_url:
                print(f"[AssemblyAI] upload_url topilmadi: {resp.json()}")
                return []

            print(f"[AssemblyAI] Yuklandi: {upload_url[:60]}...")

        except Exception as e:
            print(f"[AssemblyAI] Upload exception: {e}")
            return []

        # 2. Transkripsiya boshlash
        try:
            aai_lang = _AAI_LANG_MAP.get(language)
            payload: Dict[str, Any] = {
                "audio_url": upload_url,
                "word_boost": [],
            }
            if aai_lang:
                payload["language_code"] = aai_lang
            else:
                payload["language_detection"] = True  # auto-detect

            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    ASSEMBLYAI_TRANSCRIPT_URL,
                    headers=headers,
                    json=payload,
                )

            if resp.status_code != 200:
                print(f"[AssemblyAI] Transcribe xato: {resp.status_code} — {resp.text[:300]}")
                return []

            job_id = resp.json().get("id")
            if not job_id:
                print(f"[AssemblyAI] job_id topilmadi: {resp.json()}")
                return []

            print(f"[AssemblyAI] Job boshlandi: {job_id}")

        except Exception as e:
            print(f"[AssemblyAI] Transcribe exception: {e}")
            return []

        # 3. Polling
        poll_url  = f"{ASSEMBLYAI_TRANSCRIPT_URL}/{job_id}"
        max_polls = 90   # max 3 daqiqa (90 × 2s)

        for attempt in range(max_polls):
            time.sleep(2.0)
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(poll_url, headers={"authorization": self.api_key})

                if resp.status_code != 200:
                    print(f"[AssemblyAI] Poll xato: {resp.status_code}")
                    continue

                data   = resp.json()
                status = data.get("status", "")

                if status == "completed":
                    print(f"[AssemblyAI] Tayyor ({attempt+1} polling).")
                    return self._parse_result(data)

                elif status == "error":
                    print(f"[AssemblyAI] Xato: {data.get('error')}")
                    return []

                print(f"[AssemblyAI] Status: {status} ({attempt+1}/{max_polls})")

            except Exception as e:
                print(f"[AssemblyAI] Polling exception: {e}")

        print("[AssemblyAI] Timeout: 3 daqiqada natija kelmadi.")
        return []

    def _parse_result(self, data: Dict) -> List[Dict]:
        """Word-level segmentlar yaratadi."""
        segments: List[Dict] = []
        try:
            words = data.get("words") or []
            if words:
                for w in words:
                    text = str(w.get("text") or "").strip()
                    if not text:
                        continue
                    segments.append({
                        "start": round(float(w.get("start", 0)) / 1000.0, 3),  # ms → s
                        "end":   round(float(w.get("end",   0)) / 1000.0, 3),
                        "text":  text,
                        "__timing_source__": "assemblyai_word",
                    })
            else:
                # Fallback — to'liq matn
                full = str(data.get("text") or "").strip()
                dur  = float(data.get("audio_duration") or 1.0)
                if full:
                    word_list = full.split()
                    step = dur / max(len(word_list), 1)
                    for i, w in enumerate(word_list):
                        segments.append({
                            "start": round(i * step, 3),
                            "end":   round((i + 1) * step, 3),
                            "text":  w,
                            "__timing_source__": "assemblyai_fallback",
                        })

            print(f"[AssemblyAI] {len(segments)} segment tahlil qilindi.")
        except Exception as e:
            print(f"[AssemblyAI] Parse xato: {e}")
        return segments
