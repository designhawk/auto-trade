# intraday_strategy.py
"""
5-minute Intraday Momentum Strategy.

This strategy generates BUY signals when:
1. Price breaks above the 20-period high with volume
2. Stock is in uptrend (price above 50 EMA)
3. RSI shows momentum (not overbought)
4. Risk-reward ratio is favorable (2:1)

Exit conditions:
- Trailing stop loss based on ATR
- End of session (3:25 PM)
"""

import pandas as pd
import numpy as np
from base_strategy import BaseStrategy, Signal


class IntradayMomentumStrategy(BaseStrategy):
    """
    5-minute momentum strategy for intraday trading.

    Strategy Logic:
    - Entry: Breakout above 20-period high with volume + uptrend confirmation
    - Stop Loss: ATR-based or recent 5-bar low
    - Take Profit: 2:1 risk-reward ratio
    - Confidence: Based on volume ratio and trend strength
    """

    def __init__(
        self,
        lookback: int = 20,
        volume_multiplier: float = 1.2,
        min_risk_reward: float = 2.0,
        max_stop_loss_pct: float = 0.025,
        cooldown_bars: int = 10,
        trend_lookback: int = 20,  # Lowered from 50 for intraday (50 EMA on 5m = 4hrs)
    ):
        self.lookback = lookback
        self.volume_multiplier = volume_multiplier
        self.min_risk_reward = min_risk_reward
        self.max_stop_loss_pct = max_stop_loss_pct
        self.cooldown_bars = cooldown_bars
        self.trend_lookback = trend_lookback
        self.last_signal_bar = {}

    @property
    def name(self) -> str:
        """Return strategy name."""
        return "IntradayMomentum"

    def required_bars(self) -> int:
        """Return minimum bars needed (lookback + buffer)."""
        return self.lookback + 2  # 22 bars minimum for 5m intraday

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]

        return atr

    def generate_signals(self, symbol: str, df: pd.DataFrame) -> list[Signal]:
        """
        Generate trading signals based on momentum breakout.

        Args:
            symbol: Trading symbol
            df: OHLCV DataFrame with at least required_bars() rows

        Returns:
            List of Signal objects (empty if no signal)
        """
        # Validate data
        if not self.validate_dataframe(df):
            return []

        if len(df) < self.required_bars():
            return []

        # Cooldown check
        current_bar = len(df)
        if symbol in self.last_signal_bar:
            if current_bar - self.last_signal_bar[symbol] < self.cooldown_bars:
                return []

        signals = []

        # Get the latest candle
        latest = df.iloc[-1]
        current_price = latest["close"]

        # Calculate indicators
        # 1. 20-period rolling high
        rolling_high = df["high"].rolling(window=self.lookback).max().iloc[-2]

        # 2. Average volume over lookback period
        avg_volume = df["volume"].rolling(window=self.lookback).mean().iloc[-2]

        # 3. Recent 5-bar average volume (smoother, matches selector)
        recent_avg_volume = df["volume"].tail(5).mean()

        # 4. Recent 5-bar low for stop loss
        recent_low = df["low"].tail(5).min()

        # 4. ATR for dynamic stop loss
        atr = self.calculate_atr(df)

        # 5. EMA for trend (50-period)
        ema50 = df["close"].ewm(span=self.trend_lookback, adjust=False).mean().iloc[-1]
        ema50_prev = (
            df["close"].ewm(span=self.trend_lookback, adjust=False).mean().iloc[-2]
        )

        # 6. RSI for momentum (14-period)
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]

        # 7. Previous close for context
        prev_close = df["close"].iloc[-2]

        # === STRICT BUY CONDITIONS ===

        # Condition 1: Strong breakout (price breaks above 20-period high)
        breakout = current_price > rolling_high

        # Condition 2: Volume confirmation (5-bar avg volume, matches selector)
        volume_confirmed = recent_avg_volume > (avg_volume * self.volume_multiplier)

        # Condition 3: Trend confirmation (price above 50 EMA - uptrend)
        in_uptrend = current_price > ema50

        # Condition 4: RSI not overbought (between 30-70, prefer 40-60)
        rsi_ok = 30 < rsi < 75

        # Condition 5: Positive momentum (close > previous close)
        momentum = current_price > prev_close

        # ALL conditions must be met for a signal
        buy_signal = (
            breakout and volume_confirmed and in_uptrend and rsi_ok and momentum
        )

        if buy_signal:
            # Calculate stop loss (use ATR or recent low, whichever is tighter)
            atr_stop = current_price - (atr * 1.5)
            stop_loss = max(recent_low, atr_stop)

            # Check if stop loss is within acceptable range
            risk_per_share = current_price - stop_loss
            risk_pct = risk_per_share / current_price

            if risk_pct > self.max_stop_loss_pct:
                return []

            if risk_per_share <= 0:
                return []

            # Calculate take profit for 2:1 risk-reward
            risk = current_price - stop_loss
            take_profit = current_price + (risk * self.min_risk_reward)

            # Calculate confidence based on multiple factors
            volume_ratio = recent_avg_volume / avg_volume
            trend_strength = (current_price - ema50) / ema50 * 100

            confidence = min(volume_ratio / (self.volume_multiplier * 2), 1.0) * 0.6
            confidence += min(trend_strength / 5, 0.2)  # Up to 0.2 for trend strength
            confidence = min(confidence, 1.0)

            # Create signal
            signal = Signal(
                symbol=symbol,
                action="BUY",
                confidence=round(confidence, 2),
                entry_price=round(current_price, 2),
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                reason=(
                    f"Breakout above {self.lookback}-period high (₹{rolling_high:.2f}) "
                    f"with {volume_ratio:.1f}x volume. "
                    f"Trend: {'up' if in_uptrend else 'down'} (EMA50: ₹{ema50:.2f}). "
                    f"RSI: {rsi:.0f}. "
                    f"Risk: ₹{risk:.2f} ({risk_pct * 100:.1f}%), "
                    f"Reward: ₹{take_profit - current_price:.2f}"
                ),
            )

            signals.append(signal)
            self.last_signal_bar[symbol] = len(df)

        return signals

    def validate_dataframe(self, df: pd.DataFrame) -> bool:
        """
        Validate DataFrame has required columns.

        Args:
            df: DataFrame to validate

        Returns:
            True if valid
        """
        required_columns = ["open", "high", "low", "close", "volume"]

        if not isinstance(df, pd.DataFrame):
            return False

        if len(df) == 0:
            return False

        missing_cols = set(required_columns) - set(df.columns)
        if missing_cols:
            return False

        return True
