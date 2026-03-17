import os
import tempfile
import time
import random
import threading
import logging
import httpx
from typing import Optional, List, Dict
try:
    from elevenlabs.client import ElevenLabs
except ImportError:
    ElevenLabs = None

# --- Konfiguratsiya ---
# Environment variable'dan olinadi
API_KEY = os.environ.get("ELEVEN_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")
NOIZ_API_KEY = os.environ.get("NOIZ_API_KEY")

DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb" # George (ElevenLabs)
NOIZ_DEFAULT_VOICE = "Brian" # Brian (Noiz AI)
MAX_TEXT_LENGTH = 3000

# Logging sozlamalari
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ElevenLabsSafeTTS")

# Faqat 1 ta request bir vaqtning o'zida ishlashi uchun Lock
_tts_lock = threading.Lock()

def eleven_tts(text: str) -> Optional[bytes]:
    """
    ElevenLabs API ni chaqiradi va audio bytes qaytaradi.
    Text juda uzun bo'lsa, uni bo'laklarga bo'lib, birlashtirib bitta request yuboradi.
    """
    if not API_KEY:
        logger.error("❌ XATO: ELEVEN_API_KEY topilmadi.")
        return None

    try:
        # 1. Textni tekshirish va birlashtirish (Spamni oldini olish uchun)
        if len(text) > MAX_TEXT_LENGTH:
            logger.info("⚠️ Text uzunligi 3000 dan oshdi. Bo'linmoqda...")
            # Oddiy bo'lish (gap asosida bo'lish professionalroq bo'ladi)
            mid = len(text) // 2
            chunks = [text[:mid], text[mid:]]
            text = " ".join(chunks) # Bitta request uchun birlashtirildi
            logger.info(f"Birlashtirilgan text uzunligi: {len(text)}")

        client = ElevenLabs(api_key=API_KEY)
        
        logger.info("🚀 ElevenLabs chaqirildi...")
        audio_generator = client.text_to_speech.convert(
            text=text,
            voice_id=DEFAULT_VOICE,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128"
        )
        
        # Generator natijasini bytesga o'tkazamiz
        audio_bytes = b"".join(chunk for chunk in audio_generator if chunk)
        
        if audio_bytes:
            logger.info("✅ Audio muvaffaqiyatli generatsiya qilindi.")
            return audio_bytes
        else:
            logger.error("❌ XATO: Bo'sh audio qaytarildi.")
            return None

    except Exception as e:
        err_msg = str(e)
        if "detected_unusual_activity" in err_msg:
            logger.critical("🛑 SECURITY ALERT: Unusual activity detected! Request to'xtatildi.")
        else:
            logger.error(f"❌ XATO yuz berdi: {err_msg}")
        return None

def noiz_tts(text: str) -> Optional[bytes]:
    """
    Noiz AI API ni chaqiradi.
    """
    if not NOIZ_API_KEY:
        logger.error("❌ XATO: NOIZ_API_KEY topilmadi.")
        return None

    url = "https://noiz.ai/v1/text-to-speech"
    headers = {"Authorization": NOIZ_API_KEY}
    data = {
        "text": text,
        "voice_id": NOIZ_DEFAULT_VOICE,
        "output_format": "mp3"
    }

    try:
        logger.info("🚀 Noiz AI chaqirildi...")
        with httpx.Client() as client:
            response = client.post(url, headers=headers, data=data, timeout=60.0)
            if response.status_code == 200:
                logger.info("✅ Noiz AI audio muvaffaqiyatli generatsiya qilindi.")
                return response.content
            else:
                logger.error(f"❌ Noiz AI Xatosi: {response.text}")
                return None
    except Exception as e:
        logger.error(f"❌ Noiz AI Umumiy Xato: {e}")
        return None

def align_tts_with_whisper(audio_bytes: bytes, text: str) -> List[Dict]:
    """
    TTS orqali yaratilgan audio vaqtlarini Whisper yordamida so'zma-so'z aniqlaydi.
    """
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_f:
            tmp_f.write(audio_bytes)
            tmp_path = tmp_f.name

        from speech_to_text import SpeechToText
        # Whisper 'base' modelini ishlatamiz (tez va aniq)
        stt = SpeechToText(engine_name="Whisper")
        stt.whisper_model_size = "base"
        
        whisper_results = stt._transcribe_whisper(tmp_path)
        
        # Tozalash
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        if not whisper_results:
            return []

        # TTS matnini Whisper vaqtlariga moslash (Alignment)
        original_words = [w.strip() for w in text.split() if w.strip()]
        aligned = []
        w_idx = 0
        
        for word in original_words:
            if w_idx < len(whisper_results):
                aligned.append({
                    "start": whisper_results[w_idx]["start"],
                    "end": whisper_results[w_idx]["end"],
                    "text": word
                })
                w_idx += 1
            else:
                last_end = aligned[-1]["end"] if aligned else 0.0
                aligned.append({
                    "start": last_end + 0.01,
                    "end": last_end + 0.3,
                    "text": word
                })
        
        return aligned
    except Exception as e:
        logger.error(f"❌ Alignment hatosi: {e}")
        return []

def safe_tts(text: str, engine: str = "Whisper") -> tuple[Optional[bytes], List[Dict]]:
    """
    Rate Limit va xavfsizlik qoidalariga rioya qilgan holda TTS chaqiradi.
    Natija: (audio_bytes, segments)
    engine: 'Whisper'
    """
    # Hozircha faqat Whisper (lokal) yoki kelajakda Muxlisa TTS qo'shilishi mumkin
    # Bir vaqtning o'zida faqat 1 ta generate ishlasin
    with _tts_lock:
        logger.info(f"🎯 TTS jarayoni boshlandi ({engine})...")
        
        # Muxlisa TTS hozircha mavjud emas, shuning uchun Whisper fallback
        # Eslatma: Haqiqiy TTS motori kerak bo'ladi.
        # Agar ElevenLabs va Noiz o'chirilsa, lokal motor (masalan gTTS yoki pyttsx3) kerak.
        # Hozircha bo'sh qaytaramiz yoki ogohlantiramiz.
        
        return None, []

def save_audio_to_file(audio_bytes: bytes, filename: str = "output.mp3"):
    """Audio matnni faylga saqlaydi."""
    try:
        with open(filename, "wb") as f:
            f.write(audio_bytes)
        logger.info(f"💾 Audio fayl saqlandi: {filename}")
    except Exception as e:
        logger.error(f"❌ Faylga saqlashda xato: {e}")
