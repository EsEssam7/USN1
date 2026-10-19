"""Colors and shared style values. Each colour is a (light, dark) tuple for CustomTkinter."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

import customtkinter as ctk

ASSETS = Path(__file__).resolve().parents[2] / "assets"

BG = ("#FFFFFF", "#000000")
SURFACE = ("#F7F9F9", "#0F0F0F")
SURFACE_HOVER = ("#E7ECEE", "#181818")
TEXT = ("#0F1419", "#FFFFFF")
MUTED = ("#536471", "#8B8B8B")
BORDER = ("#EFF3F4", "#2F3336")
BUTTON = ("#0F1419", "#FFFFFF")
BUTTON_TEXT = ("#FFFFFF", "#000000")
BUTTON_HOVER = ("#333939", "#D7D9DB")
SUCCESS_TEXT = ("#0F1419", "#FFFFFF")
RADIUS = 12

STATUS_COLORS = {
    "taken": ("#0F1419", "#FFFFFF"),
    "likely_available": ("#0F1419", "#FFFFFF"),
    "unknown": MUTED,
    "invalid": MUTED,
}


def apply_mode(theme: str) -> None:
    """Set CustomTkinter appearance: dark, light or system."""
    ctk.set_appearance_mode({"dark": "dark", "light": "light"}.get(theme, "system"))


def theme_name() -> str:
    """Current effective theme, 'dark' or 'light'."""
    return "dark" if ctk.get_appearance_mode().lower() == "dark" else "light"


_icon_cache: dict[tuple[str, int], ctk.CTkImage] = {}


def ui_icon(name: str, size: int = 20) -> ctk.CTkImage | None:
    """Lucide UI icon as a CTkImage that follows light/dark mode, or None if missing."""
    key = (f"ui:{name}", size)
    if key in _icon_cache:
        return _icon_cache[key]
    light = ASSETS / "icons" / "ui" / f"{name}_light.png"
    dark = ASSETS / "icons" / "ui" / f"{name}_dark.png"
    if not (light.exists() and dark.exists()):
        return None
    image = ctk.CTkImage(light_image=Image.open(light), dark_image=Image.open(dark), size=(size, size))
    _icon_cache[key] = image
    return image


def platform_logo(key: str, size: int = 16) -> ctk.CTkImage | None:
    """Platform logo (60% opacity) for light and dark modes, or None if no logo file exists."""
    light = ASSETS / "icons" / "platforms" / f"{key}_light.png"
    dark = ASSETS / "icons" / "platforms" / f"{key}_dark.png"
    if not (light.exists() and dark.exists()):
        return None
    cache_key = (f"plat:{key}", size)
    if cache_key not in _icon_cache:
        _icon_cache[cache_key] = ctk.CTkImage(
            light_image=Image.open(light), dark_image=Image.open(dark), size=(size, size)
        )
    return _icon_cache[cache_key]


def clear_icon_cache() -> None:
    """Drop cached images. Call when a new Tk root is created (images belong to one root)."""
    _icon_cache.clear()
    clear_tk_cache()


class Frame(ctk.CTkFrame):
    """CTkFrame that sizes to its content. CustomTkinter defaults frames to 200px tall."""

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("height", 0)
        super().__init__(master, **kwargs)


# ---- lightweight Tk icons for result cards -------------------------------
# CustomTkinter draws every rounded button on a canvas, which is slow when a batch has
# hundreds of them. Result cards use plain Tk labels with PIL-rendered icons instead.
import tkinter as tk  # noqa: E402
import weakref  # noqa: E402

from PIL import ImageTk  # noqa: E402

_tk_photo_cache: dict[tuple[str, int, str], object] = {}
_tk_registry: "weakref.WeakSet[tk.Widget]" = weakref.WeakSet()


def pick(color):
    """Resolve a (light, dark) tuple to the colour for the current mode."""
    if isinstance(color, tuple):
        return color[1] if theme_name() == "dark" else color[0]
    return color


def tk_icon(name: str, size: int = 16):
    """Tk PhotoImage for a UI icon in the current mode, or None if the file is missing."""
    mode = theme_name()
    key = (name, size, mode)
    if key not in _tk_photo_cache:
        path = ASSETS / "icons" / "ui" / f"{name}_{mode}.png"
        if not path.exists():
            return None
        image = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        _tk_photo_cache[key] = ImageTk.PhotoImage(image)
    return _tk_photo_cache[key]


def register_tk_widget(widget: tk.Widget) -> None:
    """Widgets that must re-colour when the theme changes."""
    _tk_registry.add(widget)


def refresh_tk_widgets() -> None:
    """Ask every registered Tk widget to re-apply its colours."""
    for widget in list(_tk_registry):
        try:
            if widget.winfo_exists():
                widget.apply_colors()
        except tk.TclError:
            pass


def clear_tk_cache() -> None:
    _tk_photo_cache.clear()
    _tk_registry.clear()
