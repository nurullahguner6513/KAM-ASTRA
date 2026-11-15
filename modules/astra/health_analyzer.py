"""
ASTRA sağlık analiz motoru.

Ham kayıtlardan günlük özet çıkarır, kişisel referans değerlerini hesaplar ve
bugünü bu referansla karşılaştırır. Risk seviyesi burada belirlenmez; o iş
risk_engine.py içindeki kurallara aittir.

Kişisel referans, tıbbi "normal" anlamına gelmez: yalnızca bu astronotun son
haftalardaki tipik değeridir. Kayan pencere kullanıldığı için uzay ortamına
uyum sürecindeki kalıcı değişimler zamanla referansa yansır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import linear_regression, mean, median, pstdev

from .health_database import HealthDatabase
from .models import parse_utc_iso


@dataclass(frozen=True)
class Indicator:
    key: str
    label_tr: str
    unit: str
    group: str    # aynı gruptaki göstergeler çoklu-gösterge kuralında tek sayılır
    adverse: str  # olumsuz yön: "high", "low" veya "both"


INDICATORS: dict[str, Indicator] = {
    i.key: i
    for i in (
        Indicator("resting_hr", "Dinlenik kalp atış hızı", "bpm", "cardio_rate", "high"),
        Indicator("heart_rate_mean", "Gün içi ortalama kalp atış hızı", "bpm", "cardio_rate", "high"),
        Indicator("hrv_rmssd", "Kalp atış hızı değişkenliği", "ms", "hrv", "low"),
        Indicator("spo2_mean", "Ortalama oksijen doygunluğu", "%", "spo2", "low"),
        Indicator("skin_temp_mean", "Ortalama deri sıcaklığı", "°C", "temperature", "both"),
        Indicator("sleep_total_min", "Toplam uyku süresi", "dk", "sleep", "low"),
        Indicator("steps", "Günlük adım", "adım", "activity", "low"),
        Indicator("longest_sedentary_min", "En uzun hareketsizlik süresi", "dk", "activity", "high"),
        Indicator("stress_level", "Stres bildirimi", "puan", "stress", "high"),
    )
}

# ölçüm türü → (gösterge, günlük özetleme yöntemi)
_METRIC_TO_INDICATOR = {
    "resting_heart_rate": ("resting_hr", "last"),
    "heart_rate": ("heart_rate_mean", "mean"),
    "hrv_rmssd": ("hrv_rmssd", "mean"),
    "spo2": ("spo2_mean", "mean"),
    "skin_temperature": ("skin_temp_mean", "mean"),
    "stress_level": ("stress_level", "mean"),
}


def day_start(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass
class DaySummary:
    day: datetime
    values: dict[str, float] = field(default_factory=dict)        # gösterge → günlük değer
    counts: dict[str, int] = field(default_factory=dict)          # gösterge → geçerli örnek sayısı
    samples: dict[str, list[dict]] = field(default_factory=dict)  # ölçüm türü → geçerli ham örnekler
    excluded: int = 0                                             # şüpheli/düşük kaliteli, hesaba katılmayan
    last_sample_at: datetime | None = None
    exercise_min: float | None = None
    sleep_stages: dict[str, float] | None = None


@dataclass
class Baseline:
    median: float
    spread: float        # sağlam yayılım ölçüsü (1,4826 × MAD)
    days_used: int
    count_median: float  # günlük tipik örnek sayısı


@dataclass
class Deviation:
    value: float
    baseline: Baseline
    z: float    # (değer − medyan) / yayılım
    pct: float  # medyana göre yüzde değişim


class HealthAnalyzer:
    def __init__(self, db: HealthDatabase, simulated: bool, min_quality: float = 0.5):
        """simulated=True yalnızca SIMULATED, False yalnızca gerçek veriyi kullanır; ikisi karışmaz."""
        self.db = db
        self.simulated = simulated
        self.min_quality = min_quality

    # ── Günlük özetler ───────────────────────────────────────────────────
    def summaries(self, astronaut_id: int, first_day: datetime, days: int) -> list[DaySummary]:
        first_day = day_start(first_day)
        end = first_day + timedelta(days=days)
        out = {(first_day + timedelta(days=i)).strftime("%Y-%m-%d"): DaySummary(first_day + timedelta(days=i))
               for i in range(days)}
        grouped: dict[tuple[str, str], list[dict]] = {}

        for row in self.db.get_all_measurements(astronaut_id, first_day, end, self.simulated):
            summary = out.get(row["measured_at_utc"][:10])
            if summary is None:
                continue
            if row["status"] != "ok" or row["quality"] < self.min_quality:
                summary.excluded += 1
                continue
            grouped.setdefault((row["measured_at_utc"][:10], row["metric"]), []).append(row)
            at = parse_utc_iso(row["measured_at_utc"])
            if summary.last_sample_at is None or at > summary.last_sample_at:
                summary.last_sample_at = at

        for (day_key, metric), rows in grouped.items():
            summary = out[day_key]
            summary.samples[metric] = rows
            target = _METRIC_TO_INDICATOR.get(metric)
            if target:
                key, how = target
                values = [r["value"] for r in rows]
                summary.values[key] = values[-1] if how == "last" else mean(values)
                summary.counts[key] = len(values)

        for row in self.db.get_sleep(astronaut_id, first_day, end, self.simulated):
            summary = out.get(row["end_utc"][:10])
            if summary is None or row["quality"] < self.min_quality:
                continue
            total = row["deep_min"] + row["rem_min"] + row["light_min"]
            summary.values["sleep_total_min"] = summary.values.get("sleep_total_min", 0.0) + total
            summary.counts["sleep_total_min"] = summary.counts.get("sleep_total_min", 0) + 1
            stages = summary.sleep_stages or {"deep_min": 0.0, "rem_min": 0.0, "light_min": 0.0}
            for stage in stages:
                stages[stage] += row[stage]
            summary.sleep_stages = stages

        for row in self.db.get_activity(astronaut_id, first_day, end, self.simulated):
            summary = out.get(row["day_utc"])
            if summary is None or row["quality"] < self.min_quality:
                continue
            summary.values["steps"] = float(row["steps"])
            summary.values["longest_sedentary_min"] = row["longest_sedentary_min"]
            summary.counts["steps"] = summary.counts["longest_sedentary_min"] = 1
            summary.exercise_min = row["exercise_min"]

        return list(out.values())

    def day_summary(self, astronaut_id: int, day: datetime) -> DaySummary:
        return self.summaries(astronaut_id, day, 1)[0]

    # ── Kişisel referans ─────────────────────────────────────────────────
    @staticmethod
    def baselines(history: list[DaySummary], min_days: int, spread_floors: dict[str, float]) -> dict[str, Baseline]:
        """history: değerlendirilen günden önceki günler. Yeterli gün yoksa gösterge referanssız kalır."""
        result = {}
        for key in INDICATORS:
            values = [s.values[key] for s in history if key in s.values]
            if len(values) < min_days:
                continue
            mid = median(values)
            mad = median(abs(v - mid) for v in values)
            spread = 1.4826 * mad if mad > 0 else pstdev(values)
            counts = [s.counts[key] for s in history if key in s.counts]
            result[key] = Baseline(mid, max(spread, spread_floors.get(key, 0.0)), len(values), median(counts))
        return result

    @staticmethod
    def deviations(summary: DaySummary, baselines: dict[str, Baseline]) -> dict[str, Deviation]:
        result = {}
        for key, base in baselines.items():
            if key not in summary.values:
                continue
            value = summary.values[key]
            pct = (value - base.median) / base.median * 100 if base.median else 0.0
            result[key] = Deviation(value, base, (value - base.median) / base.spread, pct)
        return result

    # ── Dönem karşılaştırması ve eğilim ──────────────────────────────────
    def period_comparison(self, astronaut_id: int, end_day: datetime, days: int = 7,
                          min_days: int | None = None) -> dict[str, dict]:
        """Son `days` günü (end_day dahil) bir önceki `days` günle karşılaştırır.
        Bir dönemde `min_days`'ten az veri varsa yüzde değişim hesaplanmaz (varsayılan: dönemin yarısı)."""
        min_days = max(3, days // 2) if min_days is None else min_days
        first = day_start(end_day) - timedelta(days=2 * days - 1)
        all_days = self.summaries(astronaut_id, first, 2 * days)
        previous, recent = all_days[:days], all_days[days:]
        result = {}
        for key in INDICATORS:
            now_values = [s.values[key] for s in recent if key in s.values]
            old_values = [s.values[key] for s in previous if key in s.values]
            if not now_values:
                continue
            entry = {"recent_mean": mean(now_values), "recent_days": len(now_values),
                     "previous_mean": None, "previous_days": len(old_values), "pct_change": None}
            if old_values:
                entry["previous_mean"] = mean(old_values)
                if entry["previous_mean"] and len(old_values) >= min_days and len(now_values) >= min_days:
                    entry["pct_change"] = (entry["recent_mean"] - entry["previous_mean"]) / entry["previous_mean"] * 100
            result[key] = entry
        return result

    def trend(self, astronaut_id: int, end_day: datetime, days: int = 30) -> dict[str, float]:
        """Her gösterge için günlük değişim eğimi (birim/gün). En az 5 günlük veri gerekir."""
        first = day_start(end_day) - timedelta(days=days - 1)
        result = {}
        history = self.summaries(astronaut_id, first, days)
        for key in INDICATORS:
            points = [(i, s.values[key]) for i, s in enumerate(history) if key in s.values]
            if len(points) >= 5:
                result[key] = linear_regression([p[0] for p in points], [p[1] for p in points]).slope
        return result
