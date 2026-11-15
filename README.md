# KAM – Kişisel Yapay Zekâ Asistanı + KAM ASTRA

Windows üzerinde çalışan, Türkçe konuşan kişisel yapay zekâ asistanı **KAM** ve ona entegre astronot sağlık takip modülü **KAM ASTRA** (`modules/astra`).

> **Önemli:** KAM ASTRA geliştirme aşamasında bir prototiptir. Sağlık verileri **simülasyon** verisidir; sistem tıbbi teşhis koymaz ve doktorun yerini almaz.

---

## Gereksinimler

| Gereksinim | Not |
|---|---|
| **Windows 10 / 11** | KAM Windows'a özel özellikler kullanır; macOS ve Linux'ta çalışmaz. |
| **Python 3.10 – 3.12** | Önerilen: **3.12**. Kurulumda **"Add python.exe to PATH"** kutusunu işaretleyin. |
| **Mikrofon ve hoparlör** | Sesli konuşma için. |
| **İnternet** | Sesli sohbet Google Gemini Live API kullanır. KAM ASTRA'nın sağlık analizi ve uyarıları internetsiz de çalışır. |
| Kamera (isteğe bağlı) | Nesne tanıma ve yüz tanıma için. |

---

## Hızlı başlangıç

### 1. Depoyu indirin

GitHub'da **Code → Download ZIP** ile indirip bir klasöre çıkarın veya:

```powershell
git clone https://github.com/nurullahguner6513/KAM-ASTRA.git
cd KAM-ASTRA
```

### 2. Sanal ortamı kurun ve paketleri yükleyin

Proje klasöründe **PowerShell** açın ve sırayla çalıştırın:

```powershell
python -m venv venv
.\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install websockets librosa scikit-learn pycaw screen-brightness-control duckduckgo-search winrt-Windows.UI.Notifications.Management
```

> PowerShell "betik çalıştırma devre dışı" hatası verirse bir kez şunu çalıştırın:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

> Depodaki `.venv` klasörü başka bir bilgisayarda oluşturulmuştur ve taşınabilir değildir; **kullanmayın**, yukarıdaki gibi yeni bir `venv` kurun.

### 3. API anahtarını kontrol edin

Anahtarlar `config/api_keys.json` dosyasındadır:

```json
{
  "gemini_api_key": "GEMINI_ANAHTARINIZ",
  "voice": "Charon",
  "youtube_api_key": "",
  "youtube_channel_handle": ""
}
```

- Sesli sohbet için **`gemini_api_key` zorunludur.** Ücretsiz anahtar: https://aistudio.google.com/apikey
- Depodaki anahtar geçicidir ve ileride iptal edilecektir. Çalışmazsa kendi anahtarınızı yazın (`config/api_keys.example.json` örnek dosyadır).
- `youtube_api_key` yalnızca YouTube kanal istatistikleri için gerekir; boş bırakılabilir.

### 4. Çalıştırın

```powershell
python main.py
```

KAM arayüzü açılır ve dinlemeye başlar. Örnek komutlar:

- "Merhaba KAM, nasılsın?"
- "Sağlık analizi yap" → KAM ASTRA holografik sağlık penceresini açar
- "Son 7 gündeki değişimlerimi göster"
- "Radyasyon durumum nedir?"
- "Ne için geliştirildin?"

Sonraki açılışlarda yalnızca şu ikisi yeterlidir:

```powershell
.\venv\Scripts\activate
python main.py
```

---

## KAM ASTRA sağlık modülü

- Konum: `modules/astra`
- Varsayılan olarak **SIMULATED** (simülasyon) verisiyle çalışır; tüm simülasyon kayıtları açıkça etiketlenir.
- Risk seviyelerini (0 Normal – 4 Acil) yapay zekâ değil, test edilmiş ve yapılandırılabilir kurallar belirler: `modules/astra/config/`
- Sağlık verileri yerel SQLite veritabanında tutulur: `modules/astra/data/astra.db`
- Proaktif sesli uyarılar internetsiz, Windows'un yerel Türkçe sesiyle verilir. Windows'ta Türkçe ses yoksa: **Ayarlar → Saat ve dil → Konuşma → Ses ekle → Türkçe**.

### Testler

```powershell
python -m unittest discover -s modules/astra/tests -t .
```

113 otomatik test çalışır (simülasyon verisiyle).

---

## Mobil uygulama (isteğe bağlı)

`kam-mobile` klasörü, KAM'a telefondan bağlanan Expo uygulamasıdır. KAM çalışırken bilgisayarda `ws://<bilgisayar-IP>:8765` adresinde bir sunucu açılır.

```powershell
cd kam-mobile
npm install
npx expo start
```

Gerekli: Node.js 20+ ve telefonda **Expo Go** uygulaması.

---

## Klasör yapısı

| Klasör / dosya | İçerik |
|---|---|
| `main.py` | Ana program: Gemini Live bağlantısı, araçlar, ses akışı |
| `ui.py` | Tkinter HUD arayüzü |
| `core/prompt.txt` | KAM ASTRA kişilik ve davranış talimatı |
| `actions/` | Araçlar (uygulama açma, hava durumu, nesne tanıma, biyometri…) |
| `actions/ssd_mobilenet_v2_coco_2018_03_29/` | Nesne tanıma modeli |
| `modules/astra/` | KAM ASTRA sağlık modülü |
| `memory/` | Hafıza, yüz ve ses kayıtları |
| `config/` | API anahtarları |
| `kam-mobile/` | Mobil uygulama |

---

## Sık karşılaşılan sorunlar

| Sorun | Çözüm |
|---|---|
| `ModuleNotFoundError: No module named 'xxx'` | `pip install xxx` ile eksik paketi yükleyin (sanal ortam etkinken). |
| `pyaudio` kurulmuyor | Python 3.10–3.12 kullanın; 3.13+ sürümlerde sorun çıkabilir. |
| KAM konuşmuyor / bağlanmıyor | İnternet bağlantısını ve `gemini_api_key` değerini kontrol edin. |
| ASTRA uyarıları İngilizce okunuyor | Windows'a Türkçe konuşma sesi ekleyin (yukarıya bakın). |
| Mikrofon algılanmıyor | Windows **Ayarlar → Gizlilik → Mikrofon** izinlerini açın. |

---

## Depoda bulunmayanlar

`memory/phone_book.json` (telefon rehberi) ve diğer kişilere ait yüz kayıtları gizlilik nedeniyle eklenmemiştir. Rehber için `memory/phone_book.example.json` dosyasını kullanabilirsiniz; yüz kayıtları KAM'a "bu yüzü kaydet" denilerek yeniden oluşturulur.

Nesne tanıma modelinin sıkıştırılmış arşivi (`actions/ssd_mobilenet.tar.gz`, 188 MB) GitHub sınırını aştığı için eklenmemiştir; açılmış hâli `actions/ssd_mobilenet_v2_coco_2018_03_29/` klasöründe mevcuttur.
