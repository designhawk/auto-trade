# paths.py
"""
Project-root-anchored filesystem locations.

All runtime files (database, logs, backups) resolve against the directory
containing this file, so every tool uses the same files no matter which
working directory it is launched from.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "trading.db"
LOG_DIR = PROJECT_ROOT / "logs"
BACKUP_DIR = PROJECT_ROOT / "backups"
