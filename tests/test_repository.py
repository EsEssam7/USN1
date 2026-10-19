"""Repository persistence tests using a temporary directory."""
from app.services.repository import Repository


def test_favorites_toggle_and_persist(tmp_path):
    repo = Repository(tmp_path)
    assert repo.toggle_favorite("kenoro", 80) is True
    assert Repository(tmp_path).is_favorite("KENORO")
    assert repo.toggle_favorite("kenoro") is False


def test_used_mark_per_platform(tmp_path):
    repo = Repository(tmp_path)
    repo.mark_used("kenoro", "github")
    assert repo.is_used("kenoro", "github")
    assert not repo.is_used("kenoro", "x")
    assert repo.used_platforms("kenoro") == ["github"]


def test_history_keeps_latest_100(tmp_path):
    repo = Repository(tmp_path)
    for i in range(105):
        repo.add_history({"pattern": f"P{i}"})
    assert len(repo.history) == 100 and repo.history[0]["pattern"] == "P104"


def test_import_skips_duplicates(tmp_path):
    repo = Repository(tmp_path)
    repo.toggle_favorite("kenoro")
    added = repo.replace_favorites([{"username": "KENORO"}, {"username": "tavi"}])
    assert added == 1


def test_reminder_due_after_three_days(tmp_path):
    repo = Repository(tmp_path)
    repo.reserve("kenoro", "github")
    key = "github:kenoro"
    repo.reminders[key]["reserved_at"] -= 4 * 24 * 3600
    assert len(repo.due_reminders()) == 1
    repo.set_reminder_status(key, "registered")
    assert repo.due_reminders() == []
