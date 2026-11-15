"""Analiz motoru, raporlar ve çekirdek (AstraCore) testleri."""

import json
import unittest
from datetime import timedelta

from modules.astra import health_reports
from modules.astra.health_analyzer import HealthAnalyzer
from modules.astra.tests.helpers import D0, TempDb


class AnalyzerTest(unittest.TestCase):
    def test_day_summary_values(self):
        with TempDb() as t:
            last = t.simulate(1)
            s = HealthAnalyzer(t.db, simulated=True).day_summary(t.aid, last)
            self.assertAlmostEqual(s.values["resting_hr"], 58, delta=5)
            self.assertAlmostEqual(s.values["heart_rate_mean"], 71, delta=3)
            self.assertAlmostEqual(s.values["spo2_mean"], 97, delta=1)
            self.assertAlmostEqual(s.values["sleep_total_min"], 427, delta=40)
            self.assertEqual(s.counts["heart_rate_mean"], 144)
            self.assertEqual(s.excluded, 0)
            self.assertIsNotNone(s.last_sample_at)

    def test_suspect_readings_are_excluded_from_summary(self):
        with TempDb() as t:
            last = t.simulate(1, "faulty_measurement", 1)
            faulty = HealthAnalyzer(t.db, True).day_summary(t.aid, last)
            raw = [r["value"] for r in t.db.get_measurements(t.aid, "heart_rate")]
        self.assertEqual(faulty.excluded, 3)
        self.assertEqual(faulty.counts["heart_rate_mean"], 144)
        self.assertEqual(len(raw), 147)  # 3 şüpheli okuma kayıtlı ama hesaba katılmıyor
        self.assertLess(faulty.values["heart_rate_mean"], sum(raw) / len(raw) - 1.5)
        self.assertAlmostEqual(faulty.values["heart_rate_mean"], 71, delta=2)

    def test_baseline_is_robust_and_needs_enough_days(self):
        with TempDb() as t:
            t.add_daily("resting_heart_rate", "bpm", [57, 59] * 10 + [95])  # tek aykırı gün
            analyzer = HealthAnalyzer(t.db, True)
            history = analyzer.summaries(t.aid, D0, 21)
            base = analyzer.baselines(history, 7, {})["resting_hr"]
            self.assertEqual(base.median, 59)
            self.assertLess(base.spread, 3)  # aykırı değer yayılımı şişirmemeli
            self.assertEqual(base.days_used, 21)
            self.assertEqual(analyzer.baselines(history[:5], 7, {}), {})

    def test_period_comparison_detects_sleep_drop(self):
        with TempDb() as t:
            last = t.simulate(14, "sleep_deficit", scenario_days=7)
            cmp = HealthAnalyzer(t.db, True).period_comparison(t.aid, last, 7)
            self.assertLess(cmp["sleep_total_min"]["pct_change"], -35)
            self.assertLess(abs(cmp["spo2_mean"]["pct_change"]), 1)

    def test_trend_slope(self):
        with TempDb() as t:
            last = t.add_daily("resting_heart_rate", "bpm", [58 + 0.5 * i for i in range(20)])
            slope = HealthAnalyzer(t.db, True).trend(t.aid, last, 20)
            self.assertAlmostEqual(slope["resting_hr"], 0.5, places=2)


class ReportTest(unittest.TestCase):
    def test_daily_report_content(self):
        with TempDb() as t:
            core = t.core()
            text = core.daily_report(t.aid, t.simulate(31, "multi_risk", 1))
            self.assertTrue(text.startswith(health_reports.SIM_BANNER))
            self.assertIn("Seviye 3 (YÜKSEK RİSK)", text)
            self.assertIn("kişisel referans", text)
            self.assertIn("Radyasyon:", text)
            self.assertTrue(text.endswith(health_reports.DISCLAIMER))

    def test_report_says_when_data_is_missing(self):
        with TempDb() as t:
            core = t.core()
            text = core.daily_report(t.aid, t.simulate(31, "missing_data", 1))
            self.assertIn("Kalp atış hızı değişkenliği: veri yok", text)
            self.assertIn("Bugün şu veriler alınamadı", text)
            empty = core.daily_report(t.aid, D0 + timedelta(days=200))
            self.assertIn("kayıtlı sağlık verisi yok", empty)
            self.assertIn("dozimetre verisi yok", t.core(simulated=False).radiation_report(t.aid, D0))

    def test_period_and_radiation_reports(self):
        with TempDb() as t:
            last = t.simulate(14, "sleep_deficit", scenario_days=7)
            core = t.core()
            weekly = core.period_report(t.aid, last, 7)
            self.assertIn("Toplam uyku süresi", weekly)
            self.assertIn("azaldı", weekly)
            rad = core.radiation_report(t.aid, last + timedelta(hours=23, minutes=12))
            self.assertIn("görev sınırının yüzde", rad)
            self.assertIn("Son ölçüm 12 dakika önce alındı", rad)


class CoreTest(unittest.TestCase):
    def test_evaluate_persists_event_baselines_alerts_and_reports(self):
        with TempDb() as t:
            last = t.simulate(31, "multi_risk", 1)
            core = t.core()
            a = core.evaluate(t.aid, last, now=last + timedelta(days=1))
            self.assertEqual(a.level, 3)
            event = t.db.query("SELECT * FROM health_risk_events")[0]
            self.assertEqual((event["level"], event["is_simulated"]), (3, 1))
            self.assertTrue(json.loads(event["findings"]))
            self.assertEqual(len(t.db.query("SELECT * FROM health_baselines")), 9)
            kinds = sorted(r["kind"] for r in t.db.query("SELECT kind FROM health_reports"))
            self.assertEqual(kinds, ["daily", "emergency"])
            report = json.loads(t.db.query("SELECT content FROM health_reports WHERE kind='emergency'")[0]["content"])
            self.assertEqual(report["data_source"], "SIMULATED")
            self.assertEqual(report["risk_level"], 3)
            active = core.alerts.active(t.aid)
            self.assertEqual(active[0]["level"], 3)
            self.assertTrue(all(x["message"].startswith("Simülasyon.") for x in active))
            # aynı günü yeniden değerlendirmek uyarıları çoğaltmamalı
            core.evaluate(t.aid, last, now=last + timedelta(days=1, minutes=5))
            self.assertEqual(len(core.alerts.active(t.aid)), len(active))

    def test_normal_day_creates_no_alerts_and_no_emergency_report(self):
        with TempDb() as t:
            last = t.simulate(31)
            core = t.core()
            self.assertEqual(core.evaluate(t.aid, last, now=last + timedelta(days=1)).level, 0)
            self.assertEqual(core.alerts.active(t.aid), [])
            self.assertEqual(t.db.query("SELECT * FROM health_reports WHERE kind='emergency'"), [])


if __name__ == "__main__":
    unittest.main()
