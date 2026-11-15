"""
KAM ↔ ASTRA köprüsü.

main.py yalnızca bu dosyayı kullanır:
  - ASTRA_TOOL_DECLARATIONS : Gemini'ye eklenen sağlık araçları
  - start_astra(ui, kam)     : köprüyü kurar ve arka plan izlemesini başlatır
  - AstraBridge.handle_tool  : Gemini araç çağrısını yanıtlar
  - AstraBridge.handle_text  : "astra ..." ile başlayan yazılı komutları yerel olarak yanıtlar
  - astra_is_speaking        : ASTRA konuşurken mikrofonun Gemini'ye gönderilmemesi için

Ses kararı (kullanıcı, 15.11.2026): Soru cevaplarını Gemini okur (answer_voice="gemini");
bu kipte sorulan sağlık sonucu Gemini'ye gider. answer_voice="local" seçilirse sağlık verisi
Gemini'ye gitmez, cevap Windows sesiyle okunur. Kendiliğinden uyarılar ve "astra ..."
yazılı komutları her zaman yerel olarak okunur. İzleme ve sesli uyarılar kendi iş parçacığında çalışır;
internet veya Gemini bağlantısı kesilse de sürer.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import display, get_astra_logger
from .alert_manager import LEVEL_NAMES
from .astra_core import AstraCore
from .health_analyzer import INDICATORS
from .health_database import HealthDatabase
from .health_reports import daily_report
from .manual_entry import build_measurements, describe
from .models import InvalidDataError, utc_now
from .radiation.radiation_analyzer import assess_radiation
from .risk_engine import RiskAssessment, day_start
from .simulation.live_feed import LiveSimulationFeed
from .simulation.mission_scenarios import SCENARIOS
from .voice import health_voice
from .voice.voice_alerts import VoiceAlerts, astra_is_speaking, make_speaker
from .voice.windows_tts import choose_voice, onecore_voices, sapi_voices

SETTINGS_PATH = Path(__file__).resolve().parent / "config" / "astra_settings.json"
DEFAULT_SETTINGS = {
    "enabled": True,
    "mode": "simulation",          # "simulation" veya "device" (gerçek cihaz verisi)
    "astronaut": "SIM Astronot",
    "scenario": "normal",          # canlı simülasyonun bugünkü senaryosu
    "history_days": 60,            # ilk açılışta üretilecek geçmiş simülasyon günü
    "check_interval_seconds": 60,  # risk değerlendirme aralığı
    "notify_interval_seconds": 15, # uyarı kuyruğu kontrol aralığı
    "answer_voice": "gemini",      # soru cevapları: "gemini" (Gemini okur, veri Gemini'ye gider) | "local"
    "voice_engine": "auto",        # "auto" | "onecore" (yeni Windows sesleri) | "sapi" (KAM'ın mevcut sesi)
    "voice": "",                   # boşsa yüklü Türkçe Windows sesi aranır
    "mute_non_critical": False,    # True: seviye 1–2 sesli okunmaz (kritikler her zaman okunur)
    "manual_device": "SK27 (elle giriş)",  # elle girilen ölçümlerin kaynak cihaz adı
    "manual_quality": 0.7,         # elle girilen ölçümlerin güvenilirliği (0–1)
    "continuous_data": False,      # gerçek kipte sürekli veri akışı var mı (yoksa "veri eski" uyarısı verilmez)
    "hologram": True,              # analizde ve uyarılarda holografik astronot penceresi açılsın
    "main_hologram": True,         # KAM ana ekranındaki "SAĞLIK ÖZETİ" kartını ASTRA çizsin (dönen astronot + analiz)
}

GEMINI_RELAY = ("Aşağıdaki ASTRA sonucunu kullanıcıya doğal Türkçe ile, anlamını ve sayıları değiştirmeden "
                "aktar. Yeni değer, yorum, tahmin veya teşhis ekleme; risk seviyesini değiştirme.\n\n")
GEMINI_REPLY = ("ASTRA sonucu kullanıcıya yerel olarak sesli okunuyor ve ekranda gösteriliyor. "
                "Gizlilik gereği sağlık verisi bu yanıtta paylaşılmaz. Kullanıcıya yalnızca kısaca "
                "'ASTRA raporunu okuyor' de; değer tahmin etme, yorum veya teşhis ekleme.")

ASTRA_TOOL_DECLARATIONS = [
    {
        "name": "astra_health_status",
        "description": (
            "KAM ASTRA sağlık modülü. Astronotun sağlık durumunu kayıtlı ölçümlere ve kural tabanlı risk "
            "motoruna göre değerlendirir ve ekranda gösterir; yanıttaki talimata uy. "
            "Kullanıcı sağlık durumunu, kalp atışı, HRV, oksijen, uyku, aktivite veya stres durumunu, "
            "ya da son 7 / 30 gündeki değişimlerini sorduğunda çağır."),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "period": {"type": "STRING",
                           "description": "today (bugün) | week (son 7 gün) | month (son 30 gün)"}
            },
            "required": ["period"],
        },
    },
    {
        "name": "astra_radiation_status",
        "description": ("KAM ASTRA radyasyon durumu: dozimetreden gelen günlük ve görev boyunca biriken dozu "
                        "verir; yanıttaki talimata uy. Kullanıcı radyasyon durumunu sorduğunda çağır."),
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "astra_alerts",
        "description": ("KAM ASTRA sağlık uyarıları. action=list bekleyen uyarıları okur; action=acknowledge "
                        "kullanıcı uyarıyı aldığını söylediğinde ('tamam', 'uyarıyı onayla', 'anladım') "
                        "bekleyen tüm sağlık uyarılarını onaylar."),
        "parameters": {
            "type": "OBJECT",
            "properties": {"action": {"type": "STRING", "description": "list | acknowledge"}},
            "required": ["action"],
        },
    },
    {
        "name": "astra_record_measurement",
        "description": ("KAM ASTRA elle ölçüm girişi. Kullanıcı saatinde gördüğü bir değeri söyleyip kaydetmeni "
                        "istediğinde çağır (ör. 'nabzım 72, kaydet'). metric: nabız, dinlenik nabız, spo2, hrv, "
                        "tansiyon, sıcaklık, kilo, stres, ruh hali, yorgunluk, motivasyon. Tansiyon için value "
                        "'120/80' biçiminde. Değeri asla kendin uydurma; yalnızca kullanıcının söylediğini gir."),
        "parameters": {
            "type": "OBJECT",
            "properties": {"metric": {"type": "STRING", "description": "ölçüm adı"},
                           "value": {"type": "STRING", "description": "kullanıcının söylediği değer"}},
            "required": ["metric", "value"],
        },
    },
    {
        "name": "astra_mode",
        "description": ("KAM ASTRA veri kipini değiştirir: device = gerçek ölçümler (elle girilenler dahil), "
                        "simulation = test amaçlı simülasyon verisi."),
        "parameters": {
            "type": "OBJECT",
            "properties": {"mode": {"type": "STRING", "description": "device | simulation"}},
            "required": ["mode"],
        },
    },
    {
        "name": "astra_simulation",
        "description": ("KAM ASTRA simülasyon senaryosunu değiştirir (yalnızca test amaçlı simülasyon verisi). "
                        "Senaryolar: " + ", ".join(SCENARIOS) + "."),
        "parameters": {
            "type": "OBJECT",
            "properties": {"scenario": {"type": "STRING", "description": "senaryo adı"}},
            "required": ["scenario"],
        },
    },
]

_TEXT_HELP = ("ASTRA komutları: 'astra durum', 'astra hafta', 'astra ay', 'astra radyasyon', "
              "'astra uyarılar', 'astra onay', 'astra ölçüm nabız 72', 'astra ölçüm tansiyon 120/80', "
              "'astra kip gerçek', 'astra kip simülasyon', 'astra analiz', 'astra senaryo <ad>', 'astra senaryolar'.")


def load_settings(path: Path = SETTINGS_PATH) -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        if path.exists():
            settings.update(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        get_astra_logger().warning("astra_settings.json okunamadı, varsayılanlar kullanılıyor: %s", exc)
    return settings


def _normalize(text: str) -> str:
    text = (text or "").replace("İ", "i").replace("I", "ı").lower()
    for a, b in (("ı", "i"), ("ğ", "g"), ("ü", "u"), ("ş", "s"), ("ö", "o"), ("ç", "c")):
        text = text.replace(a, b)
    return " ".join(text.split())


class AstraBridge:
    def __init__(self, ui=None, kam=None, settings: dict | None = None, db: HealthDatabase | None = None,
                 speaker: Callable[[str], None] | None = None, clock: Callable[[], datetime] = utc_now,
                 synchronous_voice: bool = False, settings_path: Path | None = SETTINGS_PATH):
        self.settings_path = settings_path  # kip değişikliği buraya kaydedilir (None: kaydetme)
        self.settings = {**load_settings(), **(settings or {})}
        self.ui = ui
        self.kam = kam
        self.clock = clock
        self.simulated = self.settings["mode"] != "device"
        self.db = db or HealthDatabase()
        self.core = AstraCore(self.db, self.simulated)
        self.astronaut_id = self.db.add_astronaut(self.settings["astronaut"])
        self.feed = (LiveSimulationFeed(self.db, self.astronaut_id, self.settings["scenario"],
                                        int(self.settings["history_days"])) if self.simulated else None)
        self._log = get_astra_logger()
        if speaker is None:
            engine, voice, note = choose_voice(self.settings.get("voice_engine", "auto"), self.settings["voice"],
                                               onecore_voices(), sapi_voices())
            self._log.info("ASTRA ses seçimi: motor=%s ses=%s", engine, voice or "(varsayılan)")
            if note:
                self._ui_log(note)
            speaker = make_speaker(engine, voice)
        self.voice = VoiceAlerts(speaker, self._kam_busy, synchronous=synchronous_voice)
        self._lock = threading.RLock()
        self._last_eval: datetime | None = None
        self._current_day: datetime | None = None
        self.last_assessment: RiskAssessment | None = None
        self._thread: threading.Thread | None = None
        self._hologram_sync = synchronous_voice  # testlerde hologram kareleri aynı iş parçacığında üretilir
        self.hologram = self._make_hologram()
        self.main_hologram = self._make_main_hologram()
        self._stop = threading.Event()

    # ── KAM / arayüz yardımcıları ────────────────────────────────────────
    def _kam_busy(self) -> bool:
        return bool(getattr(self.kam, "_is_speaking", False))

    def _ui_call(self, method: str, *args) -> None:
        fn = getattr(self.ui, method, None)
        if fn is None:
            return
        try:
            fn(*args)
        except Exception as exc:
            self._log.warning("ASTRA arayüz çağrısı başarısız (%s): %s", method, exc)

    def _ui_log(self, text: str) -> None:
        self._ui_call("write_log", text)

    def _show(self, title: str, text: str) -> None:
        """KAM'ın eski sağlık panelini yalnızca ASTRA penceresi kullanılamıyorsa açar."""
        if self.hologram is None:
            self._ui_call("show_health_hologram", title, text)

    def _respond(self, panel_text: str, spoken: str, level: int = 1, delay: float = 0.0,
                 local_voice: bool = True) -> str:
        """Paneli günceller, yanıtı sohbet günlüğüne yazar; local_voice ise yerel olarak seslendirir."""
        self._show("astra", panel_text)
        self._ui_log("ASTRA: " + spoken)
        if local_voice:
            self.voice.say(spoken, level, delay)
        return spoken

    # ── Arka plan izleme ─────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="ASTRA-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        mode = "SİMÜLASYON" if self.simulated else "CİHAZ"
        self._ui_log(f"ASTRA: Sağlık izleme başladı ({mode} verisi).")
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # izleme asla KAM'ı düşürmemeli
                self._log.exception("ASTRA izleme hatası: %s", exc)
            self._stop.wait(float(self.settings["notify_interval_seconds"]))

    def tick(self, now: datetime | None = None) -> RiskAssessment | None:
        now = now or self.clock()
        with self._lock:
            interval = float(self.settings["check_interval_seconds"])
            if self._last_eval is None or (now - self._last_eval).total_seconds() >= interval:
                if self.feed:
                    self.feed.update(now)
                today = day_start(now)
                if self._current_day is not None and self._current_day < today:
                    self.core.evaluate(self.astronaut_id, self._current_day, now=now,
                                       force_report=True)  # biten günün son raporu
                self._current_day = today
                # "Veri eski / bugün veri yok" denetimi yalnızca sürekli veri akışı varsa anlamlıdır
                live = self.simulated or bool(self.settings.get("continuous_data", False))
                self.last_assessment = self.core.evaluate(self.astronaut_id, today, now=now, live=live)
                self._last_eval = now
                self._update_card(self.last_assessment)
            paused = bool(getattr(self.kam, "_paused", False))
            self.core.alerts.muted = bool(self.settings["mute_non_critical"]) or paused
            for alert in self.core.alerts.due_notifications(self.astronaut_id, now):
                self._announce(alert)
            return self.last_assessment

    def _make_hologram(self):
        """KAM arayüzü (Tk) varsa hologram penceresini hazırlar; yoksa None."""
        if not self.settings.get("hologram", True) or self.ui is None:
            return None
        try:
            import tkinter
        except ImportError:  # arayüzsüz ortam (ör. testler)
            return None
        try:
            root = getattr(self.ui, "root", None)
            if not isinstance(root, tkinter.Misc):
                return None
            from .ui.astra_dashboard import HologramWindow

            return HologramWindow(root, on_ack=lambda: self.acknowledge_all(self.clock()))
        except Exception as exc:
            self._log.warning("ASTRA hologram penceresi hazırlanamadı: %s", exc)
            return None

    def _make_main_hologram(self):
        """KAM ana ekranı destekliyorsa (ui.health_card_drawer) "SAĞLIK ÖZETİ" kartını ASTRA'ya verir."""
        if not self.settings.get("main_hologram", True) or self.ui is None:
            return None
        if "health_card_drawer" not in vars(self.ui):  # ui.py'de bağlantı noktası yok
            return None
        try:
            from .ui.main_hologram import HealthCardHologram

            holo = HealthCardHologram(self.ui, on_click=self.open_analysis)
            holo.set_state(0, self.simulated, [], ["Sağlık verisi yükleniyor..."])
            self.ui.health_card_drawer = holo.draw_card
            return holo
        except Exception as exc:
            self._log.warning("ASTRA ana ekran hologramı eklenemedi: %s", exc)
            return None

    def open_analysis(self) -> None:
        """Günün sağlık analizini hologram penceresinde açar (ana ekrandaki hologram tıklanınca)."""
        try:
            now = self.clock()
            with self._lock:
                if self.feed:
                    self.feed.update(now)
                a = self.core.engine.assess(self.astronaut_id, now, now)
            if self.hologram is None:
                self._ui_log("ASTRA: hologram penceresi kullanılamıyor (ayarlarda kapalı ya da arayüz yok).")
            self._open_hologram(a, "GÜNLÜK SAĞLIK ANALİZİ", daily_report(a))
            self.db.log_access("kam", "open_analysis")
        except Exception as exc:
            self._log.exception("ASTRA analiz penceresi açılamadı: %s", exc)

    def _open_hologram(self, a: RiskAssessment, title: str, text: str, level: int | None = None) -> None:
        """Holografik astronot kıyafetini analiz metniyle birlikte açar (kareler arka planda çizilir)."""
        if self.hologram is None or a is None:
            return
        level = a.level if level is None else level

        def work():
            try:
                from .ui.hologram import render_frames, zone_states

                frames = render_frames(zone_states(a), level, a.is_simulated)
                self.hologram.show(frames, title, level, text, a.is_simulated)
            except Exception as exc:
                self._log.warning("ASTRA hologramı çizilemedi: %s", exc)

        if self._hologram_sync:
            work()
        else:
            threading.Thread(target=work, name="ASTRA-hologram", daemon=True).start()

    def _announce(self, alert: dict) -> None:
        level = alert["level"]
        text = alert["message"]
        if level >= 3:
            text += " Uyarıyı aldığında KAM'a uyarıları onayla de."
        if alert["notify_count"] > 1:
            text = "Onaylanmamış uyarı tekrarı. " + text
        self._ui_log(f"ASTRA [{LEVEL_NAMES[level]}]: {alert['message']}")
        if level >= 2:
            self._show("astra", display.alert_lines([alert]))
            self._ui_call("focus_panel", "health", 8000)
            self._open_hologram(self.last_assessment, "SAĞLIK UYARISI", alert["message"], level)
        if level >= 3:
            self._ui_call("play_error_sfx")
        if level >= 2 or alert["category"] != "data":
            self.voice.say(health_voice.to_speech(text), level)

    def _update_card(self, a: RiskAssessment) -> None:
        """Arayüzdeki 'SAĞLIK ÖZETİ' kartı (en fazla 5 satır) ve ana ekran hologramının rengi."""
        if self.main_hologram is not None:
            self.main_hologram.set_state(a.level, a.is_simulated, display.card_findings(a), display.card_values(a))
        if self.ui is None:
            return
        v = a.summary.values
        tag = "SİM · " if a.is_simulated else ""
        lines = [f"{tag}Seviye {a.level} · {LEVEL_NAMES[a.level]}"]
        if "resting_hr" in v or "heart_rate_mean" in v:
            parts = []
            if "resting_hr" in v:
                parts.append(f"Dinlenik {v['resting_hr']:.0f}")
            if "heart_rate_mean" in v:
                parts.append(f"Ort. {v['heart_rate_mean']:.0f} bpm")
            lines.append("Nabız " + " · ".join(parts))
        if "hrv_rmssd" in v or "spo2_mean" in v:
            lines.append(" · ".join(x for x in (
                f"HRV {v['hrv_rmssd']:.0f} ms" if "hrv_rmssd" in v else "",
                f"SpO2 %{v['spo2_mean']:.0f}" if "spo2_mean" in v else "") if x))
        if "sleep_total_min" in v:
            total = int(v["sleep_total_min"])
            lines.append(f"Uyku {total // 60} sa {total % 60} dk")
        if a.radiation.has_data:
            lines.append(f"Radyasyon: görev sınırının %{a.radiation.pct_of_mission_limit:.0f}")
        if len(lines) == 1:
            lines.append("Bugün için sağlık verisi yok")
        try:
            self.ui._health_card_lines = lines[:5]
        except Exception:
            pass

    # ── Yanıtlar ─────────────────────────────────────────────────────────
    def _health(self, period: str, now: datetime, delay: float, local_voice: bool = True) -> str:
        with self._lock:
            if self.feed:
                self.feed.update(now)
            if period in ("week", "month"):
                days = 7 if period == "week" else 30
                thresholds = {k: v["pct_info"] for k, v in self.core.engine.config["indicators"].items()}
                comparison = self.core.engine.analyzer.period_comparison(self.astronaut_id, now, days)
                spoken = health_voice.spoken_period(comparison, days, self.simulated, thresholds)
                result = self._respond(display.period_lines(comparison, days, self.simulated), spoken,
                                       delay=delay, local_voice=local_voice)
                self._open_hologram(self.core.engine.assess(self.astronaut_id, now, now), f"SON {days} GÜN",
                                    self.core.period_report(self.astronaut_id, now, days))
            else:
                a = self.core.engine.assess(self.astronaut_id, now, now)
                result = self._respond(display.daily_lines(a), health_voice.spoken_daily(a), max(a.level, 1),
                                       delay, local_voice)
                self._open_hologram(a, "GÜNLÜK SAĞLIK ANALİZİ", daily_report(a))
        self.db.log_access("kam", "health_status", period)
        return result

    def _radiation(self, now: datetime, delay: float, local_voice: bool = True) -> str:
        with self._lock:
            if self.feed:
                self.feed.update(now)
            text = self.core.radiation_report(self.astronaut_id, now)
            status = assess_radiation(self.db, self.astronaut_id, day_start(now), self.simulated,
                                      self.core.engine.config["radiation"])
        result = self._respond(display.radiation_lines(status, now, self.simulated), health_voice.to_speech(text),
                               max(status.level, 1), delay, local_voice)
        self._open_hologram(self.core.engine.assess(self.astronaut_id, now, now), "RADYASYON DURUMU", text,
                            status.level)
        self.db.log_access("kam", "radiation_status")
        return result

    def _alerts_list(self, delay: float, local_voice: bool = True) -> str:
        active = self.core.alerts.active(self.astronaut_id)
        result = self._respond(display.alert_lines(active), health_voice.spoken_alerts(active), delay=delay,
                               local_voice=local_voice)
        text = "\n\n".join(f"[{LEVEL_NAMES[x['level']]}] {x['message']}" for x in active) or \
            "Onay bekleyen sağlık uyarısı yok."
        self._open_hologram(self.last_assessment or self.core.engine.assess(self.astronaut_id, self.clock()),
                            "BEKLEYEN UYARILAR", text, max((x["level"] for x in active), default=0))
        return result

    def acknowledge_all(self, now: datetime) -> int:
        count = sum(self.core.alerts.acknowledge(a["id"], now) for a in self.core.alerts.active(self.astronaut_id))
        self._ui_log(f"ASTRA: {count} sağlık uyarısı onaylandı.")
        self.db.log_access("kam", "acknowledge_alerts", str(count))
        return count

    def set_scenario(self, scenario: str, now: datetime) -> str:
        if not self.feed:
            return "ASTRA gerçek cihaz kipinde; simülasyon senaryosu değiştirilemez."
        if scenario not in SCENARIOS:
            return "Bilinmeyen senaryo. Senaryolar: " + ", ".join(SCENARIOS) + "."
        with self._lock:
            self.feed.set_scenario(scenario, now)
            self._last_eval = None  # sonraki turda hemen değerlendir
        message = f"Simülasyon senaryosu '{scenario}' ({SCENARIOS[scenario].description}) olarak ayarlandı."
        self._ui_log("ASTRA: " + message)
        return message

    def record_manual(self, metric: str, value: str, now: datetime) -> str:
        """Elle girilen ölçümü kaydeder; kullanıcıya gösterilecek/okunacak mesajı döndürür."""
        try:
            records = build_measurements(self.astronaut_id, metric, value, now, self.settings["manual_device"],
                                         float(self.settings["manual_quality"]))
            with self._lock:
                for record in records:
                    self.db.add(record, now)
                self._last_eval = None  # sonraki turda hemen yeniden değerlendir
        except InvalidDataError as exc:
            return f"Ölçüm kaydedilmedi: {exc}."
        self.db.log_access("kam", "manual_entry", ",".join(r.metric for r in records))
        parts = [f"Kaydedildi: {describe(records)} (elle giriş, {self.settings['manual_device']})."]
        warning = self._threshold_warning(records)
        if warning:
            parts.append(warning)
        if self.simulated:
            parts.append("Not: ASTRA şu an simülasyon kipinde; bu ölçüm değerlendirmeye girmez. "
                         "Gerçek verinle çalışmak için 'astra kip gerçek' yaz.")
        return " ".join(parts)

    def _threshold_warning(self, records) -> str:
        """Tek elle ölçüm alarm üretmez; protokol eşiğini geçiyorsa yeniden ölçüm istenir."""
        for record in records:
            for rule in self.core.engine.config["absolute_rules"]:
                if rule["metric"] != record.metric:
                    continue
                crossed = (record.value < rule["threshold"] if rule["direction"] == "below"
                           else record.value > rule["threshold"])
                if crossed:
                    side = "altında" if rule["direction"] == "below" else "üzerinde"
                    return (f"Bu değer {rule['label'].lower()} protokol eşiğinin ({rule['threshold']}) {side}. "
                            "Ölçümü birkaç dakika içinde tekrarla; art arda düşük ölçümler uyarı üretir. "
                            "Kendini kötü hissediyorsan görev sağlık protokolünü uygula.")
        return ""

    def set_mode(self, mode: str, now: datetime) -> str:
        key = _normalize(mode)
        if key in ("device", "gercek", "cihaz", "real"):
            mode = "device"
        elif key in ("simulation", "simulasyon", "sim", "test"):
            mode = "simulation"
        else:
            return "Bilinmeyen kip. Kullan: 'astra kip gerçek' veya 'astra kip simülasyon'."
        with self._lock:
            self.settings["mode"] = mode
            self.simulated = mode != "device"
            self.core = AstraCore(self.db, self.simulated)
            self.feed = (LiveSimulationFeed(self.db, self.astronaut_id, self.settings["scenario"],
                                            int(self.settings["history_days"])) if self.simulated else None)
            self._last_eval = None
            self._current_day = None
        self._save_mode(mode)
        self._ui_log(f"ASTRA: veri kipi '{'gerçek' if mode == 'device' else 'simülasyon'}' olarak ayarlandı.")
        if mode == "device":
            return ("ASTRA artık gerçek verilerle çalışıyor (elle girilen ölçümler dahil); simülasyon verisi "
                    "değerlendirmeye girmiyor. Kişisel referans için en az 7 günlük ölçüm gerekir.")
        return "ASTRA simülasyon kipine döndü; değerlendirmeler test verisiyle yapılıyor."

    def _save_mode(self, mode: str) -> None:
        if self.settings_path is None:
            return
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8")) if self.settings_path.exists() else {}
            data["mode"] = mode
            self.settings_path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as exc:
            self._log.warning("ASTRA kip ayarı kaydedilemedi: %s", exc)

    def handle_tool(self, name: str, args: dict) -> str:
        """Gemini araç çağrısı.

        answer_voice="gemini": sonuç metni Gemini'ye döner ve Gemini okur (sağlık verisi Gemini'ye gider).
        answer_voice="local": sonuç yerel olarak okunur; Gemini'ye sağlık verisi gitmez.
        """
        now = self.clock()
        delay = 1.5  # yerel kipte Gemini'nin kısa cevabının başlaması için
        local = self.settings.get("answer_voice", "gemini") == "local"

        def reply(spoken: str) -> str:
            return GEMINI_REPLY if local else GEMINI_RELAY + spoken

        try:
            if name == "astra_health_status":
                period = str(args.get("period", "today")).lower()
                period = period if period in ("week", "month") else "today"
                return reply(self._health(period, now, delay, local_voice=local))
            if name == "astra_radiation_status":
                return reply(self._radiation(now, delay, local_voice=local))
            if name == "astra_alerts":
                if str(args.get("action", "list")).lower().startswith("ack"):
                    return f"{self.acknowledge_all(now)} sağlık uyarısı onaylandı."
                return reply(self._alerts_list(delay, local_voice=local))
            if name == "astra_simulation":
                return self.set_scenario(str(args.get("scenario", "")).strip(), now)
            if name == "astra_record_measurement":
                message = self.record_manual(str(args.get("metric", "")), str(args.get("value", "")), now)
                self._ui_log("ASTRA: " + message)
                return message
            if name == "astra_mode":
                return self.set_mode(str(args.get("mode", "")), now)
            return f"Bilinmeyen ASTRA aracı: {name}"
        except Exception as exc:
            self._log.exception("ASTRA araç hatası (%s): %s", name, exc)
            return f"ASTRA hatası: {exc}"

    def _gemini_connected(self) -> bool:
        return bool(getattr(self.kam, "session", None) and getattr(self.kam, "_loop", None))

    def handle_text(self, text: str) -> bool:
        """'astra' ile başlayan yazılı komutları Gemini'ye göndermeden yanıtlar (çevrimdışı çalışır)."""
        normalized = _normalize(text)
        words = normalized.split()
        if "saglik analiz" in normalized and not words[:1] == ["astra"] and not self._gemini_connected():
            # "Sağlık analizi yap" yazıldı ama Gemini bağlı değil: internetsiz, yerel analiz
            words = ["astra", "durum"]
        if not words or words[0] != "astra":
            return False
        command = words[1] if len(words) > 1 else "durum"
        now = self.clock()
        try:
            if command in ("durum", "saglik", "bugun"):
                self._health("today", now, 0)
            elif command == "hafta":
                self._health("week", now, 0)
            elif command == "ay":
                self._health("month", now, 0)
            elif command in ("hologram", "analiz"):
                self.open_analysis()
            elif command == "radyasyon":
                self._radiation(now, 0)
            elif command.startswith("uyari"):
                self._alerts_list(0)
            elif command.startswith("onay"):
                count = self.acknowledge_all(now)
                self.voice.say(f"{count} uyarı onaylandı.", 1)
            elif command == "olcum":
                original = text.split()  # birimler ve değerler için özgün yazım
                if len(original) < 4:
                    message = "Kullanım: 'astra ölçüm nabız 72' veya 'astra ölçüm tansiyon 120/80'."
                else:
                    message = self.record_manual(" ".join(original[2:-1]), original[-1], now)
                self._ui_log("ASTRA: " + message)
                self.voice.say(health_voice.to_speech(message), 1)
            elif command == "kip" and len(words) > 2:
                message = self.set_mode(words[2], now)
                self.voice.say(message, 1)
            elif command == "senaryolar":
                self._ui_log("ASTRA senaryoları: " + ", ".join(SCENARIOS))
            elif command == "senaryo" and len(words) > 2:
                self._ui_log("ASTRA: " + self.set_scenario(words[2], now))
            else:
                self._ui_log(_TEXT_HELP)
        except Exception as exc:
            self._log.exception("ASTRA komut hatası: %s", exc)
            self._ui_log(f"ERR: ASTRA komutu çalışmadı — {exc}")
        return True


def start_astra(ui, kam) -> AstraBridge | None:
    """KAM açılırken çağrılır. Hata olursa None döner ve KAM ASTRA'sız çalışmaya devam eder."""
    try:
        settings = load_settings()
        if not settings.get("enabled", True):
            return None
        bridge = AstraBridge(ui, kam, settings)
        bridge.start()
        return bridge
    except Exception as exc:
        get_astra_logger().exception("ASTRA başlatılamadı: %s", exc)
        try:
            ui.write_log(f"ERR: ASTRA sağlık modülü başlatılamadı — {exc}")
        except Exception:
            pass
        return None


__all__ = ["ASTRA_TOOL_DECLARATIONS", "AstraBridge", "astra_is_speaking", "start_astra"]
