"""Phase B: percentile ranks, sector caps, session-boost fail-open, intraday score."""
import pandas as pd

from stock_selector import StockSelector


class _BoomBroker:
    """Never used for data here except session_boost fail-open path."""
    def get_ohlcv(self, symbol, interval, bars):
        raise RuntimeError("no data")


def _trend_df(n=60, start=100.0, step=0.5, vol=3_000_000):
    import datetime
    idx = pd.date_range("2026-01-01 09:15", periods=n, freq="5min", tz="Asia/Kolkata")
    closes = [start + i * step for i in range(n)]
    # range + turnover sized to clear the evidence-backed screens:
    # daily ATR >= 1% and median turnover >= Rs.25cr (see docs/RESEARCH.md)
    return pd.DataFrame({
        "open": [c - 0.1 for c in closes],
        "high": [c + 1.0 for c in closes],
        "low": [c - 1.0 for c in closes],
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
    mult, _ = StockSelector.session_boost("X", 100.0, 1.0)  # no snapshot
    assert mult == 1.0
    mult, _ = StockSelector.session_boost("X", 0, 1.0, 101.0, 102.0, 99.0)
    assert mult == 1.0  # no baseline


def test_session_boost_math():
    # gap +2% on a hot tape -> boosted
    mult, det = StockSelector.session_boost("X", 100.0, 1.0, 102.0, 103.0, 101.0)
    assert mult > 1.0 and abs(det["gap_pct"] - 2.0) < 1e-9
    # gap down on a dead tape -> penalized but floored
    mult2, _ = StockSelector.session_boost("X", 100.0, 1.0, 97.0, 97.0, 97.0)
    assert 0.85 <= mult2 < 1.0


def test_extreme_gap_excluded():
    """News/circuit-sized gaps return 0.0 (excluded from the watchlist)."""
    mult, det = StockSelector.session_boost("X", 100.0, 1.0, 94.0, 95.0, 93.0)
    assert mult == 0.0 and "extreme gap" in det["skipped"]
    # boundary: exactly at the cap still passes (with epsilon)
    mult_b, _ = StockSelector.session_boost("X", 100.0, 1.0, 95.0, 95.5, 94.5)
    assert mult_b > 0.0


def test_selection_filters_turnover_and_atr():
    sel = StockSelector(_BoomBroker())

    def _sleepy():
        df = _trend_df(step=0.02).copy()
        df["high"] = df["close"] + 0.05  # ~0.1% daily ATR
        df["low"] = df["close"] - 0.05
        return df

    class _B(_BoomBroker):
        def get_ohlcv(self, symbol, interval, bars):
            if symbol == "THIN":
                return _trend_df(vol=100_000)   # ~Rs.1cr turnover
            if symbol == "SLEEPY":
                return _sleepy()
            return _trend_df(step=0.8)

    sel2 = StockSelector(_B())
    ranked = sel2.rank_stocks(["GOOD", "THIN", "SLEEPY"], interval="1d", bars=100)
    syms = [m["symbol"] for m in ranked]
    assert syms == ["GOOD"], syms


def test_price_cap_excludes_expensive_stocks(monkeypatch):
    """Stocks above capital x MAX_POSITION_PCT can't buy 1 share - exclude."""
    import config as config_mod

    monkeypatch.setattr(config_mod.config, "MIN_DAILY_ATR_PCT", 0.0)
    monkeypatch.setattr(config_mod.config, "MAX_DAILY_ATR_PCT", 100.0)
    sel = StockSelector(_BoomBroker())
    df = _trend_df(start=9000.0, step=5.0)  # ~Rs.9,000+ per share

    monkeypatch.setattr(config_mod.config, "MAX_STOCK_PRICE", 0.0)
    score, _ = sel.calculate_momentum_score("X", df)
    assert score > 0  # without the cap it qualifies

    monkeypatch.setattr(config_mod.config, "MAX_STOCK_PRICE", 8000.0)
    score, det = sel.calculate_momentum_score("X", df)
    assert score == 0.0 and "cap" in det["error"]


def test_rvol_gate_in_score_intraday():
    sel = StockSelector(_BoomBroker())
    hot = _trend_df(n=40, step=0.6)  # constant volume -> rvol == 1.0
    score, _ = sel.score_intraday("X", hot)
    assert score > 0  # at the floor, still tradeable

    dead = hot.copy()
    dead.loc[dead.index[-5:], "volume"] = 10  # last bars dead -> low RVOL
    s2, det = sel.score_intraday("X", dead)
    assert s2 == 0.0 and "RVOL" in det["error"]


def test_rank_applies_snapshot_boost(monkeypatch):
    monkeypatch.setattr(StockSelector, "_market_elapsed_min",
                        staticmethod(lambda: 30))  # pin to live session
    calls = []

    class _SnapBroker:
        def get_ohlcv(self, symbol, interval, bars):
            if symbol == "UP":
                return _trend_df(step=0.8)
            raise RuntimeError("no data")

        def get_day_ohlc(self, symbols):
            calls.append(list(symbols))
            # snapshot priced near the fixture (~147), small positive gap
            return {s: {"open": 146.5, "high": 150.0, "low": 145.0, "close": 148.0}
                    for s in symbols}

    sel = StockSelector(_SnapBroker())
    ranked = sel.rank_stocks(["UP", "MISSING"], interval="1d", bars=100)
    assert ranked and ranked[0]["symbol"] == "UP"
    assert calls, "in-session snapshot must be fetched"
    assert ranked[0]["session_boost"] > 1.0  # deterministic: snapshot feeds boost


def test_snapshot_skipped_off_hours(monkeypatch):
    monkeypatch.setattr(StockSelector, "_market_elapsed_min",
                        staticmethod(lambda: 676))  # after close: stale data risk
    calls = []

    class _B:
        def get_ohlcv(self, symbol, interval, bars):
            return _trend_df(step=0.8)

        def get_day_ohlc(self, symbols):
            calls.append(symbols)
            return {}

    sel = StockSelector(_B())
    ranked = sel.rank_stocks(["UP"], interval="1d", bars=100)
    assert ranked and ranked[0]["session_boost"] == 1.0
    assert calls == [], "off-hours must not fetch a stale day snapshot"


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
