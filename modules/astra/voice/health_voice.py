"""
Sesli yanıt metinleri.

Ekrandaki raporlar uzun ve birimli; burada aynı bilgiden kısa, sesli okunmaya
uygun Türkçe metin üretilir. İçerik yalnızca risk motorunun bulgularından ve
veritabanındaki ölçümlerden gelir; yeni bilgi eklenmez.
"""

from __future__ import annotations

import re

from ..health_analyzer import INDICATORS
from ..health_reports import DISCLAIMER
from ..risk_engine import RiskAssessment

SPOKEN_LEVEL = {0: "normal", 1: "bilgilendirme", 2: "dikkat", 3: "yüksek risk", 4: "acil"}
_ADVICE = {
    2: "Bu değişiklikleri takip etmeni ve ölçümü yeniden değerlendirmeni öneririm.",
    3: "Kendini kötü hissediyorsan veya değişim sürüyorsa görev sağlık protokolünü başlat.",
    4: "Ölçümünü hemen doğrula ve acil görev sağlık protokolünü uygula.",
}

_UNITS = (
    (r"(\d) bpm\b", r"\1 atım/dakika"),
    (r"(\d) µSv/saat", r"\1 mikrosievert/saat"),
    (r"(\d) mSv\b", r"\1 milisievert"),
    (r"(\d) ms\b", r"\1 milisaniye"),
    (r"(\d) °C", r"\1 derece"),
    (r"(\d) dk\b", r"\1 dakika"),
    (r"(\d+(?:,\d+)?) %", r"yüzde \1"),
)


def to_speech(text: str) -> str:
    """Ekran metnini seslendirmeye uygun hâle getirir (ondalık virgül, birimlerin okunuşu)."""
    text = text.replace("[SİMÜLASYON VERİSİ — gerçek ölçüm değildir]", "Simülasyon verisi.")
    text = re.sub(r"(\d)\.(\d)", r"\1,\2", text)
    for pattern, repl in _UNITS:
        text = re.sub(pattern, repl, text)
    text = text.replace("yüzde +", "yüzde artı ").replace("yüzde -", "yüzde eksi ")
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    return text


def spoken_daily(a: RiskAssessment) -> str:
    parts = ["Simülasyon verisi." if a.is_simulated else ""]
    if not a.summary.values and not a.radiation.has_data:
        parts.append("Bugün için kayıtlı sağlık verisi yok; değerlendirme yapamıyorum.")
        return to_speech(" ".join(p for p in parts if p))

    parts.append(f"Bugünkü sağlık değerlendirmen seviye {a.level}, {SPOKEN_LEVEL[a.level]}.")
    findings = sorted(a.findings, key=lambda f: -f.level)
    if findings:
        parts += [f.message for f in findings[:3]]
        if len(findings) > 3:
            parts.append(f"Toplam {len(findings)} bulgu var, ayrıntılar ekranda.")
    elif a.baselines:
        parts.append("Değerlendirilen göstergeler kişisel referans aralığında.")
    else:
        parts.append("Kişisel referans henüz oluşmadığı için karşılaştırma yapamadım.")
    parts += [f.message for f in a.data_findings[:2]]
    if a.level >= 2:
        parts.append(_ADVICE[a.level])
    parts.append(DISCLAIMER)
    return to_speech(" ".join(p for p in parts if p))


def spoken_period(comparison: dict, days: int, simulated: bool, thresholds: dict) -> str:
    """thresholds: gösterge → 'kayda değer' sayılacak en az yüzde değişim."""
    parts = ["Simülasyon verisi." if simulated else ""]
    if not comparison:
        parts.append(f"Son {days} gün için kayıtlı sağlık verisi yok.")
        return to_speech(" ".join(p for p in parts if p))
    comparable = {k: v for k, v in comparison.items() if v["pct_change"] is not None}
    if not comparable:
        parts.append(f"Önceki {days} günlük dönem için veri olmadığından karşılaştırma yapamıyorum.")
        return to_speech(" ".join(p for p in parts if p))

    notable = sorted(((k, v) for k, v in comparable.items() if abs(v["pct_change"]) >= thresholds.get(k, 5)),
                     key=lambda kv: -abs(kv[1]["pct_change"]))
    if not notable:
        parts.append(f"Son {days} günde önceki {days} güne göre belirgin bir değişim görmüyorum.")
    else:
        changes = []
        for key, v in notable[:4]:
            word = "arttı" if v["pct_change"] > 0 else "azaldı"
            changes.append(f"{INDICATORS[key].label_tr.lower()} yüzde {abs(v['pct_change']):.0f} {word}")
        parts.append(f"Son {days} günde önceki {days} güne göre " + ", ".join(changes) + ".")
        parts.append("Bu değişiklikler tek başına hastalık teşhisi anlamına gelmez.")
    missing = [INDICATORS[k].label_tr for k in comparison if k not in comparable]
    if missing:
        parts.append("Şu göstergeler için önceki dönem verisi yok: " + ", ".join(missing) + ".")
    return to_speech(" ".join(p for p in parts if p))


def spoken_alerts(alerts: list[dict]) -> str:
    if not alerts:
        return "Onay bekleyen sağlık uyarısı yok."
    parts = [f"Onay bekleyen {len(alerts)} uyarı var."]
    parts += [a["message"] for a in alerts[:3]]
    if len(alerts) > 3:
        parts.append("Diğerleri ekranda.")
    parts.append("Onaylamak için uyarıları onayla diyebilirsin.")
    return to_speech(" ".join(parts))
