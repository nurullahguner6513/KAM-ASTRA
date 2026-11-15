"""Elle ölçüm girişi ve veri kipi testleri."""

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from modules.astra.kam_bridge import AstraBridge
from modules.astra.manual_entry import build_measurements, resolve_metric
from modules.astra.models import InvalidDataError
from modules.astra.tests.helpers import TempDb
from modules.astra.tests.test_bridge import NOW, BridgeCase


class ParserTest(unittest.TestCase):
    def test_aliases(self):
        for name, metric in (("Nabız", "heart_rate"), ("KALP ATIŞI", "heart_rate"), ("dinlenik nabız", "resting_heart_rate"),
                             ("SpO2", "spo2"), ("oksijen", "spo2"), ("HRV", "hrv_rmssd"), ("Tansiyon", "blood_pressure"),
                             ("sıcaklık", "skin_temperature"), ("kilo", "body_weight"), ("Stres", "stress_level"),
                             ("ruh hali", "mood"), ("yorgunluk", "fatigue"), ("motivasyon", "motivation")):
            with self.subTest(name=name):
                self.assertEqual(resolve_metric(name), metric)
        with self.assertRaises(InvalidDataError):
            resolve_metric("bağışıklık")

    def test_values(self):
        r = build_measurements(1, "dinlenik nabız", "58,5", NOW, "SK27", 0.7)
        self.assertEqual((r[0].metric, r[0].value, r[0].unit, r[0].source_type), ("resting_heart_rate", 58.5, "bpm", "MANUAL"))
        bp = build_measurements(1, "tansiyon", "120/80", NOW, "SK27", 0.7)
        self.assertEqual([(m.metric, m.value) for m in bp], [("systolic_bp", 120), ("diastolic_bp", 80)])
        self.assertEqual(build_measurements(1, "spo2", "%97", NOW, "SK27", 0.7)[0].value, 97)
        for bad in (("nabız", "yetmiş"), ("tansiyon", "120"), ("tansiyon", "a/b")):
            with self.subTest(bad=bad), self.assertRaises(InvalidDataError):
                build_measurements(1, *bad, NOW, "SK27", 0.7)


class ManualBridgeTest(BridgeCase):
    def test_text_command_records_manual_measurement(self):
        self.assertTrue(self.bridge.handle_text("astra ölçüm nabız 72"))
        row = self.t.db.latest_measurement(self.t.aid, "heart_rate", simulated=False)
        self.assertEqual((row["value"], row["source_type"], row["source_device"], row["quality"]),
                         (72, "MANUAL", "SK27 (elle giriş)", 0.7))
        self.assertIn("Kaydedildi: Kalp atış hızı 72", self.ui.logs()[-1])
        self.assertIn("simülasyon kipinde", self.ui.logs()[-1])  # kullanıcı uyarılır
        self.assertIn("atım/dakika", self.spoken[-1])

    def test_invalid_entry_is_rejected_with_reason(self):
        self.bridge.handle_text("astra ölçüm nabız 400")
        self.assertIn("Ölçüm kaydedilmedi", self.ui.logs()[-1])
        self.assertIsNone(self.t.db.latest_measurement(self.t.aid, "heart_rate", simulated=False))
        self.bridge.handle_text("astra ölçüm nabız")
        self.assertIn("Kullanım", self.ui.logs()[-1])

    def test_low_spo2_entry_asks_for_remeasurement_without_alarm(self):
        reply = self.bridge.record_manual("spo2", "86", NOW)
        self.assertIn("protokol eşiğinin (90) altında", reply)
        self.assertIn("tekrarla", reply)

    def test_gemini_tool_records_and_relays(self):
        reply = self.bridge.handle_tool("astra_record_measurement", {"metric": "tansiyon", "value": "118/76"})
        self.assertIn("Sistolik kan basıncı 118", reply)
        self.assertEqual(len(self.t.db.get_measurements(self.t.aid, "diastolic_bp", simulated=False)), 1)

    def test_device_mode_evaluates_only_real_data(self):
        self.bridge.tick(NOW)  # simülasyon verisi yazılır
        self.assertIn("gerçek verilerle", self.bridge.handle_tool("astra_mode", {"mode": "device"}))
        self.bridge.record_manual("nabız", "72", NOW)
        self.bridge.record_manual("spo2", "97", NOW)
        a = self.bridge.tick(NOW + timedelta(minutes=1))
        self.assertFalse(a.is_simulated)
        self.assertEqual(a.summary.values, {"heart_rate_mean": 72, "spo2_mean": 97})
        self.assertFalse(a.radiation.has_data)  # simülasyon dozimetresi görünmez
        self.assertEqual(self.ui._health_card_lines[0], "Seviye 0 · NORMAL")
        # Sürekli veri akışı yok: saatler sonra "veri eski" uyarısı sesli okunmaz
        self.bridge.tick(NOW + timedelta(hours=5))
        self.assertFalse(any("güncel değil" in s for s in self.spoken))
        self.assertIn("simülasyon kipine", self.bridge.set_mode("simülasyon", NOW))
        self.assertTrue(self.bridge.tick(NOW + timedelta(hours=5, minutes=2)).is_simulated)

    def test_mode_is_persisted_to_settings_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "astra_settings.json"
            path.write_text(json.dumps({"enabled": True, "mode": "simulation", "voice": ""}), encoding="utf-8")
            bridge = AstraBridge(None, None, {"voice": "test", "history_days": 3}, db=self.t.db,
                                 speaker=self.spoken.append, clock=lambda: NOW, synchronous_voice=True,
                                 settings_path=path)
            self.assertTrue(bridge.handle_text("astra kip gerçek"))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved, {"enabled": True, "mode": "device", "voice": ""})
            self.assertIn("Bilinmeyen kip", bridge.set_mode("uzay", NOW))


if __name__ == "__main__":
    unittest.main()
