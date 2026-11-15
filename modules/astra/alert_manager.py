"""
ASTRA uyarı yöneticisi.

Risk değerlendirmesindeki bulguları uyarıya çevirir ve şu kuralları uygular:
- Aynı uyarı, onaylanmamışken yeniden oluşturulmaz.
- Onaylanan uyarı bekleme süresi dolmadan yeniden açılmaz; seviye yükselirse açılır.
- Onaylanmayan kritik uyarılar (seviye 3 ve 4) belirli aralıklarla yeniden bildirilir.
- Sessize alma yalnızca seviye 1 ve 2'yi susturur; kritik uyarılar her zaman bildirilir.
- Bildirim sırası önceliğe göredir: önce en yüksek seviye.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .health_database import HealthDatabase
from .models import parse_utc_iso, to_utc_iso
from .risk_engine import Finding, RiskAssessment

CRITICAL_LEVEL = 3
RENOTIFY_MINUTES = {3: 15, 4: 2}             # onaylanmayan kritik uyarının tekrar aralığı
COOLDOWN_HOURS = {1: 24, 2: 12, 3: 4, 4: 0.5}  # onaydan sonra aynı uyarının yeniden açılmama süresi

LEVEL_NAMES = {0: "NORMAL", 1: "BİLGİLENDİRME", 2: "DİKKAT", 3: "YÜKSEK RİSK", 4: "ACİL"}
_PREFIX = {1: "Bilgi.", 2: "Dikkat.", 3: "Uyarı, yüksek risk.", 4: "Acil durum."}
_ACTION = {
    1: "",
    2: "Ölçümü yeniden değerlendirmeni öneririm.",
    3: "Kendini kötü hissediyorsan veya değişim sürüyorsa görev sağlık protokolünü başlat.",
    4: "Ölçümünü hemen doğrula ve acil görev sağlık protokolünü uygula.",
}


def spoken_text(finding: Finding, simulated: bool) -> str:
    """Sesli ve görsel uyarı metni. Teşhis içermez; yalnızca bulguyu ve önerilen adımı söyler."""
    parts = ["Simülasyon." if simulated else "", _PREFIX[finding.level], finding.message]
    if finding.category != "data":
        parts.append(_ACTION[finding.level])
    return " ".join(p for p in parts if p)


class AlertManager:
    def __init__(self, db: HealthDatabase, muted: bool = False):
        self.db = db
        self.muted = muted

    def process(self, assessment: RiskAssessment, now: datetime) -> list[dict]:
        """Bulgulardan yeni veya seviyesi yükselen uyarıları oluşturur ve döndürür."""
        changed = []
        sim = int(assessment.is_simulated)
        for finding in assessment.findings + assessment.data_findings:
            if finding.level < 1:
                continue
            message = spoken_text(finding, assessment.is_simulated)
            open_alert = self.db.query(
                "SELECT * FROM health_alerts WHERE astronaut_id = ? AND code = ? AND is_simulated = ? "
                "AND acknowledged_at_utc IS NULL ORDER BY id DESC LIMIT 1",
                (assessment.astronaut_id, finding.code, sim))
            if open_alert:
                if finding.level > open_alert[0]["level"]:  # seviye yükseldi: güncelle ve yeniden bildir
                    self.db.execute(
                        "UPDATE health_alerts SET level = ?, message = ?, last_notified_at_utc = NULL WHERE id = ?",
                        (finding.level, message, open_alert[0]["id"]))
                    changed.append(self._get(open_alert[0]["id"]))
                continue
            last_ack = self.db.query(
                "SELECT * FROM health_alerts WHERE astronaut_id = ? AND code = ? AND is_simulated = ? "
                "AND acknowledged_at_utc IS NOT NULL ORDER BY acknowledged_at_utc DESC, id DESC LIMIT 1",
                (assessment.astronaut_id, finding.code, sim))
            if last_ack and finding.level <= last_ack[0]["level"]:
                cooldown = timedelta(hours=COOLDOWN_HOURS[last_ack[0]["level"]])
                if now - parse_utc_iso(last_ack[0]["acknowledged_at_utc"]) < cooldown:
                    continue
            alert_id = self.db.execute(
                "INSERT INTO health_alerts(astronaut_id, code, category, level, message, created_at_utc, "
                "is_simulated) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (assessment.astronaut_id, finding.code, finding.category, finding.level, message,
                 to_utc_iso(now), sim))
            changed.append(self._get(alert_id))
        return changed

    def _get(self, alert_id: int) -> dict:
        return self.db.query("SELECT * FROM health_alerts WHERE id = ?", (alert_id,))[0]

    def active(self, astronaut_id: int) -> list[dict]:
        """Onay bekleyen uyarılar, öncelik sırasıyla."""
        return self.db.query(
            "SELECT * FROM health_alerts WHERE astronaut_id = ? AND acknowledged_at_utc IS NULL "
            "ORDER BY level DESC, created_at_utc, id", (astronaut_id,))

    def due_notifications(self, astronaut_id: int, now: datetime) -> list[dict]:
        """Şimdi seslendirilmesi gereken uyarıları döndürür ve bildirildi olarak işaretler."""
        due = []
        for alert in self.active(astronaut_id):
            critical = alert["level"] >= CRITICAL_LEVEL
            if self.muted and not critical:
                continue
            last = alert["last_notified_at_utc"]
            if last is not None:
                if not critical:
                    continue
                if now - parse_utc_iso(last) < timedelta(minutes=RENOTIFY_MINUTES[alert["level"]]):
                    continue
            self.db.execute(
                "UPDATE health_alerts SET last_notified_at_utc = ?, notify_count = notify_count + 1 WHERE id = ?",
                (to_utc_iso(now), alert["id"]))
            due.append(self._get(alert["id"]))
        return due

    def acknowledge(self, alert_id: int, now: datetime) -> bool:
        rows = self.db.query("SELECT acknowledged_at_utc FROM health_alerts WHERE id = ?", (alert_id,))
        if not rows or rows[0]["acknowledged_at_utc"] is not None:
            return False
        self.db.execute("UPDATE health_alerts SET acknowledged_at_utc = ? WHERE id = ?",
                        (to_utc_iso(now), alert_id))
        return True
