"""Broker layer: candle parsing (new ISO + legacy epoch), depth guard, batching."""
import pandas as pd
import pytest

from groww_broker import GrowwBroker, candles_to_df, _depth_price


NEW_ROWS = [
    ["2025-09-24T10:30:00", 245.95, 246.15, 245.05, 245.6, 735060, None],
    ["2025-09-24T11:00:00", 245.64, 245.66, 244.8, 244.94, 682373, None],
]

LEGACY_ROWS = [
    [1633072800, 150.0, 155.0, 145.0, 152.0, 10000],
    [1633073100, 152.0, 156.0, 150.0, 155.0, 12000],
]


def test_new_iso_format():
    df = candles_to_df(NEW_ROWS)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert str(df.index.tz) == "Asia/Kolkata"
    assert df["close"].iloc[-1] == 244.94
    # IST wall time preserved, not shifted
    assert df.index[0].hour == 10 and df.index[0].minute == 30


def test_legacy_epoch_format():
    df = candles_to_df(LEGACY_ROWS)
    assert len(df) == 2 and df["close"].iloc[0] == 152.0
    assert str(df.index.tz) == "Asia/Kolkata"


def test_empty_candles():
    df = candles_to_df([])
    assert len(df) == 0 and list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_depth_price_guard():
    assert _depth_price(None, "buy", 10.0) == 10.0
    assert _depth_price({}, "buy", 10.0) == 10.0
    assert _depth_price({"buy": []}, "buy", 10.0) == 10.0  # empty book, not IndexError
    assert _depth_price({"buy": [{}]}, "buy", 10.0) == 10.0
    assert _depth_price({"buy": [{"price": 99.5}]}, "buy", 10.0) == 99.5
    assert _depth_price({"buy": [{"price": None}]}, "buy", 0.0) == 0.0


class _FakeClient:
    EXCHANGE_NSE = "NSE"
    SEGMENT_CASH = "CASH"
    CANDLE_INTERVAL_MIN_5 = "5minute"
    CANDLE_INTERVAL_DAY = "1day"

    def __init__(self):
        self.ltp_calls = []

    def get_historical_candles(self, **kw):
        assert kw["groww_symbol"] == "NSE-RELIANCE"  # dash format, not bare
        assert kw["candle_interval"] == "5minute"
        return {"candles": NEW_ROWS}

    def get_ltp(self, segment, exchange_trading_symbols):
        self.ltp_calls.append(len(exchange_trading_symbols))
        assert len(exchange_trading_symbols) <= 50
        return {s: 100.0 for s in exchange_trading_symbols}


def test_get_ohlcv_uses_new_api():
    b = GrowwBroker()
    b._client = _FakeClient()
    df = b.get_ohlcv("RELIANCE", "5m", 50)
    assert isinstance(df, pd.DataFrame) and len(df) == 2
    assert str(df.index.tz) == "Asia/Kolkata"


def test_get_ohlcv_bad_interval():
    b = GrowwBroker()
    b._client = _FakeClient()
    with pytest.raises(RuntimeError):
        b.get_ohlcv("RELIANCE", "9m", 50)


def test_get_ltp_chunks_over_50():
    b = GrowwBroker()
    fake = _FakeClient()
    b._client = fake
    out = b.get_ltp([f"S{i}" for i in range(60)])
    assert len(out) == 60 and out["S59"] == 100.0
    assert fake.ltp_calls == [50, 10]


def test_get_day_ohlc_batch_and_parse():
    class _C(_FakeClient):
        def __init__(self):
            super().__init__()
            self.ohlc_calls = []

        def get_ohlc(self, segment, exchange_trading_symbols):
            self.ohlc_calls.append(len(exchange_trading_symbols))
            assert len(exchange_trading_symbols) <= 50
            return {
                "NSE_A": {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0},
                "NSE_BAD": {"open": 1.0},  # missing keys -> skipped
            }

    b = GrowwBroker()
    fake = _C()
    b._client = fake
    out = b.get_day_ohlc(["A", "BAD"])
    assert out == {"A": {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0}}
    b.get_day_ohlc([f"S{i}" for i in range(55)])
    assert fake.ohlc_calls[-2:] == [50, 5]


class _FeedMgr:
    def __init__(self, prices, fresh=True):
        self._prices = prices
        self._fresh = fresh
        self.active = True

    def get_cached(self, symbols):
        return {s: self._prices[s] for s in symbols if s in self._prices}, True

    def is_fresh(self, max_age_s):
        return self._fresh


def test_get_ltp_prefers_fresh_feed():
    b = GrowwBroker()
    b._client = _FakeClient()
    b._client.get_ltp = lambda **kw: (_ for _ in ()).throw(RuntimeError("no REST"))
    b._feed_mgr = _FeedMgr({"X": 5.0}, fresh=True)
    assert b.get_ltp(["X"]) == {"X": 5.0}


def test_get_ltp_falls_back_when_stale():
    b = GrowwBroker()
    b._client = _FakeClient()
    b._feed_mgr = _FeedMgr({"X": 5.0}, fresh=False)
    out = b.get_ltp(["X"])
    assert out == {"X": 100.0}  # REST top-up, NSE_ prefix stripped
