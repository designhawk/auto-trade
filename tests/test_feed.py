"""Feed layer: manager diff/cache/watchdog + instrument token map."""
import os
import time

import pandas as pd

from feed_manager import FeedManager
import instruments
from instruments import build_token_map, ensure_tokens


class _FakeFeed:
    def __init__(self):
        self.subs = []
        self.unsubs = []
        self.store = {"ltp": {"NSE": {"CASH": {}}}}

    def subscribe_ltp(self, insts):
        self.subs.append(insts)

    def unsubscribe_ltp(self, insts):
        self.unsubs.append(insts)

    def get_ltp(self):
        return self.store


def _mgr(now=1_000_000.0):
    return FeedManager(_FakeFeed(), now=lambda: now)


def test_resubscribe_diffs():
    m = _mgr()
    assert m.resubscribe(["A", "B"], {"A": "1", "B": "2"}) is True
    assert m.active and m._subscribed == {"A", "B"}
    m.resubscribe(["B", "C"], {"B": "2", "C": "3"})
    assert m._subscribed == {"B", "C"}
    flat = [d for batch in m._feed.unsubs for d in batch]
    assert {"exchange": "NSE", "segment": "CASH", "exchange_token": "1"} in flat
    assert m._feed.subs[-1] == [
        {"exchange": "NSE", "segment": "CASH", "exchange_token": "3"}]


def test_resubscribe_failure_fail_open():
    class _Boom(_FakeFeed):
        def subscribe_ltp(self, insts):
            raise RuntimeError("socket down")

    m = FeedManager(_Boom())
    assert m.resubscribe(["A"], {"A": "1"}) is False
    assert m.active is False


def test_get_cached_parses_and_timestamps():
    m = _mgr()
    m.resubscribe(["A", "B"], {"A": "1", "B": "2"})
    m._feed.store = {"ltp": {"NSE": {"CASH": {
        "1": {"tsInMillis": 1_000_000_000.0, "ltp": 10.5},
        "2": {"tsInMillis": 999_000_000.0, "ltp": "bad"},
    }}}}
    prices, parsed = m.get_cached(["A", "B", "C"])
    assert prices == {"A": 10.5} and parsed is True
    assert m.last_ok == 1_000_000.0
    assert m.is_fresh(60) is True
    m2 = _mgr(now=1_000_000.0 + 3600)
    m2.last_ok = 1_000_000.0
    m2.active = True
    assert m2.is_fresh(60) is False  # stale socket -> REST fallback


def test_stop_clears():
    m = _mgr()
    m.resubscribe(["A"], {"A": "1"})
    m.stop()
    assert m._subscribed == set() and m.active is False
    assert m._feed.unsubs  # unsubscribed exactly once


def _inst_df():
    return pd.DataFrame([
        {"exchange": "NSE", "segment": "CASH", "series": "EQ",
         "trading_symbol": "RELIANCE", "exchange_token": 2885},
        {"exchange": "NSE", "segment": "CASH", "series": "BE",
         "trading_symbol": "RELIANCE", "exchange_token": 9999},
        {"exchange": "BSE", "segment": "CASH", "series": "A",
         "trading_symbol": "RELIANCE", "exchange_token": 500325},
        {"exchange": "NSE", "segment": "FNO", "series": None,
         "trading_symbol": "NIFTY25FUT", "exchange_token": 12345},
        {"exchange": "NSE", "segment": "CASH", "series": "EQ",
         "trading_symbol": "TCS", "exchange_token": "2857.0"},
    ])


def test_build_token_map_prefers_eq_cash():
    m = build_token_map(_inst_df())
    assert m == {"RELIANCE": "2885", "TCS": "2857"}
    assert build_token_map(pd.DataFrame([{"a": 1}])) == {}


def test_ensure_tokens_uses_fresh_cache(tmp_path, monkeypatch):
    cache = tmp_path / "instruments.csv"
    cache.write_text("trading_symbol,exchange_token\nRELIANCE,2885\n")
    monkeypatch.setattr(instruments, "INSTRUMENTS_CACHE", cache)

    class _BoomClient:
        def get_all_instruments(self):
            raise AssertionError("cache is fresh - must not call API")

    out = ensure_tokens(_BoomClient(), ["RELIANCE", "UNKNOWN"])
    assert out == {"RELIANCE": "2885"}


def test_ensure_tokens_refreshes_stale_cache(tmp_path, monkeypatch):
    cache = tmp_path / "instruments.csv"
    cache.write_text("trading_symbol,exchange_token\nOLD,1\n")
    old = time.time() - 8 * 86400
    os.utime(cache, (old, old))
    monkeypatch.setattr(instruments, "INSTRUMENTS_CACHE", cache)

    class _Client:
        def get_all_instruments(self):
            return _inst_df()

    out = ensure_tokens(_Client(), ["RELIANCE"], ttl_days=7)
    assert out == {"RELIANCE": "2885"}
    assert cache.exists()  # cache rewritten
