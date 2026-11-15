# KAM – Kişisel Yapay Zekâ Asistanı + KAM ASTRA

Windows üzerinde çalışan KAM asistanı ve astronot sağlık takip modülü KAM ASTRA (`modules/astra`).

> KAM ASTRA geliştirme aşamasında bir prototiptir. Sağlık verileri simülasyondur; sistem tıbbi teşhis koymaz.

## Kurulum

1. `setup.ps1` ile sanal ortamı kurun veya `pip install -r requirements.txt` çalıştırın.
2. `config/api_keys.example.json` dosyasını `config/api_keys.json` olarak kopyalayıp kendi anahtarınızı girin.
3. `memory/*.example.json` dosyalarını `.example` olmadan kopyalayın.
4. Depoda bulunmayan büyük model dosyaları:
   - Nesne tanıma modeli: `python download_tf_ssd.py` (veya `download_mobilenet.py`)
   - Türkçe Piper sesi: `tr_TR-dfki-medium.onnx` (`tr_TR-dfki-medium.onnx.json` yanına koyun)
5. `python main.py`

## Depoya eklenmeyenler

API anahtarları, hafıza ve rehber dosyaları, yüz/ses biyometri kayıtları, ASTRA veritabanı ve yedekleri, günlükler, sanal ortamlar ve büyük model dosyaları.

## Testler

```
python -m unittest discover modules/astra/tests
```
