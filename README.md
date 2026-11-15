# KAM – Kişisel Yapay Zekâ Asistanı + KAM ASTRA

Windows üzerinde çalışan KAM asistanı ve astronot sağlık takip modülü KAM ASTRA (`modules/astra`).

> KAM ASTRA geliştirme aşamasında bir prototiptir. Sağlık verileri simülasyondur; sistem tıbbi teşhis koymaz.

## Kurulum

1. `setup.ps1` ile sanal ortamı kurun veya `pip install -r requirements.txt` çalıştırın.
2. `config/api_keys.example.json` dosyasını `config/api_keys.json` olarak kopyalayıp kendi anahtarınızı girin.
3. `memory/*.example.json` dosyalarını `.example` olmadan kopyalayın.
4. Büyük model dosyaları (nesne tanıma modeli ve Türkçe Piper sesi) Git LFS ile depoda; klonlamadan önce `git lfs install` çalıştırın.
5. `python main.py`

## Depoya eklenmeyenler

API anahtarları, hafıza ve rehber dosyaları, yüz/ses biyometri kayıtları (kişisel veri) ile yeniden oluşturulabilen sanal ortamlar (`.venv`) ve `node_modules`.

## Testler

```
python -m unittest discover modules/astra/tests
```
