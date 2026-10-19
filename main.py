"""USN entry point. Run with: python main.py"""
from __future__ import annotations

import logging

from app.services.storage import data_dir, setup_logging


def main() -> None:
    setup_logging(data_dir())
    # Import the UI lazily so tests and core modules never need a display.
    from app.ui.app import USNApp

    try:
        USNApp().mainloop()
    except Exception:  # noqa: BLE001 - log any fatal error before exiting
        logging.getLogger("usn").exception("fatal error")
        raise


if __name__ == "__main__":
    main()
