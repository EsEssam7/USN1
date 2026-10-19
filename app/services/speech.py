"""Optional pronunciation preview using pyttsx3 (offline TTS)."""
from __future__ import annotations

import logging
import threading

log = logging.getLogger("usn")


def speech_available() -> bool:
    """True if pyttsx3 can be imported. A literal import lets PyInstaller bundle it."""
    try:
        import pyttsx3 as engine_module

        return engine_module is not None
    except Exception:  # noqa: BLE001 - any failure means no speech
        return False


def speak(text: str) -> None:
    """Speak text in a background thread. Never raises."""

    def _run() -> None:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:  # noqa: BLE001
            log.warning("speech failed: %s", exc)

    threading.Thread(target=_run, daemon=True).start()
