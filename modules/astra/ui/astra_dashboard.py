"""
ASTRA hologram penceresi (Tkinter).

KAM'ın kamera önizleme penceresiyle aynı düzende (çerçevesiz, sürüklenebilir,
KAM renkleri) ayrı bir pencere açar. KAM'ın ana arayüzüne (ui.py) dokunmaz.
Solda dönen holografik astronot kıyafeti, sağda analiz metni ve büyük düğmeler.

Tkinter yalnızca ana iş parçacığından kullanılabildiği için show() her
iş parçacığından çağrılabilir; asıl iş root.after(0, ...) ile ana iş parçacığında yapılır.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from PIL import ImageTk

from .. import get_astra_logger
from .hologram import H, LEVEL_RGB, LEVEL_WORD, W

C_BG = "#020c0c"
C_PRI = "#00d4c0"
C_DIM = "#0a2a28"
C_TEXT = "#7dfff6"
C_ORG = "#ff6600"
FRAME_MS = 80


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % rgb


class HologramWindow:
    def __init__(self, root: tk.Misc, on_ack: Callable[[], int] | None = None):
        self.root = root
        self.on_ack = on_ack
        self.win: tk.Toplevel | None = None
        self._photos: list = []
        self._frame = 0
        self._anim_job = None
        self._close_job = None
        self._log = get_astra_logger()

    # ── her iş parçacığından çağrılabilir ────────────────────────────────
    def show(self, frames, title: str, level: int, text: str, simulated: bool,
             auto_close_ms: int | None = 30000) -> None:
        """frames: hologram.render_frames() çıktısı (PIL görüntüleri)."""
        try:
            self.root.after(0, lambda: self._show(frames, title, level, text, simulated, auto_close_ms))
        except Exception as exc:
            self._log.warning("ASTRA hologram penceresi açılamadı: %s", exc)

    def close(self) -> None:
        try:
            self.root.after(0, self._close)
        except Exception:
            pass

    # ── yalnızca ana iş parçacığı ────────────────────────────────────────
    def _build(self) -> None:
        win = tk.Toplevel(self.root)
        win.attributes("-topmost", True)
        win.overrideredirect(True)
        w, h = W + 520, H + 34
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
        win.configure(bg=C_BG)

        bar = tk.Frame(win, bg=C_DIM)
        bar.pack(side="top", fill="x")
        title = tk.Label(bar, text="KAM ASTRA · SAĞLIK ANALİZİ", bg=C_DIM, fg=C_TEXT, font=("Segoe UI", 10, "bold"))
        title.pack(side="left", padx=8, pady=3)
        close = tk.Label(bar, text="×", bg=C_DIM, fg=C_ORG, font=("Segoe UI", 14, "bold"), cursor="hand2")
        close.pack(side="right", padx=8)
        close.bind("<Button-1>", lambda e: self._close())

        def start(e):
            win._drag = (e.x, e.y)

        def move(e):
            dx, dy = getattr(win, "_drag", (0, 0))
            win.geometry(f"+{win.winfo_x() - dx + e.x}+{win.winfo_y() - dy + e.y}")

        for widget in (bar, title):
            widget.bind("<ButtonPress-1>", start)
            widget.bind("<B1-Motion>", move)

        border = tk.Frame(win, bg=C_PRI, bd=1)
        border.pack(expand=True, fill="both")
        body = tk.Frame(border, bg=C_BG)
        body.pack(expand=True, fill="both")

        self.image_label = tk.Label(body, bg=C_BG, bd=0)
        self.image_label.pack(side="left", padx=(6, 0), pady=6)

        right = tk.Frame(body, bg=C_BG)
        right.pack(side="left", expand=True, fill="both", padx=14, pady=10)
        self.header = tk.Label(right, text="", bg=C_BG, fg=C_TEXT, font=("Segoe UI", 16, "bold"), anchor="w")
        self.header.pack(fill="x")
        self.source = tk.Label(right, text="", bg=C_BG, fg="#ffcc00", font=("Segoe UI", 10, "bold"), anchor="w")
        self.source.pack(fill="x", pady=(0, 6))
        self.text = tk.Text(right, bg=C_BG, fg=C_TEXT, font=("Segoe UI", 11), wrap="word", bd=0,
                            highlightthickness=0, padx=4, pady=4)
        self.text.pack(expand=True, fill="both")

        buttons = tk.Frame(right, bg=C_BG)
        buttons.pack(fill="x", pady=(8, 0))
        self.ack_button = tk.Button(buttons, text="UYARILARI ONAYLA", command=self._ack, bg="#3a1206", fg=C_ORG,
                                    activebackground=C_ORG, activeforeground=C_BG, font=("Segoe UI", 13, "bold"),
                                    relief="flat", padx=18, pady=10, cursor="hand2")
        self.close_button = tk.Button(buttons, text="KAPAT", command=self._close, bg=C_DIM, fg=C_TEXT,
                                      activebackground=C_PRI, activeforeground=C_BG, font=("Segoe UI", 13, "bold"),
                                      relief="flat", padx=18, pady=10, cursor="hand2")
        self.close_button.pack(side="right")
        self.win = win

    def _show(self, frames, title, level, text, simulated, auto_close_ms) -> None:
        try:
            if self.win is None or not self.win.winfo_exists():
                self._build()
            self._photos = [ImageTk.PhotoImage(f) for f in frames]  # referans tutulmalı
            self._frame = 0
            self.header.configure(text=f"{title} — Seviye {level} · {LEVEL_WORD[level]}",
                                  fg=_hex(LEVEL_RGB[level]) if level else C_TEXT)
            self.source.configure(text="SİMÜLASYON VERİSİ — gerçek ölçüm değildir" if simulated else "")
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.insert("end", text)
            self.text.configure(state="disabled")
            if self.on_ack and level >= 2:
                self.ack_button.pack(side="right", padx=(0, 10))
            else:
                self.ack_button.pack_forget()
            self.win.deiconify()
            self.win.lift()
            if self._anim_job is None:
                self._animate()
            if self._close_job is not None:
                self.win.after_cancel(self._close_job)
                self._close_job = None
            if auto_close_ms and level < 3:  # yüksek risk ve acil pencereler kendiliğinden kapanmaz
                self._close_job = self.win.after(auto_close_ms, self._close)
        except Exception as exc:
            self._log.warning("ASTRA hologram penceresi gösterilemedi: %s", exc)

    def _animate(self) -> None:
        if self.win is None or not self.win.winfo_exists() or not self._photos:
            self._anim_job = None
            return
        self.image_label.configure(image=self._photos[self._frame % len(self._photos)])
        self._frame += 1
        self._anim_job = self.win.after(FRAME_MS, self._animate)

    def _ack(self) -> None:
        try:
            count = self.on_ack() if self.on_ack else 0
            self.ack_button.pack_forget()
            self.source.configure(text=f"{count} uyarı onaylandı.")
        except Exception as exc:
            self._log.warning("ASTRA uyarı onayı başarısız: %s", exc)

    def _close(self) -> None:
        if self.win is not None:
            try:
                if self._anim_job is not None:
                    self.win.after_cancel(self._anim_job)
                self.win.destroy()
            except Exception:
                pass
        self.win = None
        self._anim_job = None
        self._close_job = None
        self._photos = []
