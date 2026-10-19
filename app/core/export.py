"""Export and import helpers for favorites and results (pure functions)."""
from __future__ import annotations

import csv
import io
import json
from typing import Iterable


def favorites_to_json(favorites: list[dict]) -> str:
    return json.dumps(favorites, ensure_ascii=False, indent=2)


def favorites_to_csv(favorites: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["username", "score", "note", "date"])
    writer.writeheader()
    for f in favorites:
        writer.writerow({k: f.get(k, "") for k in writer.fieldnames})
    return buf.getvalue()


def favorites_from_json(text: str) -> list[dict]:
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("expected a JSON list")
    return [d for d in data if isinstance(d, dict) and d.get("username")]


def favorites_from_csv(text: str) -> list[dict]:
    return [dict(row) for row in csv.DictReader(io.StringIO(text)) if row.get("username")]


def as_plain_list(usernames: Iterable[str], platforms: dict[str, list[str]] | None = None) -> str:
    """One username per line. With platforms, append them after a tab."""
    lines = []
    for name in usernames:
        if platforms and platforms.get(name):
            lines.append(f"{name}\t{', '.join(platforms[name])}")
        else:
            lines.append(name)
    return "\n".join(lines)


def matrix_to_markdown(username: str, rows: list[tuple[str, str, str]]) -> str:
    """rows: (platform name, status label, profile url or '')."""
    out = ["| Platform | Status | Link |", "|---|---|---|"]
    for name, status, url in rows:
        out.append(f"| {name} | {status} | {url} |")
    return f"Username: {username}\n\n" + "\n".join(out)


def matrix_to_csv(rows: list[tuple[str, str, str]]) -> str:
    """CSV for the per-platform matrix: platform, status, profile link."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["platform", "status", "link"])
    writer.writerows(rows)
    return buf.getvalue()
