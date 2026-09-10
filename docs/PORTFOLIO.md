# Paper Portfolio

`paper_portfolio.py` — `PaperPortfolio` simulates fills with the NSE equity-intraday cost schedule. No persistence of its own; it **rehydrates from `trades`** on startup (`load_positions_from_db`, `live_trader.py`).

## Costs (verify against your broker's contract note)

Per fill: brokerage 0.03% each side, STT 0.025% **sell-side only**, stamp 0.002% buy-side, exchange ~0.00297% + SEBI ₹10/crore + 18% GST (grouped as `other_costs`), plus adverse slippage sampled U[0, 0.04%] per fill (seed via `SLIPPAGE_SEED` for reproducibility). All rates are constructor params fed from `config.py`. Every `execute_*` result and `trades` row carries the full breakdown (`brokerage, stt, other_costs, slippage_cost`).

## Positions & transactions

* `Position(symbol, qty, avg_price, side="LONG", entry_time, stop_loss, take_profit, trailing_stop=True, trail_activation_pct=2%, trail_distance_pct=1.5%, scaled=False, initial_risk, mfe=0, mae=0)`. `initial_risk` (entry avg − entry SL) is the R reference for MFE/MAE, partials, and scratch; `scaled` marks the 1R partial as taken.
* `Transaction(timestamp, symbol, side, qty, price, value, brokerage, stt, net_value)`.
* `execute_buy(symbol, qty, price, stop_loss?, take_profit?)`: slippage worsens price `×(1+0.02%)`, cost = `gross + brokerage(0.03%) + STT(0.025%)`; needs `net ≤ cash`; averages into existing position; defaults SL/TP to ±2% if not passed (trader always passes real ones).
* `execute_sell(symbol, qty, price)`: price `×(1−0.02%)`, proceeds = `gross − brokerage − STT`; `net_pnl = proceeds − avg×qty`, `pnl_pct` on cost basis; deletes position at zero.
* `get_portfolio_value({symbol: price})` → cash, positions_value, total, return %, unrealized P&L, per-position detail, cumulative brokerage/STT.

## Reload semantics (important)

`load_positions_from_db` nets BUYs against SELLs per symbol (`net_qty > 0` stays open) at the buy-weighted average price (ignores slippage/costs), with synthetic `SL = −2% / TP = +2%`, trailing on — signal-level SL/TP can't be recovered (the trades table doesn't store them). Cash is recomputed as `initial − ΣBUY.value + ΣSELL.value`. Costs tracked in-memory reset each restart. Restart mid-day only via the same DB.

## Trailing stop (driven by trader, not portfolio)

In `on_bar`, once `(price−avg)/avg ≥ activation` (2%, trail distance halved after 14:30), SL ratchets to `price×(1−distance)` whenever that exceeds the current SL — evaluated before the SL/TP checks each bar. After the 1R partial, SL moves to breakeven (`max(SL, avg)`). Portfolio just stores the mutated SL.

## Helpers

`get_positions / has_position / get_position_qty / get_transactions / get_summary`. Costs are class constants overridable at construction; trader uses `PaperPortfolio(initial_capital)` defaults rather than config cost values — keep them in sync manually.
