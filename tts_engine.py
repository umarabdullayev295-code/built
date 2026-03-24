# ElevenLabs and Noiz AI removed to simplify the application.


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
