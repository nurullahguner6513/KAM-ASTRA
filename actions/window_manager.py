"""
Pencere yönetimi — Windows ctypes tabanlı
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
import time


user32 = ctypes.windll.user32


def _enum_windows() -> list[dict]:
    """Tüm görünür pencereleri listele."""
    windows = []

    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title:
                    windows.append({"hwnd": hwnd, "title": title})
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return windows


def _find_window(app_name: str) -> dict | None:
    """İsme göre pencere bul."""
    app_lower = (app_name or "").strip().lower()
    if not app_lower:
        return None
    windows = _enum_windows()
    # Tam eşleşme öncelikli
    for w in windows:
        if app_lower in w["title"].lower():
            return w
    return None


def window_control(action: str, app_name: str = "") -> str:
    action = (action or "").strip().lower()

    if action == "list":
        windows = _enum_windows()
        if not windows:
            return "Açık pencere bulunamadı."
        lines = [f"🪟 {len(windows)} açık pencere:"]
        for w in windows[:25]:
            lines.append(f"  • {w['title']}")
        if len(windows) > 25:
            lines.append(f"  ... ve {len(windows) - 25} pencere daha")
        return "\n".join(lines)

    elif action == "focus":
        w = _find_window(app_name)
        if not w:
            return f"'{app_name}' penceresi bulunamadı."
        try:
            hwnd = w["hwnd"]
            # Minimize edilmişse geri getir
            SW_RESTORE = 9
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            return f"'{w['title']}' öne getirildi."
        except Exception as e:
            return f"Pencere öne getirilemedi: {e}"

    elif action == "minimize":
        if app_name:
            w = _find_window(app_name)
            if not w:
                return f"'{app_name}' penceresi bulunamadı."
            hwnd = w["hwnd"]
        else:
            hwnd = user32.GetForegroundWindow()
        try:
            SW_MINIMIZE = 6
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            return "Pencere küçültüldü."
        except Exception as e:
            return f"Pencere küçültülemedi: {e}"

    elif action == "maximize":
        if app_name:
            w = _find_window(app_name)
            if not w:
                return f"'{app_name}' penceresi bulunamadı."
            hwnd = w["hwnd"]
        else:
            hwnd = user32.GetForegroundWindow()
        try:
            SW_MAXIMIZE = 3
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
            return "Pencere büyütüldü."
        except Exception as e:
            return f"Pencere büyütülemedi: {e}"

    elif action == "close":
        if app_name:
            w = _find_window(app_name)
            if not w:
                return f"'{app_name}' penceresi bulunamadı."
            hwnd = w["hwnd"]
        else:
            hwnd = user32.GetForegroundWindow()
        try:
            WM_CLOSE = 0x0010
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return "Pencere kapatıldı."
        except Exception as e:
            return f"Pencere kapatılamadı: {e}"

    return f"Bilinmeyen pencere eylemi: {action}. 'list', 'focus', 'minimize', 'maximize' veya 'close' kullan."
