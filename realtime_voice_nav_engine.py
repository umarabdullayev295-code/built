"""
Production-grade realtime subtitle + voice-controlled video navigation engine.

Key design choice:
- Subtitle transcription pipeline and voice-command pipeline are fully separated.
- They communicate only through thread-safe queues/events, never in one tight loop.

This prevents:
- subtitle jitter due to command processing
- command lag due to subtitle bursts
- cross-contamination between unstable subtitle hypotheses and command triggers
"""

from __future__ import annotations

import bisect
import collections
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


# =========================
# Shared data structures
# =========================


@dataclass
class WordItem:
    token: str
    start: float
    end: float
    stable: bool = False
    idx: int = -1


@dataclass
class SubtitleConfig:
    sample_rate: int = 16000
    # Pseudo-streaming: decode last 5s every 0.5s for stable context.
    window_sec: float = 5.0
    hop_sec: float = 0.5
    block_sec: float = 0.2
    language: str = "uz"
    model_size: str = "small"
    min_confirmations: int = 2
    trailing_stability_sec: float = 0.4
    max_emit_per_tick: int = 2
    dedup_time_quant_sec: float = 0.04


@dataclass
class SearchConfig:
    search_window_sec: float = 120.0
    similarity_threshold: float = 0.72
    dedup_trigger_cooldown_sec: float = 2.5
    max_candidates: int = 512


# =========================
# Utility helpers
# =========================


def normalize_token(token: str) -> str:
    return "".join(ch for ch in (token or "").strip().lower() if ch.isalnum() or ch in ("'", "’", "ʻ"))


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def similarity(a: str, b: str) -> float:
    a_n = normalize_token(a)
    b_n = normalize_token(b)
    if not a_n and not b_n:
        return 1.0
    if not a_n or not b_n:
        return 0.0
    d = levenshtein(a_n, b_n)
    return 1.0 - (d / max(len(a_n), len(b_n)))


# =========================
# Audio input with global timeline
# =========================


class MicWindowStream:
    """
    Provides overlapping windows over a single global timeline.
    """

    def __init__(self, sample_rate: int, window_sec: float, hop_sec: float, block_sec: float, device: Optional[int] = None):
        self.sample_rate = sample_rate
        self.window_sec = window_sec
        self.hop_sec = hop_sec
        self.block_sec = block_sec
        self.device = device
        self._q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._running = False
        self._total_samples = 0

    def _cb(self, indata, _frames, _time_info, _status):
        if self._stop.is_set():
            return
        mono = np.asarray(indata, dtype=np.float32).reshape(-1)
        try:
            self._q.put_nowait(mono.copy())
        except queue.Full:
            try:
                _ = self._q.get_nowait()
                self._q.put_nowait(mono.copy())
            except Exception:
                pass

    def start(self) -> None:
        import sounddevice as sd

        if self._running:
            return
        self._stop.clear()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=max(1, int(self.block_sec * self.sample_rate)),
            callback=self._cb,
            device=self.device,
        )
        self._stream.start()
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._stop.set()
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._running = False

    def windows(self) -> Iterable[Tuple[np.ndarray, float, float, float]]:
        window_n = int(self.window_sec * self.sample_rate)
        hop_n = int(self.hop_sec * self.sample_rate)
        if hop_n <= 0 or window_n <= 0 or hop_n > window_n:
            raise ValueError("Invalid window/hop configuration")

        rolling = np.zeros(0, dtype=np.float32)
        emitted_samples = 0
        while not self._stop.is_set():
            try:
                blk = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            rolling = np.concatenate([rolling, blk], axis=0)
            self._total_samples += len(blk)

            while len(rolling) >= window_n:
                w = rolling[:window_n].copy()
                g_start = emitted_samples / self.sample_rate
                g_end = (emitted_samples + window_n) / self.sample_rate
                clock = self._total_samples / self.sample_rate
                yield w, g_start, g_end, clock
                rolling = rolling[hop_n:]
                emitted_samples += hop_n


# =========================
# Subtitle pipeline
# =========================


class FasterWhisperWordDecoder:
    def __init__(self, model_size: str, language: str):
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
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.language = language

    def decode_words(self, audio_window: np.ndarray) -> List[WordItem]:
        segs, _ = self.model.transcribe(
            audio_window,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
            word_timestamps=True,
        )
        out: List[WordItem] = []
        for seg in segs:
            for w in getattr(seg, "words", []) or []:
                tok = (w.word or "").strip()
                if not tok:
                    continue
                s = float(w.start)
                e = max(s + 0.01, float(w.end))
                out.append(WordItem(token=tok, start=s, end=e, stable=False))
        return out


class PrefixStabilityCommitter:
    """
    Commit logic for subtitle stability:
    - Compare current overlap hypothesis with previous one
    - Commit only common prefix that remains consistent
    """

    def __init__(self, cfg: SubtitleConfig):
        self.cfg = cfg
        self._prev_hyp: List[WordItem] = []
        self._next_idx = 0
        self._seen_counts: Dict[Tuple[str, int, int], int] = {}
        self._emitted_keys: set[Tuple[str, int, int]] = set()

    @staticmethod
    def _common_prefix_len(a: Sequence[WordItem], b: Sequence[WordItem]) -> int:
        n = min(len(a), len(b))
        i = 0
        while i < n:
            ta = normalize_token(a[i].token)
            tb = normalize_token(b[i].token)
            # token + near timestamp match
            if ta != tb:
                break
            if abs(a[i].start - b[i].start) > 0.12:
                break
            i += 1
        return i

    def _q(self, t: float) -> int:
        return int(round(t / max(0.001, self.cfg.dedup_time_quant_sec)))

    def _key(self, w: WordItem) -> Tuple[str, int, int]:
        return (normalize_token(w.token), self._q(w.start), self._q(w.end))

    def _can_emit(self, w: WordItem, current_audio_clock: float) -> bool:
        k = self._key(w)
        seen = self._seen_counts.get(k, 0)
        stable_by_confirm = seen >= self.cfg.min_confirmations
        stable_by_trailing = w.end <= (current_audio_clock - self.cfg.trailing_stability_sec)
        return stable_by_confirm or stable_by_trailing

    def commit(self, global_hypothesis: List[WordItem], current_audio_clock: float) -> List[WordItem]:
        # First pass: we need another overlap to confirm
        if not self._prev_hyp:
            self._prev_hyp = list(global_hypothesis)
            return []

        cpl = self._common_prefix_len(self._prev_hyp, global_hypothesis)
        committed = []
        for w in self._prev_hyp[:cpl]:
            k = self._key(w)
            self._seen_counts[k] = self._seen_counts.get(k, 0) + 1
            if k in self._emitted_keys:
                continue
            if not self._can_emit(w, current_audio_clock):
                continue
            w.stable = True
            w.idx = self._next_idx
            self._next_idx += 1
            committed.append(w)
            self._emitted_keys.add(k)

        # Remaining part stays hypothesis for next overlap
        self._prev_hyp = list(global_hypothesis[cpl:])
        # Burst prevention: only a tiny number of words per update.
        committed.sort(key=lambda x: (x.start, x.end))
        return committed[: self.cfg.max_emit_per_tick]


class SubtitlePipeline:
    """
    Stable subtitle producer (separate from command pipeline).
    """

    def __init__(self, cfg: SubtitleConfig, on_word: Callable[[WordItem], None]):
        self.cfg = cfg
        self.on_word = on_word
        self.mic = MicWindowStream(cfg.sample_rate, cfg.window_sec, cfg.hop_sec, cfg.block_sec)
        self.decoder = FasterWhisperWordDecoder(cfg.model_size, cfg.language)
        self.committer = PrefixStabilityCommitter(cfg)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._transcript_index = TranscriptIndex()

    @property
    def transcript_index(self) -> "TranscriptIndex":
        return self._transcript_index

    def start(self):
        self.mic.start()
        self._stop.clear()
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.mic.stop()

    def _run(self):
        for window, g_start, _g_end, clock in self.mic.windows():
            if self._stop.is_set():
                break
            local_words = self.decoder.decode_words(window)
            # Map local->global for this hypothesis
            global_hyp = [
                WordItem(token=w.token, start=g_start + w.start, end=g_start + w.end, stable=False)
                for w in local_words
            ]
            committed = self.committer.commit(global_hyp, current_audio_clock=clock)
            if not committed:
                continue
            for w in committed:
                self._transcript_index.add(w)
                self.on_word(w)


# =========================
# Transcript index for search
# =========================


class TranscriptIndex:
    """
    Time-ordered stable words for efficient recent-window search.
    """

    def __init__(self):
        self._words: List[WordItem] = []
        self._starts: List[float] = []
        self._lock = threading.Lock()
        self._latest_time: float = 0.0

    def add(self, w: WordItem) -> None:
        with self._lock:
            self._words.append(w)
            self._starts.append(w.start)
            if w.end > self._latest_time:
                self._latest_time = w.end

    def latest_time(self) -> float:
        with self._lock:
            return float(self._latest_time)

    def recent_window(self, now_sec: float, window_sec: float, max_candidates: int) -> List[WordItem]:
        with self._lock:
            left = max(0.0, now_sec - window_sec)
            i = bisect.bisect_left(self._starts, left)
            arr = self._words[i:]
            if max_candidates > 0 and len(arr) > max_candidates:
                arr = arr[-max_candidates:]
            return list(arr)


# =========================
# Voice command pipeline
# =========================


@dataclass
class VoiceCommandEvent:
    query: str
    at_time: float


class CommandRecognizer:
    """
    Placeholder for command recognition pipeline.

    In production you can:
    - use a second dedicated ASR model, or
    - feed external command text events here.
    """

    def __init__(self):
        self._q: "queue.Queue[VoiceCommandEvent]" = queue.Queue(maxsize=64)

    def submit_text_command(self, query: str, at_time: Optional[float] = None):
        evt = VoiceCommandEvent(query=query, at_time=at_time if at_time is not None else time.monotonic())
        try:
            self._q.put_nowait(evt)
        except queue.Full:
            try:
                _ = self._q.get_nowait()
                self._q.put_nowait(evt)
            except Exception:
                pass

    def events(self) -> Iterable[VoiceCommandEvent]:
        while True:
            try:
                yield self._q.get(timeout=0.25)
            except queue.Empty:
                continue


class VoiceSearchController:
    """
    Asynchronous voice search that does NOT block subtitle pipeline.
    """

    def __init__(
        self,
        transcript_index: TranscriptIndex,
        on_seek: Callable[[float, str], None],
        cfg: Optional[SearchConfig] = None,
    ):
        self.cfg = cfg or SearchConfig()
        self.transcript_index = transcript_index
        self.on_seek = on_seek
        self.recognizer = CommandRecognizer()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._recent_triggers: Deque[Tuple[str, float]] = collections.deque(maxlen=256)

    def start(self):
        self._stop.clear()
        self._thread.start()

    def stop(self):
        self._stop.set()

    def submit_command_text(self, query: str):
        self.recognizer.submit_text_command(query, at_time=time.monotonic())

    def _trigger_allowed(self, norm_q: str, now_mono: float) -> bool:
        while self._recent_triggers and (now_mono - self._recent_triggers[0][1]) > (self.cfg.dedup_trigger_cooldown_sec + 0.5):
            self._recent_triggers.popleft()
        for q, t0 in self._recent_triggers:
            if q == norm_q and (now_mono - t0) <= self.cfg.dedup_trigger_cooldown_sec:
                return False
        return True

    def _run(self):
        for evt in self.recognizer.events():
            if self._stop.is_set():
                break
            q = normalize_token(evt.query)
            if not q:
                continue
            now_mono = time.monotonic()
            if not self._trigger_allowed(q, now_mono):
                continue

            # Search only recent transcript window
            now_sec = self.transcript_index.latest_time()
            candidates = self.transcript_index.recent_window(
                now_sec=now_sec,
                window_sec=self.cfg.search_window_sec,
                max_candidates=self.cfg.max_candidates,
            )
            if not candidates:
                continue

            best: Optional[WordItem] = None
            best_score = 0.0
            for w in candidates:
                s = similarity(q, w.token)
                if s > best_score:
                    best_score = s
                    best = w
            if best is None or best_score < self.cfg.similarity_threshold:
                continue

            self._recent_triggers.append((q, now_mono))
            self.on_seek(best.start, best.token)


# =========================
# End-to-end engine
# =========================


class RealtimeSubtitleAndVoiceNavEngine:
    """
    Production orchestrator with two independent pipelines:
      A) subtitle transcription pipeline
      B) voice command/search pipeline
    """

    def __init__(
        self,
        subtitle_cfg: Optional[SubtitleConfig] = None,
        search_cfg: Optional[SearchConfig] = None,
        on_subtitle_word: Optional[Callable[[WordItem], None]] = None,
        on_seek: Optional[Callable[[float, str], None]] = None,
    ):
        self.subtitle_cfg = subtitle_cfg or SubtitleConfig()
        self.search_cfg = search_cfg or SearchConfig()
        self.on_subtitle_word = on_subtitle_word or (lambda w: print(f"SUB[{w.start:07.3f}] {w.token}"))
        self.on_seek = on_seek or (lambda ts, tok: print(f"SEEK -> {ts:07.3f}s ({tok})"))

        self.subtitle = SubtitlePipeline(self.subtitle_cfg, on_word=self.on_subtitle_word)
        self.voice = VoiceSearchController(self.subtitle.transcript_index, on_seek=self.on_seek, cfg=self.search_cfg)

    def start(self):
        self.subtitle.start()
        self.voice.start()

    def stop(self):
        self.voice.stop()
        self.subtitle.stop()

    def submit_voice_query_text(self, text: str):
        """
        Feed command text from your command recognizer pipeline.
        This stays separate from subtitle decoder loop.
        """
        self.voice.submit_command_text(text)


if __name__ == "__main__":
    engine = RealtimeSubtitleAndVoiceNavEngine()
    engine.start()
    try:
        # Demo: emulate command events from terminal input
        while True:
            q = input("voice-query> ").strip()
            if q.lower() in {"exit", "quit"}:
                break
            engine.submit_voice_query_text(q)
    finally:
        engine.stop()

