"""Render UI icons (Lucide, ISC licence) and platform logos (Simple Icons, CC0) to PNG.

Run once when you update icons:
    npm install lucide-static simple-icons   (in any temp folder)
    python tools/build_icons.py /path/to/node_modules

Outputs:
    assets/icons/ui/<name>_{dark,light}.png          24px UI icons
    assets/icons/platforms/<key>_{dark,light}.png    16px logos, 60% opacity
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import cairosvg

ROOT = Path(__file__).resolve().parents[1]
UI_ICONS = ["copy", "check", "star", "volume-2", "search", "history", "settings",
            "external-link", "x", "chevron-down", "chevron-up", "download", "upload",
            "trash-2", "sparkles", "bookmark", "keyboard", "shield", "globe"]
PLATFORM_LOGOS = {
    "x": "x", "instagram": "instagram", "tiktok": "tiktok", "github": "github",
    "reddit": "reddit", "telegram": "telegram", "youtube": "youtube", "twitch": "twitch",
    "snapchat": "snapchat", "pinterest": "pinterest", "threads": "threads", "discord": "discord",
}
COLORS = {"dark": "#FFFFFF", "light": "#0F1419"}


def render_ui(lucide_dir: Path) -> None:
    out = ROOT / "assets" / "icons" / "ui"
    out.mkdir(parents=True, exist_ok=True)
    for name in UI_ICONS:
        svg = (lucide_dir / f"{name}.svg").read_text(encoding="utf-8")
        for theme, color in COLORS.items():
            themed = svg.replace("currentColor", color)
            cairosvg.svg2png(bytestring=themed.encode(), write_to=str(out / f"{name}_{theme}.png"),
                             output_width=24, output_height=24)


def render_platforms(simple_dir: Path) -> None:
    out = ROOT / "assets" / "icons" / "platforms"
    out.mkdir(parents=True, exist_ok=True)
    for key, slug in PLATFORM_LOGOS.items():
        svg = (simple_dir / f"{slug}.svg").read_text(encoding="utf-8")
        svg = re.sub(r"<svg ", '<svg fill-opacity="0.6" ', svg, count=1)  # subtle 60% opacity
        for theme, color in COLORS.items():
            themed = re.sub(r"<svg ", f'<svg fill="{color}" ', svg, count=1)
            cairosvg.svg2png(bytestring=themed.encode(), write_to=str(out / f"{key}_{theme}.png"),
                             output_width=16, output_height=16)


if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("node_modules")
    render_ui(base / "lucide-static" / "icons")
    render_platforms(base / "simple-icons" / "icons")
    print("icons rendered")
