"""
KAM ana ekranındaki "SAĞLIK ÖZETİ" kartı — ASTRA sürümü.

KAM'ın eski dönen vücut hologramının ve eski sağlık özetinin yerine çizilir:
  - sağda: dönen holografik astronot kıyafeti (renk genel risk seviyesini gösterir)
  - solda: ASTRA analizi (seviye, öne çıkan bulgular, günün değerleri)
Karta tıklanınca ASTRA sağlık analizi penceresi açılır.

ui.py içindeki `health_card_drawer` bağlantısıyla çağrılır; draw_card() yalnızca
Tk ana iş parçacığında çalışır, hologram kareleri arka planda üretilir.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from .. import get_astra_logger
from .hologram import LEVEL_RGB, LEVEL_WORD, render_turntable

TAG = "astra_health_card"
FPS = 12
TEXT = "#7dfff6"
DIM_TEXT = "#7e8a88"
HINT = "#006a62"


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % rgb


def _default_photo(image):
    from PIL import ImageTk

    return ImageTk.PhotoImage(image)


class HealthCardHologram:
    def __init__(self, ui, on_click: Callable[[], None], to_photo: Callable = _default_photo):
        self.ui = ui
        self.on_click = on_click
        self.to_photo = to_photo
        self.level = 0
        self.simulated = True
        self.findings: list[str] = []   # öne çıkan bulgular (kısa)
        self.values: list[str] = []     # günün değerleri (kısa)
        self._photos: list = []
        self._photo_key = None
        self._ready: dict = {}
        self._rendering: set = set()
        self._lock = threading.Lock()
        self._bound = False
        self._log = get_astra_logger()

    def set_state(self, level: int, simulated: bool, findings: list[str] | None = None,
                  values: list[str] | None = None) -> None:
        self.level, self.simulated = level, simulated
        if findings is not None:
            self.findings = findings
        if values is not None:
            self.values = values

    @staticmethod
    def size_for(card_w: int, card_h: int) -> tuple[int, int]:
        """Hologram boyutu: kart yüksekliğini kullanır, kart genişliğinin %60'ını geçmez
        (KAM'ın eski vücut hologramı 130×180 idi; tipik ekranda bu ~180×240 – 200×260).
        Boyut 20 pikselin katlarına yuvarlanır (kart hafifçe büyüyüp küçülünce yeniden çizim olmasın)."""
        height = max(80, (card_h - 42) // 20 * 20)
        width = min(int(height * 0.72), int(card_w * 0.6)) // 10 * 10
        height = min(height, int(width / 0.72) // 20 * 20)
        return width, height

    def _start_render(self, key) -> None:
        if key in self._rendering:
            return
        self._rendering.add(key)

        def work():
            try:
                frames = render_turntable(*key)
                with self._lock:
                    self._ready[key] = frames
            except Exception as exc:
                self._log.warning("ASTRA sağlık kartı hologramı çizilemedi: %s", exc)
            finally:
                self._rendering.discard(key)

        threading.Thread(target=work, name="ASTRA-card-holo", daemon=True).start()

    def _bind(self, canvas) -> None:
        if self._bound:
            return

        def click(_event):
            threading.Thread(target=self.on_click, name="ASTRA-analysis", daemon=True).start()

        canvas.tag_bind(TAG, "<Button-1>", click)
        canvas.tag_bind(TAG, "<Enter>", lambda e: canvas.configure(cursor="hand2"))
        canvas.tag_bind(TAG, "<Leave>", lambda e: canvas.configure(cursor=""))
        self._bound = True

    def _photo_frame(self, key):
        if key != self._photo_key:
            with self._lock:
                frames = self._ready.get(key)
            if frames is None:
                self._start_render(key)
            else:
                self._photos = [self.to_photo(f) for f in frames]
                self._photo_key = key
        if not self._photos:
            return None
        return self._photos[int(time.time() * FPS) % len(self._photos)]

    def draw_card(self, canvas, x, y, w, h, pad, dimmed=False) -> None:
        hw, hh = self.size_for(w, h)
        hx = x + w - hw - 6
        hy = y + 36 + max(0, (h - 36 - hh) // 2)
        photo = self._photo_frame((self.level, hw, hh))
        if photo is not None:
            canvas.create_image(hx, hy, image=photo, anchor="nw", tags=(TAG,))
        self._bind(canvas)

        tx = x + pad
        text_w = max(60, hx - tx - 6)
        ty = y + 48
        bottom = y + h - 24
        color = _hex(LEVEL_RGB[self.level]) if self.level else "#00d4c0"
        if dimmed:
            color = DIM_TEXT
        head = ("SİM · " if self.simulated else "") + f"SEVİYE {self.level}"
        canvas.create_text(tx, ty, text=head, fill=color, font=("Segoe UI", 11, "bold"), anchor="w", tags=(TAG,))
        canvas.create_text(tx, ty + 18, text=LEVEL_WORD[self.level], fill=color, font=("Segoe UI", 10, "bold"),
                           anchor="w", tags=(TAG,))
        ty += 44
        for line in self.findings[:2]:
            if ty > bottom:
                break
            canvas.create_text(tx, ty, text=line, fill=DIM_TEXT if dimmed else color, font=("Segoe UI", 9, "bold"),
                               anchor="w", width=text_w, tags=(TAG,))
            ty += 18
        for line in self.values:
            if ty > bottom:
                break
            canvas.create_text(tx, ty, text=f"• {line}", fill=DIM_TEXT if dimmed else TEXT, font=("Segoe UI", 10),
                               anchor="w", width=text_w, tags=(TAG,))
            ty += 19
        canvas.create_text(tx, y + h - 12, text="▸ analiz için tıkla", fill=HINT, font=("Segoe UI", 8),
                           anchor="w", tags=(TAG,))
