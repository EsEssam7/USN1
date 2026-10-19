"""Reusable widgets: username result card, platform badge and a small picker dialog."""
from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from app.core.platform_rules import get_rule
from app.i18n.i18n import is_rtl, t
from app.services.availability import Status
from app.ui import theme


def anchor() -> str:
    """Text anchor for the current layout direction."""
    return "e" if is_rtl() else "w"


class Tooltip:
    """Small hover hint. Works with any widget that supports bind()."""

    def __init__(self, widget, text_fn: Callable[[], str]) -> None:
        self.widget = widget
        self.text_fn = text_fn
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self.tip is not None:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.geometry(f"+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty() + 26}")
        tk.Label(self.tip, text=self.text_fn(), bg="#222222", fg="#FFFFFF",
                 padx=8, pady=4, font=("TkDefaultFont", 9)).pack()

    def _hide(self, _event=None) -> None:
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class PlatformBadge(theme.Frame):
    """Small platform logo (or monogram fallback) shown next to a username."""

    def __init__(self, master, key: str, on_click: Callable[[], None] | None = None, **kwargs):
        super().__init__(master, fg_color="transparent", width=20, height=20, **kwargs)
        image = theme.platform_logo(key)
        name = get_rule(key).name
        if image is not None:
            label = ctk.CTkLabel(self, text="", image=image, width=16)
        else:
            label = ctk.CTkLabel(self, text=name[:1].upper(), width=18, height=18,
                                 font=ctk.CTkFont(size=10, weight="bold"),
                                 text_color=theme.MUTED, fg_color=theme.SURFACE, corner_radius=9)
        label.pack()
        label.configure(cursor="hand2")
        if on_click:
            label.bind("<Button-1>", lambda _e: on_click())
        self.tooltip_text = name


class ActionLabel(tk.Label):
    """Clickable icon + text. Plain Tk, so a batch of cards stays fast to draw."""

    def __init__(self, master, icon: str | None, text: str, command: Callable[[], None]):
        super().__init__(master, text=text, compound="left", cursor="hand2",
                         padx=6, pady=4, font=("TkDefaultFont", 10))
        self._icon = icon
        self._command = command
        self._photo = None
        self.bind("<Button-1>", lambda _e: self._command())
        self.bind("<Enter>", lambda _e: self.configure(bg=theme.pick(theme.SURFACE_HOVER)))
        self.bind("<Leave>", lambda _e: self.configure(bg=theme.pick(theme.SURFACE)))
        theme.register_tk_widget(self)
        self.apply_colors()

    def set_content(self, text: str, icon: str | None = None) -> None:
        self._icon = icon or self._icon
        self.configure(text=text)
        self.apply_colors()

    def apply_colors(self) -> None:
        self._photo = theme.tk_icon(self._icon, 16) if self._icon else None
        self.configure(image=self._photo or "", bg=theme.pick(theme.SURFACE),
                       fg=theme.pick(theme.TEXT), activebackground=theme.pick(theme.SURFACE_HOVER))


class UsernameCard(theme.Frame):
    """One generated username with score, badges and action buttons."""

    def __init__(self, master, app, username: str, score: int, arabic: str | None = None,
                 reasons: list[str] | None = None):
        super().__init__(master, fg_color=theme.SURFACE, border_width=1,
                         border_color=theme.BORDER, corner_radius=theme.RADIUS)
        self.app = app
        self.username = username
        self._selected = False

        top = theme.Frame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 0))
        self.name_label = ctk.CTkLabel(
            top, text=username, font=ctk.CTkFont(size=18, weight="bold"),
            text_color=theme.TEXT, anchor=anchor(),
        )
        self.name_label.pack(side="left" if not is_rtl() else "right")
        self.name_label.bind("<Button-1>", lambda _e: app.select_username(username))
        self.score_label = ctk.CTkLabel(
            top, text=t("card.score", score=score), font=ctk.CTkFont(size=12),
            text_color=theme.MUTED,
        )
        self.score_label.pack(side="right" if not is_rtl() else "left", padx=6)
        weakest = reasons or []
        Tooltip(self.score_label, lambda: t("card.tip", a=t("factor." + weakest[0]), b=t("factor." + weakest[1]))
                if len(weakest) >= 2 else "")

        self.badges = theme.Frame(top, fg_color="transparent")
        self.badges.pack(side="left" if not is_rtl() else "right", padx=8)

        if arabic:
            ctk.CTkLabel(self, text=t("card.arabic", text=arabic), font=ctk.CTkFont(size=12),
                         text_color=theme.MUTED, anchor=anchor()).pack(fill="x", padx=14, pady=(2, 0))

        actions = theme.Frame(self, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(8, 10))
        self.star_btn = self._action(actions, "star", t("card.star"),
                                     lambda: app.toggle_favorite(username))
        self.copy_btn = self._action(actions, "copy", t("card.copy"),
                                     lambda: app.copy_username(username, self))
        self._action(actions, "volume-2", t("card.speak"), lambda: app.speak(username))
        self._action(actions, "shield", t("card.check"), lambda: app.check_username(username))
        self._action(actions, "bookmark", t("card.used"), lambda: app.mark_used_dialog(username))
        self.refresh_star()

    def _action(self, parent, icon: str, text: str, command) -> ActionLabel:
        label = ActionLabel(parent, icon, text, command)
        label.pack(side="left" if not is_rtl() else "right", padx=2)
        return label

    def refresh_star(self) -> None:
        """Show a filled marker when this username is a favorite."""
        is_fav = self.app.repo.is_favorite(self.username)
        self.star_btn.set_content(("★ " if is_fav else "") + t("card.star"), "star")

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.configure(border_color=theme.TEXT if selected else theme.BORDER)

    def flash_copied(self) -> None:
        """Visual confirmation for 1.5 seconds after copying."""
        self.copy_btn.set_content(t("card.copied"), "check")
        self.after(1500, lambda: self.copy_btn.set_content(t("card.copy"), "copy"))

    def set_badges(self, platforms: list[str], used: list[str], taken: list[str]) -> None:
        for child in self.badges.winfo_children():
            child.destroy()
        for key in taken:
            PlatformBadge(self.badges, key, on_click=None).pack(side="left", padx=2)
        for key in used:
            PlatformBadge(self.badges, key,
                          on_click=lambda k=key: self.app.confirm_unmark_used(self.username, k)
                          ).pack(side="left", padx=2)


STATUS_LABELS = {
    Status.TAKEN: "status.taken",
    Status.LIKELY_AVAILABLE: "status.likely_available",
    Status.UNKNOWN: "status.unknown",
    Status.NOT_CHECKABLE: "status.not_checkable",
    Status.INVALID: "status.invalid",
}


def ask_platform(master, title: str, platforms: list[str], on_confirm: Callable[[str], None]) -> None:
    """Small dialog: pick one platform from a list, then confirm."""
    names = {get_rule(k).name: k for k in platforms}
    dialog = ctk.CTkToplevel(master)
    dialog.title(title)
    dialog.geometry("320x180")
    dialog.transient(master.winfo_toplevel())
    dialog.grab_set()
    ctk.CTkLabel(dialog, text=title, font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(18, 10))
    menu = ctk.CTkOptionMenu(dialog, values=list(names))
    menu.pack(pady=6)

    def confirm() -> None:
        on_confirm(names[menu.get()])
        dialog.destroy()

    row = theme.Frame(dialog, fg_color="transparent")
    row.pack(pady=14)
    ctk.CTkButton(row, text=t("common.cancel"), fg_color="transparent", text_color=theme.TEXT,
                  border_width=1, border_color=theme.BORDER, command=dialog.destroy).pack(side="left", padx=6)
    ctk.CTkButton(row, text=t("common.confirm"), fg_color=theme.BUTTON, text_color=theme.BUTTON_TEXT,
                  hover_color=theme.BUTTON_HOVER, command=confirm).pack(side="left", padx=6)
