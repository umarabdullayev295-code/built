"""
semantic_search.py
------------------
Semantik qidiruv moduli — FAISS + sentence-transformers asosida.

O'zbek tilini qo'llab-quvvatlash uchun ko'p tilli model ishlatiladi:
  paraphrase-multilingual-MiniLM-L12-v2

Bu model 50+ tilni, jumladan o'zbek tilini ham qo'llab-quvvatlaydi.
"""

import numpy as np
import gc
import streamlit as st
from typing import List, Dict, Optional, Tuple

@st.cache_resource
def load_sentence_model(model_name: str):
    from sentence_transformers import SentenceTransformer
    print(f"[SemanticSearch] Model yuklanmoqda: {model_name}...")
    return SentenceTransformer(model_name)


# O'zbek tilini yaxshi qo'llab-quvvatlaydigan ko'p tilli modellar
MULTILINGUAL_MODELS = [
    "paraphrase-multilingual-MiniLM-L12-v2",   # Tavsiya etilgan (50+ til)
    "paraphrase-multilingual-mpnet-base-v2",    # Yuqori sifat, kattaroq
    "all-MiniLM-L6-v2",                         # Faqat ingliz (fallback)
]


class SemanticSearch:
    """
    FAISS asosidagi semantik qidiruv tizimi.

    Ko'p tilli model yordamida o'zbek tilidagi
    sinonimlar va kontekstga asoslanib qidiruv amalga oshiradi.
    """

    def __init__(self, model_name: Optional[str] = None):
        """
        Args:
            model_name: Sentence-transformer model nomi.
                        None bo'lsa, avtomatic ko'p tilli model tanlanadi.
        """
        self.model_name = model_name or MULTILINGUAL_MODELS[0]
        self._encoder = None
        self.index = None
        self.segments: List[Dict] = []
        self.dimension: int = 0

    def _load_encoder(self):
        """Encoder modelini lazy loading va st.cache_resource bilan yuklaydi."""
        if self._encoder is None:
            self._encoder = load_sentence_model(self.model_name)
        return self._encoder

    def add_transcripts(self, segments: List[Dict]) -> int:
        """
        Transkript segmentlarini embeddingga o'tkazadi va
        FAISS indeksini yaratadi.

        Args:
            segments: [{"start": float, "end": float, "text": str}, ...]

        Returns:
            Indeksga qo'shilgan segmentlar soni
        """
        import faiss

        if not segments:
            return 0

        # Bo'sh matnlarni filtrlash
        valid_segments = [s for s in segments if s.get("text", "").strip()]
        if not valid_segments:
            return 0

        self.segments = valid_segments
        texts = [seg["text"] for seg in valid_segments]

        encoder = self._load_encoder()
        print(f"[SemanticSearch] {len(texts)} segment embeddingga o'tkazilmoqda...")
        embeddings = encoder.encode(
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,  # Cosine similarity uchun normalizatsiya
            batch_size=32,
        )

        embeddings = np.array(embeddings).astype("float32")
        self.dimension = embeddings.shape[1]

        # FAISS IndexFlatIP — normalizatsiyalangan vektorlar uchun cosine similarity
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(embeddings)

        print(f"[SemanticSearch] FAISS indeks yaratildi: {self.index.ntotal} segment")
        return len(valid_segments)

    def search(self, query: str, top_k: int = 5, min_score: float = 0.1) -> List[Dict]:
        """
        Matn so'rovi bo'yicha eng o'xshash segmentlarni qaytaradi.

        Args:
            query: Qidiruv matni (o'zbek tilida)
            top_k: Qaytariladigan natijalar soni
            min_score: Minimal o'xshashlik chegarasi (0–1)

        Returns:
            [{"start", "end", "text", "score"}, ...]
        """
        import faiss

        if self.index is None or not self.segments:
            return []

        encoder = self._load_encoder()
        query_emb = encoder.encode(
            [query],
            normalize_embeddings=True,
        )
        query_emb = np.array(query_emb).astype("float32")

        k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_emb, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            score_val = float(score)
            if score_val < min_score:
                continue
            seg = self.segments[idx].copy()
            seg["score"] = round(score_val, 4)
            results.append(seg)

        # O'xshashlik bo'yicha tartib
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def search_with_context(
        self, query: str, top_k: int = 3, context_window: int = 1
    ) -> List[Dict]:
        """
        Qidiruv natijasiga qo'shni segmentlarni ham qo'shib qaytaradi.
        Bu orqali kontekst to'liqroq ko'rsatiladi.
        
        Args:
            context_window: Har tomonda qo'shni segmentlar soni
        """
        results = self.search(query, top_k=top_k)
        enriched = []

        for res in results:
            # Javob segmentining indeksini topish
            idx = self.segments.index(
                next(s for s in self.segments
                     if s["start"] == res["start"] and s["end"] == res["end"])
            )

            # Qo'shni segmentlarni birlashtirish
            start_idx = max(0, idx - context_window)
            end_idx = min(len(self.segments) - 1, idx + context_window)

            context_texts = [self.segments[i]["text"] for i in range(start_idx, end_idx + 1)]
            combined_text = " ".join(context_texts)

            enriched.append({
                **res,
                "context_start": self.segments[start_idx]["start"],
                "context_end": self.segments[end_idx]["end"],
                "context_text": combined_text,
            })

        return enriched

    def is_ready(self) -> bool:
        """Indeks tayyor ekanligini tekshiradi."""
        return self.index is not None and len(self.segments) > 0

    def get_stats(self) -> Dict:
        """Indeks statistikasini qaytaradi."""
        return {
            "total_segments": len(self.segments),
            "index_size": self.index.ntotal if self.index else 0,
            "model": self.model_name,
            "dimension": self.dimension,
        }

    def reset(self):
        """Indeksni tozalaydi."""
        self.index = None
        self.segments = []
        self.dimension = 0
        print("[SemanticSearch] Indeks tozalandi.")
