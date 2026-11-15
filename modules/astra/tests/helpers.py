"""Testler için ortak yardımcılar. Tüm veriler SIMULATED veya açıkça test verisidir."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules.astra.astra_core import AstraCore
from modules.astra.health_database import HealthDatabase
from modules.astra.models import Measurement
from modules.astra.simulation.health_simulator import HealthSimulator, store

D0 = datetime(2025, 3, 1, tzinfo=timezone.utc)


class TempDb:
    """Geçici bir ASTRA veritabanı; with bloğu bitince silinir."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = HealthDatabase(Path(self._tmp.name) / "astra.db")
        self.aid = self.db.add_astronaut("SIM Astronot")
        return self

    def __exit__(self, *exc):
        self.db.close()
        self._tmp.cleanup()

    def simulate(self, days=31, scenario="normal", scenario_days=0):
        """D0'dan başlayarak veri üretir; son günün tarihini döndürür."""
        for day in HealthSimulator(self.aid).generate_history(D0, days, scenario, scenario_days):
            store(self.db, day)
        return D0 + timedelta(days=days - 1)

    def core(self, simulated=True, config=None):
        return AstraCore(self.db, simulated, config)

    def add_daily(self, metric, unit, values, hour=6, source_type="SIMULATED", device="SIM-WATCH-01"):
        """Her gün için tek ölçüm ekler (D0'dan başlayarak)."""
        for i, value in enumerate(values):
            self.db.add(Measurement(self.aid, metric, value, unit, D0 + timedelta(days=i, hours=hour),
                                    device, source_type))
        return D0 + timedelta(days=len(values) - 1)
