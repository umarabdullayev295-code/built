import httpx
import os
import soundfile as sf
import numpy as np
import tempfile
from dotenv import load_dotenv

# Load .env explicitly
load_dotenv()

MUXLISA_API_URL = "https://service.muxlisa.uz/api/v2/stt"
API_KEY = os.environ.get("MUXLISA_API_KEY")

def test_muxlisa_from_env():
    if not API_KEY:
        print("Error: MUXLISA_API_KEY not found in environment after load_dotenv().")
        return

    # Create a 1-second silent audio file
    samplerate = 16000
    data = np.zeros(samplerate)
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        sf.write(tmp_wav.name, data, samplerate)
        tmp_wav_path = tmp_wav.name

    print(f"Testing Muxlisa AI starting with: {API_KEY[:5]}...")
    
    try:
        headers = {"x-api-key": API_KEY}
        with open(tmp_wav_path, "rb") as f:
            files = {"audio": (os.path.basename(tmp_wav_path), f, "audio/wav")}
            with httpx.Client(timeout=30.0) as client:
                response = client.post(MUXLISA_API_URL, headers=headers, files=files)
                print(f"Status: {response.status_code}")
                print(f"Response: {response.text}")
                
    except Exception as e:
        print(f"Exception: {e}")
    finally:
        if os.path.exists(tmp_wav_path):
            os.remove(tmp_wav_path)

if __name__ == "__main__":
    test_muxlisa_from_env()
