# Risk Management

`risk_manager.py` — `RiskManager.approve(signal, current_positions, available_cash) -> RiskDecision(approved, adjusted_qty, reason)`. Every signal goes through it in `LiveTrader.on_bar` (`live_trader.py:269`); rejections are stored in `signals.rejection_reason`.

## Gates (in order, first failure rejects)

1. **Daily loss halt:** `daily_pnl < −(current_capital × DAILY_LOSS_LIMIT_PCT)` (default 3%). Resets on date change.
2. **All-time drawdown breaker:** `(all_time_peak − current) / all_time_peak > MAX_DRAWDOWN_PCT` (10%). `all_time_peak` never resets; `peak_capital` resets daily (informational).
3. **Concurrency:** `len(positions) >= MAX_OPEN_POSITIONS` (8).
4. **Duplicate symbol:** already holding `signal.symbol`.
5. **Cash reserve:** `available_cash < MIN_CASH_RESERVE` (₹2L).
6. **Risk-reward:** `(TP−entry)/(entry−SL) >= MIN_RISK_REWARD` (2.0). Long-assumed; `risk ≤ 0` rejected.
7. **Volatility:** `0.3% ≤ volatility_pct ≤ 4.0%` — now live, the strategy sets `volatility_pct` (ATR%) on every signal.
8. **Portfolio heat:** Σ `(avg−SL)×qty` over open positions `>= HEAT_CAP_PCT × capital` (6%) rejects. Needs `avg_price`/`stop_loss` per position (provided by `live_trader`).
9. **Sizing:** base 2% of capital at risk, scaled by volatility targeting (`TARGET_VOL_PCT / signal_vol`, clamped 0.5–1.5×), halved past the soft-throttle line (`THROTTLE_START_MULT × daily limit`, default half of 3%), scaled by confidence (`0.5 + 0.5×confidence`), capped at `MAX_POSITION_PCT` value and affordable cash. `qty < 1` rejected.
10. **Affordability:** position cost capped to `⌊cash/entry⌋`.

Approval reason looks like `"Approved: R:R 2.0, Qty 42"` (+ `" (throttled)"` when halved).

## State tracking

* `update_daily_pnl(pnl)` — called on every close (SL/TP/force-close).
* `update_capital(value)` — called on every close; drives peak/drawdown math.
* `get_status()` — `current/peak/all-time-peak`, drawdown %, daily P&L vs limit, breaker flags. Not wired to API/monitor — query via Python.

## Defaults vs `.env.example`

Code: 8% / 8 pos / 3% daily / 10% DD / ₹2L reserve. Example env: 10% / 10 pos / 2% daily / 5% DD / ₹1L. Runtime = `.env` → `config.py`. Reconcile before comparing runs.
