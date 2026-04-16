"""
Production-grade real-time STT pipeline (Whisper/Faster-Whisper).

Why this file exists:
- Streaming subtitle systems fail mostly because of timeline instability, not raw model speed.
- This module enforces a single global timeline, stability gating, deduplication, and
  incremental output (YouTube/Zoom-like behavior).

Design goals:
- No naive independent chunking
- No repeated full-text printing
- No unstable partial-word spam
- Smooth incremental words in chronological order
"""

from __future__ import annotations

import queue
import threading
import time
import tempfile
import os
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    # Pseudo-streaming defaults: keep long context, update frequently.
    window_sec: float = 5.0
    hop_sec: float = 0.5
    block_sec: float = 0.2
    device: Optional[int] = None


@dataclass
class DecodeConfig:
    language: str = "uz"
    beam_size: int = 5
    vad_filter: bool = True
    condition_on_previous_text: bool = False
    word_timestamps: bool = True


@dataclass
class StabilityConfig:
    # Emit when the same word is observed in >=2 overlapping windows
    min_confirmations: int = 2
    # Or emit when the word end is this far behind current audio clock
    trailing_stability_sec: float = 0.45
    # Prevent bursty output spikes
    max_emit_per_tick: int = 2
    # Quantization for robust dedup keys
    time_quant_sec: float = 0.04


@dataclass
class RefinementConfig:
    enabled: bool = True
    language: str = "uz"
    # Buffer to send for refinement when no punctuation boundary appears
    max_buffer_sec: float = 6.0
    # If corrected token count deviates too much, keep original (timing safety)
    max_token_ratio_deviation: float = 0.30
    # Worker queue size for async refinement
    queue_size: int = 8


@dataclass
class WordEvent:
    token: str
    start: float
    end: float
    idx: int = -1


class AudioTimelineBuffer:
    """
    Append-only PCM buffer with global timeline indexing.

    WHY:
    - Muxlisa refinement needs audio slices for finalized phrase/sentence ranges.
    - Extracting by global time keeps refinement aligned with live timeline.
    """

    def __init__(self, sample_rate: int, keep_sec: float = 90.0):
        self.sample_rate = sample_rate
        self.keep_samples = int(max(1.0, keep_sec) * sample_rate)
        self._buf = np.zeros(0, dtype=np.float32)
        self._base_sample = 0  # global sample index of _buf[0]
        self._lock = threading.Lock()

    def append(self, samples: np.ndarray) -> None:
        with self._lock:
            if len(samples) == 0:
                return
            self._buf = np.concatenate([self._buf, samples.astype(np.float32, copy=False)])
            overflow = len(self._buf) - self.keep_samples
            if overflow > 0:
                self._buf = self._buf[overflow:]
                self._base_sample += overflow

    def extract(self, start_sec: float, end_sec: float) -> Optional[np.ndarray]:
        if end_sec <= start_sec:
            return None
        s = int(round(start_sec * self.sample_rate))
        e = int(round(end_sec * self.sample_rate))
        with self._lock:
            local_s = s - self._base_sample
            local_e = e - self._base_sample
            if local_e <= 0 or local_s >= len(self._buf):
                return None
            local_s = max(0, local_s)
            local_e = min(len(self._buf), local_e)
            if local_e <= local_s:
                return None
            return self._buf[local_s:local_e].copy()


class MicrophoneSlidingWindowInput:
    """
    Captures mic audio and yields overlapping windows on a global timeline.

    WHY:
    - Overlap is required to stabilize word boundaries.
    - Global sample clock avoids resetting timeline per chunk.
    """

    def __init__(self, config: AudioConfig):
        self.config = config
        self._q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self._started = False
        self._start_monotonic = 0.0
        self._total_samples = 0
        self.timeline_buffer = AudioTimelineBuffer(config.sample_rate, keep_sec=120.0)

    def _audio_callback(self, indata, frames, _time_info, _status) -> None:
        if self._stop.is_set():
            return
        mono = np.asarray(indata, dtype=np.float32).reshape(-1)
        try:
            self._q.put_nowait(mono.copy())
        except queue.Full:
            # Drop oldest behavior: we prefer continuity over blocking callback thread
            try:
                _ = self._q.get_nowait()
                self._q.put_nowait(mono.copy())
            except Exception:
                pass

    def start(self) -> None:
        import sounddevice as sd

        if self._started:
            return
        self._stop.clear()
        self._start_monotonic = time.monotonic()
        self._stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="float32",
            blocksize=max(1, int(self.config.block_sec * self.config.sample_rate)),
            callback=self._audio_callback,
            device=self.config.device,
        )
        self._stream.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._stop.set()
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._started = False

    def windows(self) -> Iterable[Tuple[np.ndarray, float, float, float]]:
        """
        Yields: (audio_window, global_start_sec, global_end_sec, current_audio_clock_sec)
        """
        window_n = int(self.config.window_sec * self.config.sample_rate)
        hop_n = int(self.config.hop_sec * self.config.sample_rate)
        if window_n <= 0 or hop_n <= 0:
            raise ValueError("window_sec/hop_sec must be positive.")
        if hop_n > window_n:
            raise ValueError("hop_sec must be <= window_sec for overlap.")

        rolling = np.zeros(0, dtype=np.float32)
        emitted_samples = 0

        while not self._stop.is_set():
            try:
                block = self._q.get(timeout=0.25)
            except queue.Empty:
                continue
            rolling = np.concatenate([rolling, block], axis=0)
            self._total_samples += len(block)
            self.timeline_buffer.append(block)

            while len(rolling) >= window_n:
                window = rolling[:window_n].copy()
                global_start = emitted_samples / self.config.sample_rate
                global_end = (emitted_samples + window_n) / self.config.sample_rate
                current_clock = self._total_samples / self.config.sample_rate
                yield window, global_start, global_end, current_clock

                rolling = rolling[hop_n:]
                emitted_samples += hop_n


class FasterWhisperTranscriber:
    """
    Word-level transcriber using Faster-Whisper.

    WHY:
    - Word timestamps are mandatory for stable subtitle timing.
    - GPU is used when available, else CPU int8 for stability.
    """

    def __init__(self, model_size: str = "small", decode_cfg: Optional[DecodeConfig] = None):
        self.decode_cfg = decode_cfg or DecodeConfig()
        self.model_size = model_size
        self.model = self._load_model(model_size)

    @staticmethod
    def _load_model(model_size: str):
        from faster_whisper import WhisperModel

        device = "cpu"
        compute_type = "int8"
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
        except Exception:
            pass
        return WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe_words(self, audio_window: np.ndarray) -> List[WordEvent]:
        segs, _info = self.model.transcribe(
            audio_window,
            language=self.decode_cfg.language,
            beam_size=self.decode_cfg.beam_size,
            vad_filter=self.decode_cfg.vad_filter,
            condition_on_previous_text=self.decode_cfg.condition_on_previous_text,
            word_timestamps=self.decode_cfg.word_timestamps,
        )
        out: List[WordEvent] = []
        for seg in segs:
            if not getattr(seg, "words", None):
                continue
            for w in seg.words:
                token = (w.word or "").strip()
                if not token:
                    continue
                s = float(w.start)
                e = max(s + 0.01, float(w.end))
                out.append(WordEvent(token=token, start=s, end=e))
        return out


class TimelineStabilityManager:
    """
    Converts local chunk words to global time, stabilizes, deduplicates, and emits in-order.

    WHY:
    - Overlapping windows produce duplicate/partial hypotheses.
    - Stable emission logic prevents early words and bursty delayed dumps.
    """

    def __init__(self, cfg: Optional[StabilityConfig] = None):
        self.cfg = cfg or StabilityConfig()
        self._seen: Dict[Tuple[str, int, int], Dict[str, float]] = {}
        self._emitted: set[Tuple[str, int, int]] = set()

    def _q(self, t: float) -> int:
        return int(round(t / self.cfg.time_quant_sec))

    def _key(self, w: WordEvent) -> Tuple[str, int, int]:
        return (w.token.lower(), self._q(w.start), self._q(w.end))

    def ingest(
        self,
        local_words: Sequence[WordEvent],
        chunk_global_start: float,
        chunk_global_end: float,
        current_audio_clock: float,
    ) -> List[WordEvent]:
        # Normalize words into global timeline
        global_words: List[WordEvent] = []
        for w in local_words:
            gs = chunk_global_start + max(0.0, w.start)
            ge = chunk_global_start + max(w.end, w.start + 0.01)
            if gs > chunk_global_end + 0.5:
                continue
            global_words.append(WordEvent(token=w.token, start=gs, end=ge))

        # Update hypothesis memory
        now = time.monotonic()
        for w in global_words:
            k = self._key(w)
            item = self._seen.get(k)
            if item is None:
                self._seen[k] = {
                    "count": 1.0,
                    "start": w.start,
                    "end": w.end,
                    "first_seen": now,
                    "last_seen": now,
                }
            else:
                item["count"] += 1.0
                # Average times for smoother estimate
                c = item["count"]
                item["start"] = (item["start"] * (c - 1.0) + w.start) / c
                item["end"] = (item["end"] * (c - 1.0) + w.end) / c
                item["last_seen"] = now

        # Decide stable emissions
        candidates: List[Tuple[Tuple[str, int, int], Dict[str, float]]] = []
        for k, item in self._seen.items():
            if k in self._emitted:
                continue
            stable_by_overlap = item["count"] >= self.cfg.min_confirmations
            stable_by_trailing = item["end"] <= (current_audio_clock - self.cfg.trailing_stability_sec)
            if stable_by_overlap or stable_by_trailing:
                candidates.append((k, item))

        candidates.sort(key=lambda x: (x[1]["start"], x[1]["end"]))
        out: List[WordEvent] = []
        for k, item in candidates[: self.cfg.max_emit_per_tick]:
            self._emitted.add(k)
            out.append(
                WordEvent(
                    token=k[0],
                    start=float(item["start"]),
                    end=max(float(item["start"]) + 0.01, float(item["end"])),
                )
            )
        return out


class IncrementalTranscriptOutput:
    """
    Incremental output engine that never reprints full transcript repeatedly.
    """

    def __init__(
        self,
        on_emit: Optional[Callable[[WordEvent], None]] = None,
        on_refined: Optional[Callable[[List[WordEvent]], None]] = None,
    ):
        self.words: List[WordEvent] = []
        self.on_emit = on_emit or self._default_print
        self.on_refined = on_refined

    @staticmethod
    def _default_print(w: WordEvent) -> None:
        print(f"[{w.start:07.3f}-{w.end:07.3f}] {w.token}")

    def emit(self, new_words: Sequence[WordEvent]) -> None:
        for w in new_words:
            self.words.append(w)
            self.on_emit(w)

    def transcript_text(self) -> str:
        return " ".join(w.token for w in self.words)

    def apply_refined_patch(self, patch_words: Sequence[WordEvent]) -> None:
        if not patch_words:
            return
        idx_to_word = {w.idx: w for w in patch_words if w.idx >= 0}
        if not idx_to_word:
            return
        for i, old in enumerate(self.words):
            if old.idx in idx_to_word:
                nw = idx_to_word[old.idx]
                self.words[i] = WordEvent(token=nw.token, start=old.start, end=old.end, idx=old.idx)
        if self.on_refined:
            self.on_refined(list(patch_words))


class AsyncMuxlisaRefiner:
    """
    Background Uzbek text quality enhancer.

    IMPORTANT:
    - Never blocks live emission.
    - Never rewrites timing.
    - Only patches token text when confidence/count checks pass.
    """

    def __init__(
        self,
        sample_rate: int,
        cfg: Optional[RefinementConfig] = None,
    ):
        self.cfg = cfg or RefinementConfig()
        self.sample_rate = sample_rate
        self._q: "queue.Queue[Tuple[List[WordEvent], np.ndarray]]" = queue.Queue(maxsize=self.cfg.queue_size)
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._worker, daemon=True)
        self._on_patch: Optional[Callable[[List[WordEvent]], None]] = None
        self._client = None
        self._th.start()

    def attach_patch_callback(self, cb: Callable[[List[WordEvent]], None]) -> None:
        self._on_patch = cb

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from ai_labs_api import MuxlisaClient

            c = MuxlisaClient()
            if c.is_available():
                self._client = c
                return c
        except Exception:
            pass
        return None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [t for t in (text or "").strip().split() if t]

    def _worker(self) -> None:
        try:
            import soundfile as sf
        except Exception:
            sf = None
        while not self._stop.is_set():
            try:
                words, audio = self._q.get(timeout=0.25)
            except queue.Empty:
                continue
            if not words or audio is None or len(audio) == 0:
                continue
            client = self._get_client()
            if client is None or sf is None:
                continue
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                    tmp = f.name
                sf.write(tmp, audio, self.sample_rate)
                segs = client.transcribe_audio(tmp, language=self.cfg.language)
                if not segs:
                    continue
                corrected_text = " ".join((s.get("text") or "").strip() for s in segs if (s.get("text") or "").strip())
                corrected = self._tokenize(corrected_text)
                original = [w.token for w in words]
                if not corrected or not original:
                    continue
                ratio_dev = abs(len(corrected) - len(original)) / max(len(original), 1)
                if ratio_dev > self.cfg.max_token_ratio_deviation:
                    continue

                # Keep timing/order fixed; patch only token strings.
                n = min(len(corrected), len(words))
                patch: List[WordEvent] = []
                for i in range(n):
                    o = words[i]
                    patch.append(WordEvent(token=corrected[i], start=o.start, end=o.end, idx=o.idx))
                if self._on_patch and patch:
                    self._on_patch(patch)
            except Exception:
                continue
            finally:
                if tmp and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass

    def submit(self, words: List[WordEvent], audio_slice: np.ndarray) -> None:
        if not self.cfg.enabled:
            return
        try:
            self._q.put_nowait((words, audio_slice))
        except queue.Full:
            # Drop oldest task to keep live behavior stable
            try:
                _ = self._q.get_nowait()
                self._q.put_nowait((words, audio_slice))
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()


class RealtimeSTTPipeline:
    """
    End-to-end orchestrator.
    """

    def __init__(
        self,
        audio_cfg: Optional[AudioConfig] = None,
        decode_cfg: Optional[DecodeConfig] = None,
        stability_cfg: Optional[StabilityConfig] = None,
        refine_cfg: Optional[RefinementConfig] = None,
        model_size: str = "small",
        on_word: Optional[Callable[[WordEvent], None]] = None,
        on_refined_patch: Optional[Callable[[List[WordEvent]], None]] = None,
    ):
        self.audio_cfg = audio_cfg or AudioConfig()
        self.decode_cfg = decode_cfg or DecodeConfig()
        self.mic = MicrophoneSlidingWindowInput(self.audio_cfg)
        self.asr = FasterWhisperTranscriber(model_size=model_size, decode_cfg=self.decode_cfg)
        self.timeline = TimelineStabilityManager(stability_cfg or StabilityConfig())
        self.output = IncrementalTranscriptOutput(on_emit=on_word, on_refined=on_refined_patch)
        self.refiner = AsyncMuxlisaRefiner(sample_rate=self.audio_cfg.sample_rate, cfg=refine_cfg or RefinementConfig())
        self.refiner.attach_patch_callback(self.output.apply_refined_patch)
        self._next_idx = 0
        self._pending_refine: List[WordEvent] = []
        self._last_boundary_end = 0.0

    @staticmethod
    def _is_boundary_token(token: str) -> bool:
        t = (token or "").strip()
        return t.endswith(".") or t.endswith("?") or t.endswith("!")

    def _maybe_schedule_refinement(self, newly_emitted: List[WordEvent], current_clock: float) -> None:
        if not newly_emitted:
            return
        self._pending_refine.extend(newly_emitted)

        should_flush = False
        if any(self._is_boundary_token(w.token) for w in newly_emitted):
            should_flush = True
        elif self._pending_refine:
            span = self._pending_refine[-1].end - self._pending_refine[0].start
            if span >= self.refiner.cfg.max_buffer_sec:
                should_flush = True

        if not should_flush:
            return

        s = self._pending_refine[0].start
        e = self._pending_refine[-1].end
        # Guard against overlapping repeats
        s = max(s, self._last_boundary_end)
        audio_slice = self.mic.timeline_buffer.extract(s, e)
        if audio_slice is not None and len(audio_slice) > 0:
            self.refiner.submit(list(self._pending_refine), audio_slice)
            self._last_boundary_end = e
        self._pending_refine = []

    def run_forever(self) -> None:
        self.mic.start()
        try:
            for window, g_start, g_end, clock in self.mic.windows():
                local_words = self.asr.transcribe_words(window)
                stable_words = self.timeline.ingest(local_words, g_start, g_end, clock)
                for w in stable_words:
                    w.idx = self._next_idx
                    self._next_idx += 1
                self.output.emit(stable_words)
                self._maybe_schedule_refinement(stable_words, clock)
        finally:
            self.mic.stop()
            self.refiner.stop()


if __name__ == "__main__":
    # Example usage: production defaults favor stability over raw latency.
    pipe = RealtimeSTTPipeline(
        audio_cfg=AudioConfig(window_sec=4.0, hop_sec=2.0, block_sec=0.2),
        decode_cfg=DecodeConfig(language="uz", beam_size=5, vad_filter=True),
        stability_cfg=StabilityConfig(
            min_confirmations=2,
            trailing_stability_sec=0.65,
            max_emit_per_tick=4,
            time_quant_sec=0.04,
        ),
        refine_cfg=RefinementConfig(
            enabled=True,
            language="uz",
            max_buffer_sec=6.0,
            max_token_ratio_deviation=0.30,
            queue_size=8,
        ),
        model_size="small",
    )
    pipe.run_forever()

