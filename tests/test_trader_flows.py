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
        self.frames = frames  # symbol -> {interval: df, "15m": df} or df

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
            df = f[config.TRADE_INTERVAL] if isinstance(f, dict) else f
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
    t = _trader({"E": {config.TRADE_INTERVAL: _breakout_5m(), "15m": _up_15m()}})
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
    t = _trader({"E": {config.TRADE_INTERVAL: _breakout_5m(), "15m": _up_15m()}})
    t.watchlist = ["E"]
    t.on_bar()
    assert not t.paper_portfolio.has_position("E")
    assert db.get_signals_for_date(datetime.now().date().isoformat()) == []


def test_lunch_pause_blocks_entries_when_enabled(tmpdb, monkeypatch):
    """11:45-13:30 is the highest-loss window in Indian intraday studies.
    The pause ships disabled (paper data collection) - when enabled it
    must block fresh entries."""
    monkeypatch.setattr(config, "ENTRY_PAUSE_START", (11, 45))
    monkeypatch.setattr(config, "ENTRY_PAUSE_END", (13, 30))
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 12, 30)))
    t = _trader({"E": {config.TRADE_INTERVAL: _breakout_5m(), "15m": _up_15m()}})
    t.watchlist = ["E"]
    t.on_bar()
    assert not t.paper_portfolio.has_position("E")
    assert db.get_signals_for_date(datetime.now().date().isoformat()) == []


def test_lunch_entries_allowed_when_pause_disabled(tmpdb, monkeypatch):
    """Default config: no midday pause (paper trading wants the data)."""
    assert config.ENTRY_PAUSE_START == (0, 0)
    assert config.ENTRY_PAUSE_END == (0, 0)
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 12, 30)))
    t = _trader({"E": {config.TRADE_INTERVAL: _breakout_5m(), "15m": _up_15m()}})
    t.watchlist = ["E"]
    t.on_bar()
    assert t.paper_portfolio.has_position("E")


def test_trade_cap_blocks_entries(tmpdb, monkeypatch):
    """Overtrading is the #1 documented retail killer; cap entries/day."""
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 11, 0)))
    # pinned clock date must match the fake trade's date for the cap to count
    db.insert_trade({"timestamp": "2026-01-01T09:00:00", "symbol": "F0",
                     "side": "BUY", "qty": 1, "price": 10.0, "value": 10.0})
    frames = {"E": {config.TRADE_INTERVAL: _breakout_5m(), "15m": _up_15m()},
              "F0": _flat_5m(10.0)}

    monkeypatch.setattr(config, "MAX_TRADES_PER_DAY", 1)
    t1 = _trader(frames)
    t1.watchlist = ["E"]
    t1.on_bar()
    assert not t1.paper_portfolio.has_position("E")  # cap reached -> blocked

    monkeypatch.setattr(config, "MAX_TRADES_PER_DAY", 2)
    t2 = _trader(frames)
    t2.watchlist = ["E"]
    t2.on_bar()
    assert t2.paper_portfolio.has_position("E")  # under cap -> allowed


def test_vix_filter_blocks_extreme(tmpdb, monkeypatch):
    """VIX filter: entries pause in panic/euphoria regimes, not in normal ones."""
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 11, 0)))
    frames = {"E": {config.TRADE_INTERVAL: _breakout_5m(), "15m": _up_15m()}}

    t1 = _trader(frames)
    t1.watchlist = ["E"]
    t1.vix_value = 30.0  # above VIX_MAX -> no entries
    t1.on_bar()
    assert not t1.paper_portfolio.has_position("E")

    t2 = _trader(frames)
    t2.watchlist = ["E"]
    t2.vix_value = 15.0  # normal regime -> entry allowed
    t2.on_bar()
    assert t2.paper_portfolio.has_position("E")


def test_vix_fail_open_without_quote(tmpdb):
    """Missing VIX must never block trading."""
    t = _trader({})
    t._refresh_vix()  # fake broker has no get_quote -> must not raise
    assert t.vix_value is None
    assert t._vix_ok() is None  # unknown -> entry check passes


def test_exclude_symbols_filters_universe(tmpdb, monkeypatch, tmp_path):
    """Manual exclusion list (e.g. results-day names) removes from the scan."""
    monkeypatch.setattr(config, "NSE_STOCKS", ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(config, "EXCLUDE_SYMBOLS", {"BBB"})
    monkeypatch.setattr(db, "BACKUP_DIR", tmp_path / "backups")

    t = _trader({})
    t.pre_market()
    assert t.universe == ["AAA", "CCC"]


def test_entry_start_blocks_first_15min(tmpdb, monkeypatch):
    """Research: the first 15 minutes are false-breakout territory."""
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 9, 20)))
    t = _trader({"E": {config.TRADE_INTERVAL: _breakout_5m(), "15m": _up_15m()}})
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


def test_entry_fetch_covers_lookback(tmpdb, monkeypatch):
    """Longer lookbacks (e.g. 60 bars on 1m) must still be fetched in full."""
    monkeypatch.setattr(LiveTrader, "_ist_now",
                        staticmethod(lambda: datetime(2026, 1, 1, 10, 0)))
    strategy = IntradayMomentumStrategy(lookback=60, volume_multiplier=0.5,
                                        cooldown_bars=0)
    needed = strategy.required_bars()

    class _B(_Broker):
        def get_ohlcv(self, symbol, interval, bars):
            if interval == config.TRADE_INTERVAL:
                assert bars >= needed, f"fetched {bars}, strategy needs {needed}"
            return super().get_ohlcv(symbol, interval, bars)

    t = LiveTrader(strategy=strategy,
                   broker=_B({"E": {config.TRADE_INTERVAL: _breakout_5m(),
                                    "15m": _up_15m()}}),
                   initial_capital=1_000_000)
    t.watchlist = ["E"]
    t.paper_portfolio.slippage_max_pct = 0
    t.on_bar()  # the fetch assertion is the point; signal may not fire


def test_min_stop_pct_floor_widens_stops(tmpdb):
    """A noise-floor stop keeps fast-bar targets economically meaningful."""
    floored = IntradayMomentumStrategy(volume_multiplier=0.5, cooldown_bars=0,
                                       min_stop_pct=0.02, max_stop_loss_pct=0.05)
    natural = IntradayMomentumStrategy(volume_multiplier=0.5, cooldown_bars=0,
                                       max_stop_loss_pct=0.05)
    s_floored = floored.generate_signals("X", _breakout_5m(), _up_15m())
    s_natural = natural.generate_signals("X", _breakout_5m(), _up_15m())
    assert s_floored and s_natural
    entry = s_floored[0].entry_price
    risk_pct = (entry - s_floored[0].stop_loss) / entry
    # signal levels are rounded to 2dp, hence the loose tolerance
    assert abs(risk_pct - 0.02) < 1e-3, risk_pct          # floor binds
    assert s_floored[0].stop_loss < s_natural[0].stop_loss  # wider stop
    # 2R target is now at least 4% away
    tp_pct = (s_floored[0].take_profit - entry) / entry
    assert abs(tp_pct - 0.04) < 1e-3, tp_pct


def test_wider_stop_params_lower_the_stop(tmpdb):
    """stop_atr_mult + recent_low_bars widen (lower) the protective stop."""
    narrow = IntradayMomentumStrategy(volume_multiplier=0.5, cooldown_bars=0)
    wide = IntradayMomentumStrategy(volume_multiplier=0.5, cooldown_bars=0,
                                    stop_atr_mult=2.5, recent_low_bars=15,
                                    max_stop_loss_pct=0.05)  # cap relaxed: this
    # synthetic tape has 5m-scale volatility, so the default 2.5% cap would bind
    s1 = narrow.generate_signals("X", _breakout_5m(), _up_15m())
    s2 = wide.generate_signals("X", _breakout_5m(), _up_15m())
    assert s1 and s2, "both variants must produce a signal"
    assert s2[0].stop_loss < s1[0].stop_loss


def test_portfolio_value_empty_is_cash(tmpdb):
    t = _trader({})
    assert t.get_portfolio_value() == t.paper_portfolio.cash == 1_000_000
