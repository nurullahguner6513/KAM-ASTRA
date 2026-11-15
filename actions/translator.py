"""
Metin çevirisi — Gemini API tabanlı
"""

from __future__ import annotations

from google import genai  # type: ignore[reportMissingImports]
from google.genai import types  # type: ignore[reportMissingImports]

from app_config import get_app_config_value


LANG_MAP = {
    "en": "English", "tr": "Turkish", "de": "German",
    "fr": "French", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "ru": "Russian", "ja": "Japanese",
    "ko": "Korean", "zh": "Chinese", "ar": "Arabic",
    "nl": "Dutch", "sv": "Swedish", "pl": "Polish",
    "ingilizce": "English", "türkçe": "Turkish", "almanca": "German",
    "fransızca": "French", "ispanyolca": "Spanish", "italyanca": "Italian",
    "portekizce": "Portuguese", "rusça": "Russian", "japonca": "Japanese",
    "korece": "Korean", "çince": "Chinese", "arapça": "Arabic",
}


def translate_text(text: str, target_lang: str = "en") -> str:
    if not text:
        return "Çevrilecek metin belirtilmedi."

    api_key = str(get_app_config_value("gemini_api_key", "") or "").strip()
    if not api_key:
        return "Gemini API anahtarı eksik olduğu için çeviri yapılamadı."

    target = (target_lang or "en").strip().lower()
    lang_name = LANG_MAP.get(target, target.title())

    prompt = (
        f"Translate the following text to {lang_name}. "
        "Only output the translation, nothing else.\n\n"
        f"{text}"
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="models/gemini-2.0-flash",
            contents=[types.Part.from_text(text=prompt)],
            config=types.GenerateContentConfig(temperature=0.1),
        )
        result = str(getattr(response, "text", "") or "").strip()
        if not result:
            return "Çeviri sonucu boş döndü."
        return f"[{lang_name}] {result}"
    except Exception as e:
        return f"Çeviri hatası: {e}"
