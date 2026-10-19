"""Local data storage: platform data directory and atomic JSON files."""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

APP_NAME = "USN"


def data_dir() -> Path:
    """Directory for user data. USN_DATA_DIR overrides the default."""
    override = os.environ.get("USN_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform.startswith("win"):
        path = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


class JsonStore:
    """A JSON file with atomic writes (temp file, then rename)."""

    def __init__(self, path: Path, default: Any) -> None:
        self.path = path
        self._default = default

    def load(self) -> Any:
        """Read the file, returning the default if it is missing or corrupt."""
        if not self.path.exists():
            return _copy(self._default)
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logging.getLogger("usn").error("could not read %s: %s", self.path, exc)
            return _copy(self._default)

    def save(self, data: Any) -> None:
        """Write atomically so a crash never leaves a half-written file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def setup_logging(directory: Path) -> logging.Logger:
    """Log errors to data/usn.log without crashing the app."""
    logger = logging.getLogger("usn")
    if not logger.handlers:
        handler = logging.FileHandler(directory / "usn.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
