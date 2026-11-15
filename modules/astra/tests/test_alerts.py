"""Uyarı yöneticisi testleri: tekrar etmeme, onay, kritik tekrar, sessize alma, öncelik."""

import unittest
from datetime import timedelta

from modules.astra.alert_manager import AlertManager, spoken_text
from modules.astra.health_analyzer import DaySummary
from modules.astra.radiation.radiation_analyzer import RadiationStatus
from modules.astra.risk_engine import Finding, RiskAssessment
from modules.astra.tests.helpers import D0, TempDb

NOW = D0 + timedelta(hours=12)


def assessment(aid, *findings, simulated=True):
    health = [f for f in findings if f.category != "data"]
    data = [f for f in findings if f.category == "data"]
    return RiskAssessment(aid, D0, max((f.level for f in health), default=0), health, data, simulated,
                          DaySummary(D0), {}, {}, RadiationStatus())


def finding(code, level, category="health"):
    return Finding(code, category, level, f"{code} test bulgusu.")


class AlertManagerTest(unittest.TestCase):
    def setUp(self):
        self.t = TempDb().__enter__()
        self.alerts = AlertManager(self.t.db)
        self.aid = self.t.aid

    def tearDown(self):
        self.t.__exit__()

    def test_same_alert_is_not_created_twice(self):
        a = assessment(self.aid, finding("dev_hrv_rmssd", 2))
        self.assertEqual(len(self.alerts.process(a, NOW)), 1)
        self.assertEqual(self.alerts.process(a, NOW + timedelta(minutes=5)), [])
        self.assertEqual(len(self.alerts.active(self.aid)), 1)

    def test_non_critical_alert_is_announced_once(self):
        self.alerts.process(assessment(self.aid, finding("dev_hrv_rmssd", 2)), NOW)
        self.assertEqual(len(self.alerts.due_notifications(self.aid, NOW)), 1)
        self.assertEqual(self.alerts.due_notifications(self.aid, NOW + timedelta(hours=5)), [])

    def test_unacknowledged_critical_alert_repeats_until_acknowledged(self):
        self.alerts.process(assessment(self.aid, finding("abs_spo2_low", 3)), NOW)
        first = self.alerts.due_notifications(self.aid, NOW)
        self.assertEqual(len(first), 1)
        self.assertEqual(self.alerts.due_notifications(self.aid, NOW + timedelta(minutes=10)), [])
        again = self.alerts.due_notifications(self.aid, NOW + timedelta(minutes=16))
        self.assertEqual(again[0]["notify_count"], 2)
        self.assertTrue(self.alerts.acknowledge(first[0]["id"], NOW + timedelta(minutes=17)))
        self.assertFalse(self.alerts.acknowledge(first[0]["id"], NOW + timedelta(minutes=18)))
        self.assertEqual(self.alerts.due_notifications(self.aid, NOW + timedelta(hours=2)), [])
        self.assertEqual(self.alerts.active(self.aid), [])

    def test_emergency_repeats_faster_than_high_risk(self):
        self.alerts.process(assessment(self.aid, finding("abs_spo2_low", 4)), NOW)
        self.alerts.due_notifications(self.aid, NOW)
        self.assertEqual(len(self.alerts.due_notifications(self.aid, NOW + timedelta(minutes=3))), 1)

    def test_mute_silences_low_levels_but_never_critical(self):
        self.alerts.muted = True
        self.alerts.process(assessment(self.aid, finding("dev_sleep_total_min", 2),
                                       finding("rad_rate_alarm", 3, "radiation")), NOW)
        due = self.alerts.due_notifications(self.aid, NOW)
        self.assertEqual([d["code"] for d in due], ["rad_rate_alarm"])
        self.alerts.muted = False  # sessize alma kalkınca bekleyen uyarı kaybolmamış olmalı
        self.assertEqual([d["code"] for d in self.alerts.due_notifications(self.aid, NOW)],
                         ["dev_sleep_total_min"])

    def test_escalation_updates_and_reannounces(self):
        self.alerts.process(assessment(self.aid, finding("abs_spo2_low", 3)), NOW)
        self.alerts.due_notifications(self.aid, NOW)
        changed = self.alerts.process(assessment(self.aid, finding("abs_spo2_low", 4)), NOW + timedelta(minutes=1))
        self.assertEqual([c["level"] for c in changed], [4])
        self.assertEqual(len(self.alerts.active(self.aid)), 1)
        self.assertEqual(len(self.alerts.due_notifications(self.aid, NOW + timedelta(minutes=1))), 1)

    def test_cooldown_after_acknowledgement(self):
        a = assessment(self.aid, finding("dev_stress_level", 2))
        alert = self.alerts.process(a, NOW)[0]
        self.alerts.acknowledge(alert["id"], NOW)
        self.assertEqual(self.alerts.process(a, NOW + timedelta(hours=6)), [])    # 12 saatlik bekleme içinde
        self.assertEqual(len(self.alerts.process(a, NOW + timedelta(hours=13))), 1)  # bekleme doldu

    def test_higher_level_breaks_cooldown(self):
        alert = self.alerts.process(assessment(self.aid, finding("dev_stress_level", 1)), NOW)[0]
        self.alerts.acknowledge(alert["id"], NOW)
        again = self.alerts.process(assessment(self.aid, finding("dev_stress_level", 2)), NOW + timedelta(hours=1))
        self.assertEqual(len(again), 1)

    def test_priority_order_highest_level_first(self):
        self.alerts.process(assessment(self.aid, finding("missing_data", 1, "data"), finding("dev_steps", 2),
                                       finding("abs_spo2_low", 4), finding("multi_indicator", 3)), NOW)
        self.assertEqual([d["level"] for d in self.alerts.due_notifications(self.aid, NOW)], [4, 3, 2, 1])

    def test_spoken_text_marks_simulation_and_avoids_diagnosis(self):
        text = spoken_text(finding("abs_spo2_low", 4), simulated=True)
        self.assertTrue(text.startswith("Simülasyon. Acil durum."))
        self.assertIn("protokol", text)
        real = spoken_text(finding("dev_hrv_rmssd", 2), simulated=False)
        self.assertTrue(real.startswith("Dikkat."))
        self.assertNotIn("Simülasyon", real)
        data = spoken_text(finding("stale_data", 2, "data"), simulated=False)
        self.assertNotIn("öneririm", data)

    def test_simulated_and_real_alerts_do_not_block_each_other(self):
        self.alerts.process(assessment(self.aid, finding("dev_steps", 2), simulated=True), NOW)
        real = self.alerts.process(assessment(self.aid, finding("dev_steps", 2), simulated=False), NOW)
        self.assertEqual([r["is_simulated"] for r in real], [0])


if __name__ == "__main__":
    unittest.main()
