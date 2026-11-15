"""
KAM ASTRA — Astronaut Health Intelligence System.

KAM'a eklenen bağımsız sağlık modülü. Yalnızca Python standart kütüphanesini
kullanır; internet bağlantısı gerektirmez.
"""

from __future__ import annotations

import logging
import os


def get_astra_logger() -> logging.Logger:
    """KAM'ın dosya logger'ını kullanır; KAM dışında veya testlerde standart logger'a düşer."""
    if os.environ.get("ASTRA_DISABLE_FILE_LOG"):
        return logging.getLogger("ASTRA")
    try:
        from helpers.logger import get_logger

        return get_logger("ASTRA")
    except Exception:
        return logging.getLogger("ASTRA")
