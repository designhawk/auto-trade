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
from typing import List, Tuple

from groww_broker import GrowwBroker


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
        }

        return momentum_score, metrics

    def select_top_stocks(
        self,
        symbols: List[str],
        top_n: int = 20,
        interval: str = "5m",
        bars: int = 100,  # Increased for indicator warmup
    ) -> List[dict]:
        """
        Select top N momentum stocks.

        Args:
            symbols: List of symbols to evaluate
            top_n: Number of top stocks to return
            interval: Data interval
            bars: Number of bars (100 for proper warmup)

        Returns:
            List of top stock dictionaries with metrics
        """
        print(f"[SELECTOR] Evaluating {len(symbols)} stocks for momentum...")

        stock_scores = []

        for i, symbol in enumerate(symbols, 1):
            try:
                df = self.broker.get_ohlcv(symbol, interval, bars)

                if len(df) < 50:
                    continue

                score, metrics = self.calculate_momentum_score(symbol, df)

                if score > 0:
                    stock_scores.append((score, metrics))

                if i % 10 == 0:
                    print(f"  Processed {i}/{len(symbols)} stocks...")

            except Exception:
                continue

        # Sort by momentum score (descending)
        stock_scores.sort(key=lambda x: x[0], reverse=True)

        # Select top N
        top_stocks = [metrics for score, metrics in stock_scores[:top_n]]

        print(f"[SELECTOR] Selected top {len(top_stocks)} momentum stocks")

        # Print top 5
        for i, stock in enumerate(top_stocks[:5], 1):
            print(
                f"  {i}. {stock['symbol']}: Score={stock['momentum_score']:.1f}, "
                f"Price={stock['price']:.2f}, RSI={stock['rsi']:.0f}, "
                f"Vol={stock['volume_ratio']:.1f}x, EMA={stock['price_vs_ema_pct']:+.1f}%"
            )

        return top_stocks

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
