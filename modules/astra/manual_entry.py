"""
Elle ölçüm girişi.

Otomatik veri alınamayan saatler için (ör. SK27: RDFit verisi Health Connect'e
yazılmıyor, standart Bluetooth nabız servisi yok) astronot saatin ekranında
gördüğü değeri yazarak veya söyleyerek girer. Kayıtlar source_type="MANUAL"
olarak saklanır; simülasyon verisiyle karışmaz.
"""

from __future__ import annotations

from datetime import datetime

from .models import METRICS, InvalidDataError, Measurement, _fmt_unit_free

# Normalize edilmiş ad (Türkçe karakterler sadeleştirilmiş) → ölçüm türü
ALIASES = {
    "nabiz": "heart_rate", "kalp": "heart_rate", "kalp atisi": "heart_rate", "kalp atis hizi": "heart_rate",
    "heart_rate": "heart_rate",
    "dinlenik": "resting_heart_rate", "dinlenik nabiz": "resting_heart_rate", "dinlenme nabzi": "resting_heart_rate",
    "dinlenik_nabiz": "resting_heart_rate", "resting_heart_rate": "resting_heart_rate",
    "spo2": "spo2", "oksijen": "spo2", "kan oksijeni": "spo2",
    "hrv": "hrv_rmssd", "hrv_rmssd": "hrv_rmssd",
    "tansiyon": "blood_pressure", "kan basinci": "blood_pressure", "blood_pressure": "blood_pressure",
    "sicaklik": "skin_temperature", "deri sicakligi": "skin_temperature", "skin_temperature": "skin_temperature",
    "kilo": "body_weight", "agirlik": "body_weight", "body_weight": "body_weight",
    "stres": "stress_level", "stress_level": "stress_level",
    "ruh": "mood", "ruh hali": "mood", "ruh_hali": "mood", "mood": "mood",
    "yorgunluk": "fatigue", "fatigue": "fatigue",
    "motivasyon": "motivation", "motivation": "motivation",
}
SUPPORTED_TEXT = ("nabız, dinlenik nabız, spo2, hrv, tansiyon (120/80), sıcaklık, kilo, "
                  "stres / ruh hali / yorgunluk / motivasyon (0–10)")


def normalize(text: str) -> str:
    text = (text or "").replace("İ", "i").replace("I", "ı").lower()
    for a, b in (("ı", "i"), ("ğ", "g"), ("ü", "u"), ("ş", "s"), ("ö", "o"), ("ç", "c")):
        text = text.replace(a, b)
    return " ".join(text.split())


def resolve_metric(name: str) -> str:
    key = normalize(name)
    if key in ALIASES:
        return ALIASES[key]
    first = key.split(" ")[0] if key else ""
    if first in ALIASES:
        return ALIASES[first]
    raise InvalidDataError(f"tanınmayan ölçüm: '{name}'. Desteklenenler: {SUPPORTED_TEXT}")


def parse_number(text: str) -> float:
    cleaned = (text or "").strip().replace(",", ".").strip("%").strip()  # "%97" ve "97%" kabul edilir
    try:
        return float(cleaned)
    except ValueError:
        raise InvalidDataError(f"değer sayı değil: '{text}'") from None


def build_measurements(astronaut_id: int, name: str, value_text: str, at: datetime,
                       device: str, quality: float) -> list[Measurement]:
    metric = resolve_metric(name)
    if metric == "blood_pressure":
        parts = (value_text or "").replace(" ", "").split("/")
        if len(parts) != 2:
            raise InvalidDataError("tansiyon 120/80 biçiminde girilmeli")
        pairs = (("systolic_bp", parse_number(parts[0])), ("diastolic_bp", parse_number(parts[1])))
    else:
        pairs = ((metric, parse_number(value_text)),)
    return [Measurement(astronaut_id, m, value, METRICS[m].unit, at, device, "MANUAL", quality,
                        note="elle giriş") for m, value in pairs]


def describe(records: list[Measurement]) -> str:
    """Ör. 'Nabız 72 bpm' veya 'Sistolik kan basıncı 120 mmHg, Diyastolik kan basıncı 80 mmHg'."""
    return ", ".join(f"{METRICS[r.metric].label_tr} {_fmt_unit_free(r.value)} {r.unit}" for r in records)
