from faster_whisper import WhisperModel

class Transcriber:
    def __init__(self, model_size="base", device="cpu", compute_type="int8"):
        """
        Initializes the faster-whisper model.
        """
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        
    def transcribe(self, audio_path):
        """
        Transcribes audio and returns a list of dictionaries with start, end, and text.
        Returns word-level segments if available for 'YouTube style' subtitles.
        """
        segments_data = []
        try:
            # Enable word-level timestamps for premium subtitle experience
            segments, info = self.model.transcribe(audio_path, beam_size=5, word_timestamps=True)
            for segment in segments:
                if segment.words:
                    for w in segment.words:
                        segments_data.append({
                            "start": w.start,
                            "end": w.end,
                            "text": str(w.word).strip()
                        })
                else:
                    # Fallback to segment level if words are missing
                    segments_data.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": str(segment.text).strip()
                    })
        except Exception as e:
            print(f"Error during transcription: {e}")
            
        return segments_data
