# Strategy

`intraday_strategy.py` — `IntradayMomentumStrategy(BaseStrategy)`. 5-minute, long-only, breakout + trend + volume. Contract in `base_strategy.py`.

## Signal shape

`Signal(symbol, action="BUY", confidence 0–1, entry_price, stop_loss, take_profit, reason, volatility_pct?)`. Only `BUY` (or empty list) is ever emitted; exits are handled by `LiveTrader.on_bar` (SL/TP/trailing/force-close), not by signals.

## Entry (all five must hold on the latest 5m bar)

Evaluated in `generate_signals(symbol, df)` (`intraday_strategy.py:73`), needs `required_bars() = lookback + 2` (default 22):

1. **Breakout:** `close > max(high[-lookback-1:-1])` (default 20-bar high, excluding current bar).
2. **Volume:** `mean(volume[-5:]) > avg(volume[-lookback-1:-1]) × VOLUME_MULTIPLIER` (default 1.5 from config; class default 1.2 — config wins via `LiveTrader` construction? No: `live_trader.py:627` constructs with class defaults, so **1.2 is live** unless you pass config values — see gotcha below).
3. **Trend:** `close > EMA(close, trend_lookback=20)`.
4. **RSI(14):** `30 < RSI < 75`.
5. **Momentum:** `close > close[-2]`.

Plus: per-symbol cooldown (`cooldown_bars`, class default 10; config says 15) — `len(df) - last_signal_bar[symbol] >= cooldown`.

## Stops, targets, confidence

* `atr = ATR(14)` (simple rolling mean of true range, `calculate_atr`).
* `stop_loss = max(min(low[-5:]), close − 1.5×ATR)`. Rejected if `risk_pct = (close−SL)/close > MAX_STOP_LOSS_PCT` (2.5%) or `≤ 0`.
* `take_profit = close + (close−SL) × MIN_RISK_REWARD` (2.0).
* `confidence = min(vol_ratio/(mult×2),1)×0.6 + min(trend_strength_pct/5, 0.2)`, rounded to 2dp. `vol_ratio` uses the same 5-bar avg; `trend_strength` = distance above EMA20 in %.

## Gotchas (read before tuning)

* **Config is partially bypassed.** `LiveTrader` builds `IntradayMomentumStrategy()` with no args, so `.env` `VOLUME_MULTIPLIER/LOOKBACK/MIN_RISK_REWARD/MAX_STOP_LOSS_PCT/COOLDOWN_BARS` do *not* reach the strategy — only the risk-manager gates and sizing see config. Pass them explicitly if you want `.env` tuning to work.
* **RSI uses simple rolling mean** here vs Wilder's ewm in `stock_selector.py` — same name, different values.
* **Indicator warmup:** 20-bar high + EMA20 + RSI14 on 50 bars of 5m data is thin; first signals of the day are noisy.
* **No short/exit signals.** `action` is always `BUY`; `HOLD`/`SELL` never emitted.

## Tuning

Constructor: `lookback, volume_multiplier, min_risk_reward, max_stop_loss_pct, cooldown_bars, trend_lookback`. Tighten `volume_multiplier` (fewer, stronger breakouts), lower `max_stop_loss_pct` (tighter risk, more rejects), raise `cooldown_bars` (fewer repeat entries). Validate via `validate_dataframe` (needs `open/high/low/close/volume`).

## Adding a strategy

Subclass `BaseStrategy`: implement `name`, `generate_signals(symbol, df) -> list[Signal]`, `required_bars()`. Inject in `live_trader.py:627`. Keep signals long-only unless you also extend `on_bar`/risk sizing (currently long-assumed: `risk = entry − SL`).
