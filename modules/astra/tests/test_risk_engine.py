"""Risk motoru testleri: senaryo seviyeleri, yanlış alarm, kaçırılmış alarm, eski ve eksik veri."""

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from modules.astra.models import Measurement
from modules.astra.risk_engine import DEFAULT_CONFIG, load_config
from modules.astra.simulation.health_simulator import HealthSimulator, store
from modules.astra.simulation.mission_scenarios import Scenario
from modules.astra.tests.helpers import D0, TempDb

EXPECTED_LEVELS = {
    "normal": 0, "hr_elevated": 2, "hrv_drop": 2, "spo2_drop": 2, "sleep_deficit": 2, "inactivity": 2,
    "high_stress": 2, "radiation_spike": 3, "sensor_disconnect": 0, "faulty_measurement": 0,
    "missing_data": 0, "multi_risk": 3,
}


def codes(findings):
    return {f.code for f in findings}


class ScenarioLevelTest(unittest.TestCase):
    def test_each_scenario_gets_expected_level(self):
        for name, expected in EXPECTED_LEVELS.items():
            with self.subTest(scenario=name), TempDb() as t:
                last = t.simulate(31, name, scenario_days=1)
                self.assertEqual(t.core().engine.assess(t.aid, last).level, expected)

    def test_single_group_does_not_trigger_multi_indicator(self):
        with TempDb() as t:  # dinlenik ve ortalama kalp atışı aynı gruptur
            a = t.core().engine.assess(t.aid, t.simulate(31, "hr_elevated", 1))
            self.assertEqual(codes(a.findings), {"dev_resting_hr", "dev_heart_rate_mean"})

    def test_multi_risk_raises_level_through_combination(self):
        with TempDb() as t:
            a = t.core().engine.assess(t.aid, t.simulate(31, "multi_risk", 1))
            self.assertIn("multi_indicator", codes(a.findings))
            self.assertEqual(max(f.level for f in a.findings if f.code != "multi_indicator"), 2)


class FalseAlarmTest(unittest.TestCase):
    def test_normal_days_do_not_raise_alarms(self):
        with TempDb() as t:
            t.simulate(75)
            engine = t.core().engine
            levels = [engine.assess(t.aid, D0 + timedelta(days=i)).level for i in range(30, 75)]
            self.assertLessEqual(max(levels), 1)
            self.assertGreaterEqual(levels.count(0), 0.9 * len(levels))

    def test_faulty_sensor_readings_are_excluded_not_alarmed(self):
        with TempDb() as t:
            a = t.core().engine.assess(t.aid, t.simulate(31, "faulty_measurement", 1))
            self.assertEqual(a.level, 0)
            self.assertIn("suspect_excluded", codes(a.data_findings))

    def test_single_extreme_reading_is_not_an_emergency(self):
        with TempDb() as t:
            last = t.simulate(31)
            t.db.add(Measurement(t.aid, "spo2", 80, "%", last + timedelta(hours=10, minutes=7),
                                 "SIM-WATCH-01", "SIMULATED"))
            a = t.core().engine.assess(t.aid, last)
            self.assertNotIn("abs_spo2_low", codes(a.findings))
            self.assertEqual(a.level, 0)


class MissedAlarmTest(unittest.TestCase):
    def _assess_custom(self, t, scenario, history_days=30):
        t.simulate(history_days)
        day = D0 + timedelta(days=history_days)
        store(t.db, HealthSimulator(t.aid).generate_day(day, scenario))
        return t.core().engine.assess(t.aid, day)

    def test_sustained_low_spo2_is_high_risk(self):
        with TempDb() as t:
            a = self._assess_custom(t, Scenario("spo2_88", "test", spo2_offset=-9))
            self.assertEqual(a.level, 3)
            self.assertIn("abs_spo2_low", codes(a.findings))

    def test_sustained_very_low_spo2_is_emergency(self):
        with TempDb() as t:
            a = self._assess_custom(t, Scenario("spo2_83", "test", spo2_offset=-14))
            self.assertEqual(a.level, 4)

    def test_emergency_threshold_works_without_baseline(self):
        with TempDb() as t:
            a = self._assess_custom(t, Scenario("spo2_83", "test", spo2_offset=-14), history_days=0)
            self.assertEqual(a.level, 4)
            self.assertIn("baseline_insufficient", codes(a.data_findings))

    def test_mild_change_persisting_three_days_becomes_attention(self):
        base = ([57, 58, 59, 58] * 8)[:30]  # 30 gün, medyan 58
        with TempDb() as t:
            day = t.add_daily("resting_heart_rate", "bpm", base + [63])
            one = t.core().engine.assess(t.aid, day)
            self.assertEqual([(f.code, f.level) for f in one.findings], [("dev_resting_hr", 1)])
        with TempDb() as t:
            day = t.add_daily("resting_heart_rate", "bpm", base + [63, 63, 63])
            three = t.core().engine.assess(t.aid, day)
            self.assertEqual([(f.code, f.level) for f in three.findings], [("dev_resting_hr", 2)])
            self.assertIn("3 gündür", three.findings[0].message)

    def test_improvement_is_not_flagged(self):
        with TempDb() as t:  # dinlenik kalp atışının düşmesi olumsuz yön değildir
            day = t.add_daily("resting_heart_rate", "bpm", ([57, 58, 59, 58] * 8)[:30] + [50])
            self.assertEqual(t.core().engine.assess(t.aid, day).findings, [])


class DataQualityTest(unittest.TestCase):
    def test_missing_data_is_reported_not_treated_as_normal_silently(self):
        with TempDb() as t:
            a = t.core().engine.assess(t.aid, t.simulate(31, "missing_data", 1))
            note = next(f for f in a.data_findings if f.code == "missing_data")
            for label in ("Kalp atış hızı değişkenliği", "Ortalama oksijen doygunluğu", "Toplam uyku süresi"):
                self.assertIn(label, note.message)

    def test_once_daily_values_not_missing_before_day_ends(self):
        with TempDb() as t:
            last = t.simulate(31)
            today = last + timedelta(days=1)
            t.db.add(Measurement(t.aid, "heart_rate", 62, "bpm", today + timedelta(hours=1),
                                 "SIM-WATCH-01", "SIMULATED"))
            engine = t.core().engine
            morning = engine.assess(t.aid, today, now=today + timedelta(hours=2))
            note = next((f for f in morning.data_findings if f.code == "missing_data"), None)
            self.assertIsNotNone(note)  # SpO2 ve deri sıcaklığı sürekli ölçülür: eksik sayılır
            for label in ("Toplam uyku süresi", "Stres bildirimi", "Dinlenik kalp atış hızı", "Günlük adım"):
                self.assertNotIn(label, note.message)
            finished = engine.assess(t.aid, today, now=today + timedelta(days=1, hours=1))
            self.assertIn("Stres bildirimi", next(f for f in finished.data_findings if f.code == "missing_data").message)

    def test_sensor_gap_reported_as_low_coverage(self):
        with TempDb() as t:
            a = t.core().engine.assess(t.aid, t.simulate(31, "sensor_disconnect", 1))
            self.assertIn("low_coverage", codes(a.data_findings))

    def test_stale_data_and_disconnected_device_in_live_mode(self):
        with TempDb() as t:
            last = t.simulate(31)
            engine = t.core().engine
            fresh = engine.assess(t.aid, last, now=last + timedelta(hours=23, minutes=55))
            self.assertNotIn("stale_data", codes(fresh.data_findings))
            t.db.add_device_event("SIM-WATCH-01", "smartwatch", "SIMULATED", "disconnected",
                                  last + timedelta(hours=23, minutes=50))
            # ertesi gün öğlen: bugün hiç veri yok ve saat bağlı değil
            late = engine.assess(t.aid, last + timedelta(days=1), now=last + timedelta(days=1, hours=12))
            self.assertTrue({"no_data_today", "device_disconnected"} <= codes(late.data_findings))

    def test_stale_data_flag(self):
        with TempDb() as t:
            today = t.simulate(31) + timedelta(days=1)
            t.db.add(Measurement(t.aid, "heart_rate", 62, "bpm", today + timedelta(hours=1),
                                 "SIM-WATCH-01", "SIMULATED"))
            engine = t.core().engine
            recent = engine.assess(t.aid, today, now=today + timedelta(hours=2))
            self.assertNotIn("stale_data", codes(recent.data_findings))
            old = engine.assess(t.aid, today, now=today + timedelta(hours=6))  # son ölçüm 5 saat önce
            self.assertIn("stale_data", codes(old.data_findings))
            self.assertIn("300 dakika", next(f for f in old.data_findings if f.code == "stale_data").message)

    def test_insufficient_baseline_is_stated(self):
        with TempDb() as t:
            a = t.core().engine.assess(t.aid, t.simulate(4, "hr_elevated", 1))
            self.assertEqual(a.deviations, {})
            self.assertIn("baseline_insufficient", codes(a.data_findings))

    def test_simulated_data_is_invisible_in_real_mode(self):
        with TempDb() as t:
            last = t.simulate(31, "multi_risk", 1)
            real = t.core(simulated=False).engine.assess(t.aid, last)
            self.assertEqual(real.level, 0)
            self.assertEqual(real.summary.values, {})
            self.assertFalse(real.radiation.has_data)
            self.assertFalse(real.is_simulated)


class ConfigAndRadiationTest(unittest.TestCase):
    def test_json_overrides_merge_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "risk_rules.json"
            path.write_text(json.dumps({"z_info": 2.5, "radiation": {"mission_limit_msv": 18},
                                        "indicators": {"resting_hr": {"pct_info": 7}}}), encoding="utf-8")
            cfg = load_config(path)
        self.assertEqual(cfg["z_info"], 2.5)
        self.assertEqual(cfg["radiation"]["mission_limit_msv"], 18)
        self.assertEqual(cfg["radiation"]["rate_alarm_usv_h"], DEFAULT_CONFIG["radiation"]["rate_alarm_usv_h"])
        self.assertEqual(cfg["indicators"]["resting_hr"]["pct_info"], 7)
        self.assertEqual(cfg["indicators"]["resting_hr"]["pct_attention"], 10)
        self.assertEqual(DEFAULT_CONFIG["z_info"], 2.0)  # varsayılanlar değişmemeli

    def test_cumulative_dose_levels_follow_mission_limit(self):
        for limit, expected in ((150, 0), (18, 2), (10, 3)):
            with self.subTest(limit=limit), TempDb() as t:
                last = t.simulate(31)
                cfg = load_config(Path("yok.json"))
                cfg["radiation"]["mission_limit_msv"] = limit
                a = t.core(config=cfg).engine.assess(t.aid, last)
                self.assertEqual(a.level, expected)
                self.assertAlmostEqual(a.radiation.daily_dose_msv, 0.48, delta=0.05)

    def test_radiation_spike_is_separate_protocol_finding(self):
        with TempDb() as t:
            a = t.core().engine.assess(t.aid, t.simulate(31, "radiation_spike", 1))
            rad = [f for f in a.findings if f.category == "radiation"]
            self.assertIn("rad_rate_alarm", codes(rad))
            self.assertFalse([f for f in a.findings if f.category == "health"])


if __name__ == "__main__":
    unittest.main()
