"""Spoken and on-screen prompts for data collection.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

import logging
import os
import platform
import shutil
import subprocess
import threading
import time

from localization import get_active_language, tr, tr_english

logger = logging.getLogger(__name__)

speech_lock = threading.Lock()


def speak(text, lang="en", fallback=None):
    """Speak ``text`` (language ``lang``) on a background thread; returns an
    Event set when done. ``fallback`` (English) is spoken instead when the
    system has no voice for ``lang``."""
    done_event = threading.Event()
    threading.Thread(
        target=_speak_platform_specific,
        args=(text, lang, fallback or text, done_event),
        daemon=True,
    ).start()
    return done_event


def say(key):
    """Speak a ``data_collection_prompts`` line in the app's UI language."""
    full = f"data_collection_prompts.{key}"
    return speak(tr(full), get_active_language(), tr_english(full))


def prompt_text(key):
    """A ``data_collection_prompts`` line in the app's UI language."""
    return tr(f"data_collection_prompts.{key}")


def _run_tts_command(command, timeout, stdin_text=None, env=None):

    if shutil.which(command[0]) is None:
        return False
    try:
        if stdin_text is None:
            result = subprocess.run(
                command, check=False, timeout=timeout, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            return result.returncode == 0
        proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        try:
            proc.communicate(input=stdin_text.encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return False
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return False


# espeak voice names where they differ from the UI language code.
_ESPEAK_VOICES = {"zh": "cmn"}


def _bundled_espeak():
    """``(executable, env)`` for the espeak-ng the Steam Frame build ships in
    tools/tts/ (the headset has no TTS engine of its own), or None."""
    from utils.misc_utils import resource_path

    tts = resource_path("tools/tts")
    exe = os.path.join(tts, "espeak-ng")
    if not os.access(exe, os.X_OK):
        return None
    env = dict(os.environ, ESPEAK_DATA_PATH=tts, LD_LIBRARY_PATH=os.path.join(tts, "lib"))
    return exe, env


def _speak_linux(text, lang, fallback):
    """Speak with the bundled espeak-ng, else the first system TTS engine
    found. False when there is none."""
    bundled = _bundled_espeak()
    if bundled is not None:
        exe, env = bundled
        if _run_tts_command([exe, "-v", _ESPEAK_VOICES.get(lang, lang), text], timeout=20, env=env):
            return True
        if lang != "en" and _run_tts_command([exe, "-v", "en", fallback], timeout=20, env=env):
            return True
    if lang != "en":
        voice = _ESPEAK_VOICES.get(lang, lang)
        for command in (
            ["spd-say", "--wait", "-l", lang, text],
            ["espeak-ng", "-v", voice, text],
            ["espeak", "-v", voice, text],
        ):
            if _run_tts_command(command, timeout=20):
                return True
        text = fallback  # no voice for this language: say it in English
    linux_tts_commands = (
        ["spd-say", "--wait", text],
        ["espeak-ng", text],
        ["espeak", text],
    )
    for command in linux_tts_commands:
        if _run_tts_command(command, timeout=20):
            return True
    return _run_tts_command(["festival", "--tts"], timeout=20, stdin_text=text)


def _reading_seconds(text):
    """About how long ``text`` takes to say, used to pace a prompt that could
    not be spoken: the overlay card then stays up as long as the voice would
    have, instead of the next step starting before it can be read."""
    # Words for spaced scripts, characters for Chinese and Japanese.
    return min(8.0, 0.6 + max(0.4 * len(text.split()), 0.06 * len(text)))


# The text travels in environment variables, never inside the script, so quotes
# or non-ASCII characters in a translation cannot break the command. Picks an
# installed voice for the language; without one, speaks the English fallback.
_WINDOWS_TTS = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$t = $env:ETVR_TTS_TEXT; "
    "function Pick($c) { $s.GetInstalledVoices() | Where-Object { $_.Enabled -and "
    "$_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq $c } | Select-Object -First 1 }; "
    "$v = Pick $env:ETVR_TTS_LANG; "
    "if (-not $v -and $env:ETVR_TTS_LANG -ne 'en') { $t = $env:ETVR_TTS_FALLBACK; $v = Pick 'en' }; "
    "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; "
    "$s.Speak($t)"
)


def _speak_platform_specific(text, lang, fallback, done_event):
    try:
        with speech_lock:
            system = platform.system().lower()
            if system == "darwin":
                subprocess.run(
                    ["say", text], check=False, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
            elif system == "windows":
                env = dict(os.environ, ETVR_TTS_TEXT=text, ETVR_TTS_LANG=lang or "en", ETVR_TTS_FALLBACK=fallback)
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", _WINDOWS_TTS],
                    env=env,
                    check=False,
                    timeout=20,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            elif system == "linux":
                if not _speak_linux(text, lang or "en", fallback):
                    time.sleep(_reading_seconds(text))
    except Exception:
        logger.debug("Speaking the prompt failed", exc_info=True)
    finally:
        done_event.set()
