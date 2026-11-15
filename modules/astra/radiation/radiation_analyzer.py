"""
Radyasyon protokol değerlendirmesi (genel sağlık kurallarından ayrı).

Veri yalnızca harici dozimetre kayıtlarından (radiation_records) gelir.
Varsayılan eşikler YER TUTUCUDUR; görev radyasyon protokolüne ve görev
doktorlarının kararına göre risk_rules.json ile değiştirilmelidir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..health_database import HealthDatabase
from ..models import parse_utc_iso

DEFAULT_RADIATION_CONFIG = {
    "mission_limit_msv": 150.0,          # görev boyunca izin verilen toplam doz
    "cumulative_attention_pct": 80.0,    # görev sınırının bu yüzdesinde SEVİYE 2
    "daily_attention_msv": 1.0,          # günlük doz bu değeri aşarsa SEVİYE 2
    "rate_alarm_usv_h": 100.0,           # sürekli doz hızı bu değeri aşarsa SEVİYE 3
    "rate_emergency_usv_h": 1000.0,      # sürekli doz hızı bu değeri aşarsa SEVİYE 4
    "sustain_samples": 3,                # "sürekli" sayılması için art arda ölçüm sayısı
    "min_quality": 0.5,
}


@dataclass
class RadiationStatus:
    has_data: bool = False
    daily_dose_msv: float | None = None
    cumulative_dose_msv: float | None = None
    pct_of_mission_limit: float | None = None
    max_rate_usv_h: float | None = None
    last_rate_usv_h: float | None = None
    last_measured_at: datetime | None = None
    source_device: str | None = None
    level: int = 0
    findings: list[dict] = field(default_factory=list)  # {code, level, message}


def _sustained(values: list[float], threshold: float, needed: int) -> bool:
    run = 0
    for value in values:
        run = run + 1 if value >= threshold else 0
        if run >= needed:
            return True
    return False


def assess_radiation(db: HealthDatabase, astronaut_id: int, day: datetime, simulated: bool,
                     config: dict | None = None) -> RadiationStatus:
    cfg = {**DEFAULT_RADIATION_CONFIG, **(config or {})}
    status = RadiationStatus()
    rows = [r for r in db.get_radiation(astronaut_id, day, day + timedelta(days=1), simulated)
            if r["quality"] >= cfg["min_quality"]]
    if not rows:
        return status

    last = rows[-1]
    previous = [r for r in db.get_radiation(astronaut_id, None, day, simulated)
                if r["quality"] >= cfg["min_quality"]]
    start_dose = previous[-1]["cumulative_dose_msv"] if previous else rows[0]["cumulative_dose_msv"]
    rates = [r["dose_rate_usv_h"] for r in rows]

    status.has_data = True
    status.daily_dose_msv = max(0.0, last["cumulative_dose_msv"] - start_dose)
    status.cumulative_dose_msv = last["cumulative_dose_msv"]
    status.pct_of_mission_limit = last["cumulative_dose_msv"] / cfg["mission_limit_msv"] * 100
    status.max_rate_usv_h = max(rates)
    status.last_rate_usv_h = last["dose_rate_usv_h"]
    status.last_measured_at = parse_utc_iso(last["measured_at_utc"])
    status.source_device = last["source_device"]

    def add(code: str, level: int, message: str) -> None:
        status.findings.append({"code": code, "level": level, "message": message})

    needed = cfg["sustain_samples"]
    if _sustained(rates, cfg["rate_emergency_usv_h"], needed):
        add("rad_rate_emergency", 4,
            f"Radyasyon doz hızı acil eşiğin üzerinde: en yüksek {status.max_rate_usv_h:.0f} µSv/saat "
            f"(eşik {cfg['rate_emergency_usv_h']:.0f}).")
    elif _sustained(rates, cfg["rate_alarm_usv_h"], needed):
        add("rad_rate_alarm", 3,
            f"Radyasyon doz hızı alarm eşiğinin üzerinde: en yüksek {status.max_rate_usv_h:.0f} µSv/saat "
            f"(eşik {cfg['rate_alarm_usv_h']:.0f}).")

    if status.pct_of_mission_limit >= 100:
        add("rad_mission_limit", 3,
            f"Görev boyunca biriken doz görev sınırını aştı: {status.cumulative_dose_msv:.1f} mSv "
            f"(sınır {cfg['mission_limit_msv']:.0f} mSv).")
    elif status.pct_of_mission_limit >= cfg["cumulative_attention_pct"]:
        add("rad_mission_limit", 2,
            f"Görev boyunca biriken doz görev sınırının yüzde {status.pct_of_mission_limit:.0f} seviyesinde.")

    if status.daily_dose_msv >= cfg["daily_attention_msv"]:
        add("rad_daily_dose", 2,
            f"Günlük radyasyon dozu {status.daily_dose_msv:.2f} mSv; günlük dikkat eşiği "
            f"{cfg['daily_attention_msv']:.2f} mSv.")

    status.level = max((f["level"] for f in status.findings), default=0)
    return status
