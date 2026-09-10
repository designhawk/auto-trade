# Stock Selection

`stock_selector.py` — pre-market ranker plus mid-session re-ranker. `LiveTrader.pre_market()` calls `rank_stocks(universe, interval="1d", bars=100)` then `apply_sector_caps(ranked, TOP_STOCKS)`. Falls back to `universe[:20]` on error. `RESELECT_TIMES` (default 09:30, 11:00 IST) re-ranks via `score_intraday` without evicting held symbols.

## Score (weights sum to 100%)

`rank_stocks` percentile-ranks each factor across the candidate set (ties averaged), so no hand-scaled factor dominates, then composites with the same weights and applies a same-session boost:

| Factor | Weight | Raw input (percentiled) |
|---|---|---|
| Price vs EMA20 | 30% | `(close/EMA20−1)` mapped ±5% → 0–100 |
| RSI(14, Wilder ewm) | 20% | desirability curve peaking at RSI 60 |
| Volume ratio | 15% | 5-bar avg / 20-bar avg |
| 5-day return | 20% | mapped ±5% → 0–100 |
| Trend (SMA5 vs SMA20) | 15% | mapped ±3% → 0–100 |

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

## Same-session boost + sector caps + re-rank

* `session_boost` multiplies the base score by 0.85–1.20 from overnight gap direction and morning RVOL (volume so far vs time-proportional daily average). Applied to the top 60 by base score to bound API calls; **fail-open 1.0** pre-market or on any data error.
* `apply_sector_caps` (`sectors.py`, `MAX_SECTOR_POSITIONS=3`) prevents a one-sector watchlist.
* `score_intraday` (5m bars: VWAP distance, 5m trend, RVOL, day-range position, RSI band) re-ranks watchlist + top-20 reserves at `RESELECT_TIMES`; held symbols are never evicted (re-ranking only affects future entries).

## Cost note

`select_top_stocks` fetches `bars=100` daily candles **per symbol** sequentially (~150 API calls pre-market, logging every 10). Failures are silently skipped. Budget Groww rate limits / pre-market time accordingly; `bars` also doubles as indicator warmup (EMA20/RSI14/ATR14 need it).

## Smoke test

`python stock_selector.py` connects via `GrowwBroker`, ranks `["RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK"]` top-3 and prints score/price/RSI/vol/EMA-distance.
