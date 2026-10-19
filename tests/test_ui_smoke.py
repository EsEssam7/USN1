"""GUI smoke test: builds every screen and runs the main flows. Needs a display (xvfb on Linux CI)."""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not (os.environ.get("DISPLAY") or os.name == "nt" or os.environ.get("USN_GUI_TESTS")),
    reason="no display available",
)


def test_main_flows(tmp_path, monkeypatch):
    monkeypatch.setenv("USN_DATA_DIR", str(tmp_path))
    from app.ui.app import USNApp

    app = USNApp()
    try:
        app.update()
        for view in ("generator", "favorites", "history", "settings"):
            app.show(view)
            app.update()

        app.show("generator")
        gen = app._views["generator"]
        gen.pattern_entry.delete(0, "end")
        gen.pattern_entry.insert(0, "CVCV")
        gen.platform_vars["github"].set(True)
        gen.generate_new()
        app.update()
        assert gen.cards, "generation should produce cards"

        name = next(iter(gen.cards))
        app.select_username(name)
        app.update()
        assert gen.selected == name

        app.toggle_favorite(name)
        assert app.repo.is_favorite(name)
        app.repo.mark_used(name, "github")
        app.refresh_all()
        app.update()
        assert app.repo.used_platforms(name) == ["github"]

        app.set_language("ar")
        app.update()
        assert "generator" in app._views or app._active is not None
    finally:
        app.destroy()


def test_background_checks_and_history_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("USN_DATA_DIR", str(tmp_path))
    # Large checks ask for confirmation; answer yes so the headless test never blocks.
    monkeypatch.setattr("app.ui.generator_view.messagebox.askyesno", lambda *a, **k: True)
    import time
    from types import SimpleNamespace

    from app.ui.app import USNApp

    app = USNApp()
    try:
        # Replace the network with a fake: every profile is "not found".
        app.checker._fetch = lambda url, **kw: SimpleNamespace(status_code=404, text="")
        gen = app._views.get("generator") or (app.show("generator") or app._views["generator"])
        gen.platform_vars["github"].set(True)
        gen.generate_new()
        app.update()
        gen.check_visible()
        deadline = time.time() + 20
        while gen._checking and time.time() < deadline:
            app.update()
            time.sleep(0.05)
        assert not gen._checking, "background checks should finish"
        assert gen.checks, "results should be stored per username"

        history_entry = app.repo.history[0]
        app.restore_history(history_entry)
        app.update()
        assert set(gen.cards) == set(history_entry["usernames"])
    finally:
        app.destroy()


def test_large_check_asks_first(tmp_path, monkeypatch):
    monkeypatch.setenv("USN_DATA_DIR", str(tmp_path))
    asked = []
    monkeypatch.setattr("app.ui.generator_view.messagebox.askyesno",
                        lambda *a, **k: asked.append(a) or False)
    from app.ui.app import USNApp

    app = USNApp()
    try:
        gen = app._views.get("generator") or (app.show("generator") or app._views["generator"])
        for key in ("x", "instagram", "github", "reddit", "twitch"):
            gen.platform_vars[key].set(True)
        gen.generate_new()
        app.update()
        gen.check_visible()  # 50 names x 5 platforms = 250 requests, above the threshold
        assert asked and not gen._checking, "user should be asked before a large check runs"
    finally:
        app.destroy()


def test_sort_by_score_orders_cards(tmp_path, monkeypatch):
    monkeypatch.setenv("USN_DATA_DIR", str(tmp_path))
    from app.ui.app import USNApp

    app = USNApp()
    try:
        gen = app._views.get("generator") or (app.show("generator") or app._views["generator"])
        gen.generate_new()
        app.update()
        from app.i18n.i18n import t
        gen.sort_seg.set(t("gen.sort_score"))
        gen.apply_sort()
        app.update()
        # pack_slaves() returns widgets in packing order, which is what the user sees
        scores = [gen.scores[n].total for n in gen.ordered_names()]
        assert len(scores) > 1 and scores == sorted(scores, reverse=True)
    finally:
        app.destroy()


def test_shortcut_save_rejects_invalid_and_rebinds(tmp_path, monkeypatch):
    monkeypatch.setenv("USN_DATA_DIR", str(tmp_path))
    from app.ui.app import USNApp

    app = USNApp()
    try:
        assert app.save_shortcuts({"generate": "<Control-Bogus-x>"}) == "<Control-Bogus-x>"
        assert app.save_shortcuts({"generate": "<Control-j>"}) is None
        assert "<Control-j>" in app._bound_seqs
        assert app.repo.settings["shortcuts"]["generate"] == "<Control-j>"
    finally:
        app.destroy()
