"""
Yerel sesli uyarı kuyruğu.

Seslendirme KAM'ın mevcut Windows ses yardımcısıyla (actions/windows_utils.py,
System.Speech) yapılır; internet gerektirmez. Yeni bir ses motoru yazılmamıştır.

- KAM (Gemini) konuşurken beklenir, sesler üst üste binmez.
- ASTRA konuşurken mikrofon sesi Gemini'ye gönderilmez (main.py bu bayrağı okur);
  böylece Gemini uyarıyı duyup yanıtlamaz ve sağlık verisi buluta gitmez.
- Kuyruk önceliklidir: önce en yüksek seviyeli uyarı okunur.
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
from typing import Callable

from .. import get_astra_logger

_speaking = threading.Event()


def astra_is_speaking() -> bool:
    return _speaking.is_set()


def make_speaker(engine: str, voice: str = "",
                 on_error: Callable[[str], None] | None = None) -> Callable[[str], None]:
    """Seslendirme fonksiyonu döndürür.

    engine="onecore": Windows'un yeni ses sistemi (Türkçe Tolga sesi genelde buradadır).
    engine="sapi": KAM'ın mevcut Windows ses fonksiyonu (actions/windows_utils.py).
    Yeni sistem çalışmazsa bir kez uyarı verip KAM'ın mevcut ses fonksiyonuna geçer.
    """
    from .windows_tts import speak_onecore

    log = get_astra_logger()
    state = {"engine": engine}

    def report(message: str) -> None:
        log.warning(message)
        if on_error:
            on_error(message)

    def sapi(text: str) -> None:
        from actions.windows_utils import speak_with_windows

        ok, detail = speak_with_windows(text, voice if state["engine"] == "sapi" else "")
        if not ok:
            report(f"ASTRA seslendirme başarısız (SAPI): {detail}")

    def speak(text: str) -> None:
        if state["engine"] == "onecore":
            ok, detail = speak_onecore(text, voice)
            if ok:
                return
            report(f"ASTRA yeni Windows ses sistemiyle konuşamadı, eski sisteme geçiliyor: {detail}")
            state["engine"] = "sapi-fallback"
        sapi(text)

    return speak


class VoiceAlerts:
    def __init__(self, speak: Callable[[str], None], kam_busy: Callable[[], bool] = lambda: False,
                 quiet_seconds: float = 1.2, max_wait_seconds: float = 20.0, synchronous: bool = False):
        self._speak = speak
        self._kam_busy = kam_busy
        self.quiet_seconds = quiet_seconds
        self.max_wait_seconds = max_wait_seconds
        self.synchronous = synchronous  # testler için: kuyruk yerine hemen seslendir
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = itertools.count()
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._log = get_astra_logger()
        self._thread: threading.Thread | None = None

    def say(self, text: str, level: int = 1, delay_seconds: float = 0.0) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self.synchronous:
            self._run(text)
            return
        with self._lock:
            if text in self._pending:  # aynı metin zaten sırada
                return
            self._pending.add(text)
        self._queue.put((-level, next(self._seq), time.monotonic() + delay_seconds, text))
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._worker, name="ASTRA-voice", daemon=True)
            self._thread.start()

    def _wait_for_quiet(self) -> None:
        deadline = time.monotonic() + self.max_wait_seconds
        quiet_since = None
        while time.monotonic() < deadline:
            if self._kam_busy():
                quiet_since = None
            elif quiet_since is None:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since >= self.quiet_seconds:
                return
            time.sleep(0.1)

    def _run(self, text: str) -> None:
        _speaking.set()
        try:
            self._speak(text)
        except Exception as exc:
            self._log.warning("ASTRA seslendirme hatası: %s", exc)
        finally:
            _speaking.clear()

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item[2] > time.monotonic():  # gecikmesi dolmamış
                self._queue.put(item)
                time.sleep(0.1)
                continue
            self._wait_for_quiet()
            # Beklerken daha öncelikli bir uyarı gelmiş olabilir: en öncelikliyi seç
            self._queue.put(item)
            item = self._queue.get()
            if item[2] > time.monotonic():
                self._queue.put(item)
                continue
            text = item[3]
            with self._lock:
                self._pending.discard(text)
            self._run(text)
