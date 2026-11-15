"""
KAM arayüzündeki sağlık paneli (show_health_hologram) için kısa satırlar.

Panel satırları kaydırmaz: "Etiket: değer" satırları iki sütuna bölünür, diğer
satırlar tek satır olarak çizilir. Bu yüzden metinler burada kısaltılır.
Tam rapor veritabanında (health_reports) ve sesli yanıtta yer alır.
"""

from __future__ import annotations

from datetime import datetime

from .alert_manager import LEVEL_NAMES
from .health_analyzer import INDICATORS
from .radiation.radiation_analyzer import RadiationStatus
from .risk_engine import RiskAssessment, _fmt

SHORT_LABEL = {
    "resting_hr": "Dinlenik nabız",
    "heart_rate_mean": "Ortalama nabız",
    "hrv_rmssd": "HRV",
    "spo2_mean": "SpO2",
    "skin_temp_mean": "Deri sıcaklığı",
    "sleep_total_min": "Uyku",
    "steps": "Adım",
    "longest_sedentary_min": "Hareketsizlik",
    "stress_level": "Stres (öz bildirim)",
}
RULE = "──"


def short(text: str, limit: int = 50) -> str:
    text = " ".join(text.replace(":", " -").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _value(key: str, value: float) -> str:
    if key == "sleep_total_min":
        return f"{int(value) // 60} sa {int(value) % 60} dk"
    if key == "steps":
        return f"{value:.0f}"
    return f"{_fmt(value)} {INDICATORS[key].unit}"


def _source(simulated: bool) -> str:
    return "Kaynak: SİMÜLASYON" if simulated else "Kaynak: CİHAZ"


def daily_lines(a: RiskAssessment) -> str:
    lines = [_source(a.is_simulated), f"Seviye: {a.level} · {LEVEL_NAMES[a.level]}", RULE]
    for key in INDICATORS:
        if key not in a.summary.values:
            lines.append(f"{SHORT_LABEL[key]}: veri yok")
            continue
        text = _value(key, a.summary.values[key])
        if key in a.baselines:
            text += f" (ref {_value(key, a.baselines[key].median).split(' ')[0]})"
        lines.append(f"{SHORT_LABEL[key]}: {text}")
    if a.radiation.has_data:
        lines.append(f"Radyasyon: görev sınırının %{a.radiation.pct_of_mission_limit:.0f}")
    else:
        lines.append("Radyasyon: veri yok")
    if a.findings or a.data_findings:
        lines.append(RULE)
    for f in sorted(a.findings, key=lambda f: -f.level):
        if f.indicator in INDICATORS and f.pct_change is not None:
            arrow = "▲" if f.pct_change > 0 else "▼"
            lines.append(f"{arrow} {SHORT_LABEL[f.indicator]} {f.pct_change:+.0f}% (seviye {f.level})")
        else:
            lines.append(short(f.message))
    lines += [short(f.message) for f in a.data_findings]
    return "\n".join(lines)


def period_lines(comparison: dict, days: int, simulated: bool) -> str:
    lines = [_source(simulated), f"Dönem: son {days} gün / önceki {days} gün", RULE]
    if not comparison:
        lines.append("Bu dönem için veri yok")
    for key in INDICATORS:
        entry = comparison.get(key)
        if entry is None:
            continue
        if entry["pct_change"] is None:
            lines.append(f"{SHORT_LABEL[key]}: {_value(key, entry['recent_mean'])} (önceki yok)")
        else:
            lines.append(f"{SHORT_LABEL[key]}: {_value(key, entry['recent_mean'])} ({entry['pct_change']:+.0f}%)")
    return "\n".join(lines)


def radiation_lines(status: RadiationStatus, now: datetime, simulated: bool) -> str:
    lines = [_source(simulated), RULE]
    if not status.has_data:
        return "\n".join(lines + ["Radyasyon: dozimetre verisi yok"])
    lines += [
        f"Biriken doz: {status.cumulative_dose_msv:.2f} mSv",
        f"Görev sınırı: %{status.pct_of_mission_limit:.0f}",
        f"Günlük doz: {status.daily_dose_msv:.2f} mSv",
        f"Doz hızı: {status.last_rate_usv_h:.0f} µSv/saat",
    ]
    if status.last_measured_at is not None:
        lines.append(f"Son ölçüm: {int((now - status.last_measured_at).total_seconds() // 60)} dk önce")
    lines.append(f"Seviye: {status.level} · {LEVEL_NAMES[status.level]}")
    return "\n".join(lines)


def alert_lines(alerts: list[dict]) -> str:
    lines = [f"Onay bekleyen uyarı: {len(alerts)}", RULE]
    for a in alerts:
        lines.append(f"[{LEVEL_NAMES[a['level']]}] " + short(a["message"].replace("Simülasyon. ", ""), 40))
    return "\n".join(lines)


def card_findings(a: RiskAssessment) -> list[str]:
    """Ana ekran sağlık kartı için öne çıkan bulgular (kısa)."""
    out = []
    for f in sorted(a.findings, key=lambda f: -f.level):
        if f.indicator in INDICATORS and f.pct_change is not None:
            arrow = "▲" if f.pct_change > 0 else "▼"
            out.append(f"{arrow} {SHORT_LABEL[f.indicator]} {f.pct_change:+.0f}%")
        elif f.category == "radiation":
            out.append("▲ Radyasyon eşiği")
        elif f.code == "multi_indicator":
            out.append("Çoklu gösterge değişimi")
        else:
            out.append(short(f.message, 28))
    return out


def card_values(a: RiskAssessment) -> list[str]:
    """Ana ekran sağlık kartı için günün değerleri (kısa)."""
    v = a.summary.values
    out = []
    if "resting_hr" in v:
        out.append(f"Dinlenik nabız {v['resting_hr']:.0f}")
    if "heart_rate_mean" in v:
        out.append(f"Ort. nabız {v['heart_rate_mean']:.0f} bpm")
    if "hrv_rmssd" in v:
        out.append(f"HRV {v['hrv_rmssd']:.0f} ms")
    if "spo2_mean" in v:
        out.append(f"SpO2 %{v['spo2_mean']:.0f}")
    if "sleep_total_min" in v:
        total = int(v["sleep_total_min"])
        out.append(f"Uyku {total // 60} sa {total % 60} dk")
    if "steps" in v:
        out.append(f"Adım {v['steps']:.0f}")
    if "stress_level" in v:
        out.append(f"Stres {v['stress_level']:.0f}/10")
    if a.radiation.has_data:
        out.append(f"Radyasyon %{a.radiation.pct_of_mission_limit:.0f}")
    return out or ["Bugün için sağlık verisi yok"]
