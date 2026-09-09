# Paper Portfolio

`paper_portfolio.py` — `PaperPortfolio` simulates fills with costs. No persistence of its own; it **rehydrates from `trades`** on startup (`load_positions_from_db`, `live_trader.py:82`).

## Positions & transactions

* `Position(symbol, qty, avg_price, side="LONG", entry_time, stop_loss, take_profit, trailing_stop=True, trail_activation_pct=2%, trail_distance_pct=1.5%)`.
* `Transaction(timestamp, symbol, side, qty, price, value, brokerage, stt, net_value)`.
* `execute_buy(symbol, qty, price, stop_loss?, take_profit?)`: slippage worsens price `×(1+0.02%)`, cost = `gross + brokerage(0.03%) + STT(0.025%)`; needs `net ≤ cash`; averages into existing position; defaults SL/TP to ±2% if not passed (trader always passes real ones).
* `execute_sell(symbol, qty, price)`: price `×(1−0.02%)`, proceeds = `gross − brokerage − STT`; `net_pnl = proceeds − avg×qty`, `pnl_pct` on cost basis; deletes position at zero.
* `get_portfolio_value({symbol: price})` → cash, positions_value, total, return %, unrealized P&L, per-position detail, cumulative brokerage/STT.

## Reload semantics (important)

`load_positions_from_db` treats **any BUY symbol with no SELL row ever** as still open — using `AVG(price)` (ignores slippage/costs) and synthetic `SL = −2% / TP = +2%`, trailing on. Cash is recomputed as `initial − ΣBUY.value + ΣSELL.value`. Consequences: partial sells break the `NOT IN (SELL)` heuristic (symbol vanishes from portfolio while still held); costs tracked in-memory reset each restart. Restart mid-day only via the same DB.

## Trailing stop (driven by trader, not portfolio)

In `on_bar`, if `pos.trailing_stop and price > take_profit` and `(price−avg)/avg ≥ 2%`, SL ratchets to `price×(1−1.5%)`. Portfolio just stores the mutated SL.

## Helpers

`get_positions / has_position / get_position_qty / get_transactions / get_summary`. Costs are class constants overridable at construction; trader uses `PaperPortfolio(initial_capital)` defaults rather than config cost values — keep them in sync manually.
