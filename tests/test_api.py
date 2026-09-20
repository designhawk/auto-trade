"""API endpoints against a seeded temp DB (broker forced to fail -> fallback)."""
from datetime import datetime

import db
import api


def _boom(*a, **k):
    raise RuntimeError("no broker")


def _seed(monkeypatch):
    monkeypatch.setattr(api, "get_broker", _boom)
    monkeypatch.setattr(api, "_broker", None)
    now = datetime.now().isoformat()
    db.insert_session({"date": "2000-01-01", "start_capital": 100000,
                       "end_capital": 100000, "total_pnl": 0, "total_trades": 0,
                       "winning_trades": 0, "losing_trades": 0,
                       "max_drawdown_pct": 0, "sharpe_ratio": 0, "notes": "t"})
    db.insert_signal({"timestamp": now, "symbol": "A", "action": "BUY",
                      "confidence": 0.8, "entry_price": 100.0, "stop_loss": 98.0,
                      "take_profit": 104.0, "reason": "t", "approved": True,
                      "adjusted_qty": 10, "strategy": "S"})
    db.insert_signal({"timestamp": now, "symbol": "B", "action": "BUY",
                      "confidence": 0.1, "entry_price": 50.0, "stop_loss": 49.0,
                      "take_profit": 52.0, "reason": "t", "approved": False,
                      "rejection_reason": "Weak", "adjusted_qty": 0, "strategy": "S"})
    db.insert_trade({"timestamp": now, "symbol": "A", "side": "BUY", "qty": 10,
                     "price": 100.0, "value": 1000.0, "brokerage": 0.3,
                     "stt": 0.0, "other_costs": 0.1, "slippage_cost": 0.0})
    db.insert_trade({"timestamp": now, "symbol": "A", "side": "SELL", "qty": 4,
                     "price": 102.0, "value": 408.0, "pnl": 7.0, "pnl_pct": 1.7,
                     "exit_reason": "SCALED_1R", "brokerage": 0.12, "stt": 0.1,
                     "other_costs": 0.05, "slippage_cost": 0.0})
    return now


def test_health():
    h = api.health_check()
    assert h["status"] == "healthy" and "timestamp" in h


def test_status_db_flag(tmpdb, monkeypatch):
    _seed(monkeypatch)
    s = api.get_status()
    assert s["database_connected"] is True and s["today_signals"] == 2
    monkeypatch.setattr(db, "DB_PATH", db.DB_PATH.parent / "nope.db")
    s2 = api.get_status()
    assert s2["database_connected"] is False  # live DB_PATH reference


def test_signals_filters(tmpdb, monkeypatch):
    _seed(monkeypatch)
    assert api.get_signals(limit=50)["count"] == 2
    assert api.get_signals(limit=50, approved_only=True)["count"] == 1
    assert api.get_signals(limit=50, date="1999-01-01")["count"] == 0


def test_trades_filters_and_summary(tmpdb, monkeypatch):
    _seed(monkeypatch)
    assert api.get_trades()["count"] == 2
    assert api.get_trades(symbol="ZZZ")["count"] == 0
    t = api.get_trades()
    assert t["total_pnl"] == 7.0 and t["winning_trades"] == 1


def test_positions_netted_fallback(tmpdb, monkeypatch):
    _seed(monkeypatch)
    p = api.get_positions()
    assert p["count"] == 1 and p["live_prices"] is False
    row = p["positions"][0]
    assert row["symbol"] == "A" and row["qty"] == 6
    assert row["current_price"] == row["entry_price"] == 100.0


def test_portfolio_math(tmpdb, monkeypatch):
    _seed(monkeypatch)
    pf = api.get_portfolio_summary()
    assert pf["live_prices"] is False and pf["num_positions"] == 1
    # cash = 100000 - (1000+0.3+0+0.1) + (408-0.12-0.1-0.05)
    assert abs(pf["cash"] - 99407.33) < 1e-6, pf["cash"]
    assert abs(pf["position_value"] - 600.0) < 1e-6


def test_portfolio_cash_ignores_restart_baseline(tmpdb, monkeypatch):
    """Session rows are per process run: cash must baseline on the account's
    starting capital, not the last restart's start_capital (combining it with
    all-time flows double-counts pre-restart trades)."""
    _seed(monkeypatch)
    db.insert_session({"date": "2000-01-02", "start_capital": 98_000,
                       "end_capital": 98_000, "total_pnl": 0, "total_trades": 0,
                       "winning_trades": 0, "losing_trades": 0,
                       "max_drawdown_pct": 0, "sharpe_ratio": 0, "notes": "later"})
    pf = api.get_portfolio_summary()
    from config import config
    assert pf["start_capital"] == config.INITIAL_CAPITAL
    assert abs(pf["cash"] - 99407.33) < 1e-6, pf["cash"]


def test_sessions_and_today(tmpdb, monkeypatch):
    _seed(monkeypatch)
    assert api.get_sessions()["count"] == 1
    t = api.get_today_summary()
    assert t["signals_total"] == 2 and t["signals_approved"] == 1
    assert t["trades_total"] == 2 and t["total_pnl"] == 7.0


def test_today_returns_latest_not_oldest(tmpdb, monkeypatch):
    """Signals tab froze once the day passed 10 signals: /today sliced the
    oldest 10 (ASC order) instead of the latest 10."""
    monkeypatch.setattr(api, "get_broker", _boom)
    monkeypatch.setattr(api, "_broker", None)
    day = datetime.now()

    def ts(i):
        return day.replace(hour=9, minute=15, second=i, microsecond=0).isoformat()

    for i in range(12):
        db.insert_signal({"timestamp": ts(i), "symbol": f"S{i:02d}", "action": "BUY",
                          "confidence": 0.8, "entry_price": 100.0, "stop_loss": 98.0,
                          "take_profit": 104.0, "reason": "t", "approved": True,
                          "adjusted_qty": 10, "strategy": "S"})
        db.insert_trade({"timestamp": ts(i), "symbol": f"S{i:02d}", "side": "BUY",
                         "qty": 1, "price": 100.0, "value": 100.0, "brokerage": 0.0,
                         "stt": 0.0, "other_costs": 0.0, "slippage_cost": 0.0})
    t = api.get_today_summary()
    assert t["signals_total"] == 12 and t["trades_total"] == 12
    assert [s["symbol"] for s in t["signals"]] == [f"S{i:02d}" for i in range(2, 12)]
    assert [s["symbol"] for s in t["trades"]] == [f"S{i:02d}" for i in range(2, 12)]
