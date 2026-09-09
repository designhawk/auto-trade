# Stock Selection

`stock_selector.py` — pre-market ranker. Called once in `LiveTrader.pre_market()` (`live_trader.py:92`): `select_top_stocks(universe=config.NSE_STOCKS, top_n=config.TOP_STOCKS, interval="1d", bars=100)` → `get_watchlist()` (symbols only). Falls back to `universe[:20]` on error.

## Score (0–100, weights sum to 100%)

Computed in `calculate_momentum_score` (`stock_selector.py:63`), needs ≥ 50 bars:

| Factor | Weight | Formula |
|---|---|---|
| Price vs EMA20 | 30% | `clip((close/EMA20−1)*100 +5)/10*100` (±5% maps to 0–100) |
| RSI(14, Wilder ewm) | 20% | peaks at RSI 60 (100 pts), 50–70 band rewarded, >70 penalized ×3, <30 → 10, 30–50 ramp |
| Volume ratio | 15% | `mean(vol[-5:])/mean(vol[-20:]) /3*100` (5-bar avg smooths opening spike) |
| 5-day return | 20% | `clip((ret+5)/10*100)` (±5% maps to 0–100) |
| Trend (SMA5 vs SMA20) | 15% | `clip((SMA5/SMA20−1)*100 +3)/6*100` (±3% maps to 0–100) |

## Hard filters (score → 0 with `error` reason)

* Volatility: `ATR_Wilder(14)/price` must be 0.3–4% (NSE intraday bounds).
* Liquidity: 20-bar avg volume ≥ 2,00,000.
* Quality: composite ≥ 10.

## Cost note

`select_top_stocks` fetches `bars=100` daily candles **per symbol** sequentially (~150 API calls pre-market, logging every 10). Failures are silently skipped. Budget Groww rate limits / pre-market time accordingly; `bars` also doubles as indicator warmup (EMA20/RSI14/ATR14 need it).

## Smoke test

`python stock_selector.py` connects via `GrowwBroker`, ranks `["RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK"]` top-3 and prints score/price/RSI/vol/EMA-distance.
