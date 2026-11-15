"""Holografik astronot kıyafeti testleri (Pillow gerekir; Tkinter penceresi burada açılmaz)."""

import importlib.util
import unittest
from datetime import timedelta

from modules.astra.tests.helpers import TempDb
from modules.astra.tests.test_bridge import NOW, BridgeCase

HAS_PIL = importlib.util.find_spec("PIL") is not None


class FakeHologram:
    def __init__(self):
        self.shown = []

    def show(self, frames, title, level, text, simulated, auto_close_ms=30000):
        self.shown.append({"frames": len(frames), "title": title, "level": level, "text": text, "sim": simulated})


@unittest.skipUnless(HAS_PIL, "Pillow yüklü değil")
class ZoneTest(unittest.TestCase):
    def test_zone_levels_follow_findings(self):
        from modules.astra.ui.hologram import zone_states
        with TempDb() as t:
            normal = zone_states(t.core().engine.assess(t.aid, t.simulate(31)))
        self.assertEqual(normal, {"head": 0, "heart": 0, "lungs": 0, "skin": 0, "legs": 0, "suit": 0})
        with TempDb() as t:
            risk = zone_states(t.core().engine.assess(t.aid, t.simulate(31, "multi_risk", 1)))
        self.assertEqual(risk["heart"], 2)
        self.assertEqual(risk["head"], 2)  # uyku ve stres
        self.assertEqual((risk["lungs"], risk["suit"]), (0, 0))
        with TempDb() as t:
            rad = zone_states(t.core().engine.assess(t.aid, t.simulate(31, "radiation_spike", 1)))
        self.assertEqual(rad["suit"], 3)
        with TempDb() as t:
            missing = zone_states(t.core().engine.assess(t.aid, t.simulate(31, "missing_data", 1)))
        self.assertIsNone(missing["lungs"])  # SpO2 verisi yok → gri

    def test_frames_render(self):
        from modules.astra.ui.hologram import H, W, render_frames
        frames = render_frames({"head": 0, "heart": 4, "lungs": None, "skin": 1, "legs": 0, "suit": 2}, 4, True,
                               count=6)
        self.assertEqual(len(frames), 6)
        self.assertEqual(frames[0].size, (W, H))
        self.assertEqual(frames[0].mode, "RGB")
        self.assertNotEqual(frames[0].tobytes(), frames[3].tobytes())  # dönüyor


@unittest.skipUnless(HAS_PIL, "Pillow yüklü değil")
class BridgeHologramTest(BridgeCase):
    def setUp(self):
        super().setUp()
        self.holo = FakeHologram()
        self.bridge.hologram = self.holo

    def test_opens_on_health_questions(self):
        self.bridge.handle_tool("astra_health_status", {"period": "today"})
        self.bridge.handle_tool("astra_health_status", {"period": "week"})
        self.bridge.handle_tool("astra_radiation_status", {})
        self.bridge.handle_text("astra hologram")
        titles = [s["title"] for s in self.holo.shown]
        self.assertEqual(titles, ["GÜNLÜK SAĞLIK ANALİZİ", "SON 7 GÜN", "RADYASYON DURUMU",
                                  "GÜNLÜK SAĞLIK ANALİZİ"])
        self.assertTrue(all(s["frames"] == 36 and s["sim"] for s in self.holo.shown))
        self.assertIn("Bu değerlendirme tıbbi teşhis değildir.", self.holo.shown[0]["text"])

    def test_opens_on_alerts_level_two_and_up_only(self):
        self.bridge.tick(NOW)
        self.assertEqual(self.holo.shown, [])  # normal gün: açılmaz
        self.bridge.set_scenario("multi_risk", NOW)
        self.bridge.tick(NOW)
        levels = [s["level"] for s in self.holo.shown if s["title"] == "SAĞLIK UYARISI"]
        self.assertTrue(levels)
        self.assertEqual(max(levels), 3)
        self.assertTrue(all(level >= 2 for level in levels))

    def test_disabled_in_settings_or_without_tk_root(self):
        from modules.astra.kam_bridge import AstraBridge
        bridge = AstraBridge(self.ui, None, {"voice": "test", "hologram": False}, db=self.t.db,
                             speaker=self.spoken.append, clock=lambda: NOW, synchronous_voice=True,
                             settings_path=None)
        self.assertIsNone(bridge.hologram)
        self.assertIsNone(self.bridge._make_hologram())  # sahte arayüzde Tk penceresi yok
        bridge.handle_text("astra hologram")
        self.assertIn("hologram penceresi kullanılamıyor", self.ui.logs()[-1])


class FakeCanvas:
    """Tk tuvali yerine çizim çağrılarını kaydeder."""

    def __init__(self):
        self.items, self.bindings = [], {}

    def create_image(self, x, y, **kw):
        self.items.append(("image", x, y, kw))

    def create_text(self, x, y, **kw):
        self.items.append(("text", x, y, kw))

    def tag_bind(self, tag, event, fn):
        self.bindings[(tag, event)] = fn

    def configure(self, **kw):
        pass

    def texts(self):
        return [kw["text"] for kind, _, _, kw in self.items if kind == "text"]


@unittest.skipUnless(HAS_PIL, "Pillow yüklü değil")
class HealthCardTest(BridgeCase):
    def make(self, **settings):
        from modules.astra.kam_bridge import AstraBridge
        self.ui.health_card_drawer = None  # yamalı ui.py'deki bağlantı noktası
        base = {"voice": "test", "history_days": 30, "answer_voice": "local"}
        bridge = AstraBridge(self.ui, None, {**base, **settings}, db=self.t.db, speaker=self.spoken.append,
                             clock=lambda: NOW, synchronous_voice=True, settings_path=None)
        bridge.hologram = FakeHologram()
        if bridge.main_hologram:
            bridge.main_hologram.to_photo = lambda image: image  # Tk olmadan
        return bridge

    def draw(self, bridge, w=342, h=320):
        import time as _time
        canvas = FakeCanvas()  # KAM'da tuval hep aynıdır; her karede öğeler yeniden çizilir
        card = bridge.main_hologram
        bridge.ui.health_card_drawer(canvas, 10, 600, w, h, 14, False)  # ilk çizim kareleri başlatır
        deadline = _time.time() + 10
        while not any(k == "image" for k, *_ in canvas.items) and _time.time() < deadline:
            _time.sleep(0.1)
            canvas.items = []
            bridge.ui.health_card_drawer(canvas, 10, 600, w, h, 14, False)
        return canvas, card

    def test_turntable_frames(self):
        from modules.astra.ui.hologram import render_turntable
        frames = render_turntable(0, 200, 270, count=8)
        self.assertEqual(len(frames), 8)
        self.assertEqual((frames[0].size, frames[0].mode), ((200, 270), "RGBA"))
        self.assertEqual(frames[0].getpixel((0, 0))[3], 0)  # saydam arka plan
        self.assertNotEqual(frames[0].tobytes(), frames[2].tobytes())  # dönüyor
        red = render_turntable(3, 200, 270, count=8)[0].convert("RGB").getpixel((100, 120))
        self.assertGreater(red[0], red[1])  # yüksek riskte kırmızı

    def test_card_replaces_old_body_hologram_and_shows_astra_analysis(self):
        bridge = self.make()
        self.assertIs(self.ui.health_card_drawer.__self__, bridge.main_hologram)
        bridge.tick(NOW)
        canvas, card = self.draw(bridge)
        image = next(item for item in canvas.items if item[0] == "image")
        w, h = card.size_for(342, 320)
        self.assertGreater(w, 130)  # KAM'ın eski vücut hologramı 130×180 idi
        self.assertGreater(h, 180)
        self.assertLessEqual(image[1] + w, 10 + 342)  # kartın içinde
        texts = canvas.texts()
        self.assertEqual(texts[:2], ["SİM · SEVİYE 0", "NORMAL"])
        self.assertTrue(any(t.startswith("• Dinlenik nabız") for t in texts))
        self.assertTrue(any(t.startswith("• Radyasyon %") for t in texts))
        self.assertIn("▸ analiz için tıkla", texts)

    def test_card_follows_risk_and_lists_findings(self):
        bridge = self.make()
        bridge.tick(NOW)
        bridge.set_scenario("multi_risk", NOW)
        bridge.tick(NOW + timedelta(seconds=1))
        canvas, card = self.draw(bridge)
        texts = canvas.texts()
        self.assertEqual(texts[:2], ["SİM · SEVİYE 3", "YÜKSEK RİSK"])
        self.assertTrue(any(t.startswith("Çoklu gösterge") or t.startswith("▲") or t.startswith("▼")
                            for t in texts[2:4]))
        self.assertEqual(card._photo_key[0], 3)  # kırmızı kareler

    def test_click_opens_analysis_window(self):
        bridge = self.make()
        canvas, _ = self.draw(bridge)
        bridge.main_hologram.on_click()
        bridge.handle_text("astra analiz")
        self.assertEqual([s["title"] for s in bridge.hologram.shown], ["GÜNLÜK SAĞLIK ANALİZİ"] * 2)
        self.assertIn(("astra_health_card", "<Button-1>"), canvas.bindings)

    def test_old_health_overlay_not_opened_when_window_available(self):
        bridge = self.make()
        bridge.handle_tool("astra_health_status", {"period": "today"})
        self.assertFalse(any(name == "show_health_hologram" for name, _ in self.ui.calls))

    def test_not_used_when_disabled_or_ui_has_no_hook(self):
        self.assertIsNone(self.make(main_hologram=False).main_hologram)
        self.assertIsNone(self.bridge.main_hologram)  # sahte arayüzde bağlantı noktası yok

    def test_saglik_analizi_phrase_offline_is_handled_locally(self):
        bridge = self.make()
        self.assertTrue(bridge.handle_text("Sağlık analizi yap"))  # Gemini bağlı değil
        self.assertIn("Bugünkü sağlık değerlendirmen", self.spoken[-1])
        self.assertEqual(bridge.hologram.shown[-1]["title"], "GÜNLÜK SAĞLIK ANALİZİ")
        bridge.kam = type("Kam", (), {"session": object(), "_loop": object(), "_is_speaking": False})()
        self.assertFalse(bridge.handle_text("Sağlık analizi yap"))  # bağlıyken Gemini'ye gider

    def test_size_for_common_screens(self):
        from modules.astra.ui.main_hologram import HealthCardHologram
        for card_w, card_h in ((342, 348), (342, 276), (296, 200)):
            w, h = HealthCardHologram.size_for(card_w, card_h)
            self.assertLessEqual(w, card_w * 0.6)
            self.assertGreaterEqual(card_w - w - 6 - 14, 100)  # yazıya yer kalıyor
            self.assertLessEqual(h, card_h - 42)
            self.assertEqual((w % 10, h % 20), (0, 0))


if __name__ == "__main__":
    unittest.main()
