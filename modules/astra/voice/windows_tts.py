"""
Windows seslendirme motorları (ek paket gerektirmez, internet gerektirmez).

Windows'ta iki ayrı ses sistemi vardır:
  - SAPI (System.Speech): KAM'ın actions/windows_utils.py içinde kullandığı eski sistem.
    Çoğu bilgisayarda yalnızca İngilizce sesler görünür.
  - OneCore (Windows.Media.SpeechSynthesis): Windows 10/11'in yeni ses sistemi.
    Türkçe dil paketiyle gelen "Microsoft Tolga" sesi genellikle yalnızca burada bulunur.

ASTRA önce yeni sistemde Türkçe ses arar; yoksa eski sistemde arar; ikisi de
yoksa varsayılan sesle konuşur ve kullanıcıyı uyarır. Metin PowerShell'e komut
satırıyla değil ortam değişkeniyle verilir (tırnak ve özel karakter sorunu olmaz).
"""

from __future__ import annotations

import os
import subprocess
import sys

_POWERSHELL = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]
NO_VOICE_EXIT = 3

_ONECORE_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
"""

_ONECORE_LIST = _ONECORE_PRELUDE + r"""
[Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | ForEach-Object { "$($_.DisplayName)|$($_.Language)" }
"""

_ONECORE_SPEAK = _ONECORE_PRELUDE + r"""
$null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
$want = $env:ASTRA_TTS_VOICE
$voice = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object {
    if ($want) { $_.DisplayName -like "*$want*" } else { $_.Language -like 'tr*' } } | Select-Object -First 1
if (-not $voice) { exit 3 }
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$synth.Voice = $voice
$stream = Await ($synth.SynthesizeTextToStreamAsync($env:ASTRA_TTS_TEXT)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
$size = [uint32]$stream.Size
$reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
Await ($reader.LoadAsync($size)) ([uint32]) | Out-Null
$bytes = New-Object byte[] $size
$reader.ReadBytes($bytes)
$path = Join-Path $env:TEMP ("astra_tts_" + [guid]::NewGuid().ToString() + ".wav")
[IO.File]::WriteAllBytes($path, $bytes)
try { (New-Object System.Media.SoundPlayer $path).PlaySync() }
finally { Remove-Item $path -ErrorAction SilentlyContinue }
"""


def _run(script: str, env_extra: dict | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra or {})
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
    return subprocess.run(_POWERSHELL + [script], capture_output=True, text=True, errors="replace",
                          timeout=timeout, env=env, creationflags=flags)


def onecore_voices() -> list[tuple[str, str]]:
    """Yeni Windows ses sistemindeki sesler: (ad, dil)."""
    try:
        result = _run(_ONECORE_LIST, timeout=20)
        voices = []
        for line in result.stdout.splitlines():
            if "|" in line:
                name, lang = line.rsplit("|", 1)
                voices.append((name.strip(), lang.strip()))
        return voices
    except Exception:
        return []


def sapi_voices() -> list[str]:
    """KAM'ın kullandığı eski ses sistemindeki sesler."""
    try:
        from actions.windows_utils import list_windows_voices

        return list_windows_voices()
    except Exception:
        return []


def speak_onecore(text: str, voice: str = "") -> tuple[bool, str]:
    try:
        result = _run(_ONECORE_SPEAK, {"ASTRA_TTS_TEXT": text, "ASTRA_TTS_VOICE": voice}, timeout=120)
    except Exception as exc:
        return False, str(exc)
    if result.returncode == 0:
        return True, "ok"
    if result.returncode == NO_VOICE_EXIT:
        return False, "Türkçe ses bulunamadı"
    return False, (result.stderr or result.stdout or f"çıkış kodu {result.returncode}").strip()[-400:]


def _is_turkish(name: str, lang: str = "") -> bool:
    low = f"{name} {lang}".lower()
    return lang.lower().startswith("tr") or "tolga" in low or "turk" in low or "türk" in low


def choose_voice(engine: str, voice: str, onecore: list[tuple[str, str]],
                 sapi: list[str]) -> tuple[str, str, str]:
    """Hangi motor ve sesin kullanılacağını seçer: (motor, ses, kullanıcıya not).

    engine: "auto" | "onecore" | "sapi". voice: istenen sesin adı (boşsa Türkçe aranır).
    """
    one_tr = [n for n, lang in onecore if _is_turkish(n, lang)]
    sapi_tr = [n for n in sapi if _is_turkish(n)]

    if engine == "onecore" or (engine == "auto" and (one_tr or (voice and any(voice.lower() in n.lower()
                                                                                for n, _ in onecore)))):
        chosen = voice or (one_tr[0] if one_tr else "")
        if chosen:
            return "onecore", chosen, ""
    if engine in ("auto", "sapi"):
        chosen = voice or (sapi_tr[0] if sapi_tr else "")
        if chosen or engine == "sapi":
            return "sapi", chosen, "" if chosen else "ASTRA: Türkçe Windows sesi bulunamadı; varsayılan sesle okunacak."
    return ("sapi", "", "ASTRA: Türkçe Windows sesi bulunamadı; uyarılar varsayılan Windows sesiyle okunacak. "
                        "Ayarlar → Saat ve dil → Konuşma bölümünden Türkçe ses ekleyebilirsiniz.")
