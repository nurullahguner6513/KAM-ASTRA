"""
Canlı simülasyon beslemesi.

Gerçek akıllı saat yokken KAM çalıştıkça veritabanına zamanı gelmiş SIMULATED
kayıtları yazar: geçmiş günler eksikse doldurulur, bugünün kayıtları saati
geldikçe eklenir. Günlük aktivite özeti gün bitince yazılır.

Gerçek cihaz bağlandığında bu besleme kapatılır (astra_settings.json → mode).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import get_astra_logger
from ..health_analyzer import day_start
from ..health_database import HealthDatabase
from ..models import ActivityRecord, Measurement, RadiationRecord, SleepRecord, parse_utc_iso, to_utc_iso
from .health_simulator import SIMULATED, HealthSimulator
from .mission_scenarios import SCENARIOS


def available_at(record) -> datetime:
    """Kaydın 'gerçekte' cihazdan geleceği an."""
    if isinstance(record, (Measurement, RadiationRecord)):
        return record.measured_at
    if isinstance(record, SleepRecord):
        return record.end
    if isinstance(record, ActivityRecord):
        return record.day + timedelta(days=1)
    raise TypeError(type(record).__name__)


class LiveSimulationFeed:
    def __init__(self, db: HealthDatabase, astronaut_id: int, scenario: str = "normal",
                 history_days: int = 60, seed: int = 42):
        if scenario not in SCENARIOS:
            raise ValueError(f"bilinmeyen senaryo: {scenario}")
        self.db = db
        self.astronaut_id = astronaut_id
        self.scenario = scenario
        self.scenario_since: datetime | None = None  # None: senaryo yalnızca bugüne uygulanır
        self.history_days = history_days
        self.seed = seed
        self._fed_until: datetime | None = None
        self._log = get_astra_logger()

    def _scenario_for(self, day: datetime, today: datetime) -> str:
        since = self.scenario_since or today
        return self.scenario if day >= since else "normal"

    def _start_dose(self, day: datetime) -> float:
        rows = self.db.query(
            "SELECT cumulative_dose_msv FROM radiation_records WHERE astronaut_id = ? AND source_type = ? "
            "AND measured_at_utc < ? ORDER BY measured_at_utc DESC LIMIT 1",
            (self.astronaut_id, SIMULATED, to_utc_iso(day)))
        return rows[0]["cumulative_dose_msv"] if rows else 0.0

    def _initial_point(self, now: datetime) -> datetime:
        rows = self.db.query(
            "SELECT MAX(measured_at_utc) AS last FROM health_measurements WHERE astronaut_id = ? AND source_type = ?",
            (self.astronaut_id, SIMULATED))
        earliest = day_start(now) - timedelta(days=self.history_days) - timedelta(seconds=1)
        if rows and rows[0]["last"]:
            return max(parse_utc_iso(rows[0]["last"]), earliest)
        return earliest

    def update(self, now: datetime) -> int:
        """Zamanı gelmiş kayıtları yazar; eklenen kayıt sayısını döndürür."""
        start = self._fed_until or self._initial_point(now)
        if start >= now:
            return 0
        today = day_start(now)
        inserted = 0
        day = day_start(start)
        while day <= today:
            sim = HealthSimulator(self.astronaut_id, self.seed, self._start_dose(day))
            generated = sim.generate_day(day, self._scenario_for(day, today))
            batch = [r for r in generated.records if start < available_at(r) <= now]
            if batch:
                inserted += self.db.add_many(batch, now).inserted
            for name, kind, status, at in generated.device_events:
                if start < at <= now:
                    self.db.add_device_event(name, kind, SIMULATED, status, at)
            day += timedelta(days=1)
        self._fed_until = now
        return inserted

    def set_scenario(self, scenario: str, now: datetime) -> None:
        """Bugünün simülasyon verisini silip yeni senaryoyla yeniden üretir (yalnızca SIMULATED veri)."""
        if scenario not in SCENARIOS:
            raise ValueError(f"bilinmeyen senaryo: {scenario}")
        today = day_start(now)
        t, d, aid = to_utc_iso(today), to_utc_iso(today)[:10], self.astronaut_id
        for sql, value in (
            ("DELETE FROM health_measurements WHERE astronaut_id = ? AND source_type = 'SIMULATED' "
             "AND measured_at_utc >= ?", t),
            ("DELETE FROM sleep_records WHERE astronaut_id = ? AND source_type = 'SIMULATED' AND end_utc >= ?", t),
            ("DELETE FROM activity_records WHERE astronaut_id = ? AND source_type = 'SIMULATED' AND day_utc >= ?", d),
            ("DELETE FROM radiation_records WHERE astronaut_id = ? AND source_type = 'SIMULATED' "
             "AND measured_at_utc >= ?", t),
        ):
            self.db.execute(sql, (aid, value))
        self.db.execute("DELETE FROM device_connections WHERE source_type = 'SIMULATED' AND changed_at_utc >= ?", (t,))
        self.scenario = scenario
        self.scenario_since = today
        self._fed_until = today - timedelta(seconds=1)
        self._log.info("ASTRA simülasyon senaryosu değişti: %s", scenario)
        self.update(now)
