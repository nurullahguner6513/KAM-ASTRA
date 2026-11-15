"""
ASTRA çekirdeği — KAM'ın kullanacağı tek giriş noktası.

evaluate() bir günü değerlendirir: analiz → risk kuralları → uyarılar → rapor,
ve sonuçları veritabanına kaydeder. Veri kipi (simülasyon / gerçek) nesne
oluşturulurken seçilir ve iki veri türü hiçbir hesapta karışmaz.
"""

from __future__ import annotations

import json
from datetime import datetime

from . import get_astra_logger
from . import health_reports
from .alert_manager import AlertManager
from .health_database import HealthDatabase
from .models import to_utc_iso, utc_now
from .radiation.radiation_analyzer import assess_radiation
from .risk_engine import RiskAssessment, RiskEngine, day_start


class AstraCore:
    def __init__(self, db: HealthDatabase | None = None, simulated: bool = True, config: dict | None = None):
        self.db = db or HealthDatabase()
        self.simulated = simulated
        self.engine = RiskEngine(self.db, simulated, config)
        self.alerts = AlertManager(self.db)
        self._log = get_astra_logger()

    def evaluate(self, astronaut_id: int, day: datetime | None = None, now: datetime | None = None,
                 live: bool = False, force_report: bool = False) -> RiskAssessment:
        """Günü değerlendirir ve kaydeder. live=True ise verinin güncelliği de denetlenir.
        force_report=True ise sonuç değişmemiş olsa da günlük rapor yazılır (gün sonu raporu)."""
        now = now or utc_now()
        day = day_start(day or now)
        assessment = self.engine.assess(astronaut_id, day, now if live else None)
        assessment.evaluated_at = now
        sim, day_key = int(self.simulated), day.strftime("%Y-%m-%d")

        # Sonuç (bulgu kodları ve seviyeleri) son kayıttan farklıysa olay ve rapor kaydedilir;
        # izleme döngüsü her dakika değerlendirme yaptığında veritabanı şişmez.
        signature = sorted((f["code"], f["level"]) for f in assessment.findings_as_dicts())
        last = self.db.query(
            "SELECT level, findings FROM health_risk_events WHERE astronaut_id = ? AND day_utc = ? "
            "AND is_simulated = ? ORDER BY id DESC LIMIT 1", (astronaut_id, day_key, sim))
        changed = not last or last[0]["level"] != assessment.level or signature != sorted(
            (f["code"], f["level"]) for f in json.loads(last[0]["findings"]))
        if changed:
            self.db.execute(
                "INSERT INTO health_risk_events(astronaut_id, day_utc, evaluated_at_utc, level, findings, "
                "is_simulated) VALUES (?, ?, ?, ?, ?, ?)",
                (astronaut_id, day_key, to_utc_iso(now), assessment.level,
                 json.dumps(assessment.findings_as_dicts(), ensure_ascii=False), sim))
        for key, base in assessment.baselines.items():
            self.db.execute(
                "INSERT OR REPLACE INTO health_baselines(astronaut_id, indicator, day_utc, median, spread, "
                "days_used, is_simulated) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (astronaut_id, key, day_key, base.median, base.spread, base.days_used, sim))

        self.alerts.process(assessment, now)
        if changed or force_report:
            self._save_report(assessment, "daily", health_reports.daily_report(assessment), now)
            if assessment.level >= 3:
                self._save_report(assessment, "emergency", health_reports.emergency_report(assessment), now)
        self._log.info("ASTRA değerlendirme: astronot=%s gün=%s seviye=%s simülasyon=%s",
                       astronaut_id, day_key, assessment.level, self.simulated)
        return assessment

    def _save_report(self, a: RiskAssessment, kind: str, content: str, now: datetime) -> None:
        self.db.execute(
            "INSERT INTO health_reports(astronaut_id, kind, day_utc, level, content, created_at_utc, "
            "is_simulated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (a.astronaut_id, kind, a.day.strftime("%Y-%m-%d"), a.level, content, to_utc_iso(now),
             int(self.simulated)))

    # ── Salt okunur sorgular (sesli asistan için) ────────────────────────
    def daily_report(self, astronaut_id: int, day: datetime | None = None) -> str:
        return health_reports.daily_report(self.engine.assess(astronaut_id, day or utc_now()))

    def period_report(self, astronaut_id: int, end_day: datetime | None = None, days: int = 7) -> str:
        return health_reports.period_report(self.engine.analyzer, astronaut_id, end_day or utc_now(), days)

    def radiation_report(self, astronaut_id: int, now: datetime | None = None) -> str:
        now = now or utc_now()
        status = assess_radiation(self.db, astronaut_id, day_start(now), self.simulated,
                                  self.engine.config["radiation"])
        return health_reports.radiation_report(status, now, self.simulated)
