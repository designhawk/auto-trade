"""Leftovers: db backup cycle, config invariants, sectors, launcher, misc."""
from datetime import datetime

import pandas as pd

import db
from config import config, _parse_hhmm_list
from sectors import sector_of
from risk_manager import RiskManager
from base_strategy import BaseStrategy
from stock_selector import StockSelector


def test_backup_restore_cycle(tmpdb, tmp_path):
    bdir = str(tmp_path / "backups")
    db.insert_trade({"timestamp": datetime.now().isoformat(), "symbol": "Q",
                     "side": "BUY", "qty": 1, "price": 10.0, "value": 10.0})
    path = db.backup_db(bdir)
    assert path and db.get_backup_list(bdir) != []
    assert db.restore_db(path) is True
    assert db.restore_db(str(tmp_path / "nope.db")) is False
    assert db.get_backup_list(str(tmp_path / "empty")) == []


def test_config_parse_and_ordering():
    assert _parse_hhmm_list("") == []
    assert _parse_hhmm_list("09:30, 11:00") == [(9, 30), (11, 0)]
    for v in (config.HEAT_CAP_PCT, config.DAILY_LOSS_LIMIT_PCT,
              config.MAX_DRAWDOWN_PCT, config.PARTIAL_FRAC):
        assert v > 0
    assert (config.ENTRY_CUTOFF_HOUR, config.ENTRY_CUTOFF_MINUTE) < \
           (config.SCALE_START_HOUR, config.SCALE_START_MINUTE) < \
           (config.FULL_EXIT_HOUR, config.FULL_EXIT_MINUTE) <= \
           (config.MARKET_END_HOUR, config.MARKET_END_MINUTE)
    assert config.SLIPPAGE_SEED is None or isinstance(config.SLIPPAGE_SEED, int)


def test_sector_coverage():
    assert sector_of("NOPE") == "MISC"
    uncovered = [s for s in config.NSE_STOCKS if sector_of(s) == "MISC"]
    assert uncovered == [], uncovered


def test_launcher_fake_procs(tmp_path, monkeypatch, capsys):
    import subprocess
    import run as run_mod

    calls = []

    class _FakeProc:
        def __init__(self, *a, **k):
            calls.append((a, k))
            self.pid = 4242
            self.returncode = None

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(subprocess, "Popen", _FakeProc)
    launcher = run_mod.Launcher()
    launcher.log_dir = tmp_path  # never touch real logs
    launcher.start_api()
    launcher.start_trader()
    assert len(calls) == 2
    assert calls[0][0][0][-1] == "api.py" and calls[1][0][0][-1] == "live_trader.py"
    assert (tmp_path / "api.log").exists() and (tmp_path / "trader.log").exists()
    launcher.status()
    assert "RUNNING" in capsys.readouterr().out
    launcher.stop_all()
    assert launcher.processes == {}


def test_risk_status_and_reset():
    rm = RiskManager(initial_capital=100_000)
    rm.update_daily_pnl(-1_000)
    rm.update_capital(99_000)
    st = rm.get_status()
    assert st["daily_pnl"] == -1_000 and st["current_capital"] == 99_000
    assert st["daily_limit_triggered"] is False  # 1000 < 3% x 99000
    assert st["circuit_breaker_triggered"] is False
    rm.reset_daily()
    from datetime import date
    assert rm.daily_pnl[date.today()] == 0


def test_validate_dataframe():
    class _S(BaseStrategy):
        @property
        def name(self):
            return "t"

        def generate_signals(self, symbol, df, df_15m=None):
            return []

        def required_bars(self):
            return 1

    s = _S()
    assert s.validate_dataframe("nope") is False
    assert s.validate_dataframe(pd.DataFrame()) is False
    assert s.validate_dataframe(pd.DataFrame({"open": [1]})) is False
    good = pd.DataFrame({c: [1.0, 2.0] for c in
                         ["open", "high", "low", "close", "volume"]})
    assert s.validate_dataframe(good) is True


def test_selector_atr_and_empty():
    sel = StockSelector(None)
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    flat = pd.DataFrame({"open": [10.0] * 60, "high": [10.0] * 60,
                         "low": [10.0] * 60, "close": [10.0] * 60,
                         "volume": [1000] * 60}, index=idx)
    assert sel.calculate_atr(flat) == 0.0
    assert sel.calculate_momentum_score("X", flat)[0] == 0.0  # no volume filter pass
    assert sel.rank_stocks([], interval="1d", bars=100) == []
    assert sel.select_top_stocks([], top_n=5) == []


def test_monitor_down_defaults():
    import monitor
    st = monitor.get_status()  # no server running in tests
    assert st["api"]["status"] == "[X] Down"
    assert monitor.get_recent_logs() == [] or isinstance(monitor.get_recent_logs(), list)


def test_run_wiring_post_close(tmpdb, monkeypatch, tmp_path):
    """Full run() with pinned post-close clock: connect, fallback list,
    instant loop-break, session row, backup, disconnect - no network."""
    import db as dbmod
    from live_trader import LiveTrader
    from intraday_strategy import IntradayMomentumStrategy

    class _DeadBroker:
        connected = False

        def connect(self):
            self.connected = True
            return True

        def disconnect(self):
            self.connected = False

        def get_ohlcv(self, symbol, interval, bars):
            raise RuntimeError("no data")

        def get_ltp(self, symbols):
            return {}

    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 15, 26)))
    monkeypatch.setattr(dbmod, "BACKUP_DIR", tmp_path / "backups")
    import config as config_mod
    monkeypatch.setattr(config_mod.config, "NSE_STOCKS", ["A", "B"])

    broker = _DeadBroker()
    t = LiveTrader(strategy=IntradayMomentumStrategy(), broker=broker,
                   initial_capital=50_000)
    t.run()

    assert broker.connected is False  # disconnected at the end
    assert t.watchlist == []  # all symbols failed -> graceful empty, no crash
    sessions = dbmod.get_all_sessions()
    assert len(sessions) == 1 and sessions[0]["start_capital"] == 50_000
    assert list((tmp_path / "backups").glob("trading_*.db")) != []


def test_get_cash_flow_empty(tmpdb):
    assert db.get_cash_flow() == (0.0, 0.0)


def test_end_session_win_loss_split(tmpdb, monkeypatch):
    from live_trader import LiveTrader
    from intraday_strategy import IntradayMomentumStrategy
    from test_trader_flows import _Broker, _flat_5m
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 10, 0)))
    t = LiveTrader(strategy=IntradayMomentumStrategy(),
                   broker=_Broker({"W": _flat_5m(110.0), "L": _flat_5m(90.0)}),
                   initial_capital=100_000)
    t.watchlist = []
    t.paper_portfolio.slippage_max_pct = 0
    t.paper_portfolio.execute_buy("W", 10, 100.0, stop_loss=98.0, take_profit=110.0)
    t.paper_portfolio.execute_sell("W", 10, 105.0)
    t.paper_portfolio.execute_buy("L", 10, 100.0, stop_loss=98.0, take_profit=110.0)
    t.paper_portfolio.execute_sell("L", 10, 95.0)
    t.end_session()
    s = db.get_all_sessions()[0]
    assert s["total_trades"] == 2
    assert s["winning_trades"] == 1 and s["losing_trades"] == 1
