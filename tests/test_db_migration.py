"""A1: legacy-schema migration + new column round-trips."""
import sqlite3

import db


def _make_legacy():
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("""CREATE TABLE trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
        symbol TEXT NOT NULL, side TEXT NOT NULL, qty INTEGER NOT NULL,
        price REAL NOT NULL, value REAL NOT NULL, pnl REAL, pnl_pct REAL,
        exit_reason TEXT, session_id TEXT)""")
    conn.execute("""CREATE TABLE signals (id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL, symbol TEXT NOT NULL, action TEXT NOT NULL,
        confidence REAL, entry_price REAL, stop_loss REAL, take_profit REAL,
        reason TEXT, approved BOOLEAN, rejection_reason TEXT, adjusted_qty INTEGER,
        strategy TEXT)""")
    conn.execute("""CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE, start_capital REAL NOT NULL,
        end_capital REAL NOT NULL, total_pnl REAL, total_trades INTEGER,
        winning_trades INTEGER, losing_trades INTEGER, max_drawdown_pct REAL,
        sharpe_ratio REAL, notes TEXT)""")
    conn.commit()
    conn.close()


def test_legacy_upgrade(tmpdb):
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()  # start truly legacy: no tables at all
    _make_legacy()
    db.init_db()  # must migrate, not crash
    cols = {r[1] for r in sqlite3.connect(db.DB_PATH).execute("PRAGMA table_info(trades)")}
    assert {"mfe", "mae", "brokerage", "stt", "other_costs", "slippage_cost"} <= cols


def test_new_columns_round_trip(tmpdb):
    db.insert_trade({"timestamp": "2026-01-01T10:00:00", "symbol": "X", "side": "BUY",
                     "qty": 1, "price": 100.0, "value": 100.0,
                     "mfe": 1.5, "mae": -0.2, "brokerage": 0.03, "stt": 0.0,
                     "other_costs": 0.01, "slippage_cost": 0.02})
    row = db.get_trades_for_date("2026-01-01")[0]
    assert row["mfe"] == 1.5 and row["mae"] == -0.2
    assert row["stt"] == 0.0 and row["slippage_cost"] == 0.02


def test_legacy_shaped_insert(tmpdb):
    db.insert_trade({"timestamp": "2026-01-01T11:00:00", "symbol": "Y", "side": "BUY",
                     "qty": 1, "price": 50.0, "value": 50.0})
    assert len(db.get_trades_for_date("2026-01-01")) == 1
