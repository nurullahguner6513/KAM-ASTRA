# KAM – Kişisel Yapay Zekâ Asistanı + KAM ASTRA

Windows üzerinde çalışan, Türkçe konuşan kişisel yapay zekâ asistanı **KAM** ve ona entegre astronot sağlık takip modülü **KAM ASTRA** (`modules/astra`).

> **Önemli:** KAM ASTRA geliştirme aşamasında bir prototiptir. Sağlık verileri **simülasyon** verisidir; sistem tıbbi teşhis koymaz ve doktorun yerini almaz.

---

## İçindekiler

1. [Proje hakkında](#proje-hakkında)
2. [Neden geliştirildi?](#neden-geliştirildi)
3. [Nasıl çalışır?](#nasıl-çalışır)
4. [Özellikler](#özellikler)
5. [Güvenlik ve dürüstlük ilkeleri](#güvenlik-ve-dürüstlük-ilkeleri)
6. [Mevcut durum ve yol haritası](#mevcut-durum-ve-yol-haritası)
7. [Kurulum ve çalıştırma](#gereksinimler)

---

## Proje hakkında

**KAM ASTRA**, uzun süreli uzay görevlerinde astronotun sağlık durumunu sürekli takip eden, verileri astronotun kendi geçmişiyle karşılaştıran, olağan dışı değişimleri erken fark edip astronotu **kendiliğinden sesli olarak uyaran** ve gerektiğinde **internetsiz** çalışabilen bir yapay zekâ destekli sağlık asistanıdır.

Proje sıfırdan yazılmış ayrı bir uygulama değildir. Hâlihazırda çalışan kişisel yapay zekâ asistanı **KAM**'ın mimarisine bağımsız bir modül olarak entegre edilmiştir. Böylece KAM'ın sesli konuşma, görüntü işleme ve arayüz yetenekleri astronot sağlığı için kullanılır.

> "Benim önceliğim, görev boyunca astronotun güvenliğine, sağlığına ve doğru bilgiye erişimine destek olmaktır."
> — KAM ASTRA'nın temel ilkesi

**Slogan:** *Your Health. Your Mission. Your AI Companion.*

---

## Neden geliştirildi?

NASA'nın İnsan Araştırma Programı (Human Research Program), uzun süreli görevlerde insan sağlığını etkileyen beş temel tehlike tanımlar:

| Tehlike | Astronota etkisi |
|---|---|
| **Uzay radyasyonu** | Dünya'nın koruyucu manyetik alanının dışında artan radyasyon dozu |
| **İzolasyon ve kapalı yaşam** | Uyku, ruh hâli, stres ve bilişsel performans üzerinde etkiler |
| **Dünya'dan uzaklık** | İletişim gecikir veya kesilir; tıbbi yardım hemen gelmez |
| **Değişen yerçekimi** | Kas, kemik, sıvı dağılımı ve dolaşımda değişim |
| **Kapalı ve zorlu ortam** | Hava kalitesi, sıcaklık, nem ve basınç sürekli izlenmeli |

Bu tehlikelerin ortak sonucu şudur: **Mars gibi uzak bir görevde Dünya'daki sağlık ekibi her an müdahale edemez.** İletişim dakikalarca gecikebilir, hatta tamamen kesilebilir. Bu nedenle sağlık takibinin:

- astronotun **yanında** ve **kesintisiz** olması,
- herkese aynı "normal" değeri uygulamak yerine **kişiye özel** olması,
- astronotun soru sormasını beklemeden **proaktif** uyarı vermesi,
- **internet ve Dünya bağlantısı olmadan** da temel işlevlerini sürdürmesi

gerekir. KAM ASTRA bu ihtiyaçlara yanıt aramak için geliştirildi. Amacı **teşhis koymak değil**, erken farkındalık sağlamak ve görev sağlık ekibine düzenli, güvenilir veri sunmaktır.

---

## Nasıl çalışır?

```
ASTRONOT
   │
   ▼
BİYOMEDİKAL SENSÖRLER            (planlanan: vücuda / giysiye entegre)
   │
   ▼
ELEKTRONİK VERİ TOPLAMA           (ölçüm → sayısallaştırma → zaman damgası → kalite kontrolü → aktarım)
   │
   ▼
KAM ASTRA VERİ İŞLEME             (yerel SQLite veritabanı, kaynak / birim / kalite / durum etiketi)
   │
   ▼
KURAL TABANLI RİSK MOTORU          (kişisel referans, trend, çoklu gösterge, 0–4 risk seviyesi)
   │
   ▼
YAPAY ZEKÂ AÇIKLAMASI             (sonucu doğal Türkçe ile anlatır, seviyeyi değiştirmez)
   │
   ├──► SESLİ UYARI   (yerel Türkçe ses, internetsiz)
   ├──► GÖRSEL BİLDİRİM (holografik sağlık penceresi, HUD sağlık kartı)
   └──► SAĞLIK RAPORU (günlük / haftalık / aylık)
```

Bugün sensör donanımı yerine **simülasyon verisi** ve **elle ölçüm girişi** kullanılır; mimari gerçek cihaz bağlantısına hazırdır.

---

## Özellikler

### KAM ASTRA – Sağlık modülü

**Veri toplama ve kalite**
- Takip edilen göstergeler: kalp atış hızı, dinlenik nabız, HRV, SpO2, kan basıncı, deri sıcaklığı, uyku (toplam / derin / REM / hafif), adım, hareketsizlik süresi, egzersiz, stres, ruh hâli, yorgunluk, radyasyon dozu.
- Her ölçüm için **kaynak cihaz, ölçüm zamanı (UTC), birim, güvenilirlik puanı (0–1), veri kalitesi ve ölçüm durumu** kaydedilir.
- Veri kaynakları ayrı etiketlenir: `SIMULATED`, `DEVICE`, `MANUAL`, `LAB`. **Simülasyon verisi gerçek veriyle asla karıştırılmaz.**
- Fizyolojik olarak imkânsız veya bozuk değerler **reddedilir** ve ayrı bir tabloda saklanır; şüpheli ölçümler işaretlenir.
- Tekrarlanan kayıtlar otomatik engellenir; eksik ve eski veri raporlarda açıkça belirtilir.

**Kişisel analiz**
- Her astronot için son **30 günden kişisel referans** (medyan ve yayılım) hesaplanır; referans için en az **7 günlük** veri gerekir.
- Günlük analiz, **haftalık ve aylık karşılaştırma**, trend analizi.
- Birden fazla göstergenin **birlikte** değerlendirilmesi (ör. nabız artışı + HRV düşüşü + uyku eksikliği).
- Hafif bir değişim **3 gün** sürerse seviye yükselir.

**Risk motoru (deterministik, test edilmiş, yapılandırılabilir)**

| Seviye | Anlamı | KAM'ın davranışı |
|---|---|---|
| **0 – Normal** | Değerler kişisel aralıkta | — |
| **1 – Bilgilendirme** | Hafif değişim | Bilgi verir |
| **2 – Dikkat** | Süren veya çoklu değişim | Sesli uyarı, yeniden ölçüm önerisi |
| **3 – Yüksek risk** | Tıbbi değerlendirme gerektirebilir | Uyarı + sağlık protokolü bildirimi |
| **4 – Acil** | Tanımlı acil kriterler | Öncelikli alarm, açık talimat, acil rapor |

- SpO2 için mutlak eşikler (ör. art arda ölçümlerde %90 ve %85 altı) ayrıca uygulanır.
- **Radyasyon için ayrı protokol motoru:** günlük doz, görev boyunca biriken doz ve görev sınırına oranı.
- Eşikler `modules/astra/risk_engine.py` ve `config/risk_rules.json` ile görev doktorlarınca ayarlanabilir. *Prototipteki eşikler örnek değerdir.*

**Uyarı yönetimi**
- Aynı uyarı sürekli tekrarlanmaz (seviyeye göre bekleme süresi).
- Astronot uyarıyı **sesle onaylayabilir** ("uyarıyı aldım").
- Onaylanmayan kritik uyarılar yeniden bildirilir: **Seviye 3 her 15 dakikada, Seviye 4 her 2 dakikada.**
- Sessize alma yalnızca Seviye 1–2 için geçerlidir; **kritik alarmlar susturulamaz.**
- Sesli ve görsel uyarı birlikte çalışır; veri bağlantısı kesilirse astronot bilgilendirilir.

**Sesli asistan**
- "Bugün sağlık durumum nasıl?", "Son 7 günü göster", "Radyasyon durumum nedir?", "Nabzım 72, kaydet" gibi doğal Türkçe sorular.
- KAM yalnızca **veritabanında gerçekten bulunan** verilere dayanır; veri yoksa açıkça söyler.
- Proaktif uyarılar **Windows'un yerel Türkçe sesiyle, internetsiz** okunur.

**Görsel arayüz**
- **Holografik sağlık penceresi:** dönen astronot hologramı, vücut bölgelerine göre renklenen durum noktaları ve analiz metni.
- KAM ana ekranındaki **sağlık kartı:** dönen hologram ve güncel ASTRA özeti.
- "Sağlık analizi yap" sesli komutuyla pencere açılır.

**Simülasyon ve test**
- 12 senaryo: normal, nabız artışı, HRV düşüşü, SpO2 düşüşü, uyku eksikliği, uzun hareketsizlik, yüksek stres, radyasyon artışı, sensör bağlantı kesilmesi, hatalı ölçüm, eksik veri, çoklu risk.
- Canlı simülasyon akışı ve **113 otomatik test** (yanlış alarm, kaçırılmış alarm, eski veri, sensör arızası dahil).

**Veri güvenliği**
- Zaman damgaları UTC olarak saklanır, görev yerel saati ayrıca gösterilir.
- Sağlık verisine erişim kayıtları (`access_log`) tutulur.
- Bozuk veya geçersiz veri girişleri reddedilir.
- Senkronizasyon durumu tutulur; çevrimdışıyken biriken veriler kaybolmaz.

**Veritabanı tabloları:** `astronauts`, `mission_records`, `health_measurements`, `sleep_records`, `activity_records`, `radiation_records`, `device_connections`, `health_baselines`, `health_risk_events`, `health_alerts`, `health_reports`, `rejected_inputs`, `access_log`.

### KAM – Kişisel asistan yetenekleri

| Yetenek | Açıklama | İnternet |
|---|---|---|
| Doğal sesli sohbet | Gemini Live ile gerçek zamanlı Türkçe konuşma | Gerekir |
| Motivasyon sohbeti | Yalnızlık, stres ve yorgunlukta destekleyici konuşma (profesyonel desteğin yerine geçmez) | Gerekir |
| Canlı veri | Hava durumu, sistem bilgisi | Gerekir (hava) |
| İnternette araştırma | Tarayıcıda arama, YouTube | Gerekir |
| Görüntü / ekran analizi | Aktif pencereyi veya kamera görüntüsünü yorumlama | Gerekir |
| **Nesne tanıma** | Kameradaki nesneleri tanıma (SSD MobileNet, OpenCV) | **Gerekmez** |
| Yüz ve ses biyometrisi | Kullanıcıyı tanıma | Gerekmez |
| Takvim, hatırlatıcı, not | Windows takvimi ve hatırlatıcılar | Gerekmez |
| Bilgisayar kontrolü | Uygulama açma, pencere, dosya, pano, ekran görüntüsü | Gerekmez |
| Mesajlaşma ve medya | WhatsApp, Spotify, YouTube | Gerekir |
| Çeviri | Metin çevirisi | Gerekir |
| Mobil uygulama | Telefondan KAM'a bağlanma | Yerel ağ |

**Kişilik:** KAM ASTRA kendini astronotun görev asistanı olarak konumlandırır; sakin, kısa ve doğal konuşur, emir veren değil iş birliği yapan bir yol arkadaşıdır (`core/prompt.txt`).

---

## Güvenlik ve dürüstlük ilkeleri

1. **Teşhis koymaz**, doktorun ve görev sağlık ekibinin yerini almaz.
2. **Risk seviyesini yapay zekâ değil, kurallar belirler.** Dil modeli yalnızca doğrulanmış sonucu açıklar.
3. **Veri uydurmaz.** Veri yoksa, eskiyse veya güvenilmezse bunu açıkça söyler.
4. **Simülasyon verisi her zaman "SİMÜLASYON" olarak işaretlenir.**
5. Ölçülemeyen bir şeyi ölçülebilir gibi göstermez: deri yüzey sıcaklığı vücut iç sıcaklığı değildir; SpO2 hareket ve soğuktan etkilenebilir.
6. Radyasyon biyomedikal sensörlerle değil, **ayrı dozimetre** ile ölçülür.
7. Görüntü işleme yalnızca **destekleyicidir**, biyomedikal ölçümün yerini almaz.
8. Temel sağlık uyarıları **buluttan bağımsız** tasarlanmıştır.

---

## Mevcut durum ve yol haritası

| Bileşen | Durum |
|---|---|
| Veri modeli, yerel veritabanı, kalite kontrolü | ✅ Mevcut (prototip) |
| Kişisel referans, trend, risk motoru, radyasyon protokolü | ✅ Mevcut (prototip) |
| Uyarı yönetimi, yerel Türkçe sesli uyarı | ✅ Mevcut (prototip) |
| KAM sesli asistan entegrasyonu, holografik arayüz | ✅ Mevcut (prototip) |
| 12 simülasyon senaryosu, 113 otomatik yazılım testi | ✅ Mevcut |
| Elle ölçüm girişi | ✅ Mevcut |
| Biyomedikal ve çevresel sensör altyapısı | 🔶 Planlanan |
| Elektronik veri toplama donanımı | 🔶 Planlanan |
| Gerçek dozimetre entegrasyonu | 🔶 Planlanan (yazılım arayüzü hazır) |
| Tamamen yerel dil modeli (internetsiz soru–cevap) | 🔶 Planlanan |
| Dünya ile veri eşitleme | 🔶 Planlanan |
| Gerçek ölçümlerle prototip testleri, tıbbi eşik doğrulaması | 🔶 Planlanan |
| Uzay yeterliliği (güvenilirlik, radyasyon dayanımı, EMC, görev uygunluğu) | 🔶 Planlanan |

> Sistemin uçuş sertifikası yoktur. Testler simülasyon verisiyle yapılmış **yazılım testleridir**; klinik veya uçuş testi değildir.

**Akıllı saat notu:** Denenen SK27 PLUS saati verilerini standart Bluetooth sağlık servisi veya Health Connect üzerinden paylaşmadığı için doğrudan bağlanamadı; bu nedenle elle ölçüm girişi eklendi. Mimari (`Health Data Connector → Device Adapter → Sensor Data Processor`) gerçek cihaz bağlantısına hazırdır.

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
