"""Persistent user data: favorites, used marks, history, reminders, settings."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.services.storage import JsonStore

HISTORY_LIMIT = 100
REMINDER_AFTER_SECONDS = 3 * 24 * 3600

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "dark",            # dark | light | system
    "language": "en",           # en | ar
    "arabic_digits": False,
    "speech": True,
    "default_platforms": ["x", "instagram", "github"],
    "default_pattern": "CVCV",
    "cache_enabled": True,
    "shortcuts": {
        "generate": "<Control-g>", "load_more": "<Control-l>", "search": "<Control-f>",
        "star": "s", "copy": "<Control-c>", "used": "u", "check": "<Control-k>",
        "settings": "<Control-comma>",
    },
}


class Repository:
    """Thin layer over JSON stores. Every mutation is saved immediately."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._favorites = JsonStore(directory / "favorites.json", [])
        self._used = JsonStore(directory / "used.json", [])
        self._history = JsonStore(directory / "history.json", [])
        self._reminders = JsonStore(directory / "reminders.json", {})
        self._settings_store = JsonStore(directory / "settings.json", DEFAULT_SETTINGS)
        self.cache = JsonStore(directory / "cache.json", {})
        self.favorites: list[dict] = self._favorites.load()
        self.used: list[dict] = self._used.load()
        self.history: list[dict] = self._history.load()
        self.reminders: dict[str, dict] = self._reminders.load()
        self.settings: dict[str, Any] = {**DEFAULT_SETTINGS, **self._settings_store.load()}

    # ---- settings ---------------------------------------------------------
    def save_settings(self) -> None:
        self._settings_store.save(self.settings)

    # ---- favorites --------------------------------------------------------
    def is_favorite(self, username: str) -> bool:
        return any(f["username"].lower() == username.lower() for f in self.favorites)

    def toggle_favorite(self, username: str, score: int | None = None) -> bool:
        """Add or remove a favorite. Returns True if it is now a favorite."""
        if self.is_favorite(username):
            self.favorites = [f for f in self.favorites if f["username"].lower() != username.lower()]
            self._favorites.save(self.favorites)
            return False
        self.favorites.append({
            "username": username, "note": "", "score": score,
            "date": time.strftime("%Y-%m-%d"),
        })
        self._favorites.save(self.favorites)
        return True

    def set_note(self, username: str, note: str) -> None:
        for f in self.favorites:
            if f["username"].lower() == username.lower():
                f["note"] = note
        self._favorites.save(self.favorites)

    def replace_favorites(self, items: list[dict]) -> int:
        """Merge imported favorites, skipping duplicates. Returns how many were added."""
        existing = {f["username"].lower() for f in self.favorites}
        added = 0
        for item in items:
            name = str(item.get("username", "")).strip()
            if name and name.lower() not in existing:
                self.favorites.append({"username": name, "note": item.get("note", ""),
                                       "score": item.get("score"), "date": item.get("date", "")})
                existing.add(name.lower())
                added += 1
        self._favorites.save(self.favorites)
        return added

    # ---- used marks -------------------------------------------------------
    def mark_used(self, username: str, platform: str) -> None:
        if not self.is_used(username, platform):
            self.used.append({"username": username, "platform": platform,
                              "date": time.strftime("%Y-%m-%d")})
            self._used.save(self.used)

    def unmark_used(self, username: str, platform: str) -> None:
        self.used = [u for u in self.used
                     if not (u["username"].lower() == username.lower() and u["platform"] == platform)]
        self._used.save(self.used)

    def is_used(self, username: str, platform: str) -> bool:
        return any(u["username"].lower() == username.lower() and u["platform"] == platform
                   for u in self.used)

    def used_platforms(self, username: str) -> list[str]:
        return [u["platform"] for u in self.used if u["username"].lower() == username.lower()]

    # ---- history ----------------------------------------------------------
    def add_history(self, entry: dict) -> None:
        self.history.insert(0, {**entry, "timestamp": time.strftime("%Y-%m-%d %H:%M")})
        del self.history[HISTORY_LIMIT:]
        self._history.save(self.history)

    def clear_history(self) -> None:
        self.history = []
        self._history.save(self.history)

    # ---- reminders --------------------------------------------------------
    def reserve(self, username: str, platform: str) -> None:
        self.reminders[f"{platform}:{username.lower()}"] = {
            "username": username, "platform": platform, "reserved_at": time.time(),
            "status": "reserved",
        }
        self._reminders.save(self.reminders)

    def set_reminder_status(self, key: str, status: str) -> None:
        if key in self.reminders:
            self.reminders[key]["status"] = status
            self._reminders.save(self.reminders)

    def due_reminders(self, now: float | None = None) -> list[dict]:
        """Reserved names older than 3 days that are not yet registered or dropped."""
        now = now or time.time()
        return [r for r in self.reminders.values()
                if r["status"] == "reserved" and now - r["reserved_at"] > REMINDER_AFTER_SECONDS]
