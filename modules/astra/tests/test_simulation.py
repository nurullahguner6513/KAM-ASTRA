"""ASTRA simülasyon testleri: her senaryo beklenen yönde veri üretmeli ve SIMULATED etiketli olmalı."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

from modules.astra.health_database import HealthDatabase
from modules.astra.models import ActivityRecord, Measurement, RadiationRecord, SleepRecord
from modules.astra.simulation.health_simulator import SIM_WATCH, HealthSimulator, store
from modules.astra.simulation.mission_scenarios import SCENARIOS

DAY = datetime(2025, 3, 1, tzinfo=timezone.utc)


def avg(day, metric):
    return mean(m.value for m in day.metric(metric))


class SimulationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = HealthDatabase(Path(self.tmp.name) / "astra.db")
        self.aid = self.db.add_astronaut("SIM Astronot")
        self.normal = HealthSimulator(self.aid).generate_day(DAY, "normal")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def gen(self, scenario):
        return HealthSimulator(self.aid).generate_day(DAY, scenario)

    def test_all_twelve_scenarios_exist(self):
        self.assertEqual(len(SCENARIOS), 12)

    def test_every_record_is_marked_simulated(self):
        for name in SCENARIOS:
            day = self.gen(name)
            self.assertTrue(day.records)
            for record in day.records:
                self.assertEqual(record.source_type, "SIMULATED", name)
                self.assertTrue(record.source_device.startswith("SIM-"), name)

    def test_same_seed_same_data_different_seed_different_data(self):
        a = [r.row() for r in self.gen("normal").records]
        b = [r.row() for r in self.gen("normal").records]
        c = [r.row() for r in HealthSimulator(self.aid, seed=7).generate_day(DAY, "normal").records]
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_normal_day_is_complete_and_valid(self):
        self.assertEqual(len(self.normal.metric("heart_rate")), 144)
        self.assertEqual(len(self.normal.metric("spo2")), 48)
        self.assertEqual(len(self.normal.of_type(SleepRecord)), 1)
        self.assertEqual(len(self.normal.of_type(ActivityRecord)), 1)
        self.assertEqual(len(self.normal.of_type(RadiationRecord)), 24)
        result = store(self.db, self.normal)
        self.assertEqual(result.rejected, 0)
        self.assertEqual(result.inserted, len(self.normal.records))

    def test_hr_elevated(self):
        day = self.gen("hr_elevated")
        self.assertGreater(avg(day, "heart_rate"), avg(self.normal, "heart_rate") + 25)
        self.assertGreater(avg(day, "resting_heart_rate"), avg(self.normal, "resting_heart_rate") + 6)

    def test_hrv_drop(self):
        self.assertLess(avg(self.gen("hrv_drop"), "hrv_rmssd"), avg(self.normal, "hrv_rmssd") * 0.75)

    def test_spo2_drop(self):
        self.assertLess(avg(self.gen("spo2_drop"), "spo2"), avg(self.normal, "spo2") - 4)

    def test_sleep_deficit(self):
        short = self.gen("sleep_deficit").of_type(SleepRecord)[0].total_sleep_min
        self.assertLess(short, self.normal.of_type(SleepRecord)[0].total_sleep_min * 0.7)

    def test_inactivity(self):
        act = self.gen("inactivity").of_type(ActivityRecord)[0]
        base = self.normal.of_type(ActivityRecord)[0]
        self.assertLess(act.steps, base.steps * 0.3)
        self.assertEqual(act.exercise_min, 0)
        self.assertGreater(act.longest_sedentary_min, 300)

    def test_high_stress(self):
        self.assertGreater(avg(self.gen("high_stress"), "stress_level"), 7.5)
        self.assertLess(avg(self.normal, "stress_level"), 5)

    def test_radiation_spike_and_cumulative_dose_grows(self):
        spike = self.gen("radiation_spike").of_type(RadiationRecord)
        base = self.normal.of_type(RadiationRecord)
        self.assertGreater(mean(r.dose_rate_usv_h for r in spike), 5 * mean(r.dose_rate_usv_h for r in base))
        doses = [r.cumulative_dose_msv for r in base]
        self.assertEqual(doses, sorted(doses))
        sim = HealthSimulator(self.aid)
        first = sim.generate_day(DAY).of_type(RadiationRecord)[-1].cumulative_dose_msv
        second = sim.generate_day(DAY + timedelta(days=1)).of_type(RadiationRecord)[0].cumulative_dose_msv
        self.assertGreater(second, first)

    def test_sensor_disconnect_leaves_gap_but_dosimeter_continues(self):
        day = self.gen("sensor_disconnect")
        hours = [(m.measured_at - DAY).total_seconds() / 3600 for m in day.metric("heart_rate")]
        self.assertFalse(any(9 <= h < 15 for h in hours))
        self.assertTrue(any(h < 9 for h in hours) and any(h >= 15 for h in hours))
        self.assertEqual(len(day.of_type(RadiationRecord)), 24)
        self.assertEqual([e[2] for e in day.device_events], ["disconnected", "connected"])
        store(self.db, day)
        self.assertEqual(self.db.device_status(SIM_WATCH)["status"], "connected")

    def test_faulty_measurements_rejected_or_flagged(self):
        day = self.gen("faulty_measurement")
        result = store(self.db, day)
        self.assertEqual(result.rejected, 3)  # 0 bpm, 400 bpm, %140 SpO2
        self.assertEqual(self.db.counts()["rejected_inputs"], 3)
        rows = self.db.get_measurements(self.aid, "heart_rate")
        self.assertFalse(any(r["value"] <= 0 or r["value"] >= 400 for r in rows))
        suspect = [r for r in rows if r["status"] == "suspect"]
        self.assertEqual(len(suspect), 3)
        self.assertTrue(all(r["quality"] < 0.5 for r in suspect))

    def test_missing_data(self):
        day = self.gen("missing_data")
        self.assertEqual(day.metric("hrv_rmssd"), [])
        self.assertEqual(day.metric("spo2"), [])
        self.assertEqual(day.of_type(SleepRecord), [])
        self.assertTrue(day.metric("heart_rate"))

    def test_multi_risk_combines_changes(self):
        day = self.gen("multi_risk")
        self.assertGreater(avg(day, "heart_rate"), avg(self.normal, "heart_rate") + 15)
        self.assertLess(avg(day, "hrv_rmssd"), avg(self.normal, "hrv_rmssd") * 0.8)
        self.assertLess(day.of_type(SleepRecord)[0].total_sleep_min,
                        self.normal.of_type(SleepRecord)[0].total_sleep_min * 0.75)
        self.assertGreater(avg(day, "stress_level"), 6.5)

    def test_history_and_no_duplicates_on_resend(self):
        days = HealthSimulator(self.aid).generate_history(DAY, 10, "sleep_deficit", scenario_days=3)
        self.assertEqual([d.scenario for d in days], ["normal"] * 7 + ["sleep_deficit"] * 3)
        first = sum(store(self.db, d).inserted for d in days)
        before = self.db.counts()
        again = [store(self.db, d) for d in days]  # aynı veriyi yeniden gönder
        self.assertEqual(sum(r.inserted for r in again), 0)
        self.assertEqual(sum(r.duplicates for r in again), first)
        self.assertEqual(self.db.counts(), before)
        self.assertEqual(self.db.simulated_counts()["health_measurements"],
                         before["health_measurements"])
        self.assertEqual(len(self.db.get_sleep(self.aid)), 10)


if __name__ == "__main__":
    unittest.main()
