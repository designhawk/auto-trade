"""Trader flows: end-to-end entries, cutoff, reselect, force-close, end_session."""
from datetime import datetime

import pandas as pd

import db
from live_trader import LiveTrader
from intraday_strategy import IntradayMomentumStrategy
from config import config


def _idx(n, start="2026-01-01 09:15"):
    return pd.date_range(start, periods=n, freq="5min", tz="Asia/Kolkata")


def _breakout_5m():
    """5m tape that passes all 7 gates (oscillating base + final spike)."""
    n = 50
    c = [100 + i * 0.15 + (0.4 if i % 2 == 0 else -0.25) for i in range(n)]
    v = [5000] * (n - 1) + [50000]
    df = pd.DataFrame({
        "open": [x - 0.1 for x in c], "high": [x + 0.4 for x in c],
        "low": [x - 0.4 for x in c], "close": c, "volume": v}, index=_idx(n))
    rh = df["high"].iloc[-21:-1].max()
    df.loc[df.index[-1], "close"] = rh * 1.01
    df.loc[df.index[-1], "high"] = rh * 1.015
    return df


def _up_15m():
    c = [100 + i * 0.3 for i in range(60)]
    return pd.DataFrame({
        "open": c, "high": [x + 0.2 for x in c], "low": [x - 0.2 for x in c],
        "close": c, "volume": [1000] * 60}, index=_idx(60))


def _flat_5m(price=100.0, n=60):
    return pd.DataFrame({
        "open": [price] * n, "high": [price + 0.1] * n, "low": [price - 0.1] * n,
        "close": [price] * n, "volume": [1000] * n}, index=_idx(n))


class _Broker:
    def __init__(self, frames):
        self.frames = frames  # symbol -> {"5m": df, "15m": df} or df

    def connect(self):
        return True

    def disconnect(self):
        pass

    def get_ohlcv(self, symbol, interval, bars):
        f = self.frames[symbol]
        return f[interval] if isinstance(f, dict) else f

    def get_ltp(self, symbols):
        out = {}
        for s in symbols:
            f = self.frames[s]
            df = f["5m"] if isinstance(f, dict) else f
            out[s] = float(df["close"].iloc[-1])
        return out


def _trader(frames, capital=1_000_000):
    t = LiveTrader(strategy=IntradayMomentumStrategy(volume_multiplier=0.5,
                                                     cooldown_bars=0),
                   broker=_Broker(frames), initial_capital=capital)
    t.watchlist = []
    t.paper_portfolio.slippage_max_pct = 0
    return t


def test_entry_end_to_end(tmpdb, monkeypatch):
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 10, 0)))
    t = _trader({"E": {"5m": _breakout_5m(), "15m": _up_15m()}})
    t.watchlist = ["E"]
    t.on_bar()
    assert t.paper_portfolio.has_position("E")
    pos = t.paper_portfolio.positions["E"]
    assert pos.qty > 0 and pos.stop_loss > 0 and pos.take_profit > pos.avg_price
    sigs = db.get_signals_for_date(datetime.now().date().isoformat())
    assert len(sigs) == 1 and sigs[0]["approved"] and sigs[0]["adjusted_qty"] > 0
    buys = [tr for tr in db.get_trades_for_date(datetime.now().date().isoformat())
            if tr["side"] == "BUY"]
    assert len(buys) == 1 and buys[0]["exit_reason"] == "SIGNAL_ENTRY"
    assert buys[0]["brokerage"] is not None  # cost columns populated


def test_entry_cutoff_blocks(tmpdb, monkeypatch):
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 15, 0)))
    t = _trader({"E": {"5m": _breakout_5m(), "15m": _up_15m()}})
    t.watchlist = ["E"]
    t.on_bar()
    assert not t.paper_portfolio.has_position("E")
    assert db.get_signals_for_date(datetime.now().date().isoformat()) == []


def test_reselect_promotes_and_protects_held(tmpdb, monkeypatch):
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 10, 5)))
    monkeypatch.setattr(config, "RESELECT_TIMES", [(10, 0)])
    monkeypatch.setattr(config, "TOP_STOCKS", 2)  # force an eviction
    hot = _breakout_5m()
    t = _trader({"HOLD": _flat_5m(100.0), "DULL": _flat_5m(50.0), "HOT": hot})
    t.paper_portfolio.execute_buy("HOLD", 10, 100.0, stop_loss=98.0, take_profit=104.0)
    t.watchlist = ["HOLD", "DULL"]
    t.ranked_all = [{"symbol": "HOLD"}, {"symbol": "DULL"}, {"symbol": "HOT"}]
    t.maybe_reselect()
    assert "HOT" in t.watchlist and "HOLD" in t.watchlist  # promoted + protected
    assert "DULL" not in t.watchlist
    # second call same slot: no-op
    before = list(t.watchlist)
    t.maybe_reselect()
    assert t.watchlist == before


def test_force_close_normal(tmpdb, monkeypatch):
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 10, 0)))
    t = _trader({"X": _flat_5m(102.0)})
    t.paper_portfolio.execute_buy("X", 10, 100.0, stop_loss=98.0, take_profit=110.0)
    t.force_close_all()
    assert not t.paper_portfolio.has_position("X")
    rows = [r for r in db.get_trades_for_date(datetime.now().date().isoformat())
            if r["side"] == "SELL"]
    assert rows and rows[-1]["exit_reason"] == "FORCE_CLOSE_EOD"
    today = __import__("datetime").date.today()
    assert t.risk_manager.daily_pnl.get(today, 0) != 0


def test_end_session_upserts(tmpdb, monkeypatch):
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 10, 0)))
    t = _trader({"X": _flat_5m(102.0)})
    t.paper_portfolio.execute_buy("X", 10, 100.0, stop_loss=98.0, take_profit=110.0)
    t.paper_portfolio.execute_sell("X", 10, 102.0)
    t.end_session()
    t.end_session()  # upsert, not duplicate
    sessions = db.get_all_sessions()
    assert len(sessions) == 1
    assert sessions[0]["total_trades"] == 1
    assert sessions[0]["end_capital"] > 0


def test_portfolio_value_empty_is_cash(tmpdb):
    t = _trader({})
    assert t.get_portfolio_value() == t.paper_portfolio.cash == 1_000_000
