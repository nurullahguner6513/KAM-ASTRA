"""
ASTRA risk motoru — deterministik, yapılandırılabilir kurallar.

Risk seviyesini (0–4) yalnızca bu dosyadaki kurallar belirler; dil modeli
belirlemez. Motor teşhis koymaz: "hangi gösterge, referansa göre ne kadar
değişti" bilgisini üretir.

Seviyeler:
  0 NORMAL        Veriler kişisel aralıkta.
  1 BİLGİLENDİRME Tek göstergede hafif değişim.
  2 DİKKAT        Belirgin değişim, birkaç gün süren hafif değişim veya birden
                  fazla göstergede hafif değişim.
  3 YÜKSEK RİSK   Birden fazla göstergede belirgin değişim veya protokol eşiği.
  4 ACİL          Önceden tanımlı acil durum eşiği (art arda, güvenilir ölçümlerle).

DEFAULT_CONFIG içindeki tüm eşikler YER TUTUCUDUR. Gerçek kullanımdan önce
görev doktorları tarafından belirlenmeli ve modules/astra/config/risk_rules.json
dosyasıyla verilmelidir.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .health_analyzer import INDICATORS, Baseline, DaySummary, Deviation, HealthAnalyzer, day_start
from .health_database import HealthDatabase
from .radiation.radiation_analyzer import DEFAULT_RADIATION_CONFIG, RadiationStatus, assess_radiation

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "risk_rules.json"
# Günde bir kez gelen değerler (sabah ölçümü, gece uykusu, gün sonu özeti, akşam öz bildirimi)
ONCE_DAILY = ("resting_hr", "hrv_rmssd", "sleep_total_min", "steps", "longest_sedentary_min", "stress_level")

DEFAULT_CONFIG = {
    "baseline_window_days": 30,   # kişisel referans için geriye bakılan gün sayısı
    "min_baseline_days": 7,       # referans oluşması için gereken en az gün
    "z_info": 2.0,                # SEVİYE 1 için referanstan sapma (yayılım katı)
    "z_attention": 3.0,           # SEVİYE 2 için
    "persistence_days": 3,        # hafif değişim bu kadar gün sürerse SEVİYE 2
    "min_quality": 0.5,           # bu kalitenin altındaki ölçümler hesaba katılmaz
    "stale_minutes": 120,         # son ölçüm bundan eskiyse "veri eski" uyarısı
    "low_coverage_ratio": 0.8,    # günlük örnek sayısı tipik sayının bu oranının altındaysa uyarı
    # gösterge başına: SEVİYE 1 ve 2 için en az yüzde değişim, en küçük yayılım
    "indicators": {
        "resting_hr":            {"pct_info": 5,  "pct_attention": 10,  "spread_floor": 2.0},
        "heart_rate_mean":       {"pct_info": 8,  "pct_attention": 15,  "spread_floor": 2.0},
        "hrv_rmssd":             {"pct_info": 15, "pct_attention": 25,  "spread_floor": 5.0},
        "spo2_mean":             {"pct_info": 2,  "pct_attention": 4,   "spread_floor": 0.4},
        "skin_temp_mean":        {"pct_info": 2,  "pct_attention": 4,   "spread_floor": 0.2},
        "sleep_total_min":       {"pct_info": 15, "pct_attention": 30,  "spread_floor": 15.0},
        "steps":                 {"pct_info": 30, "pct_attention": 60,  "spread_floor": 400.0},
        "longest_sedentary_min": {"pct_info": 50, "pct_attention": 150, "spread_floor": 15.0},
        "stress_level":          {"pct_info": 30, "pct_attention": 60,  "spread_floor": 0.8},
    },
    # Kişisel referanstan bağımsız protokol eşikleri (ham ölçümler üzerinde)
    "absolute_rules": [
        {"code": "abs_spo2_low", "metric": "spo2", "direction": "below", "threshold": 90,
         "sustain_samples": 3, "level": 3, "label": "Oksijen doygunluğu"},
        {"code": "abs_spo2_low", "metric": "spo2", "direction": "below", "threshold": 85,
         "sustain_samples": 3, "level": 4, "label": "Oksijen doygunluğu"},
    ],
    "radiation": dict(DEFAULT_RADIATION_CONFIG),
}


def load_config(path: str | Path | None = None) -> dict:
    """Varsayılanları, varsa JSON dosyasındaki değerlerle birleştirir."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    path = Path(path) if path else CONFIG_PATH
    if path.exists():
        overrides = json.loads(path.read_text(encoding="utf-8"))
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, dict) and isinstance(config[key].get(sub_key), dict):
                        config[key][sub_key].update(sub_value)
                    else:
                        config[key][sub_key] = sub_value
            else:
                config[key] = value
    return config


@dataclass
class Finding:
    code: str
    category: str   # "health", "radiation" veya "data"
    level: int
    message: str
    indicator: str | None = None
    group: str | None = None
    value: float | None = None
    reference: float | None = None
    pct_change: float | None = None


@dataclass
class RiskAssessment:
    astronaut_id: int
    day: datetime
    level: int                       # sağlık + radyasyon bulgularının en yükseği
    findings: list[Finding]          # sağlık ve radyasyon bulguları
    data_findings: list[Finding]     # eksik, eski veya güvenilmez veri notları
    is_simulated: bool
    summary: DaySummary
    baselines: dict[str, Baseline]
    deviations: dict[str, Deviation]
    radiation: RadiationStatus
    evaluated_at: datetime | None = None

    def findings_as_dicts(self) -> list[dict]:
        return [f.__dict__ for f in self.findings + self.data_findings]


def _fmt(value: float) -> str:
    return f"{value:.0f}" if abs(value) >= 100 else f"{value:.1f}"


class RiskEngine:
    def __init__(self, db: HealthDatabase, simulated: bool, config: dict | None = None):
        self.db = db
        self.config = config or load_config()
        self.simulated = simulated
        self.analyzer = HealthAnalyzer(db, simulated, self.config["min_quality"])

    # ── Kişisel sapma seviyesi ───────────────────────────────────────────
    def _deviation_level(self, key: str, dev: Deviation) -> int:
        cfg = self.config["indicators"][key]
        adverse = INDICATORS[key].adverse
        z, pct = dev.z, dev.pct
        if adverse == "low":
            z, pct = -z, -pct
        elif adverse == "both":
            z, pct = abs(z), abs(pct)
        if z >= self.config["z_attention"] and pct >= cfg["pct_attention"]:
            return 2
        if z >= self.config["z_info"] and pct >= cfg["pct_info"]:
            return 1
        return 0

    def assess(self, astronaut_id: int, day: datetime, now: datetime | None = None) -> RiskAssessment:
        """day gününü değerlendirir. now verilirse verinin eskiliği de denetlenir."""
        cfg = self.config
        day = day_start(day)
        window = cfg["baseline_window_days"]
        all_days = self.analyzer.summaries(astronaut_id, day - timedelta(days=window), window + 1)
        history, today = all_days[:-1], all_days[-1]
        floors = {k: v["spread_floor"] for k, v in cfg["indicators"].items()}
        baselines = self.analyzer.baselines(history, cfg["min_baseline_days"], floors)
        deviations = self.analyzer.deviations(today, baselines)

        findings: list[Finding] = []
        data: list[Finding] = []

        # 1) Kişisel referansa göre sapmalar
        for key, dev in deviations.items():
            level = self._deviation_level(key, dev)
            if level == 0:
                continue
            ind = INDICATORS[key]
            persisted = ""
            if level == 1:
                streak = 1
                for past in reversed(history):
                    past_dev = self.analyzer.deviations(past, {key: dev.baseline}).get(key)
                    if past_dev is None or self._deviation_level(key, past_dev) == 0:
                        break
                    streak += 1
                if streak >= cfg["persistence_days"]:
                    level = 2
                    persisted = f" Bu değişim {streak} gündür sürüyor."
            direction = "üzerinde" if dev.value > dev.baseline.median else "altında"
            findings.append(Finding(
                f"dev_{key}", "health", level,
                f"{ind.label_tr} kişisel referansın {direction}: {_fmt(dev.value)} {ind.unit} "
                f"(referans {_fmt(dev.baseline.median)} {ind.unit}, yüzde {dev.pct:+.0f}).{persisted}",
                key, ind.group, dev.value, dev.baseline.median, dev.pct))

        # 2) Protokol eşikleri: art arda güvenilir ölçüm gerekir (tek okuma alarm üretmez)
        worst: dict[str, tuple[int, dict, float]] = {}
        for rule in cfg["absolute_rules"]:
            values = [r["value"] for r in today.samples.get(rule["metric"], [])]
            run, extreme = 0, None
            for value in values:
                hit = value < rule["threshold"] if rule["direction"] == "below" else value > rule["threshold"]
                run = run + 1 if hit else 0
                if run >= rule["sustain_samples"]:  # eşik aşıldı; günün uç değerini raporla
                    extreme = min(values) if rule["direction"] == "below" else max(values)
                    break
            if extreme is not None and rule["level"] > worst.get(rule["code"], (0,))[0]:
                worst[rule["code"]] = (rule["level"], rule, extreme)
        for code, (level, rule, extreme) in worst.items():
            side = "altında" if rule["direction"] == "below" else "üzerinde"
            findings.append(Finding(
                code, "health", level,
                f"{rule['label']} art arda en az {rule['sustain_samples']} ölçümde {rule['threshold']} "
                f"eşiğinin {side}; günün uç değeri {_fmt(extreme)}.",
                rule["metric"], rule["metric"], extreme, float(rule["threshold"])))

        # 3) Birden fazla gösterge grubu birlikte değişmişse seviye yükselir
        group_levels: dict[str, int] = {}
        for f in findings:
            group_levels[f.group] = max(group_levels.get(f.group, 0), f.level)
        attention = sorted(g for g, lv in group_levels.items() if lv >= 2)
        any_change = sorted(g for g, lv in group_levels.items() if lv >= 1)
        if len(attention) >= 2:
            findings.append(Finding("multi_indicator", "health", 3,
                                    f"{len(attention)} farklı gösterge grubunda aynı anda belirgin değişim var."))
        elif len(any_change) >= 2:
            findings.append(Finding("multi_indicator", "health", 2,
                                    f"{len(any_change)} farklı gösterge grubunda aynı anda değişim var."))

        # 4) Radyasyon (ayrı protokol)
        radiation = assess_radiation(self.db, astronaut_id, day, self.simulated, cfg["radiation"])
        for item in radiation.findings:
            findings.append(Finding(item["code"], "radiation", item["level"], item["message"]))
        if not radiation.has_data:
            data.append(Finding("no_radiation_data", "data", 1, "Bu gün için radyasyon dozimetresi verisi yok."))

        # 5) Veri kalitesi notları (sağlık riski değildir)
        if len(baselines) < len(INDICATORS):
            ready = max((b.days_used for b in baselines.values()), default=0)
            if not baselines:
                data.append(Finding("baseline_insufficient", "data", 1,
                                    f"Kişisel referans henüz oluşmadı (en az {cfg['min_baseline_days']} günlük "
                                    f"veri gerekir). Yalnızca protokol eşikleri denetlendi."))
            elif ready:
                missing_ref = [INDICATORS[k].label_tr for k in INDICATORS if k not in baselines]
                data.append(Finding("baseline_partial", "data", 1,
                                    "Şu göstergeler için kişisel referans yok: " + ", ".join(missing_ref) + "."))
        # Günde bir kez gelen değerler gün bitmeden "eksik" sayılmaz; sürekli ölçümleri stale_data denetler
        unfinished = now is not None and now < day + timedelta(days=1)
        missing = [INDICATORS[k].label_tr for k in baselines
                   if k not in today.values and not (unfinished and k in ONCE_DAILY)]
        if missing:
            data.append(Finding("missing_data", "data", 1,
                                "Bugün şu veriler alınamadı: " + ", ".join(missing) + "."))
        if today.excluded:
            data.append(Finding("suspect_excluded", "data", 1,
                                f"{today.excluded} şüpheli veya düşük kaliteli ölçüm değerlendirmeye alınmadı."))
        low = [INDICATORS[k].label_tr for k, b in baselines.items()
               if k in today.counts and b.count_median > 1
               and today.counts[k] < cfg["low_coverage_ratio"] * b.count_median]
        if low and now is None:
            data.append(Finding("low_coverage", "data", 1,
                                "Şu göstergelerde ölçüm sayısı olağandan az: " + ", ".join(low) + "."))
        if now is not None:
            if today.last_sample_at is None:
                data.append(Finding("no_data_today", "data", 2, "Bugün hiç sağlık ölçümü alınmadı."))
            else:
                age_min = (now - today.last_sample_at).total_seconds() / 60
                if age_min > cfg["stale_minutes"]:
                    data.append(Finding("stale_data", "data", 2,
                                        f"Son sağlık ölçümü {age_min:.0f} dakika önce alındı; veriler güncel değil."))
        for device in self.db.device_statuses():
            if device["status"] == "disconnected" and (device["source_type"] == "SIMULATED") == self.simulated:
                data.append(Finding("device_disconnected", "data", 2,
                                    f"{device['device_name']} cihazıyla bağlantı kesik."))

        level = max((f.level for f in findings), default=0)
        return RiskAssessment(astronaut_id, day, level, findings, data, self.simulated, today,
                              baselines, deviations, radiation, now)
