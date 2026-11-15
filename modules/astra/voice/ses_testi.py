"""
ASTRA ses testi. KAM klasöründe, VS Code terminalinden:

    python -m modules.astra.voice.ses_testi

Yüklü Windows seslerini listeler, ASTRA'nın hangisini seçtiğini söyler ve
Türkçe bir deneme cümlesi okur.
"""

from __future__ import annotations

from ..kam_bridge import load_settings
from .voice_alerts import make_speaker
from .windows_tts import choose_voice, onecore_voices, sapi_voices

SENTENCE = "Merhaba, ben KAM ASTRA. Sağlık izleme sistemi Türkçe konuşuyor. Ölçüm değeri 58,5 atım/dakika."


def main() -> None:
    settings = load_settings()
    onecore, sapi = onecore_voices(), sapi_voices()
    print("Eski Windows ses sistemi (KAM'ın kullandığı, System.Speech):")
    for name in sapi or ["(ses bulunamadı)"]:
        print("   -", name)
    print("Yeni Windows ses sistemi (OneCore):")
    for name, lang in onecore or [("(ses bulunamadı veya bu sistem okunamadı)", "")]:
        print("   -", name, f"[{lang}]" if lang else "")
    engine, voice, note = choose_voice(settings.get("voice_engine", "auto"), settings.get("voice", ""), onecore, sapi)
    print(f"\nASTRA'nın seçimi: motor={engine}, ses={voice or '(Windows varsayılanı)'}")
    if note:
        print("Not:", note)
    print("\nDeneme cümlesi okunuyor...")
    errors = []
    make_speaker(engine, voice, on_error=errors.append)(SENTENCE)
    print("Sonuç:", "HATA — " + " | ".join(errors) if errors else "okundu (sesi duydunuz mu?)")


if __name__ == "__main__":
    main()
