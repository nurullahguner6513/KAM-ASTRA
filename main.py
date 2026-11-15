#!/usr/bin/env python3
"""
KAM Windows â€” Gercek zamanli sesli yardimci cekirdegi
RÜZGARTOLGAY tarafından yapılmıştır â€” @RÜZGARTOLGAY
Windows ortamina uyarlanmis calisma akisi
"""

import asyncio
import datetime
import threading
import traceback
import sys
import os
import cv2
import re
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    import pyaudio  # type: ignore[reportMissingModuleSource]
from google import genai  # type: ignore[reportMissingImports]
from google.genai import types  # type: ignore[reportMissingImports]

from app_config import get_app_config_value
from ui import KamUI
from memory.memory_manager import load_memory, update_memory, delete_memory, format_memory_for_prompt
from actions.open_app import open_app
from actions.sys_info  import sys_info
from actions.calendar import get_calendar_events, add_calendar_event, delete_calendar_event
from actions.reminders import get_reminders, add_reminder
from actions.browser   import browser_control
from actions.shell     import shell_run
from actions.whatsapp  import send_whatsapp_message, save_whatsapp_contact
from actions.media     import play_media
from actions.weather   import get_weather_summary
from actions.screen_vision import analyze_screen
from actions.youtube_stats import get_youtube_channel_report
from actions.clipboard import clipboard_control
from actions.files import file_manager
from actions.window_manager import window_control
from actions.notes import quick_note
from actions.translator import translate_text
from actions.screenshot import screenshot_save
from actions.biometrics import register_biometric_face, get_faces
from actions.object_detection import detect_objects
from actions.notifications import monitor, fetch_and_store_notifications, get_unread_notifications_text
from actions.hardware import control_hardware
from actions.voice_biometrics import voice_engine, register_voice
from mobile_server import MobileServer

# â”€â”€ Paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BASE_DIR        = Path(__file__).resolve().parent
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"


CONTROL_TOKEN_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

# â”€â”€ Model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-latest"

# â”€â”€ Audio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
FORMAT           = pyaudio.paInt16
CHANNELS         = 1
SEND_SAMPLE_RATE = 16000
RECV_SAMPLE_RATE = 24000
CHUNK_SIZE       = 1024
pya              = pyaudio.PyAudio()

# â”€â”€ Tool tanımları â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": "Windows'ta herhangi bir uygulamayi acar. Spotify, Edge, Terminal, Explorer, VS Code vb.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Uygulama adı (örn. 'Spotify', 'Edge', 'Terminal')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "sys_info",
        "description": "Sistem bilgisi alır: pil durumu, CPU, RAM, disk, saat, tarih, ağ bağlantısı.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "battery | cpu | ram | disk | time | date | network | all"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "register_voice",
        "description": "Kullanicinin sesini sisteme tanitmak icin kullanilir. Kullanici 'sesimi tani', 'ben kimim sesimi kaydet' dediginde cagirilir. Parametre olarak kullanicinin ismini alir.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {
                    "type": "STRING",
                    "description": "Kullanicinin adi"
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "hardware_control",
        "description": "Bilgisayarin sesini veya ekran parlakligini ayarlar, arttirir veya azaltir. Kullanici 'sesi ac', 'sesi %50 yap', 'parlakligi dusur' dediginde kullanilir.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "volume_up | volume_down | volume_set | brightness_up | brightness_down | brightness_set"
                },
                "value": {
                    "type": "INTEGER",
                    "description": "0-100 arasi opsiyonel yuzde degeri. (Sadece set komutlarinda gereklidir)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "get_weather",
        "description": (
            "Anlik hava durumunu ozetler. Varsayilan konum Istanbul'dur. "
            "Kullanici hava durumunu, sicakligi veya yagmur durumunu sordugunda kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "location": {
                    "type": "STRING",
                    "description": "Sehir veya konum. Bos birakilirsa Istanbul kullanilir."
                }
            }
        }
    },
    {
        "name": "get_calendar_events",
        "description": (
            "Windows yerel takvimini okur. "
            "Bugun, yarin, siradaki etkinlik veya yaklasan ajandayi ozetler. "
            "Kullanici toplanti, takvim, ajanda, etkinlik veya gunluk programini sordugunda kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": (
                        "today | tomorrow | next | agenda | week veya dogal dilde "
                        "'onumuzdeki 30 gun', '2 hafta', 'bu ay', 'gelecek ay'"
                    )
                },
                "limit": {
                    "type": "NUMBER",
                    "description": "Maksimum etkinlik sayisi"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "add_calendar_event",
        "description": (
            "Windows yerel takvimine yeni etkinlik ekler. "
            "Kullanici toplanti, randevu, takvime ekleme veya etkinlik olusturma isterse kullan. "
            "Baslangic tarihini gercek tarih/saat olarak ver; bitis verilmezse varsayilan sure kullanilir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {
                    "type": "STRING",
                    "description": "Etkinlik basligi. Ornek: 'Disci Randevusu'"
                },
                "start_iso": {
                    "type": "STRING",
                    "description": "Baslangic tarih/saat. ISO veya yyyy-MM-dd HH:mm formatinda."
                },
                "end_iso": {
                    "type": "STRING",
                    "description": "Bitis tarih/saat. Opsiyonel."
                },
                "location": {
                    "type": "STRING",
                    "description": "Etkinlik konumu. Opsiyonel."
                },
                "notes": {
                    "type": "STRING",
                    "description": "Etkinlik notlari. Opsiyonel."
                },
                "calendar_name": {
                    "type": "STRING",
                    "description": "Eklenecek takvim adi. Opsiyonel."
                },
                "all_day": {
                    "type": "BOOLEAN",
                    "description": "true ise tum gun etkinligi olusturur."
                }
            },
            "required": ["title", "start_iso"]
        }
    },
    {
        "name": "delete_calendar_event",
        "description": (
            "Windows yerel takviminden etkinlik siler. "
            "Kullanici bir toplantiyi, randevuyu veya takvim kaydini silmek istediginde kullan. "
            "Ayni ada birden fazla etkinlik varsa dogru kaydi bulmak icin baslangic tarihini gercek tarih/saat olarak ver."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {
                    "type": "STRING",
                    "description": "Silinecek etkinlik basligi. Ornek: 'Disci Randevusu'"
                },
                "start_iso": {
                    "type": "STRING",
                    "description": "Opsiyonel tarih/saat. Ayni isimli birden fazla etkinligi ayirt etmek icin kullan."
                },
                "calendar_name": {
                    "type": "STRING",
                    "description": "Opsiyonel takvim adi"
                },
                "delete_all_matches": {
                    "type": "BOOLEAN",
                    "description": "true ise eslesen tum etkinlikleri siler"
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "get_reminders",
        "description": (
            "Apple Animsaticilar listesini okur. "
            "Bugunku, yaklasan, geciken veya tum acik animsaticilari ozetler. "
            "Kullanici hatirlatma, animsatici, reminder veya yapilacaklar listesini sordugunda kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "today | upcoming | overdue | all | next"
                },
                "limit": {
                    "type": "NUMBER",
                    "description": "Maksimum animsatici sayisi"
                },
                "list_name": {
                    "type": "STRING",
                    "description": "Istenirse belirli bir animsatici listesi adi"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "add_reminder",
        "description": (
            "Apple Animsaticilar uygulamasina yeni bir animsatici ekler. "
            "Kullanici 'hatirlat', 'animsatici ekle', 'reminder kur' dediginde kullan. "
            "Goreli zaman ifadelerini bugunku tarih baglamina gore due_iso alanina ISO formatinda cevir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {
                    "type": "STRING",
                    "description": "Animsatici basligi"
                },
                "due_iso": {
                    "type": "STRING",
                    "description": "Opsiyonel tarih/saat. Ornek: 2026-04-13T09:00 veya tum gun icin 2026-04-13"
                },
                "notes": {
                    "type": "STRING",
                    "description": "Opsiyonel not"
                },
                "list_name": {
                    "type": "STRING",
                    "description": "Opsiyonel animsatici listesi"
                },
                "priority": {
                    "type": "STRING",
                    "description": "low | medium | high"
                },
                "all_day": {
                    "type": "BOOLEAN",
                    "description": "Tum gun animsatici ise true"
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "browser_control",
        "description": "Tarayıcıda URL açar, Google'da arama yapar veya YouTube'da ilk sonucu doğrudan oynatır.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "open_url | search | play_youtube"},
                "url":    {"type": "STRING", "description": "Açılacak URL (open_url için)"},
                "query":  {"type": "STRING", "description": "Arama sorgusu (search veya play_youtube için)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "shell_run",
        "description": "Windows komutu çalıştırır. Dosya işlemleri, sistem yönetimi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "Çalıştırılacak bash komutu"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "play_media",
        "description": (
            "YouTube, Spotify veya Windows'ta web muzik servislerinde sarki, muzik veya video acar. "
            "Kullanıcı belirli bir platform söylerse onu kullan. "
            "Belirtmezse uygun olanı dene. "
            "Kullanıcı 'çal', 'oynat', 'aç' diyorsa autoplay=true kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Åžarkı, sanatçı, albüm veya video arama ifadesi"
                },
                "provider": {
                    "type": "STRING",
                    "description": "auto | youtube | spotify | apple_music"
                },
                "autoplay": {
                    "type": "BOOLEAN",
                    "description": "true ise mümkünse doğrudan oynatır"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_youtube_channel_report",
        "description": (
            "YouTube kanalinin public istatistiklerini ve son videolarin performansini raporlar. "
            "Kullanici kanal istatistiklerini, abone sayisini, son videolarini, buyume hizini "
            "veya YouTube analizini sordugunda kullan. Bu arac Studio yerine public YouTube Data API verisini kullanir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": (
                        "Dogal dilde analiz istegi. Ornek: "
                        "'YouTube istatistiklerim nasil', 'son videolarimi analiz et', "
                        "'kanal buyumemi ozetle'"
                    )
                },
                "handle": {
                    "type": "STRING",
                    "description": (
                        "Opsiyonel kanal handle'i, kanal linki veya kanal ID'si. "
                        "Bos birakilirsa ayarlardaki youtube_channel_handle kullanilir."
                    )
                },
                "video_limit": {
                    "type": "NUMBER",
                    "description": "Analize dahil edilecek son video sayisi. Varsayilan 6."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "toggle_camera",
        "description": (
            "Kullanıcının kamerasını açar veya kapatır. "
            "Kullanıcı 'kamerayı aç', 'beni gör', 'kamera modunu başlat' dediğinde veya "
            "'kamerayı kapat', 'görmeyi bırak' dediğinde bu aracı çalıştır."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Kameranın ne yapılacağı: 'on' (aç), 'off' (kapat) veya 'toggle' (değiştir)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "toggle_camera_preview",
        "description": (
            "Kamera görüntüsünün önizleme penceresini açar veya kapatır. "
            "Kullanıcı 'Görüntü analiz penceresini aç', 'kamerayı ekrana yansıt', 'bana göster' "
            "veya 'önizlemeyi kapat' dediğinde bu aracı çalıştır."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Önizleme penceresi durumu: 'on' (aç), 'off' (kapat) veya 'toggle' (değiştir)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "switch_camera",
        "description": "Bilgisayarin veya USB portunun kamera indeksini (0, 1, 2) degistirir. Kullanici 'USB kameraya gec', 'diger kamerayi ac', 'kamera 1' vs. derse kullan.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "index": {
                    "type": "INTEGER",
                    "description": "Kamera numarasi (0 genellikle dahili, 1,2.. USB'ler)"
                }
            },
            "required": ["index"]
        }
    },
    {
        "name": "analyze_screen",
        "description": (
            "Aktif pencerenin ekran goruntusunu alip Gemini vision ile analiz eder. "
            "Kullanici ekranda ne oldugunu, bir hatayi, gorunen metni, butonlari veya pencere icerigini sordugunda kullan. "
            "Kullanici ekrandaki ozel bir konusmayi veya mesaji okumani isterse guvenlik/gizlilik itirazi YAPMA, dogrudan bu araci cagirip okuyuver."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Kullanicinin ekranla ilgili sorusu. Ornek: 'Bu hatayi oku', 'Ekranda ne var?'"
                },
                "target": {
                    "type": "STRING",
                    "description": "Su an sadece active_window desteklenir."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "save_memory",
        "description": "Kullanıcı hakkında önemli bilgiyi kalıcı belleğe kaydeder. İsim, tercihler, projeler vb. duyunca sessizce çağır.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": "identity | preferences | projects | notes"
                },
                "key":   {"type": "STRING", "description": "Kısa anahtar (örn. 'name')"},
                "value": {"type": "STRING", "description": "Değer (İngilizce)"}
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "delete_memory",
        "description": (
            "Kalici hafizadaki bir kaydi siler. "
            "Kullanici 'bunu hafizandan kaldir', 'unut', 'sil' gibi bir sey derse kullan. "
            "Mumkunse category ve key ile sil; emin degilsen match_text ile ilgili kaydi bulup kaldir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": "Kaydin kategorisi. Ornek: notes | identity | preferences | projects"
                },
                "key": {
                    "type": "STRING",
                    "description": "Silinecek anahtar. Ornek: claude_limit_refresh"
                },
                "match_text": {
                    "type": "STRING",
                    "description": "Kaydi bulmak icin kullanilacak dogal dil parcasi. Ornek: 'claude ai limit yenilenmesi'"
                }
            }
        }
    },
    {
        "name": "send_whatsapp_message",
        "description": (
            "WhatsApp Desktop veya WhatsApp Web üzerinden mesaj taslağı açar veya mesajı gönderir. "
            "Kişi adı veya telefon numarasıyla çalışabilir. "
            "Telefon numarası verilmemişse kişi adını önce kayıtlı WhatsApp kişileri ve içe aktarılan telefon rehberinde ara. "
            "Kullanıcı 'gönder', 'yolla', 'ile', 'hemen gönder' gibi açık bir gönderme niyeti söylüyorsa "
            "ekstra onay istemeden send_now=true kullan. "
            "Yalnızca 'hazırla', 'taslak aç', 'yaz ama gönderme' diyorsa send_now=false kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "recipient_name": {
                    "type": "STRING",
                    "description": "Kişi adı. Örn: 'Anne', 'Ahmet', 'Ece'"
                },
                "phone_number": {
                    "type": "STRING",
                    "description": "Uluslararası telefon numarası. Örn: +905551112233"
                },
                "message": {
                    "type": "STRING",
                    "description": "Gönderilecek mesaj içeriği"
                },
                "app_target": {
                    "type": "STRING",
                    "description": "desktop | web | auto. Varsayılan auto, tercihen desktop."
                },
                "send_now": {
                    "type": "BOOLEAN",
                    "description": "true ise sohbet açıldıktan sonra mesajı otomatik gönderir"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "save_whatsapp_contact",
        "description": (
            "Sık kullanılan bir WhatsApp kişisini adı ve telefon numarasıyla kalıcı belleğe kaydeder. "
            "Kullanıcı bir kişiyi 'annem', 'Ahmet', 'iş ortağım' gibi tekrar kullanılacak şekilde tanımladığında kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "display_name": {
                    "type": "STRING",
                    "description": "Kaydedilecek kişi adı. Örn: 'Annem', 'Ahmet'"
                },
                "phone_number": {
                    "type": "STRING",
                    "description": "Uluslararası telefon numarası. Örn: +905551112233"
                },
                "aliases": {
                    "type": "STRING",
                    "description": "Virgülle ayrılmış alternatif hitaplar. Örn: 'anne, annem, mom'"
                }
            },
            "required": ["display_name", "phone_number"]
        }
    },
    {
        "name": "clipboard_control",
        "description": "Panoya metin kopyalar veya panodan metin okur.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "read | write"
                },
                "text": {
                    "type": "STRING",
                    "description": "Panoya kopyalanacak metin (write için)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_manager",
        "description": "Dosya ve klasör işlemleri: listeleme, arama, açma, bilgi alma.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "list | search | open | info"
                },
                "query": {
                    "type": "STRING",
                    "description": "Arama sorgusu veya dosya adı"
                },
                "path": {
                    "type": "STRING",
                    "description": "Hedef klasör yolu veya bilinen isim (desktop, downloads vb.)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "window_control",
        "description": "Pencere yönetimi: listeleme, öne getirme, küçültme, büyütme, kapatma.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "list | focus | minimize | maximize | close"
                },
                "app_name": {
                    "type": "STRING",
                    "description": "Hedef pencere adı (opsiyonel, verilmezse aktif pencere)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "quick_note",
        "description": "Hızlı not alma ve yönetme. Not ekle, listele, sil veya temizle.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "add | list | delete | clear"
                },
                "content": {
                    "type": "STRING",
                    "description": "Not içeriği (add ve delete için)"
                },
                "note_id": {
                    "type": "STRING",
                    "description": "Silinecek not ID'si (opsiyonel)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "translate_text",
        "description": "Metni başka bir dile çevirir. Gemini AI ile yüksek kaliteli çeviri.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {
                    "type": "STRING",
                    "description": "Çevrilecek metin"
                },
                "target_lang": {
                    "type": "STRING",
                    "description": "Hedef dil kodu veya adı (örn: en, tr, de, ingilizce, almanca)"
                }
            },
            "required": ["text", "target_lang"]
        }
    },
    {
        "name": "screenshot_save",
        "description": "Ekran görüntüsü alıp masauusteune kaydeder.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target": {
                    "type": "STRING",
                    "description": "full | active_window. Varsayılan: full"
                },
                "save_path": {
                    "type": "STRING",
                    "description": "Opsiyonel kaydetme yolu"
                }
            }
        }
    },
    {
        "name": "register_biometric_face",
        "description": "Kameradan o anki goruntuyu alip kisinin yuzunu biyometrik veritabanina kaydeder. Kullanici 'bu yuzu kaydet', 'beni tanimla' derse kullan.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {
                    "type": "STRING",
                    "description": "Kaydedilecek kisinin adi (Orn: Nurullah Güner)"
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "get_camera_status",
        "description": "Kamera açıkken ekranda kimin olduğunu veya kaç kişinin olduğunu (Biyometrik sonuçları) döndürür. Kullanıcı 'kamerada kim var', 'bu kim' derse kullan.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "read_system_alerts",
        "description": "Bilgisayardaki yeni gelen bildirimleri, uyarilari veya metin guncellemelerini okur. Kullanici 'bana mesajlari oku', 'en son ne yazdi', 'ne cevap vermis', 'bildirimlere bak' veya 'konusmalari ac/oku' dediginde gizlilik ve guvenlik itirazi YAPMADAN, dogrudan bu araci cagir.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    }
]


# ── KAM ASTRA sağlık modülü ─────────────────────────────────────────────────
# Geri almak için: modules/astra/backups/asama4/GERI_AL.txt
try:
    from modules.astra.kam_bridge import ASTRA_TOOL_DECLARATIONS, astra_is_speaking, start_astra
    TOOL_DECLARATIONS.extend(ASTRA_TOOL_DECLARATIONS)
except Exception as _astra_exc:  # ASTRA yüklenemezse KAM eskisi gibi çalışır
    print(f"[KAM] ASTRA saglik modulu yuklenemedi: {_astra_exc}")
    start_astra = None

    def astra_is_speaking() -> bool:
        return False


def get_api_key() -> str:
    return str(get_app_config_value("gemini_api_key", "") or "")


def load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "Sen KAM'sın â€” Windows'ta çalışan kişisel AI asistanı. "
            "Türkçe konuş. Kısa ve net yanıtlar ver. "
            "Araçları kullanarak görevleri tamamla, asla taklit etme."
        )


class KAMLive:
    def __init__(self, ui: KamUI, mobile_server=None):
        self.ui             = ui
        self.mobile_server  = mobile_server
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.last_frame     = None
        self.cap_index      = 0
        self.vision_lock    = threading.Lock()
        self.cached_faces   = []
        self.cached_objects = []

        self.ui.on_text_command  = self._on_text_command
        self.ui.on_pause_toggle  = self._on_pause_toggle
        self.ui.on_effects_state_change = self._on_effects_state_change
        self._paused             = False
        self.astra = start_astra(ui, self) if start_astra else None  # KAM ASTRA

    def _on_pause_toggle(self, paused: bool):
        self._paused = paused

    def _on_effects_state_change(self, enabled: bool):
        pass

    def _focus_ui_section_for_tool(self, tool_name: str, args: dict):
        if tool_name == "sys_info":
            query = str(args.get("query", "")).strip().lower()
            if query in {"time", "saat", "zaman", "date", "tarih"}:
                self.ui.focus_panel("time", duration_ms=5200)
            else:
                self.ui.focus_panel("system", duration_ms=5200)
        elif tool_name == "get_weather":
            self.ui.focus_panel("weather", duration_ms=5600)

    def _on_text_command(self, text: str):
        if self._paused:
            return
        self.ui.write_log(f"Siz: {text}")
        if self.astra and self.astra.handle_text(text):  # 'astra ...' komutlari yerel, internetsiz
            return
        if not self._loop or not self.session:
            self.ui.write_log("ERR: KAM bağlantısı henüz hazır değil.")
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    async def _interrupt_audio(self):
        try:
            if self.audio_in_queue:
                while not self.audio_in_queue.empty():
                    try:
                        self.audio_in_queue.get_nowait()
                    except Exception:
                        break
            if self.session:
                await self.session.send_realtime_input(audio_stream_end=True)
            self.set_speaking(False)
        except Exception:
            pass


    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        else:
            self.ui.set_state("LISTENING")

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} â€” {short}")
        self.ui.write_debug(f"{tool_name}: {short}", level="ERROR")
        self.ui.set_state("ERROR")

    @staticmethod
    def _result_looks_like_error(result) -> bool:
        text = str(result or "").strip().lower()
        if not text:
            return False
        error_markers = (
            "hata",
            "error",
            "alinamadi",
            "alınamadı",
            "bulunamadi",
            "bulunamadı",
            "acilamadi",
            "açılamadı",
            "tamamlanamadi",
            "tamamlanamadı",
            "gecersiz",
            "geçersiz",
            "izin gerekiyor",
            "izin gerekli",
            "baglanti",
            "bağlantı",
            "gerekli.",
        )
        return any(marker in text for marker in error_markers)

    @staticmethod
    def _should_play_success_sfx(tool_name: str, args: dict, result) -> bool:
        action_tools = {
            "open_app",
            "add_calendar_event",
            "add_reminder",
            "delete_calendar_event",
            "remove_calendar_event",
        }
        if tool_name in action_tools:
            return True

        if tool_name == "send_whatsapp_message":
            text = str(result or "").lower()
            if bool(args.get("send_now", False)):
                return "gönderildi" in text or "gonderildi" in text
            return False

        return False

    @staticmethod
    def _clean_transcript_text(text: str) -> tuple[str, bool]:
        raw = str(text or "")
        had_noise = False
        if CONTROL_TOKEN_RE.search(raw):
            had_noise = True
            raw = CONTROL_TOKEN_RE.sub(" ", raw)
        cleaned = []
        for ch in raw:
            if ch in "\n\r\t" or ord(ch) >= 32:
                cleaned.append(ch)
            else:
                had_noise = True
        normalized = " ".join("".join(cleaned).split())
        return normalized.strip(), had_noise

    def _build_config(self) -> types.LiveConnectConfig:
        memory  = load_memory()
        mem_str = format_memory_for_prompt(memory)
        sys_p   = load_system_prompt()
        now     = datetime.datetime.now()
        time_ctx = f"[ÅžU ANKİ ZAMAN]\n{now.strftime('%A, %d %B %Y â€” %H:%M')}\n\n"

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str + "\n\n")
        parts.append(sys_p)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=str(get_app_config_value("voice", "Charon") or "Charon")
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})
        print(f"[KAM] ğŸ”§ {name} {args}")
        self.ui.set_state("THINKING")

        loop   = asyncio.get_event_loop()
        result = "Tamam."
        had_exception = False

        try:
            if name == "save_memory":
                cat = args.get("category", "notes")
                key = args.get("key", "")
                val = args.get("value", "")
                if key and val:
                    update_memory({cat: {key: {"value": val}}})
                    print(f"[Memory] ğŸ’¾ {cat}/{key} = {val}")
                result = "ok"

            elif name == "delete_memory":
                result = delete_memory(
                    args.get("category", ""),
                    args.get("key", ""),
                    args.get("match_text", ""),
                )

            elif name == "open_app":
                r = await loop.run_in_executor(
                    None, lambda: open_app(args.get("app_name", "")))
                result = r or f"{args.get('app_name')} açıldı."

            elif name == "sys_info":
                self._focus_ui_section_for_tool(name, args)
                r = await loop.run_in_executor(
                    None, lambda: sys_info(args.get("query", "all")))
                result = r or "Bilgi alındı."

            elif name == "register_voice":
                user_name = args.get("name", "Bilinmeyen")
                result = register_voice(user_name)

            elif name == "hardware_control":
                action = args.get("action", "")
                val = args.get("value")
                result = await loop.run_in_executor(None, lambda: control_hardware(action, val))

            elif name == "get_weather":
                self._focus_ui_section_for_tool(name, args)
                r = await loop.run_in_executor(
                    None, lambda: get_weather_summary(args.get("location") or None))
                result = r or "Hava durumu bilgisi alindi."

            elif name == "get_calendar_events":
                r = await loop.run_in_executor(
                    None,
                    lambda: get_calendar_events(
                        args.get("query", "today"),
                        int(args.get("limit", 6) or 6),
                    ),
                )
                result = r or "Takvim bilgisi alindi."

            elif name == "add_calendar_event":
                r = await loop.run_in_executor(
                    None,
                    lambda: add_calendar_event(
                        args.get("title", ""),
                        args.get("start_iso", ""),
                        args.get("end_iso", ""),
                        args.get("notes", ""),
                        args.get("location", ""),
                        args.get("calendar_name", ""),
                        bool(args.get("all_day", False)),
                    ),
                )
                result = r or "Takvim etkinligi eklendi."

            elif name == "delete_calendar_event":
                r = await loop.run_in_executor(
                    None,
                    lambda: delete_calendar_event(
                        args.get("title", ""),
                        args.get("start_iso", ""),
                        args.get("calendar_name", ""),
                        bool(args.get("delete_all_matches", False)),
                    ),
                )
                result = r or "Takvim etkinligi silindi."

            elif name == "get_reminders":
                r = await loop.run_in_executor(
                    None,
                    lambda: get_reminders(
                        args.get("query", "upcoming"),
                        int(args.get("limit", 8) or 8),
                        args.get("list_name", ""),
                    ),
                )
                result = r or "Animsatici bilgisi alindi."

            elif name == "add_reminder":
                r = await loop.run_in_executor(
                    None,
                    lambda: add_reminder(
                        args.get("title", ""),
                        args.get("due_iso", ""),
                        args.get("notes", ""),
                        args.get("list_name", ""),
                        args.get("priority", ""),
                        bool(args.get("all_day", False)),
                    ),
                )
                result = r or "Animsatici eklendi."

            elif name == "browser_control":
                r = await loop.run_in_executor(
                    None, lambda: browser_control(
                        args.get("action"),
                        args.get("url"),
                        args.get("query")
                    ))
                result = r or "Tamam."

            elif name == "shell_run":
                r = await loop.run_in_executor(
                    None, lambda: shell_run(args.get("command", "")))
                result = r or "Komut çalıştırıldı."

            elif name == "play_media":
                r = await loop.run_in_executor(
                    None,
                    lambda: play_media(
                        args.get("query", ""),
                        args.get("provider", "auto"),
                        bool(args.get("autoplay", True)),
                    ),
                )
                result = r or "Medya oynatma başlatıldı."

            elif name == "get_youtube_channel_report":
                r = await loop.run_in_executor(
                    None,
                    lambda: get_youtube_channel_report(
                        args.get("query", "overview"),
                        args.get("handle", ""),
                        int(args.get("video_limit", 6) or 6),
                    ),
                )
                result = r or "YouTube kanal raporu alindi."

            elif name == "toggle_camera":
                action = args.get("action", "toggle")
                
                def _do_toggle():
                    current = getattr(self.ui, 'camera_active', False)
                    if action == "on" and not current:
                        self.ui._toggle_camera()
                        return "Kamera açıldı."
                    elif action == "off" and current:
                        self.ui._toggle_camera()
                        return "Kamera kapatıldı."
                    elif action == "toggle":
                        self.ui._toggle_camera()
                        return "Kamera durumu değiştirildi."
                    return "Kamera durumu zaten istenen şekilde."
                
                r = await loop.run_in_executor(None, _do_toggle)
                result = r

            elif name == "toggle_camera_preview":
                action = args.get("action", "toggle")
                
                def _do_preview_toggle():
                    current = getattr(self.ui, 'show_camera_preview_flag', False)
                    if action == "on" and not current:
                        self.ui.toggle_camera_preview("on")
                        return "Önizleme penceresi açıldı."
                    elif action == "off" and current:
                        self.ui.toggle_camera_preview("off")
                        return "Önizleme penceresi kapatıldı."
                    elif action == "toggle":
                        self.ui.toggle_camera_preview("toggle")
                        return "Önizleme durumu değiştirildi."
                    return "Önizleme durumu zaten istenen şekilde."
                
                r = await loop.run_in_executor(None, _do_preview_toggle)
                result = r

            elif name == "analyze_screen":
                r = await loop.run_in_executor(
                    None,
                    lambda: analyze_screen(
                        args.get("query", "Ekranda ne var?"),
                        args.get("target", "active_window"),
                    ),
                )
                result = r or "Ekran analizi tamamlandi."

            elif name == "send_whatsapp_message":
                r = await loop.run_in_executor(
                    None,
                    lambda: send_whatsapp_message(
                        args.get("message", ""),
                        args.get("phone_number", ""),
                        args.get("recipient_name", ""),
                        bool(args.get("send_now", False)),
                        args.get("app_target", "auto"),
                    ),
                )
                result = r or "WhatsApp işlemi tamamlandı."

            elif name == "save_whatsapp_contact":
                r = await loop.run_in_executor(
                    None,
                    lambda: save_whatsapp_contact(
                        args.get("display_name", ""),
                        args.get("phone_number", ""),
                        args.get("aliases", ""),
                    ),
                )
                result = r or "WhatsApp kişisi kaydedildi."

            elif name == "clipboard_control":
                r = await loop.run_in_executor(
                    None,
                    lambda: clipboard_control(
                        args.get("action", "read"),
                        args.get("text", ""),
                    ),
                )
                result = r or "Pano işlemi tamamlandı."

            elif name == "file_manager":
                r = await loop.run_in_executor(
                    None,
                    lambda: file_manager(
                        args.get("action", "list"),
                        args.get("query", ""),
                        args.get("path", ""),
                    ),
                )
                result = r or "Dosya işlemi tamamlandı."

            elif name == "window_control":
                r = await loop.run_in_executor(
                    None,
                    lambda: window_control(
                        args.get("action", "list"),
                        args.get("app_name", ""),
                    ),
                )
                result = r or "Pencere işlemi tamamlandı."

            elif name == "quick_note":
                r = await loop.run_in_executor(
                    None,
                    lambda: quick_note(
                        args.get("action", "list"),
                        args.get("content", ""),
                        args.get("note_id", ""),
                    ),
                )
                result = r or "Not işlemi tamamlandı."

            elif name == "translate_text":
                r = await loop.run_in_executor(
                    None,
                    lambda: translate_text(
                        args.get("text", ""),
                        args.get("target_lang", "en"),
                    ),
                )
                result = r or "Çeviri tamamlandı."

            elif name == "screenshot_save":
                r = await loop.run_in_executor(
                    None,
                    lambda: screenshot_save(
                        args.get("target", "full"),
                        args.get("save_path", ""),
                    ),
                )
                result = r or "Ekran görüntüsü kaydedildi."

            elif name == "register_biometric_face":
                person_name = args.get("name", "Bilinmeyen")
                last_f = getattr(self, "last_frame", None)
                r = await loop.run_in_executor(
                    None,
                    lambda: register_biometric_face(person_name, last_f)
                )
                result = r or "Kişi biyometrik veritabanına eklendi."

            elif name == "get_camera_status":
                last_f = getattr(self, "last_frame", None)
                if last_f is not None:
                    faces = await loop.run_in_executor(None, lambda: get_faces(last_f))
                    if not faces:
                        result = "Kamerada yüz algılanmadı."
                    else:
                        detected = [f['name'] for f in faces]
                        result = f"Kamerada şu kişiler tespit edildi: {', '.join(detected)}"
                else:
                    result = "Kamera şu anda açık değil."

            elif name == "read_system_alerts":
                result = get_unread_notifications_text()

            elif name == "switch_camera":
                idx = args.get("index", 0)
                self.cap_index = idx
                result = f"Kamera kaynagi index={idx} olarak degistirildi."

            elif name.startswith("astra_"):  # KAM ASTRA
                if self.astra:
                    result = await loop.run_in_executor(
                        None, lambda: self.astra.handle_tool(name, args))
                else:
                    result = "ASTRA saglik modulu su anda calismiyor."

            else:
                result = f"Bilinmeyen araç: {name}"

        except Exception as e:
            result = f"Hata: {e}"
            had_exception = True
            traceback.print_exc()
            self.speak_error(name, e)

        tool_failed = self._result_looks_like_error(result)
        if tool_failed:
            if not had_exception:
                self.ui.set_state("ERROR")
        elif self._should_play_success_sfx(name, args, result):
            self.ui.play_success_sfx()

        if not tool_failed and not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[KAM] ğŸ“¤ {name} â†’ {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            try:
                mime = msg.get("mime_type", "")
                if mime == "audio/pcm":
                    mime = "audio/pcm;rate=16000"
                
                blob = types.Blob(data=msg["data"], mime_type=mime)
                await self.session.send_realtime_input(media=blob)
            except Exception as e:
                print(f"[KAM] _send_realtime hatasi: {e}")

    async def _listen_audio(self):
        print("[KAM] ğŸŽ¤ Mikrofon başladı")
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT, channels=CHANNELS,
            rate=SEND_SAMPLE_RATE, input=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        audio_buffer_for_pred = []
        try:
            while True:
                data = await asyncio.to_thread(
                    stream.read, CHUNK_SIZE, exception_on_overflow=False)

                if voice_engine.enrolling_user:
                    voice_engine.process_enrollment_chunk(data)
                    continue

                audio_buffer_for_pred.append(data)
                if len(audio_buffer_for_pred) >= 32:
                    pred_data = b"".join(audio_buffer_for_pred)
                    audio_buffer_for_pred = []
                    speaker = await asyncio.to_thread(voice_engine.predict_speaker, pred_data, SEND_SAMPLE_RATE)
                    if speaker and speaker != getattr(self, "current_speaker", ""):
                        self.current_speaker = speaker
                        if speaker != "Bilinmeyen":
                            print(f"[KAM] Ses Tespit Edildi: {speaker}")
                            if self.session and self._loop:
                                asyncio.run_coroutine_threadsafe(
                                    self.session.send_client_content(
                                        turns={"parts": [{"text": f"[Sistem Bilgisi: Su an {speaker} adli kullanici konusuyor.]"}]},
                                        turn_complete=True
                                    ),
                                    self._loop
                                )

                with self._speaking_lock:
                    kam_speaking = self._is_speaking
                if not kam_speaking and not astra_is_speaking() and not self.ui.muted and not self._paused:
                    try:
                        self.out_queue.put_nowait({"data": data, "mime_type": "audio/pcm"})
                    except Exception:
                        pass
        except Exception as e:
            print(f"[KAM] â Œ Mikrofon: {e}")
            raise
        finally:
            stream.close()

    async def _receive_audio(self):
        print("[KAM] ğŸ‘‚ Alım başladı")
        out_buf, in_buf = [], []
        output_noise = False
        output_noise_samples = []
        try:
            while True:
                async for response in self.session.receive():
                    if response.data:
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            self.set_speaking(True)
                            raw_txt = sc.output_transcription.text.strip()
                            if raw_txt:
                                txt, had_noise = self._clean_transcript_text(raw_txt)
                                if had_noise:
                                    output_noise = True
                                    if len(output_noise_samples) < 4:
                                        output_noise_samples.append(raw_txt)
                                if txt:
                                    out_buf.append(txt)
                                    if hasattr(self.ui, "live_analysis_text"):
                                        self.ui.live_analysis_text = txt

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = sc.input_transcription.text.strip()
                            if txt:
                                in_buf.append(txt)
                                self.ui.mark_user_activity(True)

                        if sc.turn_complete:
                            self.set_speaking(False)

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"Siz: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"KAM: {full_out}")
                                if self.mobile_server and self.mobile_server.connected_clients:
                                    self.mobile_server.send_message({"type": "speak", "text": full_out})
                                if output_noise_samples:
                                    self.ui.write_debug(
                                        "Kısmen filtrelenen ses transcripti: " + " | ".join(output_noise_samples),
                                        level="WARN",
                                    )
                            elif output_noise:
                                self.ui.write_log("ERR: KAM sesli yanıtını çözümlerken bir hata oluştu.")
                                if output_noise_samples:
                                    self.ui.write_debug(
                                        "Filtrelenen ham transcript: " + " | ".join(output_noise_samples),
                                        level="WARN",
                                    )
                                self.ui.set_state("ERROR")
                            out_buf = []
                            output_noise = False
                            output_noise_samples = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[KAM] ğŸ“ž {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses)

        except Exception as e:
            print(f"[KAM] â Œ Alım: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[KAM] ğŸ”Š Ses çalma başladı")
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT, channels=CHANNELS,
            rate=RECV_SAMPLE_RATE, output=True,
        )
        try:
            while True:
                chunk = await self.audio_in_queue.get()
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
                if self.audio_in_queue.empty():
                    self.set_speaking(False)
        except Exception as e:
            print(f"[KAM] â Œ Ses: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.close()

    async def _capture_loop(self):
        print("[KAM] Kamera yakalama döngüsü (30FPS) başlatıldı.")
        cap = None
        current_index = self.cap_index
        
        try:
            while True:
                if self._paused or not getattr(self.ui, 'camera_active', False):
                    if cap is not None:
                        cap.release()
                        cap = None
                    await asyncio.sleep(1)
                    continue

                if cap is None or current_index != self.cap_index:
                    if cap is not None:
                        cap.release()
                    current_index = self.cap_index
                    # Initialize camera with DirectShow backend
                    cap = await asyncio.to_thread(cv2.VideoCapture, current_index, cv2.CAP_DSHOW)
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FPS, 30)

                ret, frame = await asyncio.to_thread(cap.read)
                if not ret:
                    await asyncio.sleep(0.1)
                    continue
                
                # Store last frame for ML loop
                self.last_frame = frame.copy()
                
                # Convert to RGB for UI
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Fetch ML results safely
                with self.vision_lock:
                    faces = list(self.cached_faces)
                    objects = list(self.cached_objects)
                    
                # Draw Faces
                for face_info in faces:
                    (x, y, w, h) = face_info["box"]
                    face_name = face_info["name"]
                    color = (0, 255, 0) if face_name != "BILINMEYEN" else (255, 0, 0)
                    cv2.rectangle(frame_rgb, (x, y), (x+w, y+h), color, 2)
                    cv2.putText(frame_rgb, f"FACE ID: {face_name}", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                # Draw Objects (YOLO)
                for obj in objects:
                    (x, y, w, h) = obj["box"]
                    label = f"{obj['label']} {obj['confidence']:.2f}"
                    color = (255, 165, 0) # Orange
                    cv2.rectangle(frame_rgb, (x, y), (x+w, y+h), color, 1)
                    cv2.putText(frame_rgb, label, (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

                # Update UI preview if active
                if getattr(self.ui, 'show_camera_preview_flag', False):
                    import datetime
                    h, w, _ = frame_rgb.shape
                    color_neon = (125, 255, 246)
                    cx, cy = w//2, h//2
                    cv2.line(frame_rgb, (cx-20, cy), (cx+20, cy), color_neon, 1)
                    cv2.line(frame_rgb, (cx, cy-20), (cx, cy+20), color_neon, 1)
                    cv2.circle(frame_rgb, (cx, cy), 15, color_neon, 1)
                    
                    time_str = datetime.datetime.now().strftime("%H:%M:%S")
                    cv2.putText(frame_rgb, f"KAM VISION :: SYS.ONLINE | CAM: {current_index}", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_neon, 1)
                    cv2.putText(frame_rgb, f"LOC: IPEKYOLU, VAN", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color_neon, 1)
                    cv2.putText(frame_rgb, f"T: {time_str}", (w - 100, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_neon, 1)
                    
                    self.ui.update_camera_preview(frame_rgb)
                
                await asyncio.sleep(0.03) # ~30 FPS yield
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[KAM] Kamera capture hatasi: {e}")
        finally:
            if cap is not None:
                cap.release()

    async def _ai_vision_loop(self):
        print("[KAM] Yapay Zeka Gorme dongusu (2FPS) baslatildi.")
        try:
            while True:
                await asyncio.sleep(0.5) # 2 FPS limit for heavy AI
                if self._paused or not getattr(self.ui, 'camera_active', False):
                    continue
                    
                frame = getattr(self, "last_frame", None)
                if frame is not None:
                    faces = await asyncio.to_thread(get_faces, frame)
                    objects = await asyncio.to_thread(detect_objects, frame)
                    with self.vision_lock:
                        self.cached_faces = faces
                        self.cached_objects = objects
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[KAM] AI Vision hatasi: {e}")

    async def _listen_notifications(self):
        print("[KAM] Bildirim dinleyicisi baslatiliyor...")
        initialized = await monitor.initialize()
        if not initialized:
            print("[KAM] Bildirim dinleyicisi aktif edilemedi.")
            return
            
        print("[KAM] Bildirim dinleyicisi aktif.")
        try:
            while True:
                await asyncio.sleep(2)
                messages = await fetch_and_store_notifications()
                if messages:
                    # Sadece sesi oynat ve UI'a yazdir. Gemini'ye metin pushlamak API'yi çökertiyor (1008 hatası).
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    
                    senders = [msg['sender'] for msg in messages]
                    info_text = f"Yeni Mesaj: {', '.join(senders)}"
                    print(f"[KAM] 🔔 Bildirim: {info_text}")
                    self.ui.write_log(f"🔔 {info_text}")
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[KAM] Bildirim Dongusu Hatasi: {e}")

    async def run(self):
        client = genai.Client(
            api_key=get_api_key(),
            http_options={"api_version": "v1alpha"}
        )

        while True:
            # Duraklatılmışsa bağlanma, bekle
            if self._paused:
                await asyncio.sleep(1)
                continue

            try:
                print("[KAM] ğŸ”Œ Bağlanıyor...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=0)

                    print("[KAM] âœ… Bağlandı.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: KAM hazır. Dinliyorum...")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._capture_loop())
                    tg.create_task(self._ai_vision_loop())
                    tg.create_task(self._listen_notifications())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[KAM] âš ï¸  {e}")
                traceback.print_exc()
                self.set_speaking(False)
                self.ui.write_log(f"ERR: KAM baglantisi kesildi veya internete ulasilamiyor â€” {e}")
                self.ui.set_state("ERROR")
                print("[KAM] ğŸ”„ 3 saniyede yeniden bağlanıyor...")
                await asyncio.sleep(3)


def main():
    if os.environ.get("TERM_PROGRAM") == "vscode":
        print("[KAM] VS Code icinden baslatildi.")

    ui = KamUI()

    kam_ref = []
    def on_mobile_msg(raw_msg):
        try:
            data = json.loads(raw_msg)
            if data.get("type") == "text" and kam_ref:
                kam_ref[0]._on_text_command(data.get("content"))
        except Exception:
            pass
            
    m_server = MobileServer(on_message_callback=on_mobile_msg)
    m_server.start()

    def runner():
        ui.wait_for_api_key()
        kam = KAMLive(ui, m_server)
        kam_ref.append(kam)
        try:
            asyncio.run(kam.run())
        except KeyboardInterrupt:
            print("\n🔴 Kapatılıyor...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()
