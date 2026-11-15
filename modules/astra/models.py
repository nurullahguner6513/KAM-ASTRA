"""
ASTRA veri modelleri ve giriş doğrulaması.

Her kayıt kaynağını (cihaz + kaynak türü), ölçüm zamanını (UTC), birimini,
kalitesini ve durumunu taşır. Buradaki alt/üst sınırlar tıbbi eşik DEĞİLDİR;
yalnızca fiziksel olarak imkânsız veya bozuk girişleri reddetmek içindir.
Risk eşikleri AŞAMA 3'teki kural motorunda ayrıca tanımlanır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import ClassVar

UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
SOURCE_TYPES = ("SIMULATED", "DEVICE", "MANUAL", "LAB")
STATUSES = ("ok", "suspect")
FUTURE_TOLERANCE = timedelta(minutes=5)


class InvalidDataError(ValueError):
    """Bozuk, eksik veya fiziksel olarak imkânsız veri girişi."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_utc_iso(dt: datetime) -> str:
    if not isinstance(dt, datetime) or dt.tzinfo is None:
        raise InvalidDataError("zaman damgası saat dilimi bilgisi içermiyor")
    return dt.astimezone(timezone.utc).strftime(UTC_FORMAT)


def parse_utc_iso(text: str) -> datetime:
    return datetime.strptime(text, UTC_FORMAT).replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label_tr: str
    unit: str
    min_value: float
    max_value: float


METRICS: dict[str, MetricSpec] = {
    m.key: m
    for m in (
        MetricSpec("heart_rate", "Kalp atış hızı", "bpm", 25, 250),
        MetricSpec("resting_heart_rate", "Dinlenik kalp atış hızı", "bpm", 25, 150),
        MetricSpec("hrv_rmssd", "Kalp atış hızı değişkenliği (RMSSD)", "ms", 1, 300),
        MetricSpec("spo2", "Oksijen doygunluğu", "%", 50, 100),
        MetricSpec("systolic_bp", "Sistolik kan basıncı", "mmHg", 50, 260),
        MetricSpec("diastolic_bp", "Diyastolik kan basıncı", "mmHg", 30, 160),
        MetricSpec("skin_temperature", "Deri sıcaklığı", "°C", 20, 45),
        MetricSpec("body_weight", "Vücut ağırlığı", "kg", 30, 200),
        # Astronotun kendi bildirimi (0 = hiç, 10 = çok yüksek)
        MetricSpec("stress_level", "Stres seviyesi (öz bildirim)", "puan", 0, 10),
        MetricSpec("mood", "Ruh hâli (öz bildirim)", "puan", 0, 10),
        MetricSpec("fatigue", "Yorgunluk (öz bildirim)", "puan", 0, 10),
        MetricSpec("motivation", "Motivasyon (öz bildirim)", "puan", 0, 10),
    )
}


def _number(name: str, value, low: float, high: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InvalidDataError(f"{name} sayısal değil: {value!r}")
    if not low <= value <= high:
        raise InvalidDataError(f"{name} geçerli aralığın dışında: {value} (beklenen {low}–{high})")


def _time(name: str, value: datetime, now: datetime) -> None:
    to_utc_iso(value)
    if value > now + FUTURE_TOLERANCE:
        raise InvalidDataError(f"{name} gelecekte: {to_utc_iso(value)}")


def _source(astronaut_id, source_device, source_type, quality) -> None:
    if not isinstance(astronaut_id, int) or astronaut_id <= 0:
        raise InvalidDataError(f"geçersiz astronot kimliği: {astronaut_id!r}")
    if not isinstance(source_device, str) or not source_device.strip():
        raise InvalidDataError("kaynak cihaz belirtilmemiş")
    if source_type not in SOURCE_TYPES:
        raise InvalidDataError(f"bilinmeyen kaynak türü: {source_type!r}")
    _number("veri kalitesi", quality, 0.0, 1.0)


@dataclass
class Measurement:
    """Tek değerli ölçüm (kalp atışı, SpO2, stres bildirimi vb.)."""

    table: ClassVar[str] = "health_measurements"

    astronaut_id: int
    metric: str
    value: float
    unit: str
    measured_at: datetime
    source_device: str
    source_type: str
    quality: float = 1.0
    status: str = "ok"
    note: str = ""

    def validate(self, now: datetime | None = None) -> None:
        _source(self.astronaut_id, self.source_device, self.source_type, self.quality)
        spec = METRICS.get(self.metric)
        if spec is None:
            raise InvalidDataError(f"bilinmeyen ölçüm türü: {self.metric!r}")
        if self.unit != spec.unit:
            raise InvalidDataError(f"{self.metric} için birim {spec.unit!r} olmalı, gelen {self.unit!r}")
        if self.status not in STATUSES:
            raise InvalidDataError(f"bilinmeyen ölçüm durumu: {self.status!r}")
        _number(spec.label_tr, self.value, spec.min_value, spec.max_value)
        _time("ölçüm zamanı", self.measured_at, now or utc_now())

    def row(self) -> dict:
        return {
            "astronaut_id": self.astronaut_id,
            "metric": self.metric,
            "value": float(self.value),
            "unit": self.unit,
            "measured_at_utc": to_utc_iso(self.measured_at),
            "source_device": self.source_device,
            "source_type": self.source_type,
            "quality": float(self.quality),
            "status": self.status,
            "note": self.note,
        }


@dataclass
class SleepRecord:
    table: ClassVar[str] = "sleep_records"

    astronaut_id: int
    start: datetime
    end: datetime
    deep_min: float
    rem_min: float
    light_min: float
    awake_min: float
    source_device: str
    source_type: str
    quality_score: float | None = None  # cihazın verdiği 0–100 uyku puanı
    quality: float = 1.0

    @property
    def total_sleep_min(self) -> float:
        return self.deep_min + self.rem_min + self.light_min

    def validate(self, now: datetime | None = None) -> None:
        _source(self.astronaut_id, self.source_device, self.source_type, self.quality)
        now = now or utc_now()
        _time("uyku başlangıcı", self.start, now)
        _time("uyku bitişi", self.end, now)
        span_min = (self.end - self.start).total_seconds() / 60
        if span_min <= 0 or span_min > 24 * 60:
            raise InvalidDataError(f"geçersiz uyku aralığı: {span_min:.0f} dk")
        for name, value in (("derin uyku", self.deep_min), ("REM", self.rem_min),
                            ("hafif uyku", self.light_min), ("uyanık süre", self.awake_min)):
            _number(name, value, 0, 24 * 60)
        if self.total_sleep_min + self.awake_min > span_min + 1:
            raise InvalidDataError("uyku evrelerinin toplamı uyku aralığından uzun")
        if self.quality_score is not None:
            _number("uyku puanı", self.quality_score, 0, 100)

    def row(self) -> dict:
        return {
            "astronaut_id": self.astronaut_id,
            "start_utc": to_utc_iso(self.start),
            "end_utc": to_utc_iso(self.end),
            "deep_min": float(self.deep_min),
            "rem_min": float(self.rem_min),
            "light_min": float(self.light_min),
            "awake_min": float(self.awake_min),
            "quality_score": self.quality_score,
            "source_device": self.source_device,
            "source_type": self.source_type,
            "quality": float(self.quality),
        }


@dataclass
class ActivityRecord:
    """Bir UTC gününün aktivite özeti."""

    table: ClassVar[str] = "activity_records"

    astronaut_id: int
    day: datetime  # günün 00:00 UTC başlangıcı
    steps: int
    active_min: float
    exercise_min: float
    longest_sedentary_min: float
    source_device: str
    source_type: str
    quality: float = 1.0

    def validate(self, now: datetime | None = None) -> None:
        _source(self.astronaut_id, self.source_device, self.source_type, self.quality)
        _time("aktivite günü", self.day, now or utc_now())
        _number("adım sayısı", self.steps, 0, 200_000)
        for name, value in (("hareket süresi", self.active_min), ("egzersiz süresi", self.exercise_min),
                            ("en uzun hareketsizlik", self.longest_sedentary_min)):
            _number(name, value, 0, 24 * 60)

    def row(self) -> dict:
        return {
            "astronaut_id": self.astronaut_id,
            "day_utc": to_utc_iso(self.day)[:10],
            "steps": int(self.steps),
            "active_min": float(self.active_min),
            "exercise_min": float(self.exercise_min),
            "longest_sedentary_min": float(self.longest_sedentary_min),
            "source_device": self.source_device,
            "source_type": self.source_type,
            "quality": float(self.quality),
        }


@dataclass
class RadiationRecord:
    """Harici dozimetre ölçümü. Akıllı saatten gelmez."""

    table: ClassVar[str] = "radiation_records"

    astronaut_id: int
    measured_at: datetime
    dose_rate_usv_h: float       # anlık doz hızı, µSv/saat
    cumulative_dose_msv: float   # görev boyunca biriken doz, mSv
    source_device: str
    source_type: str
    quality: float = 1.0

    def validate(self, now: datetime | None = None) -> None:
        _source(self.astronaut_id, self.source_device, self.source_type, self.quality)
        _time("ölçüm zamanı", self.measured_at, now or utc_now())
        _number("doz hızı", self.dose_rate_usv_h, 0, 1_000_000)
        _number("biriken doz", self.cumulative_dose_msv, 0, 100_000)

    def row(self) -> dict:
        return {
            "astronaut_id": self.astronaut_id,
            "measured_at_utc": to_utc_iso(self.measured_at),
            "dose_rate_usv_h": float(self.dose_rate_usv_h),
            "cumulative_dose_msv": float(self.cumulative_dose_msv),
            "source_device": self.source_device,
            "source_type": self.source_type,
            "quality": float(self.quality),
        }


def _fmt_unit_free(value: float) -> str:
    """Tam sayıları ondalıksız, diğerlerini tek ondalıkla yazar."""
    return f"{value:.0f}" if float(value).is_integer() else f"{value:.1f}"
