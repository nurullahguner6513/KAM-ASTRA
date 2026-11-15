"""
ASTRA sağlık raporları — şablon tabanlı Türkçe metinler.

Metinler yalnızca veritabanındaki veriden ve risk motorunun bulgularından
üretilir; veri yoksa bu açıkça söylenir. İleride dil modeli bu metinleri
yalnızca daha doğal bir dille yeniden ifade edebilir, içerik ekleyemez.
"""

from __future__ import annotations

import json
from datetime import datetime

from .alert_manager import LEVEL_NAMES
from .health_analyzer import INDICATORS, HealthAnalyzer
from .models import to_utc_iso
from .radiation.radiation_analyzer import RadiationStatus
from .risk_engine import RiskAssessment, _fmt

DISCLAIMER = "Bu değerlendirme tıbbi teşhis değildir."
SIM_BANNER = "[SİMÜLASYON VERİSİ — gerçek ölçüm değildir]"


def _banner(simulated: bool) -> list[str]:
    return [SIM_BANNER] if simulated else []


def daily_report(a: RiskAssessment) -> str:
    lines = _banner(a.is_simulated)
    lines.append(f"{a.day:%d.%m.%Y} günlük sağlık değerlendirmesi — Seviye {a.level} ({LEVEL_NAMES[a.level]})")

    if not a.summary.values and not a.radiation.has_data:
        lines.append("Bu gün için kayıtlı sağlık verisi yok; değerlendirme yapılamadı.")
        return "\n".join(lines)

    if a.findings:
        lines.append("Bulgular:")
        lines += [f"- {f.message}" for f in sorted(a.findings, key=lambda f: -f.level)]
    elif a.baselines:
        lines.append("Değerlendirilen göstergeler kişisel referans aralığında.")
    else:
        lines.append("Kişisel referans oluşmadığı için karşılaştırma yapılamadı.")

    lines.append("Ölçümler:")
    for key, ind in INDICATORS.items():
        if key not in a.summary.values:
            lines.append(f"- {ind.label_tr}: veri yok")
            continue
        text = f"- {ind.label_tr}: {_fmt(a.summary.values[key])} {ind.unit}"
        if key in a.baselines:
            text += f" (kişisel referans {_fmt(a.baselines[key].median)} {ind.unit})"
        lines.append(text)
    lines.append("- " + radiation_report(a.radiation, a.evaluated_at, banner=False))

    if a.data_findings:
        lines.append("Veri notları:")
        lines += [f"- {f.message}" for f in a.data_findings]
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def radiation_report(status: RadiationStatus, now: datetime | None = None, simulated: bool = False,
                     banner: bool = True) -> str:
    prefix = (SIM_BANNER + " ") if banner and simulated else ""
    if not status.has_data:
        return prefix + "Radyasyon: dozimetre verisi yok."
    text = (f"Radyasyon: görev boyunca biriken doz {status.cumulative_dose_msv:.2f} mSv, görev sınırının "
            f"yüzde {status.pct_of_mission_limit:.0f} seviyesinde. Günlük doz {status.daily_dose_msv:.2f} mSv, "
            f"son doz hızı {status.last_rate_usv_h:.0f} µSv/saat.")
    if now is not None and status.last_measured_at is not None:
        age = int((now - status.last_measured_at).total_seconds() // 60)
        text += f" Son ölçüm {age} dakika önce alındı."
    return prefix + text


def period_report(analyzer: HealthAnalyzer, astronaut_id: int, end_day: datetime, days: int = 7) -> str:
    comparison = analyzer.period_comparison(astronaut_id, end_day, days)
    lines = _banner(analyzer.simulated)
    lines.append(f"Son {days} günün bir önceki {days} günle karşılaştırması ({end_day:%d.%m.%Y} itibarıyla)")
    if not comparison:
        lines.append("Bu dönem için kayıtlı sağlık verisi yok.")
        return "\n".join(lines)
    for key, ind in INDICATORS.items():
        entry = comparison.get(key)
        if entry is None:
            lines.append(f"- {ind.label_tr}: veri yok")
        elif entry["pct_change"] is None:
            lines.append(f"- {ind.label_tr}: ortalama {_fmt(entry['recent_mean'])} {ind.unit} "
                         f"({entry['recent_days']} gün); önceki dönem verisi olmadığı için karşılaştırılamadı")
        else:
            change = entry["pct_change"]
            word = "değişmedi" if abs(change) < 1 else ("arttı" if change > 0 else "azaldı")
            lines.append(f"- {ind.label_tr}: ortalama {_fmt(entry['recent_mean'])} {ind.unit}, önceki dönem "
                         f"{_fmt(entry['previous_mean'])} {ind.unit} (yüzde {change:+.0f}, {word})")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def emergency_report(a: RiskAssessment) -> str:
    """Görev sağlık ekibine iletilmek üzere yapılandırılmış rapor (seviye 3 ve 4)."""
    payload = {
        "report_type": "ASTRA_MEDICAL_ALERT",
        "data_source": "SIMULATED" if a.is_simulated else "REAL",
        "astronaut_id": a.astronaut_id,
        "day_utc": a.day.strftime("%Y-%m-%d"),
        "evaluated_at_utc": to_utc_iso(a.evaluated_at) if a.evaluated_at else None,
        "risk_level": a.level,
        "risk_level_name": LEVEL_NAMES[a.level],
        "findings": [f.__dict__ for f in a.findings],
        "data_quality_notes": [f.message for f in a.data_findings],
        "daily_values": {k: round(v, 2) for k, v in a.summary.values.items()},
        "personal_baselines": {k: {"median": round(b.median, 2), "days_used": b.days_used}
                               for k, b in a.baselines.items()},
        "radiation": {
            "daily_dose_msv": a.radiation.daily_dose_msv,
            "cumulative_dose_msv": a.radiation.cumulative_dose_msv,
            "pct_of_mission_limit": a.radiation.pct_of_mission_limit,
            "max_rate_usv_h": a.radiation.max_rate_usv_h,
        },
        "note": "Otomatik kural tabanlı değerlendirme; tıbbi teşhis değildir.",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
