# Contributing

1. Fork the repository and create a branch.
2. Install the requirements: `pip install -r requirements.txt`.
3. Run the tests before you open a pull request: `python -m pytest -q` (on Linux: `xvfb-run -a python -m pytest -q`).
4. Keep the core (`app/core`, `app/services`) free of UI imports, so it stays testable.
5. Platform rules live in `app/core/platform_rules.json`. Only change a rule when you can link to the platform's official help page, and update `last_verified`.
6. Every user-facing string goes in both `app/i18n/en.json` and `app/i18n/ar.json`.
