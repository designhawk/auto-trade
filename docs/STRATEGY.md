# Strategy

`intraday_strategy.py` — `IntradayMomentumStrategy(BaseStrategy)`. 5-minute, long-only, breakout + trend + volume. Contract in `base_strategy.py`.

## Signal shape

`Signal(symbol, action="BUY", confidence 0–1, entry_price, stop_loss, take_profit, reason, volatility_pct?)`. Only `BUY` (or empty list) is ever emitted; exits are handled by `LiveTrader.on_bar` (SL/TP/trailing/force-close), not by signals.

## Entry (all seven must hold on the latest 5m bar)

Evaluated in `generate_signals(symbol, df, df_15m)` (`intraday_strategy.py`), needs `required_bars() = lookback + 2` (default 22):

1. **Breakout:** `close > max(high[-lookback-1:-1])` (default 20-bar high, excluding current bar).
2. **Volume:** `mean(volume[-5:]) > avg(volume[-lookback-1:-1]) × VOLUME_MULTIPLIER` (from `.env`, wired via `live_trader.py`).
3. **Trend:** `close > EMA(close, trend_lookback=20)`.
4. **RSI(14):** `30 < RSI < 75`.
5. **Momentum:** `close > close[-2]`.
6. **15m trend alignment:** 15m `close > EMA(close, TREND_EMA=20)`. Fail-open when 15m data is missing/short.
7. **Session VWAP:** 5m `close > VWAP` (computed from today's bars; skipped when fewer than 2 session bars exist). Disable via `VWAP_REQUIRED=false`.

Plus: per-symbol cooldown (`COOLDOWN_BARS`, from `.env`), and every emitted signal carries `volatility_pct` (ATR%) for risk sizing.

## Stops, targets, confidence

* `atr = ATR(14)` (simple rolling mean of true range, `calculate_atr`).
* `stop_loss = max(min(low[-5:]), close − 1.5×ATR)`. Rejected if `risk_pct = (close−SL)/close > MAX_STOP_LOSS_PCT` (2.5%) or `≤ 0`.
* `take_profit = close + (close−SL) × MIN_RISK_REWARD` (2.0).
* `confidence = min(vol_ratio/(mult×2),1)×0.6 + min(trend_strength_pct/5, 0.2)`, rounded to 2dp. `vol_ratio` uses the same 5-bar avg; `trend_strength` = distance above EMA20 in %.

## Notes

* All strategy params (`LOOKBACK`, `VOLUME_MULTIPLIER`, `COOLDOWN_BARS`, `TREND_EMA`, `VWAP_REQUIRED`, …) come from `.env` via `config.py` — `LiveTrader` passes them explicitly.
* **Indicator warmup:** 20-bar high + EMA20 + RSI14 on 50 bars of 5m data is thin; first signals of the day are noisy.
* **No short/exit signals.** `action` is always `BUY`; `HOLD`/`SELL` never emitted.

## Tuning

Constructor: `lookback, volume_multiplier, min_risk_reward, max_stop_loss_pct, cooldown_bars, trend_lookback, trend_ema, vwap_required`. Tighten `volume_multiplier` (fewer, stronger breakouts), lower `max_stop_loss_pct` (tighter risk, more rejects), raise `cooldown_bars` (fewer repeat entries). Validate via `validate_dataframe` (needs `open/high/low/close/volume`).

## Adding a strategy

Subclass `BaseStrategy`: implement `name`, `generate_signals(symbol, df, df_15m=None) -> list[Signal]`, `required_bars()`. Inject in `live_trader.py` (`main()`). Keep signals long-only unless you also extend `on_bar`/risk sizing (currently long-assumed: `risk = entry − SL`).
