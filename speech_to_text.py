"""
speech_to_text.py
-----------------
Nutqni matnga o'tkazish — unified interface.

Ustuvorlik tartibi:
  1. ElevenLabs Scribe v1  (API kalit mavjud bo'lsa — eng aniq va tez)
  2. faster-whisper        (offline, local model)

O'zbek tili uchun optimallashtirilgan.
"""

import os
import gc
import streamlit as st
from typing import List, Dict, Optional

@st.cache_resource
def load_whisper_model(model_size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel
    print(f"[STT] Whisper yuklanmoqda: {model_size} ({device})...")
    return WhisperModel(model_size, device=device, compute_type=compute_type)


class SpeechToText:
    """
    Unified Speech-to-Text engine.
    API mavjudligiga qarab eng yaxshi dvigatelni avtomatik tanlaydi.
    """

    def __init__(
        self,
        whisper_model_size: str = "medium",
        language: str = "uz",
        use_api: bool = True,
        engine_name: str = "Muxlisa AI (Pro)"
    ):
        """
        Args:
            whisper_model_size : 'tiny'|'base'|'small'|'medium'|'large-v2'|'large-v3'
            language           : Til kodi  ('uz' — o'zbek)
            use_api            : True bo'lsa API ishlatishga harakat qiladi
            elevenlabs_api_key : ElevenLabs API kaliti
            engine_name        : Tanlangan STT motori nomi
        """
        self.language = language
        self.whisper_model_size = whisper_model_size
        self._whisper_model = None
        self._api_client = None
        self.active_engine: str = ""

        if use_api:
            self._api_client, self.active_engine = self._pick_api_client(
                engine_name
            )

        if not self.active_engine:
            self.active_engine = f"faster-whisper ({whisper_model_size})"

    # ------------------------------------------------------------------ #
    def _pick_api_client(
        self,
        engine_name: str = "Muxlisa AI (Pro)"
    ):
        """
        Mavjud va ishlaydigan API mijozini tanlaydi.
        """
        from ai_labs_api import get_best_api_client

        # 1. Muxlisa AI
        if "Muxlisa" in engine_name:
            client, name = get_best_api_client(engine_name="Muxlisa")
            if client:
                return client, name

        # 2. Fallback: Avtomatik tanlash (Muxlisa yoki boshqa)
        client, name = get_best_api_client(engine_name=engine_name)
        if client:
            return client, name

        return None, ""

    # ------------------------------------------------------------------ #
    def transcribe(self, audio_path: str) -> List[Dict]:
        """
        Audio faylni matnga o'tkazadi.

        Returns:
            [{"start": 0.0, "end": 3.4, "text": "Assalomu alaykum"}, ...]
        """
        if not os.path.exists(audio_path):
            print(f"[STT] Fayl topilmadi: {audio_path}")
            return []

        # Faqat o'zbek tili uchun Muxlisa AI'ni ishlatamiz
        client = self._api_client
        if client is not None and client.is_available() and self.language == "uz":
            try:
                print(f"[STT] {self.active_engine} orqali tahlil qilinmoqda...")
                results = client.transcribe_audio(audio_path, language=self.language)
                
                # O'zbekda Whisper alignment noto'g'ri bo'lishi mumkin:
                # shu sabab Muxlisa chunk vaqtining o'zida so'zlarni taqsimlaymiz.
                if results and any(r.get("type") == "muxlisa_raw" for r in results):
                    print("[STT] Muxlisa AI matni chunk vaqtlarida so'zlarga ajratilmoqda...")
                    whisper_timing = self._transcribe_whisper(audio_path)
                    results = self._expand_muxlisa_chunks(
                        results,
                        audio_path=audio_path,
                        whisper_words=whisper_timing,
                    )
                
                if results:
                    return self._finalize_segments_auto(results, audio_path)
            except Exception as e:
                # DNS yoki internet xatosi bo'lsa tinchgina Whisperga o'tamiz
                if "getaddrinfo failed" in str(e) or "connection" in str(e).lower():
                    print("[STT] Internet ulanishida muammo. Lokal (Whisper) modelga o'tilmoqda...")
                else:
                    print(f"[STT] API xatosi: {e}. Lokal model ishlatiladi.")

        # Whisper fallback
        whisper_results = self._transcribe_whisper(audio_path)
        return self._finalize_segments_auto(whisper_results, audio_path)

    def _align_with_whisper(self, results: List[Dict], audio_path: str) -> List[Dict]:
        """
        Muxlisa AI matnini Whisper vaqtlariga 100% aniqlik bilan bog'laydi.
        """
        try:
            # 1. Muxlisa matnini olish
            full_text = " ".join(r.get("text", "") for r in results if r.get("type") == "muxlisa_raw")
            muxlisa_words = [w.strip() for w in full_text.split() if w.strip()]
            if not muxlisa_words:
                return results

            # 2. Whisper orqali vaqtlarni aniqlash
            whisper_results = self._transcribe_whisper(audio_path)

            # 3. Muxlisa chunklari orqali yopishtiramiz
            aligned = []
            import difflib

            for m_chunk in results:
                if m_chunk.get("type") != "muxlisa_raw":
                    continue
                    
                text = m_chunk.get("text", "")
                m_words = [w.strip() for w in text.split() if w.strip()]
                if not m_words:
                    continue
                    
                c_start = m_chunk["start"]
                c_end = m_chunk["end"]
                
                # Shu oraliqdagi Whisper so'zlarini ajratib olamiz
                w_sub = [w for w in whisper_results if w["start"] >= c_start - 2.0 and w["start"] <= c_end + 2.0]
                
                if not w_sub:
                    step = (c_end - c_start) / len(m_words)
                    for i, w in enumerate(m_words):
                        aligned.append({"start": round(c_start + i*step, 3), "end": round(c_start + (i+1)*step, 3), "text": w})
                else:
                    # AGRESSIV SINXRONIZATSIYA:
                    # Agar so'zlar soni juda yaqin bo'lsa, to'g'ridan-to'g'ri ZIP qilamiz.
                    # Bu eng aniq timingni beradi (har bir so'z o'z o'rnida).
                    if abs(len(m_words) - len(w_sub)) <= max(1, len(m_words) // 8):
                        # Eng yaqin so'zlar soniga moslaymiz
                        for i in range(min(len(m_words), len(w_sub))):
                            aligned.append({
                                "start": round(w_sub[i]["start"], 3),
                                "end": round(w_sub[i]["end"], 3),
                                "text": m_words[i]
                            })
                        continue

                    # Agar farq katta bo'lsa, SequenceMatcher ishlatamiz
                    w_words = [w["text"].strip().lower() for w in w_sub]
                    m_words_lower = [w.lower() for w in m_words]
                    
                    matcher = difflib.SequenceMatcher(None, w_words, m_words_lower)
                    m_times = [{"start": None, "end": None} for _ in range(len(m_words))]
                    
                    for w_idx, m_idx, length in matcher.get_matching_blocks():
                        for i in range(length):
                            m_times[m_idx + i]["start"] = w_sub[w_idx + i]["start"]
                            m_times[m_idx + i]["end"] = w_sub[w_idx + i]["end"]
                    
                    for i in range(len(m_words)):
                        if m_times[i]["start"] is None:
                            prev_t = c_start
                            for j in range(i - 1, -1, -1):
                                if m_times[j]["end"] is not None:
                                    prev_t = m_times[j]["end"]
                                    break
                            next_t = c_end
                            for j in range(i + 1, len(m_words)):
                                if m_times[j]["start"] is not None:
                                    next_t = m_times[j]["start"]
                                    break
                            
                            gap_start = i
                            gap_end = i
                            for j in range(i + 1, len(m_words)):
                                if m_times[j]["start"] is None:
                                    gap_end = j
                                else:
                                    break
                            
                            gap_size = gap_end - gap_start + 1
                            step = (next_t - prev_t) / (gap_size + 1)
                            for k in range(gap_size):
                                idx = gap_start + k
                                m_times[idx]["start"] = prev_t + (k + 0.1) * step
                                m_times[idx]["end"] = prev_t + (k + 0.9) * step
                                
                    for i, w in enumerate(m_words):
                        aligned.append({
                            "start": round(m_times[i]["start"], 3),
                            "end": round(m_times[i]["end"], 3),
                            "text": w
                        })
            return aligned
        except Exception as e:
            print(f"[STT] Alignment hatosi: {e}")
            return results

    def _expand_muxlisa_chunks(
        self,
        results: List[Dict],
        audio_path: Optional[str] = None,
        whisper_words: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        Muxlisa qaytargan chunk-level segmentlarni word-level segmentlarga aylantiradi.
        Whisperga bog'lanmasdan, audio energiya xaritasiga qarab vaqtni taqsimlaydi.
        """
        data = None
        samplerate = 0
        try:
            if audio_path:
                import soundfile as sf
                import numpy as np
                data, samplerate = sf.read(audio_path)
                if len(data.shape) > 1:
                    data = np.mean(data, axis=1)
        except Exception:
            data = None
            samplerate = 0

        def _equal_split(start: float, end: float, words: List[str]) -> List[Dict]:
            out = []
            step = (end - start) / max(len(words), 1)
            for i, w in enumerate(words):
                out.append(
                    {
                        "start": round(start + i * step, 3),
                        "end": round(start + (i + 1) * step, 3),
                        "text": w,
                        "__timing_locked__": True,
                        "__timing_source__": "muxlisa_audio",
                    }
                )
            return out
        
        def _word_weight(word: str) -> float:
            import re
            clean = re.sub(r"[^\wʻʼ'-]", "", word, flags=re.UNICODE)
            if not clean:
                return 1.0
            vowels = sum(1 for ch in clean.lower() if ch in "aeiouoʻʼ")
            # Uzunroq va ko'proq bo'g'inli so'zga biroz kattaroq vaqt ulushi beramiz.
            return max(1.0, len(clean) * 0.7 + vowels * 0.6)

        expanded: List[Dict] = []
        for seg in results:
            if seg.get("type") != "muxlisa_raw":
                continue

            text = (seg.get("text") or "").strip()
            if not text:
                continue

            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
            if end <= start:
                end = start + 0.01

            words = [w.strip() for w in text.split() if w.strip()]
            if not words:
                continue

            # 0) Whisper timing skeleton mavjud bo'lsa, avval shu bilan joylaymiz.
            # Matn Muxlisa'dan qoladi, vaqt esa real gap ritmidan olinadi.
            if whisper_words:
                w_sub = [
                    w for w in whisper_words
                    if float(w.get("start", 0.0)) >= (start - 0.6)
                    and float(w.get("start", 0.0)) <= (end + 0.6)
                ]
                if len(w_sub) >= 2:
                    try:
                        import numpy as np

                        # Agar Muxlisa va Whisper so'zlar soni jiddiy farq qilsa,
                        # force-map qilish o'rniga Whisper word timeline'ni ishlatamiz.
                        # Bu holat amalda timingni ancha barqaror qiladi.
                        m = len(w_sub)
                        n = len(words)
                        if n > 0 and (abs(m - n) / max(n, 1)) > 0.35:
                            for ww in w_sub:
                                ws = max(start, min(end, float(ww.get("start", start))))
                                we = max(ws + 0.02, min(end, float(ww.get("end", ws + 0.02))))
                                expanded.append(
                                    {
                                        "start": round(ws, 3),
                                        "end": round(we, 3),
                                        "text": str(ww.get("text", "")).strip() or str(ww.get("word", "")).strip(),
                                        "__timing_locked__": True,
                                        "__timing_source__": "whisper_word_timestamps",
                                    }
                                )
                            continue

                        # Whisper bo'yicha boundary: har bir so'z start'i + oxirgi end
                        wb = [float(w_sub[0]["start"])]
                        wb.extend(float(w["start"]) for w in w_sub[1:])
                        wb.append(float(w_sub[-1]["end"]))

                        # Monotonik va chunk chegarasiga clamp
                        wb = [max(start, min(end, t)) for t in wb]
                        for i in range(1, len(wb)):
                            if wb[i] < wb[i - 1]:
                                wb[i] = wb[i - 1]

                        # Boundary mapping: mux boundaries -> whisper boundaries
                        # (ritmni saqlash uchun linear index interpolation)
                        src_x = np.linspace(0.0, 1.0, num=m + 1, dtype=np.float32)
                        dst_x = np.linspace(0.0, 1.0, num=n + 1, dtype=np.float32)
                        mapped = np.interp(dst_x, src_x, np.array(wb, dtype=np.float32))

                        min_dur = 0.03
                        prev_end = start
                        for i, token in enumerate(words):
                            s = max(float(mapped[i]), prev_end)
                            e2 = max(float(mapped[i + 1]), s + min_dur)
                            e2 = min(e2, end)
                            if e2 <= s:
                                e2 = min(end, s + min_dur)
                            expanded.append(
                                {
                                    "start": round(s, 3),
                                    "end": round(e2, 3),
                                    "text": token,
                                    "__timing_locked__": True,
                                    "__timing_source__": "muxlisa_whisper_rhythm",
                                }
                            )
                            prev_end = e2

                        # Oxirgi so'zni chunk oxiriga yaqin tutish
                        if expanded:
                            last = expanded[-1]
                            if last.get("__timing_source__") == "muxlisa_whisper_rhythm":
                                last["end"] = round(float(end), 3)
                        continue
                    except Exception:
                        pass

            # Audio mavjud bo'lmasa, oddiy teng taqsimlash fallback.
            if data is None or samplerate <= 0:
                expanded.extend(_equal_split(start, end, words))
                continue

            try:
                import numpy as np

                start_idx = max(0, int(start * samplerate))
                end_idx = min(len(data), int(end * samplerate))
                chunk = np.abs(data[start_idx:end_idx])

                # Juda qisqa chunklarda fallback
                if len(chunk) < 256:
                    expanded.extend(_equal_split(start, end, words))
                    continue

                # 20ms frame bo'yicha RMS energiya
                frame = max(1, int(0.02 * samplerate))
                energies = []
                for i in range(0, len(chunk), frame):
                    fr = chunk[i:i + frame]
                    if len(fr) == 0:
                        continue
                    energies.append(float(np.sqrt(np.mean(fr * fr)) + 1e-12))

                if not energies:
                    expanded.extend(_equal_split(start, end, words))
                    continue

                e = np.array(energies, dtype=np.float32)
                max_e = float(np.max(e))
                if max_e <= 1e-8:
                    expanded.extend(_equal_split(start, end, words))
                    continue

                # 1) Smooth + voiced mask
                kernel = np.ones(5, dtype=np.float32) / 5.0
                e_smooth = np.convolve(e, kernel, mode="same")
                thr = max(float(np.percentile(e_smooth, 45)), max_e * 0.12)
                speech_mask = (e_smooth >= thr).astype(np.float32)
                speech_ratio = float(np.mean(speech_mask))
                if speech_ratio < 0.15:
                    # Juda shovqinli/yassi signal bo'lsa fallback
                    expanded.extend(_equal_split(start, end, words))
                    continue

                # 2) Faqat gap bo'laklarini yuqori vazn bilan to'playmiz
                weights = (e_smooth * speech_mask) + 1e-6
                csum = np.cumsum(weights)
                total = float(csum[-1])

                if total <= 1e-6:
                    expanded.extend(_equal_split(start, end, words))
                    continue

                # 3) Word-weight (uzunlik + unli) bo'yicha ulush
                n = len(words)
                word_weights = np.array([_word_weight(w) for w in words], dtype=np.float32)
                ww_sum = float(np.sum(word_weights))
                if ww_sum <= 1e-6:
                    expanded.extend(_equal_split(start, end, words))
                    continue
                word_mass = np.cumsum(word_weights / ww_sum) * total

                # 4) Candidate split points (mass-based)
                split_idx = [0]
                prev_mass = 0.0
                for i in range(n):
                    b = float(word_mass[i])
                    a_idx = int(np.searchsorted(csum, prev_mass, side="left"))
                    b_idx = int(np.searchsorted(csum, b, side="left"))
                    b_idx = max(b_idx, a_idx + 1)
                    split_idx.append(min(b_idx, len(e_smooth) - 1))
                    prev_mass = b

                # 5) Boundary snapping: splitlarni yaqin pauza/energiyasi past nuqtaga yopishtiramiz
                snapped = split_idx[:]
                for bi in range(1, len(snapped) - 1):
                    center = snapped[bi]
                    left = max(1, center - 3)
                    right = min(len(e_smooth) - 2, center + 3)
                    local = e_smooth[left:right + 1]
                    rel = int(np.argmin(local))
                    candidate = left + rel
                    if candidate > snapped[bi - 1] and candidate < snapped[bi + 1]:
                        snapped[bi] = candidate

                # 6) Har so'z ichida onset/offset'ni local gradient bilan aniqlash
                seg_words: List[Dict] = []
                for i, w in enumerate(words):
                    li = int(snapped[i])
                    ri = int(max(snapped[i + 1], li + 1))
                    ri = min(ri, len(e_smooth) - 1)

                    part = e_smooth[li:ri + 1]
                    if len(part) < 2:
                        w_start = start + (li * frame) / samplerate
                        w_end = start + (ri * frame) / samplerate
                        seg_words.append({"start": w_start, "end": w_end, "text": w})
                        continue

                    pmax = float(np.max(part))
                    pon = max(float(np.percentile(part, 35)), pmax * 0.22)
                    poff = max(float(np.percentile(part, 25)), pmax * 0.16)

                    onset_rel = 0
                    offset_rel = len(part) - 1

                    for j, val in enumerate(part):
                        if val >= pon:
                            onset_rel = j
                            break
                    for j in range(len(part) - 1, -1, -1):
                        if part[j] >= poff:
                            offset_rel = j
                            break

                    s_idx = li + onset_rel
                    e_idx = li + max(offset_rel, onset_rel + 1)
                    e_idx = min(e_idx, ri)

                    w_start = start + (s_idx * frame) / samplerate
                    w_end = start + (e_idx * frame) / samplerate
                    seg_words.append({"start": w_start, "end": w_end, "text": w})

                # 7) Timeline smoothing (monotonic + min/max duration + tail fit)
                min_dur = 0.045
                max_dur = 1.20
                prev_end = start
                for idx, wseg in enumerate(seg_words):
                    remaining_words = len(seg_words) - idx - 1
                    tail_limit = end - (remaining_words * min_dur)

                    s = max(wseg["start"], prev_end)
                    e2 = max(wseg["end"], s + min_dur)
                    e2 = min(e2, s + max_dur, tail_limit)

                    if e2 <= s:
                        e2 = min(end, s + min_dur)

                    expanded.append(
                        {
                            "start": round(s, 3),
                            "end": round(e2, 3),
                            "text": wseg["text"],
                            "__timing_locked__": True,
                            "__timing_source__": "muxlisa_audio",
                        }
                    )
                    prev_end = e2

                # Oxirgi so'z ko'pincha erta yopilib qoladi:
                # uni chunk yakuniga yaqinlashtirib, final talaffuzni ushlab turamiz.
                if expanded:
                    last = expanded[-1]
                    if (
                        last.get("__timing_locked__")
                        and abs(float(last.get("end", 0.0)) - float(end)) > 0.06
                    ):
                        last["end"] = round(float(end), 3)
            except Exception:
                expanded.extend(_equal_split(start, end, words))

        return expanded

    # ------------------------------------------------------------------ #
    def _load_whisper(self):
        """Whisper modelini lazy loading va st.cache_resource bilan yuklaydi."""
        if self._whisper_model is None:
            device = "cpu"
            compute_type = "int8"
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                    compute_type = "float16"
            except ImportError:
                pass
            
            self._whisper_model = load_whisper_model(
                self.whisper_model_size, device=device, compute_type=compute_type
            )
        return self._whisper_model

    def _transcribe_whisper(self, audio_path: str) -> List[Dict]:
        """faster-whisper orqali lokal transkripsiya."""
        try:
            model = self._load_whisper()
            print(f"[STT] Whisper transkripsiya (til: {self.language})...")
            segments, info = model.transcribe(
                audio_path,
                language=self.language,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 400},
                condition_on_previous_text=True,
                word_timestamps=True,  # So'zma-so'z vaqtlar uchun
            )
            lang = getattr(info, "language", self.language)
            prob = getattr(info, "language_probability", 0)
            print(f"[STT] Til aniqlandi: {lang} ({prob:.0%})")

            result = []
            for seg in segments:
                # Agar word_timestamps=True bo'lsa, har bir segmentda .words bo'ladi
                if hasattr(seg, "words") and seg.words:
                    for w in seg.words:
                        w_text = w.word.strip()
                        if w_text:
                            result.append({
                                "start": round(w.start, 3),
                                "end": round(w.end, 3),
                                "text": w_text,
                            })
                else:
                    # Fallback — butun segmentni so'zlarga bo'lib chiqamiz
                    text = seg.text.strip()
                    if text:
                        words = [w.strip() for w in text.split() if w.strip()]
                        s0 = float(seg.start)
                        e0 = float(seg.end)
                        if words and e0 > s0:
                            step = (e0 - s0) / len(words)
                            for i, w in enumerate(words):
                                ws = s0 + i * step
                                we = s0 + (i + 1) * step
                                result.append({
                                    "start": round(ws, 3),
                                    "end": round(we, 3),
                                    "text": w,
                                })
                        else:
                            result.append({
                                "start": round(seg.start, 2),
                                "end": round(seg.end, 2),
                                "text": text,
                            })
            print(f"[STT] {len(result)} so'z/segment topildi (Whisper).")
            return result
        except Exception as e:
            print(f"[STT] Whisper xatosi: {e}")
            return []

    # ------------------------------------------------------------------ #
    def get_engine_name(self) -> str:
        return self.active_engine or "Noma'lum"

    def get_full_text(self, segments: List[Dict]) -> str:
        return " ".join(s["text"] for s in segments if s.get("text"))

    def _refine_timestamps_with_audio(self, segments: List[Dict], audio_path: str) -> List[Dict]:
        """
        Ovoz to'lqinini (PCM) tahlil qilib, so'zlarning start/end vaqtini
        aniqroq qiladi (premium refinement).
        """
        try:
            import soundfile as sf
            import numpy as np
            
            if not segments:
                return segments

            data, samplerate = sf.read(audio_path)
            # Monoga o'tkazish
            if len(data.shape) > 1:
                data = np.mean(data, axis=1)

            if len(data) == 0:
                return segments

            # 5ms frame RMS (yuqori aniqlik)
            frame = max(1, int(0.005 * samplerate))
            rms = []
            for i in range(0, len(data), frame):
                fr = data[i:i + frame]
                if len(fr) == 0:
                    continue
                rms.append(float(np.sqrt(np.mean(fr * fr)) + 1e-12))
            if not rms:
                return segments

            e = np.array(rms, dtype=np.float32)
            e = np.convolve(e, np.ones(5, dtype=np.float32) / 5.0, mode="same")
            base_thr = max(float(np.percentile(e, 40)), float(np.max(e) * 0.10))

            def _nearest_onset(t: float) -> float:
                idx = int((t * samplerate) / frame)
                left = max(0, idx - 30)   # 150ms
                right = min(len(e) - 1, idx + 30)
                local = e[left:right + 1]
                if len(local) == 0:
                    return t
                thr = max(base_thr, float(np.max(local) * 0.22))
                above = np.where(local >= thr)[0]
                if len(above) == 0:
                    return t
                cand = left + int(above[0])
                return (cand * frame) / samplerate

            def _nearest_offset(t: float) -> float:
                idx = int((t * samplerate) / frame)
                left = max(0, idx - 40)   # 200ms
                right = min(len(e) - 1, idx + 40)
                local = e[left:right + 1]
                if len(local) == 0:
                    return t
                thr = max(base_thr * 0.9, float(np.max(local) * 0.16))
                above = np.where(local >= thr)[0]
                if len(above) == 0:
                    return t
                cand = left + int(above[-1])
                return (cand * frame) / samplerate

            refined = []
            for seg in segments:
                s0 = float(seg.get("start", 0.0))
                e0 = float(seg.get("end", s0 + 0.05))
                s1 = _nearest_onset(s0)
                e1 = _nearest_offset(e0)

                # haddan tashqari sakrashni cheklash
                if abs(s1 - s0) > 0.12:
                    s1 = s0
                if abs(e1 - e0) > 0.16:
                    e1 = e0

                if e1 <= s1 + 0.02:
                    e1 = s1 + 0.02

                refined.append({**seg, "start": round(s1, 3), "end": round(e1, 3)})

            # Timeline smoothing: overlap bo'lmasin, ketma-ketlik qat'iy bo'lsin
            smoothed = []
            for i, seg in enumerate(refined):
                s = float(seg["start"])
                e2 = float(seg["end"])

                if i > 0:
                    prev_end = float(smoothed[-1]["end"])
                    s = max(s, prev_end)
                if e2 <= s + 0.02:
                    e2 = s + 0.02

                if i < len(refined) - 1:
                    next_start = float(refined[i + 1]["start"])
                    if e2 > next_start - 0.005:
                        e2 = max(s + 0.02, next_start - 0.005)

                smoothed.append({**seg, "start": round(s, 3), "end": round(e2, 3)})

            return smoothed
        except Exception as e:
            print(f"[STT] Refinement error: {e}")
            return segments

    def _auto_global_sync_calibration(self, segments: List[Dict], audio_path: str) -> List[Dict]:
        """
        So'zlar timeline'ini audio energiya bilan solishtirib global offsetni topadi.
        Natija: barcha segment start/end qiymatlari bir xil miqdorda suriladi.
        """
        try:
            import soundfile as sf
            import numpy as np

            if not segments:
                return segments

            data, samplerate = sf.read(audio_path)
            if len(data.shape) > 1:
                data = np.mean(data, axis=1)
            if len(data) == 0:
                return segments

            # 10ms frame RMS energiya
            frame = max(1, int(0.01 * samplerate))
            rms = []
            for i in range(0, len(data), frame):
                fr = data[i:i + frame]
                if len(fr) == 0:
                    continue
                rms.append(float(np.sqrt(np.mean(fr * fr)) + 1e-12))
            if not rms:
                return segments

            e = np.array(rms, dtype=np.float32)
            kernel = np.ones(7, dtype=np.float32) / 7.0
            e = np.convolve(e, kernel, mode="same")

            # So'z boshlanishlaridan energiya signalini yig'amiz
            start_hist = np.zeros_like(e)
            for seg in segments:
                idx = int((float(seg.get("start", 0.0)) * samplerate) / frame)
                if 0 <= idx < len(start_hist):
                    start_hist[idx] += 1.0
            if float(np.sum(start_hist)) <= 0:
                return segments

            # Korrelyatsiya orqali eng yaxshi global siljishni topamiz
            max_shift_frames = int(0.35 / 0.01)  # +/-350ms
            best_shift = 0
            best_score = -1.0
            for shift in range(-max_shift_frames, max_shift_frames + 1):
                if shift >= 0:
                    a = start_hist[shift:]
                    b = e[:len(a)]
                else:
                    a = start_hist[:shift]
                    b = e[-shift:]
                if len(a) < 10:
                    continue
                score = float(np.sum(a * b))
                if score > best_score:
                    best_score = score
                    best_shift = shift

            offset_sec = (best_shift * frame) / samplerate

            # Juda katta/haqiqiy bo'lmagan siljishni qat'iy cheklaymiz
            # (katta shift amalda timingni buzib yuborishi mumkin).
            offset_sec = max(-0.08, min(0.08, offset_sec))
            if abs(offset_sec) < 0.005:
                return segments

            calibrated = []
            for seg in segments:
                s = max(0.0, float(seg.get("start", 0.0)) - offset_sec)
                e2 = max(s + 0.01, float(seg.get("end", s + 0.01)) - offset_sec)
                calibrated.append({**seg, "start": round(s, 3), "end": round(e2, 3)})

            print(f"[STT] Auto global sync calibration qo'llandi: {offset_sec:+.3f}s")
            return calibrated
        except Exception as e:
            print(f"[STT] Global calibration error: {e}")
            return segments

    def _finalize_segments_auto(self, segments: List[Dict], audio_path: str) -> List[Dict]:
        """
        Har qanday engine uchun yagona avtomatik post-processing pipeline:
        1) minimal tozalash/saralash
        2) local audio refinement
        3) global sync calibration
        4) timeline smoothing (overlap'ni yo'qotish)
        """
        if not segments:
            return []

        cleaned: List[Dict] = []
        for s in segments:
            text = str(s.get("text", "")).strip()
            if not text:
                continue
            st = max(0.0, float(s.get("start", 0.0)))
            en = max(st + 0.02, float(s.get("end", st + 0.02)))
            cleaned.append({**s, "start": round(st, 3), "end": round(en, 3), "text": text})

        if not cleaned:
            return []

        cleaned.sort(key=lambda x: (float(x.get("start", 0.0)), float(x.get("end", 0.0))))

        refined = self._refine_timestamps_with_audio(cleaned, audio_path)

        # Agar timing allaqachon ishonchli lock qilingan bo'lsa,
        # global kalibratsiya bilan qayta surmaymiz.
        locked_count = sum(1 for s in refined if bool(s.get("__timing_locked__", False)))
        locked_ratio = locked_count / max(len(refined), 1)
        dominant_source = str(refined[0].get("__timing_source__", "")) if refined else ""
        should_skip_global = locked_ratio >= 0.8 and dominant_source in (
            "muxlisa_whisper_rhythm",
            "muxlisa_audio",
            "whisper_word_timestamps",
        )

        calibrated = refined if should_skip_global else self._auto_global_sync_calibration(refined, audio_path)

        # Yakuniy qat'iy timeline (har xil video/engine uchun bir xil natija sifati)
        final_segments: List[Dict] = []
        prev_end = 0.0
        for seg in calibrated:
            s = max(float(seg.get("start", 0.0)), prev_end)
            e = max(float(seg.get("end", s + 0.02)), s + 0.02)
            out = {
                **seg,
                "start": round(s, 3),
                "end": round(e, 3),
                "__timing_locked__": True,
                "__timing_source__": str(seg.get("__timing_source__", "auto_pipeline")),
            }
            final_segments.append(out)
            prev_end = e

        return final_segments
