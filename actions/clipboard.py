"""
Pano (clipboard) kontrolü — Windows
"""

from __future__ import annotations

import subprocess


def clipboard_control(action: str, text: str = "") -> str:
    action = (action or "").strip().lower()

    if action == "read":
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, errors="replace", timeout=5,
            )
            content = (result.stdout or "").strip()
            if not content:
                return "Pano boş."
            if len(content) > 1000:
                content = content[:1000] + "\n... (kısaltıldı)"
            return f"Panodaki metin:\n{content}"
        except Exception as e:
            return f"Pano okunamadı: {e}"

    elif action == "write":
        if not text:
            return "Panoya kopyalanacak metin belirtilmedi."
        try:
            subprocess.run(
                ["clip"], input=text, text=True, errors="replace",
                check=True, timeout=5,
            )
            preview = text[:80] + "..." if len(text) > 80 else text
            return f"Panoya kopyalandı: {preview}"
        except Exception as e:
            return f"Panoya kopyalanamadı: {e}"

    return f"Bilinmeyen pano eylemi: {action}. 'read' veya 'write' kullan."
