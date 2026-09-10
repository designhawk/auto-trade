import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# growwapi is only needed at broker-connect time; stub for unit tests
sys.modules.setdefault("growwapi", MagicMock())

import pytest  # noqa: E402

import db  # noqa: E402
import config as config_mod  # noqa: E402


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    """Point the database at a temp file and silence re-ranking."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    monkeypatch.setattr(config_mod.config, "RESELECT_TIMES", [])
    return tmp_path
