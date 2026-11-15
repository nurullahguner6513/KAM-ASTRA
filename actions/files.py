"""
Dosya yönetimi — Windows PowerShell tabanlı
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


_USER_HOME = Path.home()
_KNOWN_FOLDERS = {
    "masaüstü": _USER_HOME / "Desktop",
    "masaustu": _USER_HOME / "Desktop",
    "desktop": _USER_HOME / "Desktop",
    "indirmeler": _USER_HOME / "Downloads",
    "downloads": _USER_HOME / "Downloads",
    "belgeler": _USER_HOME / "Documents",
    "documents": _USER_HOME / "Documents",
    "resimler": _USER_HOME / "Pictures",
    "pictures": _USER_HOME / "Pictures",
    "müzik": _USER_HOME / "Music",
    "muzik": _USER_HOME / "Music",
    "music": _USER_HOME / "Music",
    "videolar": _USER_HOME / "Videos",
    "videos": _USER_HOME / "Videos",
}


def _resolve_path(path: str) -> Path:
    path = (path or "").strip()
    if not path:
        return _USER_HOME / "Desktop"
    lower = path.lower()
    if lower in _KNOWN_FOLDERS:
        return _KNOWN_FOLDERS[lower]
    p = Path(path)
    if p.is_absolute():
        return p
    return _USER_HOME / path


def file_manager(action: str, query: str = "", path: str = "") -> str:
    action = (action or "").strip().lower()

    if action == "list":
        target = _resolve_path(path)
        if not target.exists():
            return f"Klasör bulunamadı: {target}"
        if not target.is_dir():
            return f"Bu bir klasör değil: {target}"
        try:
            items = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            if not items:
                return f"{target.name} klasörü boş."
            lines = [f"📂 {target.name} — {len(items)} öğe:"]
            for item in items[:50]:
                if item.is_dir():
                    lines.append(f"  📁 {item.name}/")
                else:
                    size = item.stat().st_size
                    if size < 1024:
                        sz = f"{size} B"
                    elif size < 1048576:
                        sz = f"{size/1024:.1f} KB"
                    else:
                        sz = f"{size/1048576:.1f} MB"
                    lines.append(f"  📄 {item.name}  ({sz})")
            if len(items) > 50:
                lines.append(f"  ... ve {len(items) - 50} öğe daha")
            return "\n".join(lines)
        except PermissionError:
            return f"Erişim izni yok: {target}"
        except Exception as e:
            return f"Klasör listelenirken hata: {e}"

    elif action == "search":
        if not query:
            return "Arama sorgusu belirtilmedi."
        target = _resolve_path(path)
        if not target.exists():
            return f"Arama klasörü bulunamadı: {target}"
        try:
            pattern = query if "*" in query or "?" in query else f"*{query}*"
            results = list(target.rglob(pattern))[:30]
            if not results:
                return f"'{query}' ile eşleşen dosya bulunamadı."
            lines = [f"🔍 '{query}' araması — {len(results)} sonuç:"]
            for r in results:
                rel = r.relative_to(target) if r.is_relative_to(target) else r
                icon = "📁" if r.is_dir() else "📄"
                lines.append(f"  {icon} {rel}")
            return "\n".join(lines)
        except Exception as e:
            return f"Arama hatası: {e}"

    elif action == "open":
        target = _resolve_path(path or query)
        if not target.exists():
            return f"Dosya/klasör bulunamadı: {target}"
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
            return f"Açıldı: {target.name}"
        except Exception as e:
            return f"Açılamadı: {e}"

    elif action == "info":
        target = _resolve_path(path or query)
        if not target.exists():
            return f"Dosya bulunamadı: {target}"
        try:
            stat = target.stat()
            size = stat.st_size
            if size < 1024:
                sz = f"{size} B"
            elif size < 1048576:
                sz = f"{size/1024:.1f} KB"
            elif size < 1073741824:
                sz = f"{size/1048576:.1f} MB"
            else:
                sz = f"{size/1073741824:.2f} GB"
            import time
            mod_time = time.strftime("%d.%m.%Y %H:%M", time.localtime(stat.st_mtime))
            is_dir = "Klasör" if target.is_dir() else "Dosya"
            return f"{is_dir}: {target.name}\nBoyut: {sz}\nSon değişiklik: {mod_time}\nYol: {target}"
        except Exception as e:
            return f"Dosya bilgisi alınamadı: {e}"

    return f"Bilinmeyen dosya eylemi: {action}. 'list', 'search', 'open' veya 'info' kullan."
