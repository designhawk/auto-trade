"""Phase B: percentile ranks, sector caps, session-boost fail-open, intraday score."""
import pandas as pd

from stock_selector import StockSelector


class _BoomBroker:
    """Never used for data here except session_boost fail-open path."""
    def get_ohlcv(self, symbol, interval, bars):
        raise RuntimeError("no data")


def _trend_df(n=60, start=100.0, step=0.5, vol=1_000_000):
    import datetime
    idx = pd.date_range("2026-01-01 09:15", periods=n, freq="5min", tz="Asia/Kolkata")
    closes = [start + i * step for i in range(n)]
    return pd.DataFrame({
        "open": [c - 0.1 for c in closes],
        "high": [c + 0.3 for c in closes],
        "low": [c - 0.3 for c in closes],
        "close": closes,
        "volume": [vol] * n}, index=idx)


def test_percentile_ranks_with_ties():
    assert StockSelector._percentile_ranks([10, 20, 20, 30]) == [0.0, 50.0, 50.0, 100.0]
    assert StockSelector._percentile_ranks([5.0]) == [50.0]


def test_rank_stocks_sorted_and_boosted():
    sel = StockSelector(_BoomBroker())

    class _B(_BoomBroker):
        def get_ohlcv(self, symbol, interval, bars):
            if symbol == "UP":
                return _trend_df(step=0.8)
            if symbol == "FLAT":
                return _trend_df(step=0.0)
            raise RuntimeError("no data")

    sel2 = StockSelector(_B())
    ranked = sel2.rank_stocks(["UP", "FLAT", "MISSING"], interval="1d", bars=100)
    syms = [m["symbol"] for m in ranked]
    assert syms[0] == "UP" and "MISSING" not in syms
    assert all(0 <= m["momentum_score"] <= 120 for m in ranked)


def test_session_boost_fail_open():
    sel = StockSelector(_BoomBroker())
    mult, info = sel.session_boost("X", 100.0, 1_000_000)
    assert mult == 1.0  # broker raises -> fail-open, never a veto


def test_sector_caps():
    sel = StockSelector(_BoomBroker())
    ranked = [{"symbol": s, "momentum_score": 90 - i}
              for i, s in enumerate(["RELIANCE", "ONGC", "BPCL", "IOC", "GAIL"])]
    picked = sel.apply_sector_caps(ranked, 5)
    assert len(picked) == 3  # default MAX_SECTOR_POSITIONS=3, all ENERGY


def test_score_intraday_bounds():
    sel = StockSelector(_BoomBroker())
    score, m = sel.score_intraday("X", _trend_df(n=40, step=0.6))
    assert 0 < score <= 100
    assert {"vwap", "rvol", "rsi", "intraday_score"} <= set(m)
    s2, _ = sel.score_intraday("X", _trend_df(n=10))
    assert s2 == 0.0  # too short -> unusable
