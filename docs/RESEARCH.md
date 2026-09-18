# What the Research Says (and What We Changed Because of It)

We read the public evidence on intraday trading — academic papers, multi-year Indian backtests, and SEBI's own studies — and applied the findings to the bot's **stock selection and entry rules**. This file records what the evidence actually says, what we changed, and what we deliberately left alone. Paper-trading reports from *this* bot remain the final judge — research only sets a better starting point.

Not financial advice.

## Finding 1: which stocks you trade matters more than anything else

**Zarattini, Barbon & Aziz (2024)**, *A Profitable Day Trading Strategy For The U.S. Equity Market* (Swiss Finance Institute Research Paper 24-98, 7,000+ stocks, 2016–2023):

| Variant | Total return | Annual | Sharpe | Hit rate | Max DD |
|---|---|---|---|---|---|
| Opening-range breakout, all stocks | +29% | 3.2% | 0.48 | 41% | -8% |
| Same strategy, only **"stocks in play"** (relative volume ≥ 100%, top 20) | **+1,637%** | **41.6%** | **2.81** | 48% | -12% |

The entry/exit rules were identical — the *only* difference was stock selection. Per trade: below-average opening volume earned **-0.02R**; above-average earned **+0.08R** (net of commissions).

**Changed:** the mid-morning re-rank now gates on relative volume — `MIN_RVOL=1.0` (recent volume must be at least the recent average). Below-average activity removes the stock from consideration entirely.

## Finding 2: the opening range is where Indian intraday edges are documented

- **Intraday Lab's 8-year Nifty study** (2,122 trades, 2017–2026): a mechanical 30-minute opening-range breakout ran at 48.7% win rate, profit factor 1.23, Sharpe 1.16, +91.6% total, worst drawdown -11.2% — *before costs* (expect 15–25% lower after brokerage/STT/slippage). 8 of 9 years profitable; the one losing year was a sideways, low-volatility year.
- Their filters: **skip large opening gaps** (>0.8% on the index — they distort the opening range), skip tiny opening ranges, prefer wide-range days.
- **DailyBulls (2025)** tested four Nifty ORB exit variants: ATR-based stops *destroyed* the edge (stops placed inside the noise), while the structural stop (opening-range low) plus a fixed target produced the best average R.
- Both Indian and US studies agree: breakouts work best in **volatile, directional** markets and bleed in choppy, low-volatility ones.

**Changed:**
1. **No fresh entries in the first 15 minutes** (`ENTRY_START` 9:30): the false-breakout zone the ORB filters are designed around.
2. **Extreme gaps excluded** (`MAX_GAP_PCT=5`): news/circuit-sized openings make unreliable ranges and poor fills.
3. **Daily movement floor raised to 1% ATR** (`MIN_DAILY_ATR_PCT`): a breakouts-of-sleepy-stocks strategy can't reach its targets; the old 0.3% floor let too much dead weight through (cap 6% to avoid chaos names).

## Finding 3: liquidity in rupees, not share counts

Practitioner screens (BottomStreet, Groww, NSE screener guides) converge on: high traded **value**, daily ATR around 1.5%+, price above ₹50 (no penny stocks), and avoiding illiquid small caps, results-day names and circuit/ban lists.

**Changed:** the old "2 lakh shares" floor was meaningless across price scales (₹2 stock = ₹40L traded; ₹3,000 stock = ₹600cr). Replaced with a **median daily turnover floor of ₹25 crore** (`MIN_TURNOVER_CR`) — the rupee measure of "can I get out without slippage".

## Finding 4: costs and overtrading are the real enemy (SEBI, Sept 2024)

SEBI's official study of every individual F&O trader on NSE (FY22–FY24):

- **93% of individual traders lost money**; combined net losses **₹1.81 lakh crore**.
- **Transaction costs were ~28% of total losses** — brokerage, STT, GST, exchange fees.
- Losses grew with trading frequency; only 7.2% were profitable over three years.
- The profitable cohorts skew heavily toward **algorithmic/automated** execution.

**What this validates in our design:** the bot already simulates the full intraday cost schedule on every trade, caps daily losses at 3%, halts at 10% drawdown, uses a 6% portfolio heat cap, and trades rarely by construction (7 simultaneous entry conditions). The evening report's Costs section exists precisely because the research says costs, not bad luck, is what kills retail accounts.

## What we deliberately did NOT adopt

| Idea | Why not (yet) |
|---|---|
| Short selling | Indian ORB studies attribute ~75% of profits to the short side. Our bot is long-only — this is the single biggest known gap vs the literature. Would need a short-capable strategy, broker short mechanics, and different risk math. |
| A literal opening-range strategy | The bot uses a rolling high breakout. Rebuilding signals around the 9:15–9:45 range is a re-architecture worth doing as a *separate* strategy (the `BaseStrategy` interface exists for exactly this) — but only with a backtest, not blind. |
| OI buildup, delivery %, results-day calendar | These need data sources not wired through the Groww API here. High-value next candidates. |
| Avoiding 12:30–13:30 "lunch lull" | Supported by one Indian paper; would cut a large share of opportunities. Revisit when our own MFE/MAE data shows the lunch-hour trades actually underperform. |
| Parameter optimization / ML | Overfitting risk on a small sample. The report's MFE/MAE bands are our honest feedback loop; change one knob at a time. |
| Intraday sector-leadership rotation | Requires sector-momentum data computed live; our static sector caps are the cheap version. |

## The one-line summary

Evidence says: **trade only stocks in play, avoid the open's noise, avoid huge gaps, respect costs, and expect modest edges.** The code now does all five; the long-only constraint and missing short side remain the honest gap to close next.

## Sources

- Zarattini, Barbon & Aziz (2024), *A Profitable Day Trading Strategy For The U.S. Equity Market* — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284 (PDF: https://concretumgroup.com/wp-content/uploads/2026/02/A-Profitable-Day-Trading-Strategy-For-The-U.S.-Equity-Market.pdf)
- Zarattini & Aziz (2023), *Can Day Trading Really Be Profitable? Evidence from ORB Day Trading* — SSRN 4416622
- QuantConnect, *Opening Range Breakout for Stocks in Play* (replication + parameter sensitivity) — https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/
- Intraday Lab, *Nifty 50 ORB 8-year backtest* — https://intradaylab.com/blog/nifty-orb-breakout-strategy-backtest
- DailyBulls, *ORB variants backtest (2025)* — https://dailybulls.in/orb-intraday-trading-strategy-backtest/
- CastleGate/AlphaQ, *A Rules-Based ORB Strategy for Indian Equities* — https://alphaq.wizzer.in/t/from-chaos-to-code-a-rules-based-opening-range-breakout-strategy-for-indian-equities/18
- SEBI (Sept 2024), *Analysis of Profits & Losses in the Equity Derivatives Segment (FY22–FY24)* — https://www.sebi.gov.in/media-and-notifications/press-releases/sep-2024/updated-sebi-study-reveals-93-of-individual-traders-incurred-losses-in-equity-fando-between-fy22-and-fy24-aggregate-losses-exceed-1-8-lakh-crores-over-three-years_86906.html
- BottomStreet, *Best Intraday Screener Parameters NSE* — https://bottomstreet.com/guides/best-intraday-screener-parameters-nse/
- IJCRT, *Profitability Without Complexity: Bank Nifty scalping* (time-of-day filters) — https://www.ijcrt.org/papers/IJCRT2504775.pdf
