"""Main window: sidebar navigation, shared services, shortcuts and banners."""
from __future__ import annotations

import json
import logging
import queue
import random
import socket
import threading
from tkinter import messagebox

import tkinter as tk

import customtkinter as ctk

from app.core.brandable import load_dictionary, load_syllables
from app.core.filters import parse_blocklist
from app.core.phonetics import speech_text
from app.core.platform_rules import load_rules
from app.core.scoring import score_name
from app.core.similarity import find_similar
from app.i18n import i18n
from app.i18n.i18n import is_rtl, t
from app.services import speech
from app.services.availability import AvailabilityChecker
from app.services.repository import Repository
from app.services.storage import data_dir, setup_logging
from app.ui import theme
from app.ui.generator_view import GeneratorView
from app.ui.other_views import FavoritesView, HistoryView, SettingsView
from app.ui.widgets import ask_platform

ASSETS = theme.ASSETS
NAV = [("generator", "sparkles", "nav.generator"), ("favorites", "bookmark", "nav.favorites"),
       ("history", "history", "nav.history"), ("settings", "settings", "nav.settings")]
log = logging.getLogger("usn")


class USNApp(ctk.CTk):
    """Root window. Owns services; views read them through self."""

    def __init__(self) -> None:
        super().__init__()
        theme.clear_icon_cache()
        self.data_path = data_dir()
        setup_logging(self.data_path)
        self.repo = Repository(self.data_path)
        self.checker = AvailabilityChecker(cache=self.repo.cache if self.repo.settings["cache_enabled"] else None)
        self.rng = random.Random()
        self.syllables = load_syllables()
        self.dictionary = load_dictionary()
        self.blocklist = self._load_blocklist()
        self._offline_queue: queue.Queue = queue.Queue()
        self._views: dict[str, ctk.CTkFrame] = {}
        self._active = None
        self._banner = None

        i18n.set_language(self.repo.settings["language"])
        theme.apply_mode(self.repo.settings["theme"])
        self.title(t("app.title"))
        self.geometry("1280x800")
        self.minsize(1000, 640)
        self.configure(fg_color=theme.BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_shell()
        self.show("generator")
        self._bind_shortcuts()
        self._show_reminders()
        threading.Thread(target=self._probe_network, daemon=True).start()
        self.after(300, self._poll_network)

    # ---------------------------------------------------------------- shell
    def _build_shell(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._views.clear()
        self._active = None
        side = "right" if is_rtl() else "left"

        self.sidebar = theme.Frame(self, width=190, fg_color=theme.SURFACE, corner_radius=0)
        self.sidebar.pack(side=side, fill="y")
        self.sidebar.pack_propagate(False)
        ctk.CTkLabel(self.sidebar, text="USN", font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=theme.TEXT).pack(anchor="w", padx=18, pady=(22, 18))
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for key, icon, label_key in NAV:
            btn = ctk.CTkButton(self.sidebar, text=t(label_key), image=theme.ui_icon(icon, 18),
                                anchor="e" if is_rtl() else "w", fg_color="transparent",
                                text_color=theme.TEXT, hover_color=theme.SURFACE_HOVER,
                                height=38, corner_radius=8,
                                command=lambda k=key: self.show(k))
            btn.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[key] = btn

        self.main = theme.Frame(self, fg_color=theme.BG, corner_radius=0)
        self.main.pack(side="right" if not is_rtl() else "left", fill="both", expand=True)
        self.banner_slot = theme.Frame(self.main, fg_color="transparent")
        self.banner_slot.pack(fill="x")
        self.content = theme.Frame(self.main, fg_color=theme.BG, corner_radius=0)
        self.content.pack(fill="both", expand=True)

        lang_row = theme.Frame(self.sidebar, fg_color="transparent")
        lang_row.pack(side="bottom", fill="x", padx=10, pady=14)
        ctk.CTkButton(lang_row, text="English / العربية", height=30, fg_color="transparent",
                      text_color=theme.MUTED, hover_color=theme.SURFACE_HOVER,
                      command=lambda: self.set_language("ar" if i18n.current_language() == "en" else "en")
                      ).pack(fill="x")

    def show(self, name: str) -> None:
        if self._active is not None:
            self._active.pack_forget()
        if name not in self._views:
            factory = {"generator": GeneratorView, "favorites": FavoritesView,
                       "history": HistoryView, "settings": SettingsView}[name]
            self._views[name] = factory(self.content, self)
        view = self._views[name]
        view.pack(fill="both", expand=True)
        self._active = view
        for key, btn in self.nav_buttons.items():
            btn.configure(fg_color=theme.SURFACE_HOVER if key == name else "transparent")

    def generator(self) -> GeneratorView:
        self.show("generator")
        return self._views["generator"]

    def refresh_all(self) -> None:
        if "generator" in self._views:
            self._views["generator"].refresh_cards()
        if "favorites" in self._views:
            self._views["favorites"].render()
        if "history" in self._views:
            self._views["history"].render()

    def set_language(self, lang: str) -> None:
        self.repo.settings["language"] = lang
        self.repo.save_settings()
        i18n.set_language(lang)
        self.title(t("app.title"))
        self._build_shell()
        self.show("generator")

    # ------------------------------------------------------------- services
    def _load_blocklist(self) -> frozenset[str]:
        custom = self.data_path / "blocklist.txt"
        source = custom if custom.exists() else ASSETS / "blocklist.txt"
        return parse_blocklist(source.read_text(encoding="utf-8"))

    def set_blocklist(self, text: str) -> None:
        (self.data_path / "blocklist.txt").write_text(text, encoding="utf-8")
        self.blocklist = parse_blocklist(text)

    def trending_names(self) -> list[str]:
        return [p["pattern"] for p in self._trending()]

    def trending_pattern(self, pattern: str) -> dict | None:
        """Return the trending entry for a pattern, with a text in the current language."""
        for p in self._trending():
            if p["pattern"] == pattern:
                lang = i18n.current_language()
                return {"pattern": pattern, "text": p.get(lang, p.get("en", ""))}
        return None

    def _trending(self) -> list[dict]:
        data = json.loads((ASSETS / "trending_patterns.json").read_text(encoding="utf-8"))
        return data.get("patterns", [])

    def saved_names(self) -> list[str]:
        return [f["username"] for f in self.repo.favorites]

    # ------------------------------------------------------------ actions
    def select_username(self, name: str) -> None:
        self.generator().select_username(name)

    def copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)

    def copy_username(self, name: str, card=None) -> None:
        self.copy_text(name)
        if card is not None:
            card.flash_copied()

    def toggle_favorite(self, name: str) -> None:
        if not self.repo.is_favorite(name):
            similar = find_similar(name, self.saved_names())
            if similar and not messagebox.askyesno("USN", t("similar.warning", name=similar[0].other)):
                return
        self.repo.toggle_favorite(name, score_name(name, self.dictionary).total)
        self.refresh_all()

    def speak(self, name: str) -> None:
        if not (self.repo.settings.get("speech", True) and speech.speech_available()):
            messagebox.showinfo("USN", t("set.speech_missing"))
            return
        speech.speak(speech_text(name))

    def check_username(self, name: str) -> None:
        self.generator().check_username(name)

    def mark_used_dialog(self, name: str) -> None:
        view = self.generator()
        platforms = view.selected_platforms() or list(load_rules())
        known = self.saved_names() + [u["username"] for u in self.repo.used]

        def confirm(key: str) -> None:
            similar = find_similar(name, known)
            if similar and not messagebox.askyesno(
                    "USN", t("similar.used", name=similar[0].other)):
                return
            self.repo.mark_used(name, key)
            self.refresh_all()

        ask_platform(self, t("card.used"), platforms, confirm)

    def confirm_unmark_used(self, name: str, platform: str) -> None:
        if messagebox.askyesno("USN", t("common.remove") + f" {platform}?"):
            self.repo.unmark_used(name, platform)
            self.refresh_all()

    def restore_history(self, entry: dict) -> None:
        view = self.generator()
        view.clear_results()
        for name in entry.get("usernames", []):
            view.seen.add(name)
            view._add_card(name, use_arabic=False)

    def reserve_dialog(self, name: str) -> None:
        platforms = self.generator().selected_platforms() or list(load_rules())

        def confirm(key: str) -> None:
            self.repo.reserve(name, key)
            self._show_reminders()

        ask_platform(self, t("detail.reserve"), platforms, confirm)

    # ------------------------------------------------------------ banners
    def _show_banner(self, text: str) -> None:
        for child in self.banner_slot.winfo_children():
            child.destroy()
        bar = theme.Frame(self.banner_slot, fg_color=theme.SURFACE, corner_radius=0)
        bar.pack(fill="x")
        ctk.CTkLabel(bar, text=text, text_color=theme.TEXT, wraplength=800,
                     anchor="e" if is_rtl() else "w").pack(side="left" if not is_rtl() else "right",
                                                            padx=14, pady=8, fill="x", expand=True)
        ctk.CTkButton(bar, text=t("reminder.dismiss"), width=80, height=26, fg_color="transparent",
                      text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
                      command=bar.destroy).pack(side="right" if not is_rtl() else "left", padx=10)

    def _show_reminders(self) -> None:
        due = self.repo.due_reminders()
        if due:
            names = ", ".join(f"{r['username']} ({r['platform']})" for r in due)
            self._show_banner(t("reminder.banner", names=names))

    def _probe_network(self) -> None:
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=2).close()
            self._offline_queue.put(False)
        except OSError:
            self._offline_queue.put(True)

    def _poll_network(self) -> None:
        try:
            offline = self._offline_queue.get_nowait()
        except queue.Empty:
            try:
                self.after(300, self._poll_network)
            except tk.TclError:  # window already closed
                pass
            return
        if offline:
            self._show_banner(t("offline.banner"))

    # ----------------------------------------------------------- shortcuts
    def _bind_shortcuts(self) -> None:
        """Bind every shortcut from settings. Replaces earlier bindings, so calling it again is safe."""
        for seq in getattr(self, "_bound_seqs", []):
            self.unbind_all(seq)
        self._bound_seqs: list[str] = []

        def guarded(fn):
            def handler(_event=None):
                focus = self.focus_get()
                if focus is not None and focus.winfo_class() in ("Entry", "Text"):
                    return None  # never steal keys while the user is typing
                fn()
                return "break"
            return handler

        def on_generator(method: str):
            def run():
                view = self._views.get("generator")
                if view is not None and self._active is view:
                    getattr(view, method)()
            return run

        def selected():
            view = self._views.get("generator")
            if view is not None and view.selected:
                return view
            return None

        def do_copy():
            view = selected()
            if view is not None:
                self.copy_username(view.selected, view.cards.get(view.selected))

        def do_star():
            view = selected()
            if view is not None:
                self.toggle_favorite(view.selected)

        def do_used():
            view = selected()
            if view is not None:
                self.mark_used_dialog(view.selected)

        def do_check():
            view = selected()
            if view is not None:
                self.check_username(view.selected)

        bindings = {
            "generate": on_generator("generate_new"), "load_more": on_generator("load_more"),
            "copy": do_copy, "star": do_star, "used": do_used, "check": do_check,
            "search": lambda: self.show("favorites"), "settings": lambda: self.show("settings"),
        }
        shortcuts = self.repo.settings["shortcuts"]
        for action, fn in bindings.items():
            seq = shortcuts.get(action)
            if seq:
                self.bind_all(seq, guarded(fn))
                self._bound_seqs.append(seq)
        self.bind_all("?", guarded(self.show_help))
        self._bound_seqs.append("?")

    def save_shortcuts(self, mapping: dict[str, str]) -> str | None:
        """Validate and store new shortcuts. Returns the first invalid sequence, or None on success."""
        probe = tk.Frame(self)  # validate on a throwaway widget; live bindings stay untouched
        try:
            for seq in mapping.values():
                try:
                    probe.bind(seq, lambda _e: None)
                except tk.TclError:
                    return seq
        finally:
            probe.destroy()
        self.repo.settings["shortcuts"] = {**self.repo.settings["shortcuts"], **mapping}
        self.repo.save_settings()
        self._bind_shortcuts()
        return None

    def show_help(self) -> None:
        messagebox.showinfo(t("help.title"), "\n".join(
            f"{t('help.' + a)}: {seq}" for a, seq in self.repo.settings["shortcuts"].items()))

    # ------------------------------------------------------------- lifecycle
    def on_close(self) -> None:
        log.info("closing")
        self.destroy()
