"""Phase E: partials, scratch, staged EOD, MFE/MAE, cost columns on SELL rows."""
from datetime import datetime, timedelta

import pandas as pd

from live_trader import LiveTrader
from intraday_strategy import IntradayMomentumStrategy
import db

# Pin the market clock: tests run in the evening IST, when the real clock
# would trigger EOD wind-down. 10:00 = mid-session, entries open, no scaling.
LiveTrader._ist_now = staticmethod(lambda: datetime(2026, 1, 1, 10, 0))


def _df5m(close, high=None, low=None, n=50):
    idx = pd.date_range("2026-01-01 10:00", periods=n, freq="5min", tz="Asia/Kolkata")
    return pd.DataFrame({
        "open": [close] * n,
        "high": [high if high is not None else close + 0.5] * n,
        "low": [low if low is not None else close - 0.5] * n,
        "close": [close] * n,
        "volume": [10_000] * n}, index=idx)


class _Broker:
    def __init__(self, frames):
        self.frames = frames  # symbol -> df

    def connect(self):
        return True

    def disconnect(self):
        pass

    def get_ohlcv(self, symbol, interval, bars):
        return self.frames[symbol]

    def get_ltp(self, symbols):
        return {s: float(self.frames[s]["close"].iloc[-1]) for s in symbols}


def _trader(frames, capital=100_000):
    t = LiveTrader(strategy=IntradayMomentumStrategy(), broker=_Broker(frames),
                   initial_capital=capital)
    t.watchlist = []
    t.paper_portfolio.slippage_max_pct = 0  # deterministic fills
    return t


def test_partial_half_at_1r_and_breakeven(tmpdb):
    t = _trader({"X": _df5m(102.5, high=103.0, low=101.5)})
    t.paper_portfolio.execute_buy("X", 10, 100.0, stop_loss=98.0, take_profit=104.0)
    t.on_bar()
    pos = t.paper_portfolio.positions["X"]
    assert pos.qty == 5 and pos.scaled is True
    assert pos.stop_loss >= pos.avg_price  # breakeven-or-better (trailing ran first)
    assert abs(pos.mfe - 1.5) < 1e-9  # (103-100)/2
    rows = [r for r in db.get_trades_for_date(datetime.now().date().isoformat())
            if r["symbol"] == "X" and r["side"] == "SELL"]
    assert rows and rows[-1]["exit_reason"] == "SCALED_1R" and rows[-1]["qty"] == 5
    assert rows[-1]["mfe"] == pos.mfe


def test_scratch_dead_trade(tmpdb):
    t = _trader({"X": _df5m(100.2, high=100.4, low=99.9)})
    t.paper_portfolio.execute_buy("X", 10, 100.0, stop_loss=98.0, take_profit=104.0)
    pos = t.paper_portfolio.positions["X"]
    pos.entry_time = datetime.now() - timedelta(hours=3)  # well past SCRATCH_BARS
    t.on_bar()
    assert not t.paper_portfolio.has_position("X")
    rows = [r for r in db.get_trades_for_date(datetime.now().date().isoformat())
            if r["symbol"] == "X" and r["side"] == "SELL"]
    assert rows[-1]["exit_reason"] == "SCRATCH"


def test_eod_exit_frac():
    assert LiveTrader._eod_exit_frac(datetime(2026, 1, 1, 10, 0)) == 0.0
    assert LiveTrader._eod_exit_frac(datetime(2026, 1, 1, 15, 5)) == 0.5
    assert LiveTrader._eod_exit_frac(datetime(2026, 1, 1, 15, 21)) == 1.0


def test_trailing_still_ratchets(tmpdb):
    t = _trader({"X": _df5m(103.0, high=103.2, low=102.8)})
    t.paper_portfolio.execute_buy("X", 10, 100.0, stop_loss=98.0, take_profit=110.0)
    t.on_bar()
    pos = t.paper_portfolio.positions.get("X")
    # partial fired (R=1.5) leaving 5 @ breakeven SL=avg; trailing also active
    assert pos is not None and pos.scaled is True
    assert pos.stop_loss >= pos.avg_price
