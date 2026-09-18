# Every Setting, in Plain Words

All settings live in one file: **`.env`** (your private copy; `.env.example` shows the blanks). Change a value, restart the bot. Format is always `NAME=value` — percentages are decimals (3% = `0.03`), money is rupees.

## "How much am I playing with?"

| Setting | Default | What happens if you change it |
|---|---|---|
| `INITIAL_CAPITAL` | 10,00,000 | Your pretend starting money. Lower (e.g., ₹1,00,000) makes every lesson cheaper and position sizes realistic for a beginner. |
| `IS_LIVE` | false | Leave it false. It changes nothing except a label — the bot cannot trade real money regardless. |
| `MIN_CASH_RESERVE` | ₹2,00,000 | Money the bot refuses to touch. Raise it while learning = trade smaller, survive longer. |

## "How does it pick stocks?"

| Setting | Default | What happens if you change it |
|---|---|---|
| `TOP_STOCKS` | 30 | Watchlist size. Fewer = more focused, more API calls per stock; more = broader, noisier. |
| `MIN_DAILY_ATR_PCT` / `MAX_DAILY_ATR_PCT` | 1.0 / 6.0 | Daily movement band. Below 1% = too sleepy to reach intraday targets; above 6% = news/circuit chaos. Evidence: docs/RESEARCH.md. |
| `MIN_TURNOVER_CR` | ₹25cr | Median daily traded value (price × volume). Rupee liquidity, not share count — lets you exit without slippage. |
| `MIN_RVOL` | 1.0 | "Stock in play" floor at re-rank: recent volume must be at least average. Below-average activity has negative expectancy (Zarattini et al. 2024). |
| `MAX_GAP_PCT` | 5.0 | Skip stocks gapping more than this (news/circuit events; false opening ranges). |
| `MAX_SECTOR_POSITIONS` | 3 | Max picks per sector. Lower = more diversified; higher = lets hot sectors dominate. |
| `RESELECT_TIMES` | 09:30,11:00 | Mid-morning re-ranks. Remove them and the morning list never adapts. |
| `LOOKBACK` | 20 | "Recent high" window for breakouts. Shorter = more (worse?) signals; longer = fewer, stronger ones. |
| `VOLUME_MULTIPLIER` | 1.5 | How much heavier than average the volume must be. Lower = more trades, more fakes. |
| `TREND_EMA` / `VWAP_REQUIRED` | 20 / true | The two confirmation filters. Turning VWAP off lets the bot buy weak stocks below the day's fair price — not recommended until you know why. |
| `COOLDOWN_BARS` | 15 | Breather after trading a stock, in bars (~75 min on 5m, ~15 min on 1m). Lower = possible over-trading frenzy. |
| `TRADE_INTERVAL` | 5m | Bar size for signals: `1m 2m 3m 5m 10m 15m 30m 1h`. 1m trades more often (more costs, more noise) — all "bars" below scale with it. |
| `STOP_ATR_MULT` / `RECENT_LOW_BARS` | 1.5 / 5 | Stop construction. Widen both on faster bars (1m starting point: 2.5 / 15), otherwise 1-minute noise shakes you out. |
| `MIN_STOP_PCT` | 0.0075 | Minimum stop distance (noise floor). Since targets = 2× risk, a 0.75% floor guarantees targets ≥1.5% — fast bars otherwise produce sub-1% targets that costs eat whole. |
| `MIN_VOLATILITY_PCT` / `MAX_VOLATILITY_PCT` | auto | The ATR% gate. Auto-scales from the 5m baseline (0.3–4.0%) by √interval: ~0.13–1.79% on 1m. Set explicitly to override. |

## "How big are my bets?" (the important table)

| Setting | Default | What happens if you change it |
|---|---|---|
| `MAX_POSITION_PCT` | 8% | Cap per trade. On ₹10L, no trade bigger than ₹80,000. |
| `MAX_OPEN_POSITIONS` | 8 | Max simultaneous trades. |
| `HEAT_CAP_PCT` | 6% | Max *combined* worst-case of all open trades. This is your real risk ceiling — lower it first if days feel scary. |
| `DAILY_LOSS_LIMIT_PCT` | 3% | Day ends at −3%. The single best knob for beginners: try 1% for your first month. |
| `MAX_DRAWDOWN_PCT` | 10% | Account halts 10% below its all-time peak. Your "stop and rethink everything" line. |
| `TARGET_VOL_PCT` | 1.5% | Anchor for equalizing wild vs calm stocks. You can ignore this until positions feel uneven. |
| `THROTTLE_START_MULT` | 0.5 | Halves trade size halfway to the daily loss limit. Smoothing, not safety — leave it. |
| `MIN_RISK_REWARD` | 2.0 | Minimum profit-target vs risk. Below 2.0 the math of winning breaks for most win rates. |

## "When does it take profits and give up?"

| Setting | Default | What happens if you change it |
|---|---|---|
| `PARTIAL_R` / `PARTIAL_FRAC` | 1.0 / 0.5 | Sell half at 1× risk profit. Higher R = greedier, fewer partials banked. |
| `SCRATCH_BARS` / `SCRATCH_R` | 12 / 0.5 | Give up after ~1 hour under half-risk profit. Higher bars = more patience for slow movers. |
| `TRAIL_TIGHTEN_MULT` | 0.5 | After 14:30 the safety net follows twice as closely. |
| Entry cutoff 14:45 → wind-down 15:00 → square-off 15:20 | fixed times | Hardcoded session rhythm (see Operations). Change in `config.py` only if you understand why. |

## "What does trading cost me?" (leave these unless verifying)

`BROKERAGE_PCT`, `STT_PCT` (sell-side only), `EXCHANGE_PCT`, `SEBI_PCT`, `STAMP_PCT` (buy-side), `GST_PCT`, `SLIPPAGE_MAX_PCT` (random 0–max per fill), `SLIPPAGE_SEED` (set a number for reproducible experiments). These mirror standard NSE intraday charges — verify against a real contract note, don't tune for prettier paper profits.

## "Plumbing" (you can ignore these)

`GROWW_TOTP_TOKEN/SECRET` (login), `GROWW_API_KEY/SECRET` (alternate login), `API_PORT`, `DASHBOARD_PORT`, `FEED_ENABLED`, `FEED_MAX_AGE_S`, `INSTRUMENTS_TTL_DAYS`, `MAX_STOP_LOSS_PCT`. The stock universe lives in `universe.py` (auto-generated from NSE's NIFTY Total Market top-750 list; refresh with `python tools/update_universe.py`).

## Beginner takeaways

- Change **one thing at a time** and paper-trade at least a week before judging it. Changing five knobs at once teaches you nothing.
- The learning order: `DAILY_LOSS_LIMIT_PCT` down → `INITIAL_CAPITAL` to your real savings level → `MAX_OPEN_POSITIONS` down → only then strategy knobs.
- Your `.env` is secret and personal. `.env.example` is the shareable blank — that's why two files exist.
