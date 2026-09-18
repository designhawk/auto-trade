# How Indian Intraday Traders Actually Trade

A companion to [`RESEARCH.md`](RESEARCH.md) (which covers the academic backtests). This file is about **practice**: what Indian intraday traders actually do all day — the setups, the clock, the risk rules — and how this bot compares. Sources are listed at the bottom; the interesting numbers come from SEBI's own broker-level studies.

Not financial advice.

## 1. Who actually trades (and how it ends)

| Fact | Number | Source |
|---|---|---|
| Individual **cash intraday** traders losing money, FY20–FY24 | **65–71% every year** | SEBI cash-segment studies |
| Average annual loss per loss-making intraday trader (FY23) | ~₹5,371 | SEBI |
| Loss rate among intraday traders under 30 (FY23) | ~76% | SEBI |
| Individual **F&O** traders losing money, FY26 | **87.7%** (₹91,685 cr aggregate) | SEBI study, Aug 2026 |
| Aggregate individual F&O losses, FY22–FY24 | ₹1.81 lakh crore | SEBI, Sep 2024 |
| Trading intensity vs outcome | Higher turnover relative to capital = higher loss rates | SEBI FY26 |
| Experience vs outcome | Multi-year traders show *similar* loss rates — experience alone doesn't fix it | SEBI FY26 |
| Who profits | "Algo entities": 99% of FPI and proprietary profits | SEBI FY26 |

The recurring behavioural finding: **activity is not edge**. Loss-making traders trade more. And the structural finding: leverage (MIS 5–8×) multiplies existing edge — including a negative one — while cutting the time you have to recover.

## 2. The canonical toolkit

| Setup | How it's traded | Where we stand |
|---|---|---|
| **Opening Range Breakout (ORB)** — the most recommended Indian setup | Mark 9:15–9:30 (or 9:15–9:45) high/low; enter on a 5m candle *closing* beyond it with ≥1.5× volume; stop at the opposite end; target 1.5–2× the range; often one trade/day | Our rolling 60-min-high breakout is the same family (structure-based breakout + volume). Not literally ORB-anchored. |
| **VWAP breakout / pullback / flip** | Above VWAP = bullish bias; pullback that *holds* VWAP is the higher-quality entry; stop below VWAP (ATR buffer); partial at 1:1, trail rest with VWAP/EMA20 | We use VWAP as a mandatory entry gate and exit via partial-at-1R + breakeven + trailing — aligned. |
| **EMA 9/21 crossover** (5m) | Mechanical long/short on cross with candle close beyond both; skip when ADX < 20 (choppy) | We use EMA20 on 1m + EMA20 on 15m as trend filters instead. |
| **Support/resistance + candles** (PDH/PDL, pivots) | Reversal candle at prior-day high/low; entry beyond the candle; stop beyond opposite extreme | Not implemented — our entries are momentum-only, no reversal plays. |
| **Supertrend / Bollinger** | Trend-following on strong days; mean-reversion on range days | Not implemented (deliberately: one strategy done well > three done casually). |

## 3. The clock is half the strategy

Practitioner guides agree strongly on timing:

| Window (IST) | Verdict | Why |
|---|---|---|
| 9:15–9:30 | **Observe only** — no trades | Opening auction, gaps, false breakouts; the range needs to form |
| 9:30/9:45–10:30 | **Best window** — most guides trade only this | ~60% of the day's range happens in the first 75 minutes |
| 10:30–11:30 | Decent | Trend continuation |
| **11:45–13:30** | **Worst window** — highest loss rate | Samco study (2.1 lakh trades): 62% loss rate — the worst of any window. Thin books, chop |
| 13:30–14:30 | Market resumes direction | Afternoon trends |
| ~15:15 | Hard exit | Before auto-square-off (brokers: 3:12–3:25 PM) and closing chaos |

**Adopted:** our entries already exclude 9:15–9:30 (`ENTRY_START=9:30`) and stop at 14:45. The lunch-lull pause is implemented (`ENTRY_PAUSE_START/END`) but **ships disabled** — paper trading exists to collect data, so we want the midday trades logged too. Enable `11:45`–`13:30` when trading real money, where the loss-rate evidence applies.

## 4. Risk conventions (what the survivors do)

- **1–2% of capital risked per trade**, sized from the stop distance, never the reverse.
- **Minimum 1:2 risk-reward** — "a 70% win rate at 1:1 is barely breakeven after costs".
- **Partial at 1:1 + move stop to cost** is called the single most overlooked rule. (We do this at 1R programmatically.)
- **Max 2–3 trades per day**; stop after 2 consecutive losses; daily loss limit ~3%. The "5th trade of the day" is where discipline dies.
- **Max 2% risk/day aggregate** in some guides; **1% while learning**.
- Costs: a 5-trades/day retail trader pays roughly **₹50,000–₹1.5 lakh/year** in brokerage + STT + GST + slippage — before any profit. Every rupee matters more than every signal.

**Adopted:** we added **`MAX_TRADES_PER_DAY` (default 6)** as a hard entry cap on top of the existing 3% daily loss halt, 6% heat cap, and per-symbol cooldown.

## 5. What they select

- Liquid leaders by **traded value** (not share count), top-volume lists, Open=High/Open=Low scanners.
- Daily ATR ≥ ~1.5% (enough room to reach targets); VIX regime roughly **12–18** for ORB days (too low = no follow-through, too high = chaotic).
- Avoid: penny stocks, illiquid small caps, circuit/ASM names, results-day stocks, huge gaps.

**How we compare:** turnover floor (₹25cr), ATR band (1–6%), RVOL ≥ 1, gap >5% exclusion, NIFTY Total Market top-750 universe. **Implemented:** an India-VIX entry filter (`VIX_FILTER_ENABLED`, default guard 10–25; the practitioner sweet spot is 12–18 — tighten if you like) and a manual results-day workaround (`EXCLUDE_SYMBOLS=TCS,INFY` each morning). Still missing: an automatic results calendar (no data path).

## 6. Side-by-side

| Dimension | Typical Indian trader | This bot |
|---|---|---|
| Entry logic | ORB / VWAP / EMA, discretionary-ish | Mechanical: 7 hard gates, 1m bars |
| Chart timeframe | 15m bias + 5m entries; 1m "for scalpers only" | 1m entries + 15m trend filter (`TRADE_INTERVAL` configurable back to 5m) |
| Timing | No first 15 min; best 9:30–10:30; avoid 11:45–13:30 | Same (implemented) |
| Stop | Structure (ORB end / VWAP) with ATR buffer | Structure (recent low) or 2.5×ATR, floored at 0.75% |
| Target | 1.5–2× risk, anchored to structure | 2× risk (≥1.5% with the stop floor) |
| Profit-taking | Partial 1:1 + breakeven + trail | Partial 1R + breakeven + trailing |
| Sizing | 1–2% risk, often MIS 5× leverage | 2% risk, **no leverage** (paper), vol-targeted |
| Max trades | 2–3/day, stop after 2 losses | `MAX_TRADES_PER_DAY=6`, cooldown per symbol, 3% daily halt |
| Selection | Liquid, ATR, VIX regime | Top-750, turnover/ATR/RVOL filters, gap exclusion |
| Costs | Often ignored → death by a thousand cuts | Fully simulated per trade (₹ line items) |

## 7. The honest gap list

1. **Short side.** Indian guides trade both directions; ORB research attributes most profit to the short leg. We're long-only. **This is the big one — it needs a dedicated strategy build, not a config fix.**
2. ~~VIX regime filter~~ **Done:** `VIX_FILTER_ENABLED` (10–25 default guard, entries-only, fail-open).
3. **Results/earnings calendar.** Named in every "avoid" list. **Workaround in place:** `EXCLUDE_SYMBOLS=TCS,INFY` manual bans; an automatic calendar would need a new data source.
4. **MIS leverage.** Everyone uses it; the data says it mostly multiplies losses. We deliberately don't model it — the paper account trades cash-only.
5. **Reversal setups.** We only do breakout momentum; PDH/PDL and VWAP-bounce reversals are unaddressed — candidates for a second `BaseStrategy` implementation.

## Sources

- SEBI, *Profitability & Trading Behaviour of Individual Traders in Equity Derivatives, FY25–FY26* (Aug 2026) — https://www.sebi.gov.in/sebi_data/attachdocs/aug-2026/1787236407005.pdf
- SEBI, *Study on Profit and Loss of Individual Traders … FY22–FY24* (Sep 2024) — https://www.sebi.gov.in/media-and-notifications/press-releases/sep-2024/updated-sebi-study-reveals-93-of-individual-traders-incurred-losses-in-equity-fando-between-fy22-and-fy24-aggregate-losses-exceed-1-8-lakh-crores-over-three-years_86906.html
- SEBI cash-segment intraday statistics (65–71% loss rate FY20–FY24) as summarised by AlphaVik — https://alphavik.com/learn/intraday-trading
- Sharenox, *Intraday Trading for Beginners — India Guide* (cost tables, Samco 11:45–13:30 62% loss-rate stat, MIS mechanics) — https://www.sharenox.com/blog/Intraday_Trading.html
- Dhanith Trading, *5 Best Intraday Trading Strategies for NSE* (ORB/VWAP/EMA/Bollinger/PDH-PDL rules, max 3 trades/day) — https://www.dhanith.com/blog/best-intraday-trading-strategies
- Dhanith Trading, *How to Trade Intraday Stocks in India* (time-of-day quality table, first-candle rule, 3:15 exit) — https://www.dhanith.com/blog/how-to-trade-intraday-stocks-in-india
- MarketsEasy, *Intraday Strategies That Actually Work in India* (9:15–10:30 window, ADX filter, 1% sizing) — https://marketseasy.in/blog/intraday-trading-strategies-india-2026
- BullSmart, *Intraday Trading Guide — Indicators, VWAP & Time Frames* (timeframe ladder, VWAP with confirmation) — https://blog.bullsmart.in/intraday-trading-vwap-guide-how-to-trade/
- Stoxra, *VWAP Strategies for Beginners India* (VWAP flip, VIX 11–17 regimes, expiry-day behaviour) — https://stoxra.com/blog/vwap-trading-strategy-beginners-india-intraday
- SAHI, *ORB with VWAP & EMA* (three-layer confluence, partial at 1:1) — https://www.sahi.com/blogs/orb-trading-strategy-explained
- Zerodha, *Latest intraday leverages and square-off timings* — https://zerodha.com/marketintel/bulletin/249809/latest-intraday-leverages-mis-bo-co
- Agarwal, Ghosh, Prabhala, Zhao, *Animal Spirits on Steroids: Retail Options Trading in India* — SSRN 5430635
