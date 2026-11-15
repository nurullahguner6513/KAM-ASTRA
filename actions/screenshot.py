"""
Ekran görüntüsü kaydetme — Windows
"""

from __future__ import annotations

import datetime
from pathlib import Path

from PIL import ImageGrab


def screenshot_save(target: str = "full", save_path: str = "") -> str:
    target = (target or "full").strip().lower()

    try:
        if target == "full":
            image = ImageGrab.grab(all_screens=True)
        else:
            # Aktif pencere
            import ctypes
            import ctypes.wintypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            rect = ctypes.wintypes.RECT()
            bbox = None
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if w > 0 and h > 0:
                    bbox = (rect.left, rect.top, rect.right, rect.bottom)
            image = ImageGrab.grab(bbox=bbox, all_screens=True)

        if save_path:
            output = Path(save_path)
        else:
            desktop = Path.home() / "Desktop"
            desktop.mkdir(exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output = desktop / f"KAM_Screenshot_{timestamp}.png"

        image.save(str(output))
        return f"Ekran görüntüsü kaydedildi: {output.name}"
    except Exception as e:
        return f"Ekran görüntüsü alınamadı: {e}"
