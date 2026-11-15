"""
Sağlık verisi simülatörü.

Gerçek akıllı saat ve dozimetre bağlanana kadar test verisi üretir. Ürettiği
her kayıt source_type = "SIMULATED" taşır ve cihaz adları "SIM-" ile başlar;
gerçek ölçümlerle karışmaz. Aynı tohum (seed) aynı veriyi üretir.

Komut satırı (KAM klasöründen):
    python -m modules.astra.simulation.health_simulator --days 30 --scenario multi_risk --scenario-days 3
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..health_database import HealthDatabase, StoreResult
from ..models import METRICS, ActivityRecord, Measurement, RadiationRecord, SleepRecord, utc_now
from .mission_scenarios import SCENARIOS, Scenario

SIMULATED = "SIMULATED"
SIM_WATCH = "SIM-WATCH-01"
SIM_DOSIMETER = "SIM-DOSIMETER-01"
SIM_SELF_REPORT = "SIM-SELF-REPORT"

BASE_SLEEP_HOURS = 7.5
WAKE_HOUR = 6.0
BASE_DOSE_RATE_USV_H = 20.0  # test amaçlı temsili değer


@dataclass
class SimulatedDay:
    day: datetime
    scenario: str
    records: list = field(default_factory=list)
    device_events: list[tuple[str, str, str, datetime]] = field(default_factory=list)  # ad, tür, durum, zaman

    def of_type(self, cls) -> list:
        return [r for r in self.records if isinstance(r, cls)]

    def metric(self, name: str) -> list[Measurement]:
        return [r for r in self.records if isinstance(r, Measurement) and r.metric == name]


class HealthSimulator:
    def __init__(self, astronaut_id: int, seed: int = 42, cumulative_dose_msv: float = 0.0):
        self.astronaut_id = astronaut_id
        self.seed = seed
        self.cumulative_dose_msv = cumulative_dose_msv

    def _measure(self, metric: str, value: float, at: datetime, device: str = SIM_WATCH,
                 quality: float = 0.95, status: str = "ok", note: str = "") -> Measurement:
        return Measurement(self.astronaut_id, metric, round(value, 1), METRICS[metric].unit, at,
                           device, SIMULATED, quality, status, note)

    def generate_day(self, day: datetime, scenario: str | Scenario = "normal") -> SimulatedDay:
        """day: günün 00:00 UTC başlangıcı (saat dilimi bilgili)."""
        spec = scenario if isinstance(scenario, Scenario) else SCENARIOS[scenario]
        day = day.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        rng = random.Random(f"{self.seed}|{day.date().isoformat()}|{spec.name}")
        out = SimulatedDay(day, spec.name)
        gap = spec.gap_hours

        def at(hour: float) -> datetime:
            return day + timedelta(hours=hour)

        def watch_online(hour: float) -> bool:
            return gap is None or not gap[0] <= hour < gap[1]

        def wanted(metric: str) -> bool:
            return metric not in spec.drop_metrics

        # Kalp atış hızı: 10 dakikada bir
        if wanted("heart_rate"):
            for i in range(144):
                hour = i / 6
                if not watch_online(hour):
                    continue
                base = 60 if hour < WAKE_HOUR else 72
                if spec.exercise and 17 <= hour < 18:
                    base += 50
                out.records.append(self._measure("heart_rate", base + spec.hr_offset + rng.gauss(0, 3), at(hour)))

        # Sabah ölçümleri: dinlenik kalp atışı ve HRV
        if wanted("resting_heart_rate"):
            out.records.append(self._measure(
                "resting_heart_rate", 58 + spec.resting_hr_offset + rng.gauss(0, 1.5), at(WAKE_HOUR)))
        if wanted("hrv_rmssd"):
            out.records.append(self._measure("hrv_rmssd", 55 * spec.hrv_factor + rng.gauss(0, 4), at(WAKE_HOUR)))

        # SpO2: 30 dakikada bir
        if wanted("spo2"):
            for i in range(48):
                hour = i / 2
                if watch_online(hour):
                    value = min(100.0, 97 + spec.spo2_offset + rng.gauss(0, 0.6))
                    out.records.append(self._measure("spo2", value, at(hour)))

        # Deri sıcaklığı: saatte bir
        if wanted("skin_temperature"):
            for hour in range(24):
                if watch_online(hour):
                    out.records.append(self._measure("skin_temperature", 33.5 + rng.gauss(0, 0.3), at(hour)))

        # Stres öz bildirimi: akşam bir kez
        if wanted("stress_level"):
            stress = min(10.0, max(0.0, spec.stress_level + rng.gauss(0, 0.5)))
            out.records.append(self._measure("stress_level", stress, at(20), SIM_SELF_REPORT, quality=1.0))

        # Uyku: sabah 06:00'da biten gece uykusu
        if not spec.drop_sleep:
            duration_min = BASE_SLEEP_HOURS * 60 * spec.sleep_factor + rng.gauss(0, 10)
            end = at(WAKE_HOUR)
            out.records.append(SleepRecord(
                self.astronaut_id, end - timedelta(minutes=duration_min), end,
                deep_min=round(duration_min * 0.18, 1), rem_min=round(duration_min * 0.22, 1),
                light_min=round(duration_min * 0.55, 1), awake_min=round(duration_min * 0.04, 1),
                source_device=SIM_WATCH, source_type=SIMULATED,
                quality_score=round(min(100.0, max(0.0, 85 * spec.sleep_factor + rng.gauss(0, 3))), 1),
                quality=0.9))

        # Günlük aktivite özeti
        out.records.append(ActivityRecord(
            self.astronaut_id, day,
            steps=max(0, int(7000 * spec.steps_factor + rng.gauss(0, 300))),
            active_min=round(max(0.0, 75 * spec.steps_factor + rng.gauss(0, 5)), 1),
            exercise_min=round(max(0.0, 60 + rng.gauss(0, 5)), 1) if spec.exercise else 0.0,
            longest_sedentary_min=round(max(0.0, spec.longest_sedentary_min + rng.gauss(0, 10)), 1),
            source_device=SIM_WATCH, source_type=SIMULATED, quality=0.9))

        # Radyasyon: harici dozimetreden saatte bir; saat bağlantısından bağımsızdır
        for hour in range(24):
            rate = max(0.0, BASE_DOSE_RATE_USV_H * spec.radiation_factor + rng.gauss(0, 2))
            self.cumulative_dose_msv += rate / 1000  # 1 saatlik doz, µSv → mSv
            out.records.append(RadiationRecord(
                self.astronaut_id, at(hour), round(rate, 2), round(self.cumulative_dose_msv, 5),
                SIM_DOSIMETER, SIMULATED, quality=0.98))

        if gap is not None:
            out.device_events.append((SIM_WATCH, "smartwatch", "disconnected", at(gap[0])))
            out.device_events.append((SIM_WATCH, "smartwatch", "connected", at(gap[1])))

        if spec.faulty:
            # Fiziksel olarak imkânsız okumalar: veritabanı reddetmeli
            out.records.append(self._measure("heart_rate", 0, at(11.05), note="sensör hatası"))
            out.records.append(self._measure("heart_rate", 400, at(11.15), note="sensör hatası"))
            out.records.append(self._measure("spo2", 140, at(11.25), note="sensör hatası"))
            # Olası ama güvenilmez okumalar: kaydedilir, "suspect" olarak işaretlenir
            for minute in (35, 45, 55):
                out.records.append(self._measure("heart_rate", 185 + rng.gauss(0, 4), at(11 + minute / 60),
                                                 quality=0.2, status="suspect", note="zayıf sensör teması"))
        return out

    def generate_history(self, start_day: datetime, days: int, scenario: str = "normal",
                         scenario_days: int = 0) -> list[SimulatedDay]:
        """days günlük veri üretir; son scenario_days günü verilen senaryoyla, öncesi normal."""
        result = []
        for i in range(days):
            name = scenario if i >= days - scenario_days else "normal"
            result.append(self.generate_day(start_day + timedelta(days=i), name))
        return result


def store(db: HealthDatabase, day: SimulatedDay, now: datetime | None = None) -> StoreResult:
    """Simüle edilmiş bir günü veritabanına yazar."""
    result = db.add_many(day.records, now)
    for name, kind, status, at in day.device_events:
        db.add_device_event(name, kind, SIMULATED, status, at)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="ASTRA veritabanına SIMULATED sağlık verisi yazar.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="normal")
    parser.add_argument("--scenario-days", type=int, default=0)
    parser.add_argument("--astronaut", default="SIM Astronot")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    db = HealthDatabase()
    astronaut_id = db.add_astronaut(args.astronaut)
    today = utc_now().replace(hour=0, minute=0, second=0)
    simulator = HealthSimulator(astronaut_id, args.seed)
    total = StoreResult()
    for day in simulator.generate_history(today - timedelta(days=args.days), args.days,
                                          args.scenario, args.scenario_days):
        r = store(db, day)
        total.inserted += r.inserted
        total.duplicates += r.duplicates
        total.rejected += r.rejected
    print(f"[ASTRA] SIMULATED veri yazıldı: {db.path}")
    print(f"[ASTRA] eklenen={total.inserted} tekrar={total.duplicates} reddedilen={total.rejected}")
    db.close()


if __name__ == "__main__":
    main()
