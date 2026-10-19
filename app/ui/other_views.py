"""Favorites, History and Settings screens."""
from __future__ import annotations

from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.core import export
from app.core.platform_rules import get_rule, load_rules
from app.i18n.i18n import is_rtl, t
from app import __version__
from app.ui import theme
from app.ui.widgets import anchor

if TYPE_CHECKING:
    from app.ui.app import USNApp


def _title(parent, text: str) -> ctk.CTkLabel:
    label = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=theme.TEXT, anchor=anchor())
    label.pack(fill="x", padx=18, pady=(16, 8))
    return label


def _outline_button(parent, text: str, command, icon: str | None = None, width: int = 0) -> ctk.CTkButton:
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=32,
                         fg_color="transparent", text_color=theme.TEXT, border_width=1,
                         border_color=theme.BORDER, hover_color=theme.SURFACE_HOVER,
                         image=theme.ui_icon(icon, 16) if icon else None)


class FavoritesView(theme.Frame):
    """Saved usernames with notes, sorting, search, import and export."""

    def __init__(self, master, app: "USNApp"):
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        _title(self, t("fav.title"))

        bar = theme.Frame(self, fg_color="transparent")
        bar.pack(fill="x", padx=18, pady=(0, 8))
        self.search = ctk.CTkEntry(bar, placeholder_text=t("fav.search"), width=220)
        self.search.pack(side="left" if not is_rtl() else "right", padx=(0, 8))
        self.search.bind("<KeyRelease>", lambda _e: self.render())
        self.sort = ctk.CTkSegmentedButton(bar, values=[t("fav.sort.date"), t("fav.sort.score"), t("fav.sort.name")],
                                           command=lambda _v: self.render())
        self.sort.set(t("fav.sort.date"))
        self.sort.pack(side="left" if not is_rtl() else "right", padx=4)
        _outline_button(bar, t("fav.export"), self.export_dialog, "download").pack(side="right", padx=4)
        _outline_button(bar, t("fav.reminders"), lambda: ReminderDialog(self, self.app), "bookmark").pack(
            side="right", padx=4)
        _outline_button(bar, t("fav.import"), self.import_dialog, "upload").pack(side="right", padx=4)
        _outline_button(bar, t("fav.copy_all"), self.copy_all, "copy").pack(side="right", padx=4)

        self.list = ctk.CTkScrollableFrame(self, fg_color=theme.BG)
        self.list.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.render()

    def render(self) -> None:
        for child in self.list.winfo_children():
            child.destroy()
        items = list(self.app.repo.favorites)
        query = self.search.get().strip().lower()
        if query:
            items = [f for f in items if query in f["username"].lower()]
        mode = self.sort.get()
        if mode == t("fav.sort.score"):
            items.sort(key=lambda f: f.get("score") or 0, reverse=True)
        elif mode == t("fav.sort.name"):
            items.sort(key=lambda f: f["username"].lower())
        else:
            items.sort(key=lambda f: f.get("date", ""), reverse=True)

        if not items:
            ctk.CTkLabel(self.list, text=t("fav.empty"), text_color=theme.MUTED).pack(pady=30)
            return
        for item in items:
            self._row(item)

    def _row(self, item: dict) -> None:
        row = theme.Frame(self.list, height=0, fg_color=theme.SURFACE, border_width=1,
                           border_color=theme.BORDER, corner_radius=theme.RADIUS)
        row.pack(fill="x", pady=4, padx=4)
        ctk.CTkLabel(row, text=item["username"], font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=theme.TEXT).pack(side="left", padx=12, pady=10)
        if item.get("score") is not None:
            ctk.CTkLabel(row, text=str(item["score"]), text_color=theme.MUTED).pack(side="left", padx=6)
        note = ctk.CTkEntry(row, placeholder_text=t("fav.note"), width=220)
        note.insert(0, item.get("note", ""))
        note.pack(side="left", padx=8)
        note.bind("<Return>", lambda _e, n=item["username"], w=note: self.app.repo.set_note(n, w.get()))
        note.bind("<FocusOut>", lambda _e, n=item["username"], w=note: self.app.repo.set_note(n, w.get()))
        _outline_button(row, t("card.copy"), lambda n=item["username"]: self.app.copy_text(n), "copy").pack(
            side="right", padx=8, pady=8)
        _outline_button(row, t("common.remove"), lambda n=item["username"]: self.remove(n), "x").pack(
            side="right", padx=4, pady=8)

    def remove(self, name: str) -> None:
        self.app.repo.toggle_favorite(name)  # toggles off because it is already a favorite
        self.app.refresh_all()

    def copy_all(self) -> None:
        text = export.as_plain_list([f["username"] for f in self.app.repo.favorites])
        self.app.copy_text(text)

    def export_dialog(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")])
        if not path:
            return
        favs = self.app.repo.favorites
        data = export.favorites_to_csv(favs) if path.lower().endswith(".csv") else export.favorites_to_json(favs)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(data)

    def import_dialog(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            items = (export.favorites_from_csv(text) if path.lower().endswith(".csv")
                     else export.favorites_from_json(text))
        except (ValueError, OSError) as exc:
            messagebox.showerror("USN", str(exc))
            return
        self.app.repo.replace_favorites(items)
        self.app.refresh_all()


class ReminderDialog(ctk.CTkToplevel):
    """Lists reserved names and lets the user mark each one Reserved, Registered or Dropped."""

    STATUSES = (("reserved", "rem.reserved"), ("registered", "rem.registered"), ("dropped", "rem.dropped"))

    def __init__(self, master, app: "USNApp"):
        super().__init__(master)
        self.app = app
        self.title(t("rem.title"))
        self.geometry("480x420")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        ctk.CTkLabel(self, text=t("rem.title"), font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=theme.TEXT).pack(anchor="w", padx=16, pady=(14, 6))
        self.list = ctk.CTkScrollableFrame(self, fg_color=theme.BG)
        self.list.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.render()

    def render(self) -> None:
        for child in self.list.winfo_children():
            child.destroy()
        items = list(self.app.repo.reminders.items())
        if not items:
            ctk.CTkLabel(self.list, text=t("rem.empty"), text_color=theme.MUTED, wraplength=400).pack(pady=20)
            return
        for key, item in items:
            row = theme.Frame(self.list, fg_color=theme.SURFACE, corner_radius=10, border_width=1,
                              border_color=theme.BORDER)
            row.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(row, text=f"{item['username']}  ·  {item['platform']}",
                         text_color=theme.TEXT).pack(anchor="w", padx=10, pady=(8, 2))
            buttons = theme.Frame(row, fg_color="transparent")
            buttons.pack(anchor="w", padx=8, pady=(0, 8))
            for status, label_key in self.STATUSES:
                selected = item["status"] == status
                ctk.CTkButton(buttons, text=t(label_key), height=26, width=100,
                              fg_color=theme.BUTTON if selected else "transparent",
                              text_color=theme.BUTTON_TEXT if selected else theme.TEXT,
                              border_width=0 if selected else 1, border_color=theme.BORDER,
                              command=lambda k=key, s=status: self._set(k, s)).pack(side="left", padx=3)

    def _set(self, key: str, status: str) -> None:
        self.app.repo.set_reminder_status(key, status)
        self.render()


class HistoryView(theme.Frame):
    """Past generation batches; click Restore to show them again."""

    def __init__(self, master, app: "USNApp"):
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        _title(self, t("nav.history"))
        bar = theme.Frame(self, fg_color="transparent")
        bar.pack(fill="x", padx=18, pady=(0, 8))
        _outline_button(bar, t("hist.clear"), self.clear, "trash-2").pack(side="right" if not is_rtl() else "left")
        self.list = ctk.CTkScrollableFrame(self, fg_color=theme.BG)
        self.list.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.render()

    def render(self) -> None:
        for child in self.list.winfo_children():
            child.destroy()
        if not self.app.repo.history:
            ctk.CTkLabel(self.list, text=t("hist.empty"), text_color=theme.MUTED).pack(pady=30)
            return
        for entry in self.app.repo.history:
            row = theme.Frame(self.list, height=0, fg_color=theme.SURFACE, border_width=1,
                               border_color=theme.BORDER, corner_radius=theme.RADIUS)
            row.pack(fill="x", pady=4, padx=4)
            platforms = ", ".join(get_rule(p).name for p in entry.get("platforms", [])) or "-"
            info = f"{entry['timestamp']}   {entry.get('pattern', '')}   {entry.get('count', 0)}   {platforms}"
            ctk.CTkLabel(row, text=info, text_color=theme.TEXT, anchor=anchor()).pack(
                side="left", padx=12, pady=10, fill="x", expand=True)
            _outline_button(row, t("hist.restore"), lambda e=entry: self.app.restore_history(e),
                            "history").pack(side="right", padx=8, pady=8)

    def clear(self) -> None:
        if messagebox.askyesno("USN", t("hist.confirm")):
            self.app.repo.clear_history()
            self.render()


class SettingsView(ctk.CTkScrollableFrame):
    """Theme, language, digits, speech, defaults, blocklist, cache and shortcuts."""

    def __init__(self, master, app: "USNApp"):
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        s = app.repo.settings
        _title(self, t("set.title"))

        self._section_label(t("set.theme"))
        self.theme_seg = ctk.CTkSegmentedButton(self, values=[t("theme.dark"), t("theme.light"), t("theme.system")])
        self.theme_seg.set({"dark": t("theme.dark"), "light": t("theme.light")}.get(s["theme"], t("theme.system")))
        self.theme_seg.configure(command=self._theme_changed)
        self.theme_seg.pack(anchor="w", padx=18)

        self._section_label(t("set.language"))
        self.lang_seg = ctk.CTkSegmentedButton(self, values=["English", "العربية"], command=self._lang_changed)
        self.lang_seg.set("العربية" if s["language"] == "ar" else "English")
        self.lang_seg.pack(anchor="w", padx=18)

        self.digits_var = ctk.BooleanVar(value=bool(s.get("arabic_digits")))
        self.speech_var = ctk.BooleanVar(value=bool(s.get("speech", True)))
        ctk.CTkSwitch(self, text=t("set.digits"), variable=self.digits_var).pack(anchor="w", padx=18, pady=(12, 4))
        ctk.CTkSwitch(self, text=t("set.speech"), variable=self.speech_var).pack(anchor="w", padx=18, pady=4)

        self._section_label(t("set.default_platforms"))
        grid = theme.Frame(self, fg_color="transparent")
        grid.pack(anchor="w", padx=18)
        self.platform_vars = {}
        for i, key in enumerate(load_rules()):
            var = ctk.BooleanVar(value=key in s.get("default_platforms", []))
            self.platform_vars[key] = var
            ctk.CTkCheckBox(grid, text=get_rule(key).name, variable=var).grid(row=i // 3, column=i % 3,
                                                                              sticky="w", padx=6, pady=3)

        self._section_label(t("set.default_pattern"))
        self.pattern_entry = ctk.CTkEntry(self, width=200)
        self.pattern_entry.insert(0, s.get("default_pattern", "CVCV"))
        self.pattern_entry.pack(anchor="w", padx=18)

        self._section_label(t("set.blocklist"))
        self.blocklist = ctk.CTkTextbox(self, height=140, width=360)
        self.blocklist.insert("1.0", "\n".join(sorted(app.blocklist)))
        self.blocklist.pack(anchor="w", padx=18)

        row = theme.Frame(self, fg_color="transparent")
        row.pack(anchor="w", padx=18, pady=12)
        ctk.CTkButton(row, text=t("set.save"), fg_color=theme.BUTTON, text_color=theme.BUTTON_TEXT,
                      hover_color=theme.BUTTON_HOVER, command=self.save).pack(side="left", padx=4)
        _outline_button(row, t("set.clear_cache"), self.clear_cache, "trash-2").pack(side="left", padx=4)

        self._section_label(t("set.shortcuts"))
        ctk.CTkLabel(self, text=t("set.shortcut_hint"), text_color=theme.MUTED,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=18)
        self.shortcut_entries: dict[str, ctk.CTkEntry] = {}
        for action, seq in s["shortcuts"].items():
            row = theme.Frame(self, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(row, text=t("help." + action), width=180, anchor=anchor(),
                         text_color=theme.TEXT).pack(side="left" if not is_rtl() else "right")
            entry = ctk.CTkEntry(row, width=200)
            entry.insert(0, seq)
            entry.pack(side="left" if not is_rtl() else "right", padx=6)
            self.shortcut_entries[action] = entry
        self.shortcut_error = ctk.CTkLabel(self, text="", text_color=theme.MUTED)
        self.shortcut_error.pack(anchor="w", padx=18)
        ctk.CTkButton(self, text=t("set.save_shortcuts"), fg_color="transparent", text_color=theme.TEXT,
                      border_width=1, border_color=theme.BORDER, hover_color=theme.SURFACE_HOVER,
                      command=self.save_shortcuts).pack(anchor="w", padx=18, pady=6)
        ctk.CTkLabel(self, text=t("set.about", version=__version__), text_color=theme.MUTED).pack(
            anchor="w", padx=18, pady=(16, 24))

    def _section_label(self, text: str) -> None:
        ctk.CTkLabel(self, text=text, font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=theme.TEXT, anchor=anchor()).pack(fill="x", padx=18, pady=(14, 4))

    def _theme_changed(self, value: str) -> None:
        mapping = {t("theme.dark"): "dark", t("theme.light"): "light"}
        self.app.repo.settings["theme"] = mapping.get(value, "system")
        theme.apply_mode(self.app.repo.settings["theme"])
        theme.refresh_tk_widgets()
        self.app.repo.save_settings()

    def _lang_changed(self, value: str) -> None:
        self.app.set_language("ar" if value == "العربية" else "en")

    def save(self) -> None:
        s = self.app.repo.settings
        s["arabic_digits"] = bool(self.digits_var.get())
        s["speech"] = bool(self.speech_var.get())
        s["default_platforms"] = [k for k, v in self.platform_vars.items() if v.get()]
        s["default_pattern"] = self.pattern_entry.get().strip() or "CVCV"
        self.app.repo.save_settings()
        self.app.set_blocklist(self.blocklist.get("1.0", "end"))
        messagebox.showinfo("USN", t("common.done"))

    def save_shortcuts(self) -> None:
        mapping = {action: entry.get().strip() for action, entry in self.shortcut_entries.items()
                   if entry.get().strip()}
        bad = self.app.save_shortcuts(mapping)
        if bad:
            self.shortcut_error.configure(text=t("set.shortcut_invalid", seq=bad))
        else:
            self.shortcut_error.configure(text=t("common.done"))

    def clear_cache(self) -> None:
        self.app.checker.clear_cache()
        messagebox.showinfo("USN", t("set.cache_cleared"))
