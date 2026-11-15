"""KAM köprüsü testleri: izleme döngüsü, sesli uyarılar, araçlar, yazılı komutlar, canlı simülasyon.

Gerçek KAM, Gemini ve Windows sesi kullanılmaz; yerlerine sahte nesneler konur.
"""

import re
import threading
import time
import unittest
from datetime import timedelta

from modules.astra import display
from modules.astra.kam_bridge import ASTRA_TOOL_DECLARATIONS, GEMINI_RELAY, GEMINI_REPLY, AstraBridge
from modules.astra.simulation.live_feed import LiveSimulationFeed
from modules.astra.tests.helpers import D0, TempDb
from modules.astra.voice.health_voice import to_speech
from modules.astra.voice.voice_alerts import VoiceAlerts, astra_is_speaking

NOW = D0 + timedelta(days=30, hours=10)  # 10:00 UTC


class FakeUI:
    def __init__(self):
        self.calls = []
        self._health_card_lines = ["Sağlık özeti yükleniyor..."]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args: self.calls.append((name, args))

    def logs(self):
        return [a[0] for n, a in self.calls if n == "write_log"]

    def count(self, name):
        return sum(1 for n, _ in self.calls if n == name)


class FakeKam:
    _is_speaking = False
    _paused = False


class BridgeCase(unittest.TestCase):
    def setUp(self):
        self.t = TempDb().__enter__()
        self.ui, self.kam, self.spoken = FakeUI(), FakeKam(), []
        self.clock = [NOW]
        self.bridge = AstraBridge(
            self.ui, self.kam, {"history_days": 30, "scenario": "normal", "mode": "simulation", "answer_voice": "local",
                                "astronaut": "SIM Astronot", "voice": "test", "mute_non_critical": False},
            db=self.t.db, speaker=self.spoken.append, clock=lambda: self.clock[0], synchronous_voice=True,
            settings_path=None)  # testler gerçek ayar dosyasına yazmaz

    def tearDown(self):
        self.t.__exit__()

    def at(self, delta):
        self.clock[0] = NOW + delta
        return self.clock[0]


class MonitorTest(BridgeCase):
    def test_normal_day_is_silent_and_updates_card(self):
        a = self.bridge.tick(NOW)
        self.assertEqual(a.level, 0)
        self.assertEqual(self.spoken, [])
        self.assertTrue(self.ui._health_card_lines[0].startswith("SİM · Seviye 0"))
        self.assertTrue(any("Radyasyon" in line for line in self.ui._health_card_lines))
        self.assertEqual(self.t.db.counts()["rejected_inputs"], 0)

    def test_multi_risk_alerts_are_spoken_repeated_and_acknowledged(self):
        self.bridge.tick(NOW)
        self.bridge.handle_tool("astra_simulation", {"scenario": "multi_risk"})
        a = self.bridge.tick(NOW)
        self.assertEqual(a.level, 3)
        self.assertTrue(self.spoken)
        self.assertTrue(self.spoken[0].startswith("Simülasyon. Uyarı, yüksek risk."))  # önce en yüksek seviye
        self.assertIn("onayla", self.spoken[0])
        self.assertEqual(self.ui.count("play_error_sfx"), 1)
        first = len(self.spoken)

        self.bridge.tick(NOW + timedelta(minutes=5))  # tekrar süresi dolmadı
        self.assertEqual(len(self.spoken), first)
        self.bridge.tick(NOW + timedelta(minutes=16))  # yalnızca kritik uyarı tekrarlanır
        self.assertEqual(len(self.spoken), first + 1)
        self.assertTrue(self.spoken[-1].startswith("Onaylanmamış uyarı tekrarı."))

        reply = self.bridge.handle_tool("astra_alerts", {"action": "acknowledge"})
        self.assertRegex(reply, r"^\d+ sağlık uyarısı onaylandı\.$")
        self.bridge.tick(NOW + timedelta(minutes=40))
        self.assertEqual(len(self.spoken), first + 1)

    def test_pause_silences_non_critical_but_not_critical(self):
        self.bridge.tick(NOW)
        self.kam._paused = True
        self.bridge.set_scenario("radiation_spike", NOW)
        self.bridge.tick(NOW)
        self.assertEqual(len(self.spoken), 1)  # yalnızca seviye 3 radyasyon uyarısı
        self.assertIn("doz hızı alarm eşiğinin üzerinde", self.spoken[0])
        self.kam._paused = False
        self.bridge.tick(NOW + timedelta(seconds=15))  # bekleyen seviye 2 uyarı kaybolmadı
        self.assertTrue(any("Dikkat." in s for s in self.spoken[1:]))

    def test_device_disconnect_is_announced(self):
        self.bridge.tick(NOW)
        self.bridge.set_scenario("sensor_disconnect", NOW)  # saat 09:00'dan beri kopuk
        self.bridge.tick(NOW)
        self.assertTrue(any("bağlantı kesik" in s for s in self.spoken))

    def test_risk_events_are_not_duplicated_every_minute(self):
        for minute in range(0, 10):
            self.bridge.tick(NOW + timedelta(minutes=minute))
        today = NOW.strftime("%Y-%m-%d")
        events = self.t.db.query("SELECT * FROM health_risk_events WHERE day_utc = ?", (today,))
        reports = self.t.db.query("SELECT * FROM health_reports WHERE day_utc = ?", (today,))
        self.assertEqual(len(events), 1)
        self.assertEqual(len(reports), 1)

    def test_day_rollover_writes_final_report_for_previous_day(self):
        self.bridge.tick(NOW.replace(hour=23, minute=59))
        self.bridge.tick(NOW + timedelta(days=1) - timedelta(hours=10) + timedelta(minutes=1))
        yesterday = NOW.strftime("%Y-%m-%d")
        reports = self.t.db.query("SELECT * FROM health_reports WHERE day_utc = ?", (yesterday,))
        self.assertTrue(any("Günlük adım: 7" in r["content"] for r in reports))

    def test_bridge_works_without_kam_or_ui(self):
        bridge = AstraBridge(None, None, {"history_days": 10, "voice": "test"}, db=self.t.db,
                             speaker=self.spoken.append, clock=lambda: NOW, synchronous_voice=True,
                             settings_path=None)
        self.assertIsNotNone(bridge.tick(NOW))
        self.assertTrue(bridge.handle_text("astra durum"))
        self.assertTrue(self.spoken)


class ToolAndTextTest(BridgeCase):
    def test_tool_reply_to_gemini_contains_no_health_data(self):
        for name, args in (("astra_health_status", {"period": "today"}), ("astra_health_status", {"period": "week"}),
                           ("astra_radiation_status", {}), ("astra_alerts", {"action": "list"})):
            with self.subTest(tool=name):
                reply = self.bridge.handle_tool(name, args)
                self.assertEqual(reply, GEMINI_REPLY)
                self.assertIsNone(re.search(r"\d", reply))
        self.assertEqual(len(self.spoken), 4)
        self.assertIn("seviye 0, normal", self.spoken[0])
        self.assertIn("Son 7 günde", self.spoken[1])
        self.assertIn("milisievert", self.spoken[2])
        self.assertEqual(self.t.db.counts()["access_log"], 3)

    def test_gemini_answer_mode_relays_result_without_local_voice(self):
        self.bridge.settings["answer_voice"] = "gemini"
        reply = self.bridge.handle_tool("astra_health_status", {"period": "today"})
        self.assertTrue(reply.startswith(GEMINI_RELAY))
        self.assertIn("Simülasyon verisi.", reply)
        self.assertIn("seviye 0, normal", reply)
        rad = self.bridge.handle_tool("astra_radiation_status", {})
        self.assertIn("milisievert", rad)
        self.assertEqual(self.spoken, [])  # Gemini okuyacak; yerel ses yok
        self.assertTrue(any(name == "show_health_hologram" for name, _ in self.ui.calls))
        self.bridge.handle_text("astra durum")  # yazılı komut internetsiz de çalışmalı: yerel ses
        self.assertEqual(len(self.spoken), 1)

    def test_unknown_inputs(self):
        self.assertIn("Bilinmeyen ASTRA aracı", self.bridge.handle_tool("astra_x", {}))
        self.assertIn("Bilinmeyen senaryo", self.bridge.handle_tool("astra_simulation", {"scenario": "yok"}))

    def test_text_commands_are_handled_locally(self):
        self.assertFalse(self.bridge.handle_text("hava durumu nasıl"))
        self.assertFalse(self.bridge.handle_text("astronotlar hakkında bilgi ver"))
        for command, expected in (("ASTRA durum", "Bugünkü sağlık değerlendirmen"),
                                  ("astra hafta", "Son 7 günde"),
                                  ("Astra radyasyon", "Radyasyon"),
                                  ("astra uyarılar", "Onay bekleyen sağlık uyarısı yok")):
            with self.subTest(command=command):
                self.assertTrue(self.bridge.handle_text(command))
                self.assertIn(expected, self.spoken[-1])
        self.assertTrue(self.bridge.handle_text("astra senaryo hrv_drop"))
        self.assertEqual(self.bridge.feed.scenario, "hrv_drop")
        self.assertTrue(self.bridge.handle_text("astra yardım"))
        self.assertIn("ASTRA komutları", self.ui.logs()[-1])

    def test_month_without_previous_period_says_so(self):
        self.bridge.handle_text("astra ay")
        self.assertIn("karşılaştırma yapamıyorum", self.spoken[-1])

    def test_device_mode_has_no_simulation(self):
        bridge = AstraBridge(None, None, {"mode": "device", "voice": "test"}, db=self.t.db,
                             speaker=self.spoken.append, clock=lambda: NOW, synchronous_voice=True,
                             settings_path=None)
        self.assertIsNone(bridge.feed)
        self.assertIn("gerçek cihaz", bridge.handle_tool("astra_simulation", {"scenario": "normal"}))
        bridge.handle_text("astra durum")
        self.assertIn("kayıtlı sağlık verisi yok", self.spoken[-1])

    def test_tool_declarations_shape(self):
        names = [d["name"] for d in ASTRA_TOOL_DECLARATIONS]
        self.assertEqual(len(names), len(set(names)))
        for d in ASTRA_TOOL_DECLARATIONS:
            self.assertTrue(d["name"].startswith("astra_"))
            self.assertEqual(d["parameters"]["type"], "OBJECT")
            for req in d["parameters"].get("required", []):
                self.assertIn(req, d["parameters"]["properties"])


class LiveFeedTest(unittest.TestCase):
    def test_only_due_records_are_written_and_faults_rejected_once(self):
        with TempDb() as t:
            feed = LiveSimulationFeed(t.db, t.aid, "faulty_measurement", history_days=3)
            feed.update(NOW)
            self.assertEqual(t.db.counts()["rejected_inputs"], 0)  # hatalı okumalar 11:05'te, henüz gelmedi
            last_hr = t.db.latest_measurement(t.aid, "heart_rate")["measured_at_utc"]
            self.assertLessEqual(last_hr, NOW.strftime("%Y-%m-%dT%H:%M:%SZ"))
            feed.update(NOW + timedelta(hours=2))
            self.assertEqual([r["day_utc"] for r in t.db.get_activity(t.aid)][-1],
                             (NOW - timedelta(days=1)).strftime("%Y-%m-%d"))  # bugünün özeti gün bitince
            rejected = t.db.counts()["rejected_inputs"]
            self.assertEqual(rejected, 3)
            feed.update(NOW + timedelta(hours=2, minutes=30))
            feed.update(NOW + timedelta(hours=3))
            self.assertEqual(t.db.counts()["rejected_inputs"], rejected)

    def test_restart_continues_without_duplicates_and_dose_is_continuous(self):
        with TempDb() as t:
            LiveSimulationFeed(t.db, t.aid, history_days=3).update(NOW)
            before = t.db.counts()["health_measurements"]
            LiveSimulationFeed(t.db, t.aid, history_days=3).update(NOW)  # KAM yeniden açıldı
            self.assertEqual(t.db.counts()["health_measurements"], before)
            doses = [r["cumulative_dose_msv"] for r in t.db.get_radiation(t.aid)]
            self.assertEqual(doses, sorted(doses))
            self.assertEqual(len(doses), 3 * 24 + 11)

    def test_scenario_change_replaces_only_today_simulated_data(self):
        with TempDb() as t:
            feed = LiveSimulationFeed(t.db, t.aid, history_days=3)
            feed.update(NOW)
            yesterday = len(t.db.get_measurements(t.aid, "heart_rate", end=NOW.replace(hour=0)))
            feed.set_scenario("hr_elevated", NOW)
            self.assertEqual(len(t.db.get_measurements(t.aid, "heart_rate", end=NOW.replace(hour=0))), yesterday)
            today = t.db.get_measurements(t.aid, "heart_rate", start=NOW.replace(hour=0))
            self.assertEqual(len(today), 61)  # 00:00–10:00, 10 dakikada bir
            self.assertGreater(sum(r["value"] for r in today) / len(today), 85)


class VoiceTest(unittest.TestCase):
    def test_to_speech(self):
        self.assertEqual(to_speech("Dinlenik kalp atış hızı: 70.4 bpm (yüzde +21)."),
                         "Dinlenik kalp atış hızı: 70,4 atım/dakika (yüzde artı 21).")
        self.assertEqual(to_speech("doz 0.48 mSv, hız 22 µSv/saat, SpO2 96.9 %, uyku 421 dk, HRV 49 ms"),
                         "doz 0,48 milisievert, hız 22 mikrosievert/saat, SpO2 yüzde 96,9, uyku 421 dakika, "
                         "HRV 49 milisaniye")
        self.assertTrue(to_speech("[SİMÜLASYON VERİSİ — gerçek ölçüm değildir]\nSatır").startswith("Simülasyon verisi."))

    def test_queue_waits_for_kam_and_speaks_highest_level_first(self):
        spoken, busy = [], threading.Event()
        flags = []

        def speak(text):
            flags.append(astra_is_speaking())
            spoken.append(text)

        voice = VoiceAlerts(speak, busy.is_set, quiet_seconds=0.2, max_wait_seconds=5)
        busy.set()  # KAM konuşuyor
        voice.say("bilgi", 1)
        voice.say("acil", 4)
        voice.say("acil", 4)  # aynı metin kuyruğa ikinci kez girmez
        time.sleep(0.5)
        self.assertEqual(spoken, [])
        busy.clear()
        deadline = time.time() + 5
        while len(spoken) < 2 and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(spoken, ["acil", "bilgi"])
        self.assertEqual(flags, [True, True])
        self.assertFalse(astra_is_speaking())

    def test_voice_choice_prefers_turkish_onecore(self):
        from modules.astra.voice.windows_tts import choose_voice
        onecore = [("Microsoft Zira", "en-US"), ("Microsoft Tolga", "tr-TR")]
        sapi = ["Microsoft Zira Desktop", "Microsoft David Desktop"]
        self.assertEqual(choose_voice("auto", "", onecore, sapi), ("onecore", "Microsoft Tolga", ""))
        # Türkçe ses yalnızca eski sistemde varsa
        self.assertEqual(choose_voice("auto", "", onecore[:1], ["Microsoft Tolga Desktop"])[:2],
                         ("sapi", "Microsoft Tolga Desktop"))
        # Hiç Türkçe ses yoksa varsayılan ses + kullanıcıya not
        engine, voice, note = choose_voice("auto", "", onecore[:1], sapi)
        self.assertEqual((engine, voice), ("sapi", ""))
        self.assertIn("Türkçe Windows sesi bulunamadı", note)
        # Kullanıcının seçtiği motor ve ses
        self.assertEqual(choose_voice("sapi", "Zira", onecore, sapi)[:2], ("sapi", "Zira"))
        self.assertEqual(choose_voice("onecore", "", [], sapi)[0], "sapi")  # yeni sistem okunamadı

    def test_speaker_falls_back_to_kam_voice_once(self):
        import sys
        import types
        from unittest import mock
        from modules.astra.voice import voice_alerts, windows_tts
        calls, errors = [], []
        fake = types.ModuleType("actions.windows_utils")
        fake.speak_with_windows = lambda text, voice="": (calls.append(("sapi", text, voice)), (True, "ok"))[1]
        pkg = types.ModuleType("actions"); pkg.windows_utils = fake
        with mock.patch.dict(sys.modules, {"actions": pkg, "actions.windows_utils": fake}), \
                mock.patch.object(windows_tts, "speak_onecore",
                                  side_effect=lambda t, v="": (calls.append(("onecore", t, v)), (False, "WinRT yok"))[1]):
            speak = voice_alerts.make_speaker("onecore", "Microsoft Tolga", on_error=errors.append)
            speak("bir")
            speak("iki")
        self.assertEqual(calls, [("onecore", "bir", "Microsoft Tolga"), ("sapi", "bir", ""), ("sapi", "iki", "")])
        self.assertEqual(len(errors), 1)
        self.assertIn("WinRT yok", errors[0])

    def test_panel_lines_are_short(self):
        with TempDb() as t:
            core = t.core()
            a = core.engine.assess(t.aid, t.simulate(31, "multi_risk", 1))
            for line in display.daily_lines(a).splitlines():
                if ":" in line:
                    label, value = line.split(":", 1)
                    self.assertLessEqual(len(label), 22, line)
                    self.assertLessEqual(len(value.strip()), 30, line)
                else:
                    self.assertLessEqual(len(line), 50, line)


if __name__ == "__main__":
    unittest.main()
