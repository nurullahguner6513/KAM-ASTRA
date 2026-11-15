"""
KAM Loglama Sistemi — helpers/logger.py
Dosya tabanlı loglama + konsol çıktısı
"""

from __future__ import annotations

import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def get_logger(name: str = "KAM") -> logging.Logger:
    """Modüle özel logger döndür."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Dosya handler — rotating, max 5MB * 3 yedek
    log_file = LOG_DIR / f"kam_{time.strftime('%Y%m%d')}.log"
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)

    # Konsol handler — sadece WARNING ve üstü
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_format = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_format)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def export_logs(output_path: str = "") -> str:
    """Log dosyalarını birleştirip tek bir dosyaya aktarır."""
    log_files = sorted(LOG_DIR.glob("kam_*.log"), reverse=True)
    if not log_files:
        return "Dışa aktarılacak log dosyası bulunamadı."

    if output_path:
        out = Path(output_path)
    else:
        out = Path.home() / "Desktop" / f"KAM_Logs_{time.strftime('%Y%m%d_%H%M%S')}.txt"

    combined = []
    for lf in log_files[:7]:  # Son 7 gün
        try:
            combined.append(f"\n{'=' * 60}\n{lf.name}\n{'=' * 60}\n")
            combined.append(lf.read_text(encoding="utf-8"))
        except Exception:
            combined.append(f"(Dosya okunamadı: {lf.name})")

    out.write_text("\n".join(combined), encoding="utf-8")
    return f"Loglar dışa aktarıldı: {out.name}"
