"""
Hızlı not sistemi — JSON tabanlı dahili not defteri
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_FILE = BASE_DIR / "memory" / "notes.json"


def _load_notes() -> list[dict]:
    try:
        if NOTES_FILE.exists():
            data = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_notes(notes: list[dict]) -> None:
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    NOTES_FILE.write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")


def quick_note(action: str, content: str = "", note_id: str = "") -> str:
    action = (action or "").strip().lower()

    if action == "add":
        if not content:
            return "Not içeriği boş olamaz."
        note = {
            "id": f"note-{int(dt.datetime.now().timestamp() * 1000)}",
            "content": content.strip(),
            "created_at": dt.datetime.now().isoformat(timespec="minutes"),
        }
        notes = _load_notes()
        notes.append(note)
        _save_notes(notes)
        return f"Not kaydedildi: {content.strip()[:60]}"

    elif action in ("list", "listele", "göster", "goster"):
        notes = _load_notes()
        if not notes:
            return "Kayıtlı not yok."
        lines = [f"📝 {len(notes)} not:"]
        for n in notes[-15:]:
            created = n.get("created_at", "?")[:16].replace("T", " ")
            text = n.get("content", "")[:80]
            lines.append(f"  [{created}] {text}")
        return "\n".join(lines)

    elif action in ("delete", "sil"):
        notes = _load_notes()
        if not notes:
            return "Silinecek not yok."
        if note_id:
            found = [n for n in notes if n.get("id") == note_id]
            if not found:
                return "Belirtilen ID ile not bulunamadı."
            notes = [n for n in notes if n.get("id") != note_id]
            _save_notes(notes)
            return "Not silindi."
        if content:
            target = content.strip().lower()
            original_count = len(notes)
            notes = [n for n in notes if target not in n.get("content", "").lower()]
            if len(notes) == original_count:
                return "Eşleşen not bulunamadı."
            _save_notes(notes)
            return f"{original_count - len(notes)} not silindi."
        # Son notu sil
        removed = notes.pop()
        _save_notes(notes)
        return f"Son not silindi: {removed.get('content', '')[:60]}"

    elif action in ("clear", "temizle"):
        _save_notes([])
        return "Tüm notlar temizlendi."

    return f"Bilinmeyen not eylemi: {action}. 'add', 'list', 'delete' veya 'clear' kullan."
