"""ASTRA veritabanı ve veri doğrulama testleri.

KAM klasöründen çalıştırma:
    python -m unittest discover -s modules/astra/tests -t . -v
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules.astra.health_database import HealthDatabase
from modules.astra.models import (ActivityRecord, InvalidDataError, Measurement, RadiationRecord,
                                  SleepRecord, utc_now)

T0 = datetime(2025, 3, 1, 8, 0, tzinfo=timezone.utc)


def hr(astronaut_id, value=64.0, at=T0, **kw):
    args = dict(astronaut_id=astronaut_id, metric="heart_rate", value=value, unit="bpm", measured_at=at,
                source_device="TEST-WATCH", source_type="DEVICE")
    args.update(kw)
    return Measurement(**args)


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "astra.db"
        self.db = HealthDatabase(self.path)
        self.aid = self.db.add_astronaut("Test Astronot")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_schema_tables_exist(self):
        con = sqlite3.connect(self.path)
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        for table in ("astronauts", "mission_records", "health_measurements", "sleep_records",
                      "activity_records", "radiation_records", "device_connections",
                      "rejected_inputs", "access_log"):
            self.assertIn(table, names)

    def test_insert_and_read_keeps_source_fields(self):
        self.assertTrue(self.db.add(hr(self.aid, quality=0.8)))
        row = self.db.latest_measurement(self.aid, "heart_rate")
        self.assertEqual(row["value"], 64.0)
        self.assertEqual(row["unit"], "bpm")
        self.assertEqual(row["source_device"], "TEST-WATCH")
        self.assertEqual(row["source_type"], "DEVICE")
        self.assertEqual(row["quality"], 0.8)
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["sync_state"], "pending")

    def test_timestamps_stored_as_utc(self):
        local = datetime(2025, 3, 1, 11, 0, tzinfo=timezone(timedelta(hours=3)))  # 08:00 UTC
        self.db.add(hr(self.aid, at=local))
        self.assertEqual(self.db.latest_measurement(self.aid, "heart_rate")["measured_at_utc"],
                         "2025-03-01T08:00:00Z")

    def test_duplicate_is_not_stored_twice(self):
        self.assertTrue(self.db.add(hr(self.aid)))
        self.assertFalse(self.db.add(hr(self.aid)))
        self.assertEqual(len(self.db.get_measurements(self.aid, "heart_rate")), 1)

    def test_invalid_inputs_are_rejected_and_logged(self):
        bad = [
            hr(self.aid, value=0),                                   # imkânsız değer
            hr(self.aid, value=400),
            hr(self.aid, value=float("nan")),
            hr(self.aid, unit="ms"),                                 # yanlış birim
            hr(self.aid, metric="immune_status"),                    # bilinmeyen ölçüm
            hr(self.aid, at=datetime(2025, 3, 1, 8, 0)),             # saat dilimi yok
            hr(self.aid, at=utc_now() + timedelta(days=1)),          # gelecekte
            hr(self.aid, source_type="WATCH"),                       # bilinmeyen kaynak türü
            hr(self.aid, source_device=""),                          # kaynak cihaz yok
            hr(self.aid, quality=1.5),
            hr(self.aid, status="great"),
            hr(999),                                                 # kayıtlı olmayan astronot
        ]
        for record in bad:
            with self.assertRaises(InvalidDataError):
                self.db.add(record)
        self.assertEqual(self.db.get_measurements(self.aid, "heart_rate"), [])
        self.assertEqual(self.db.counts()["rejected_inputs"], len(bad))

    def test_add_many_counts(self):
        result = self.db.add_many([hr(self.aid), hr(self.aid), hr(self.aid, value=999),
                                   hr(self.aid, at=T0 + timedelta(minutes=1))])
        self.assertEqual((result.inserted, result.duplicates, result.rejected), (2, 1, 1))

    def test_simulated_and_real_data_can_be_separated(self):
        self.db.add(hr(self.aid))
        self.db.add(hr(self.aid, at=T0 + timedelta(minutes=5), source_device="SIM-WATCH-01",
                       source_type="SIMULATED"))
        self.assertEqual(len(self.db.get_measurements(self.aid, "heart_rate")), 2)
        real = self.db.get_measurements(self.aid, "heart_rate", simulated=False)
        sim = self.db.get_measurements(self.aid, "heart_rate", simulated=True)
        self.assertEqual([r["source_type"] for r in real], ["DEVICE"])
        self.assertEqual([r["source_type"] for r in sim], ["SIMULATED"])

    def test_time_range_query(self):
        for i in range(5):
            self.db.add(hr(self.aid, at=T0 + timedelta(hours=i)))
        rows = self.db.get_measurements(self.aid, "heart_rate", start=T0 + timedelta(hours=1),
                                        end=T0 + timedelta(hours=3))
        self.assertEqual(len(rows), 2)

    def test_sleep_activity_radiation_records(self):
        sleep = SleepRecord(self.aid, T0 - timedelta(hours=7), T0, 80, 95, 230, 15, "TEST-WATCH", "DEVICE", 82)
        activity = ActivityRecord(self.aid, T0.replace(hour=0), 6500, 70, 45, 95, "TEST-WATCH", "DEVICE")
        radiation = RadiationRecord(self.aid, T0, 21.5, 12.4, "TEST-DOSIMETER", "DEVICE")
        self.assertEqual(self.db.add_many([sleep, activity, radiation]).inserted, 3)
        self.assertEqual(self.db.get_sleep(self.aid)[0]["deep_min"], 80)
        self.assertEqual(self.db.get_activity(self.aid)[0]["day_utc"], "2025-03-01")
        self.assertEqual(self.db.get_radiation(self.aid)[0]["cumulative_dose_msv"], 12.4)

    def test_invalid_sleep_and_radiation_rejected(self):
        with self.assertRaises(InvalidDataError):  # bitiş başlangıçtan önce
            self.db.add(SleepRecord(self.aid, T0, T0 - timedelta(hours=1), 10, 10, 10, 0, "W", "DEVICE"))
        with self.assertRaises(InvalidDataError):  # evreler aralıktan uzun
            self.db.add(SleepRecord(self.aid, T0 - timedelta(hours=2), T0, 100, 100, 100, 0, "W", "DEVICE"))
        with self.assertRaises(InvalidDataError):  # negatif doz
            self.db.add(RadiationRecord(self.aid, T0, -1, 5, "D", "DEVICE"))

    def test_device_status_and_access_log(self):
        self.db.add_device_event("TEST-WATCH", "smartwatch", "DEVICE", "connected", T0)
        self.db.add_device_event("TEST-WATCH", "smartwatch", "DEVICE", "disconnected", T0 + timedelta(hours=1))
        self.assertEqual(self.db.device_status("TEST-WATCH")["status"], "disconnected")
        self.assertIsNone(self.db.device_status("YOK"))
        self.db.log_access("test", "read", "heart_rate")
        self.assertEqual(self.db.counts()["access_log"], 1)

    def test_data_survives_reopen_and_integrity(self):
        self.db.add(hr(self.aid))
        self.db.close()
        self.db = HealthDatabase(self.path)  # yeniden açmak mevcut veriyi silmemeli
        self.assertEqual(len(self.db.get_measurements(self.aid, "heart_rate")), 1)
        self.assertEqual(self.db.add_astronaut("Test Astronot"), self.aid)
        self.assertTrue(self.db.integrity_ok())


if __name__ == "__main__":
    unittest.main()
