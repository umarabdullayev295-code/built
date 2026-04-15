# 🎬 Video AI Search (O'zbek Tilida)

Videodan O'zbek tilidagi matn va audio orqali aqlli qidiruv tizimi.

## 🚀 Xususiyatlari
- **O'zbek tilida Nutqni Matnga O'tkazish**: Faster-Whisper va AI modellari yordamida.
- **Semantik Qidiruv**: FAISS va Sentence-Transformers yordamida ma'no jihatidan qidiruv.
- **Premium UI**: Streamlit asosidagi zamonaviy va qulay interfeys.
- **Audio Qidiruv**: Ovozli xabar orqali qidirish imkoniyati.

## 🛠 O'rnatish

1. Loyihani yuklab oling.
2. Virtual muhit yarating va faollashtiring:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. Kerakli kutubxonalarni o'rnating:
   ```bash
   pip install -r requirements.txt
   ```

## 🏃 Ishga tushirish

```bash
streamlit run app.py
```

## ⚙️ Sozlamalar
`.env` faylida quyidagi kalitlarni ko'rsatishingiz mumkin:
- `MUXLISA_AI_API_KEY`: ElevenLabs API kaliti (ixtiyoriy).

