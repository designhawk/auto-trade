import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# growwapi is only needed at broker-connect time; stub it when not installed
try:
    import growwapi  # noqa: F401
except ImportError:
    sys.modules.setdefault("growwapi", MagicMock())

import pytest  # noqa: E402

import db  # noqa: E402
import config as config_mod  # noqa: E402


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    """Point the database (and runtime state files) at a temp dir."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    monkeypatch.setattr(config_mod.config, "RESELECT_TIMES", [])

    import paths

    state_dir = tmp_path / "logs_state"
    state_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(paths, "LOG_DIR", state_dir)  # watchlist.json etc.
    monkeypatch.setattr(paths, "REPORT_DIR", tmp_path / "reports")  # no real-dir writes
    monkeypatch.setattr(db, "BACKUP_DIR", tmp_path / "backups")  # no real-dir dumps
    return tmp_path
