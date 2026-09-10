# stock_selector.py
"""
Stock Selector - Selects top momentum stocks for trading.

At 9:15 AM, ranks all stocks by momentum score and selects top N.

Momentum scoring (all normalized to 0-100):
- Price vs EMA (30%)
- RSI (20%) - momentum-appropriate scoring
- Volume ratio (15%)
- 5-day returns (20%)
- Trend strength (15%)

Usage:
    selector = StockSelector(broker)
    top_stocks = selector.select_top_stocks(symbols, top_n=20)
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Tuple
import pytz

from groww_broker import GrowwBroker
from config import config
from sectors import sector_of


class StockSelector:
    """
    Selects top momentum stocks for intraday trading.
    """

    def __init__(self, broker: GrowwBroker):
        """Initialize stock selector."""
        self.broker = broker

    def calculate_rsi(self, closes: pd.Series, period: int = 14) -> float:
        """Calculate RSI using Wilder's smoothing method."""
        delta = closes.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        # Wilder's smoothing (EWM with alpha=1/period)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi.iloc[-1]

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate True ATR using Wilder's smoothing (includes gap opens)."""
        prev_close = df["close"].shift(1)

        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - prev_close).abs()
        tr3 = (df["low"] - prev_close).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean().iloc[-1]

        return atr

    def calculate_momentum_score(
        self, symbol: str, df: pd.DataFrame
    ) -> Tuple[float, dict]:
        """
        Calculate momentum score for a stock.
        All components normalized to 0-100 for proper weighting.
        """
        if len(df) < 50:
            return 0.0, {"error": "Insufficient data (need 50+ bars)"}

        latest = df.iloc[-1]
        current_price = latest["close"]
        prev_close = df["close"].iloc[-2] if len(df) >= 2 else current_price

        # 1. Price vs 20 EMA (30%) - normalized to 0-100
        ema20 = df["close"].ewm(span=20, adjust=False).mean().iloc[-1]
        price_vs_ema = (current_price / ema20 - 1) * 100  # -5% to +5% typical
        price_score = np.clip((price_vs_ema + 5) / 10 * 100, 0, 100)

        # 2. RSI (20%) - momentum-appropriate scoring
        rsi = self.calculate_rsi(df["close"], 14)

        # Momentum strategy: reward 50-70 RSI, penalize oversold
        if 50 <= rsi <= 70:
            rsi_score = 100 - abs(rsi - 60) * 2  # Peak at 60
        elif rsi > 70:
            rsi_score = max(0, 100 - (rsi - 70) * 3)  # Penalize overbought
        elif rsi < 30:
            rsi_score = 10  # Oversold = weak momentum
        else:
            rsi_score = 30 + (rsi - 30) * 1.5  # Building

        rsi_score = np.clip(rsi_score, 0, 100)

        # 3. Volume ratio (15%) - use average, not single bar
        avg_volume = df["volume"].rolling(20).mean().iloc[-1]
        # Use average of last 5 bars to smooth opening spike
        recent_avg_volume = df["volume"].tail(5).mean()
        volume_ratio = recent_avg_volume / avg_volume if avg_volume > 0 else 1.0
        volume_score = np.clip(volume_ratio / 3 * 100, 0, 100)

        # 4. 5-day returns (20%) - normalized
        returns_5d = (
            (current_price / df["close"].iloc[-6] - 1) * 100 if len(df) >= 6 else 0
        )
        return_score = np.clip((returns_5d + 5) / 10 * 100, 0, 100)

        # 5. Trend strength (15%) - normalized
        sma5 = df["close"].rolling(5).mean().iloc[-1]
        sma20 = df["close"].rolling(20).mean().iloc[-1]
        trend_strength = (sma5 / sma20 - 1) * 100  # -3% to +3% typical
        trend_score = np.clip((trend_strength + 3) / 6 * 100, 0, 100)

        # Volatility check (ATR)
        atr = self.calculate_atr(df)
        volatility_pct = (atr / current_price) * 100

        # Filters: Tight bounds for NSE intraday (0.3% - 4%)
        if volatility_pct > 4.0 or volatility_pct < 0.3:
            return 0.0, {"error": f"Volatility out of range: {volatility_pct:.1f}"}

        # Filter: Skip low volume
        if avg_volume < 200000:  # 2L minimum
            return 0.0, {"error": "Low volume"}

        # Composite score (all components 0-100, weights sum to 100%)
        momentum_score = (
            price_score * 0.30
            + rsi_score * 0.20
            + volume_score * 0.15
            + return_score * 0.20
            + trend_score * 0.15
        )

        # Minimum score threshold
        if momentum_score < 10:
            return 0.0, {"error": "Low momentum score"}

        metrics = {
            "symbol": symbol,
            "price": current_price,
            "price_vs_ema_pct": price_vs_ema,
            "price_score": price_score,
            "rsi": rsi,
            "rsi_score": rsi_score,
            "volume_ratio": volume_ratio,
            "volume_score": volume_score,
            "returns_5d": returns_5d,
            "return_score": return_score,
            "trend_strength": trend_strength,
            "trend_score": trend_score,
            "volatility_pct": volatility_pct,
            "momentum_score": momentum_score,
            "prev_close": float(prev_close),
            "avg_daily_volume": float(avg_volume),
        }

        return momentum_score, metrics

    # Composite weights for the five factors (sum to 1.0)
    WEIGHTS = {"price": 0.30, "rsi": 0.20, "volume": 0.15, "return": 0.20, "trend": 0.15}
    # Metric keys holding the (clipped) component scores
    COMPONENT_KEYS = {
        "price": "price_score",
        "rsi": "rsi_score",
        "volume": "volume_score",
        "return": "return_score",
        "trend": "trend_score",
    }

    @staticmethod
    def _percentile_ranks(values: List[float]) -> List[float]:
        """Percentile rank (0-100, ties averaged) for each value."""
        n = len(values)
        if n <= 1:
            return [50.0] * n
        order = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg_rank = (i + j) / 2
            for k in range(i, j + 1):
                ranks[order[k]] = 100.0 * avg_rank / (n - 1)
            i = j + 1
        return ranks

    def session_boost(self, symbol: str, prev_close: float, avg_daily_vol: float) -> Tuple[float, dict]:
        """
        Same-session multiplier (0.85-1.20) from gap + RVOL.

        Fail-open 1.0 before the open or on any data error - a missing
        morning read must never veto an otherwise good candidate.
        """
        try:
            IST = pytz.timezone("Asia/Kolkata")
            now = datetime.now(IST)
            elapsed = (now.hour * 60 + now.minute) - (9 * 60 + 15)
            if elapsed <= 0 or prev_close <= 0 or avg_daily_vol <= 0:
                return 1.0, {"skipped": "pre-market"}

            df = self.broker.get_ohlcv(symbol, "5m", 20)
            today = df[df.index.date == now.date()]
            if len(today) < 2:
                return 1.0, {"skipped": "no-session-bars"}

            gap_pct = (today["open"].iloc[0] / prev_close - 1) * 100
            expected_vol = avg_daily_vol * (elapsed / 375.0)
            rvol = today["volume"].sum() / expected_vol if expected_vol > 0 else 1.0

            gap_term = max(-1.0, min(1.0, gap_pct / 2.0)) * 0.05
            rvol_term = max(-0.5, min(1.0, (rvol - 1.0) / 2.0)) * 0.10
            mult = max(0.85, min(1.20, 1.0 + gap_term + rvol_term))
            return mult, {"gap_pct": gap_pct, "rvol": rvol}
        except Exception as e:
            return 1.0, {"skipped": f"error: {e}"}

    def rank_stocks(
        self,
        symbols: List[str],
        interval: str = "1d",
        bars: int = 100,
    ) -> List[dict]:
        """
        Score every symbol: base factors percentile-ranked across the
        candidate set (no hand-scaled domination), then a same-session
        gap/RVOL boost for the top 60. Returns ALL passing candidates,
        sorted by final momentum_score descending.
        """
        print(f"[SELECTOR] Evaluating {len(symbols)} stocks for momentum...")

        passing = []
        for i, symbol in enumerate(symbols, 1):
            try:
                df = self.broker.get_ohlcv(symbol, interval, bars)

                if len(df) < 50:
                    continue

                score, metrics = self.calculate_momentum_score(symbol, df)

                if score > 0:
                    passing.append(metrics)

                if i % 10 == 0:
                    print(f"  Processed {i}/{len(symbols)} stocks...")

            except Exception:
                continue

        if not passing:
            return []

        # Percentile-rank each factor across candidates, then composite
        comp_lists = {
            k: [m[key] for m in passing] for k, key in self.COMPONENT_KEYS.items()
        }
        comp_ranks = {k: self._percentile_ranks(v) for k, v in comp_lists.items()}
        for idx, m in enumerate(passing):
            m["base_score"] = sum(
                comp_ranks[k][idx] * w for k, w in self.WEIGHTS.items()
            )
            m["session_boost"] = 1.0
            m["momentum_score"] = m["base_score"]

        # Same-session boost for the top 60 by base score (bounds API calls)
        passing.sort(key=lambda m: m["base_score"], reverse=True)
        for m in passing[:60]:
            mult, _ = self.session_boost(
                m["symbol"], m.get("prev_close", 0), m.get("avg_daily_volume", 0)
            )
            m["session_boost"] = mult
            m["momentum_score"] = m["base_score"] * mult

        passing.sort(key=lambda m: m["momentum_score"], reverse=True)
        return passing

    def apply_sector_caps(self, ranked: List[dict], top_n: int) -> List[dict]:
        """Take top_n from a ranked list with max MAX_SECTOR_POSITIONS per sector."""
        picked, counts = [], {}
        for m in ranked:
            sec = sector_of(m["symbol"])
            if counts.get(sec, 0) >= config.MAX_SECTOR_POSITIONS:
                continue
            picked.append(m)
            counts[sec] = counts.get(sec, 0) + 1
            if len(picked) >= top_n:
                break
        return picked

    def select_top_stocks(
        self,
        symbols: List[str],
        top_n: int = 20,
        interval: str = "5m",
        bars: int = 100,  # Increased for indicator warmup
    ) -> List[dict]:
        """
        Select top N momentum stocks (rank-normalized, session-boosted,
        sector-capped).

        Args:
            symbols: List of symbols to evaluate
            top_n: Number of top stocks to return
            interval: Data interval
            bars: Number of bars (100 for proper warmup)

        Returns:
            List of top stock dictionaries with metrics
        """
        ranked = self.rank_stocks(symbols, interval=interval, bars=bars)

        # Select top N with sector diversification
        top_stocks = self.apply_sector_caps(ranked, top_n)

        print(f"[SELECTOR] Selected top {len(top_stocks)} momentum stocks")

        # Print top 5
        for i, stock in enumerate(top_stocks[:5], 1):
            print(
                f"  {i}. {stock['symbol']}: Score={stock['momentum_score']:.1f}, "
                f"Price={stock['price']:.2f}, RSI={stock['rsi']:.0f}, "
                f"Vol={stock['volume_ratio']:.1f}x, EMA={stock['price_vs_ema_pct']:+.1f}%"
            )

        return top_stocks

    def score_intraday(self, symbol: str, df: pd.DataFrame) -> Tuple[float, dict]:
        """
        Mid-session momentum score (0-100) from 5m bars, for re-ranking
        the watchlist once morning action exists. (0.0, err) when unusable.
        """
        if len(df) < 30:
            return 0.0, {"error": "need 30+ 5m bars"}

        closes = df["close"]
        price = closes.iloc[-1]

        # Session VWAP from available bars
        tp = (df["high"] + df["low"] + df["close"]) / 3
        cumvol = df["volume"].cumsum().iloc[-1]
        vwap = (tp * df["volume"]).cumsum().iloc[-1] / cumvol if cumvol > 0 else price
        vs_vwap = (price / vwap - 1) * 100 if vwap > 0 else 0.0

        ema20 = closes.ewm(span=20, adjust=False).mean().iloc[-1]
        trend = (price / ema20 - 1) * 100 if ema20 > 0 else 0.0

        avg20 = df["volume"].rolling(20).mean().iloc[-1]
        rvol = df["volume"].tail(5).mean() / avg20 if avg20 > 0 else 1.0

        day_high, day_low = df["high"].max(), df["low"].min()
        day_range = day_high - day_low
        range_pos = (price - day_low) / day_range * 100 if day_range > 0 else 50.0

        rsi = self.calculate_rsi(closes, 14)
        if 50 <= rsi <= 70:
            rsi_score = 100 - abs(rsi - 60) * 2
        elif rsi > 70:
            rsi_score = max(0, 100 - (rsi - 70) * 3)
        elif rsi < 30:
            rsi_score = 10
        else:
            rsi_score = 30 + (rsi - 30) * 1.5

        def clip(x):
            return max(0.0, min(100.0, x))

        vwap_score = clip((vs_vwap + 1) / 2 * 100)
        trend_score = clip((trend + 1) / 2 * 100)
        vol_score = clip(rvol / 2 * 100)
        rsi_score = clip(rsi_score)
        range_pos = clip(range_pos)

        score = (
            vwap_score * 0.25
            + trend_score * 0.25
            + vol_score * 0.20
            + range_pos * 0.15
            + rsi_score * 0.15
        )
        return score, {
            "symbol": symbol,
            "price": float(price),
            "vwap": float(vwap),
            "vs_vwap_pct": float(vs_vwap),
            "rvol": float(rvol),
            "rsi": float(rsi),
            "intraday_score": float(score),
        }

    def get_watchlist(self, top_stocks: List[dict]) -> List[str]:
        """Extract just the symbols from top stocks list."""
        return [stock["symbol"] for stock in top_stocks]


if __name__ == "__main__":
    from groww_broker import GrowwBroker

    broker = GrowwBroker()
    if broker.connect():
        selector = StockSelector(broker)

        test_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

        top_stocks = selector.select_top_stocks(test_symbols, top_n=3)

        print("\nTop stocks:")
        for stock in top_stocks:
            print(f"  {stock['symbol']}: {stock['momentum_score']:.2f}")

        broker.disconnect()
