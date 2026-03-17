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
        """
        segments_data = []
        try:
            segments, info = self.model.transcribe(audio_path, beam_size=5)
            for segment in segments:
                segments_data.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip()
                })
        except Exception as e:
            print(f"Error during transcription: {e}")
            
        return segments_data
