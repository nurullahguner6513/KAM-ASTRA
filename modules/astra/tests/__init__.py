"""ASTRA testleri. Testler KAM'ın log dosyasına yazmaz."""

import os

os.environ["ASTRA_DISABLE_FILE_LOG"] = "1"
