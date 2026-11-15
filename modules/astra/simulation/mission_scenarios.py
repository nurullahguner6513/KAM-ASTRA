"""
Simülasyon senaryoları.

Her senaryo, normal bir günün hangi yönde bozulacağını tanımlar. Değerler
yalnızca yazılımı test etmek içindir; klinik veya görev verisi değildir.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    hr_offset: float = 0.0            # tüm kalp atışı örneklerine eklenir (bpm)
    resting_hr_offset: float = 0.0    # dinlenik kalp atışına eklenir (bpm)
    hrv_factor: float = 1.0           # HRV çarpanı
    spo2_offset: float = 0.0          # SpO2'ye eklenir (yüzde puanı)
    sleep_factor: float = 1.0         # uyku süresi çarpanı
    steps_factor: float = 1.0         # adım ve hareket çarpanı
    exercise: bool = True             # egzersiz seansı var mı
    longest_sedentary_min: float = 90.0
    stress_level: float = 3.0         # öz bildirim, 0–10
    radiation_factor: float = 1.0     # doz hızı çarpanı
    gap_hours: tuple[float, float] | None = None  # saat bağlantısının koptuğu aralık
    drop_metrics: tuple[str, ...] = ()            # hiç gelmeyen ölçümler
    drop_sleep: bool = False                      # uyku kaydı gelmez
    faulty: bool = False                          # hatalı sensör okumaları eklenir


SCENARIOS: dict[str, Scenario] = {
    s.name: s
    for s in (
        Scenario("normal", "Normal sağlık verileri"),
        Scenario("hr_elevated", "Kalp atış hızında artış", hr_offset=35, resting_hr_offset=12),
        Scenario("hrv_drop", "HRV düşüşü", hrv_factor=0.55),
        Scenario("spo2_drop", "SpO2 düşüşü", spo2_offset=-6),
        Scenario("sleep_deficit", "Uyku eksikliği", sleep_factor=0.55),
        Scenario("inactivity", "Uzun süreli hareketsizlik", steps_factor=0.15, exercise=False,
                 longest_sedentary_min=420),
        Scenario("high_stress", "Yüksek stres bildirimi", stress_level=9),
        Scenario("radiation_spike", "Radyasyon doz artışı", radiation_factor=8),
        Scenario("sensor_disconnect", "Sensör bağlantı kesilmesi", gap_hours=(9, 15)),
        Scenario("faulty_measurement", "Hatalı ölçüm", faulty=True),
        Scenario("missing_data", "Eksik veri", drop_metrics=("hrv_rmssd", "spo2"), drop_sleep=True),
        Scenario("multi_risk", "Birden fazla riskin aynı anda oluşması", hr_offset=25,
                 resting_hr_offset=10, hrv_factor=0.6, sleep_factor=0.6, stress_level=8),
    )
}
