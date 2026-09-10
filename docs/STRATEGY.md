# How the Bot Decides to Buy (The Strategy, in Plain Words)

The bot follows one classic beginner-friendly idea: **momentum breakout**. In plain English: *when a stock suddenly pushes above the highest price it has touched recently, and lots of people are buying along, it often keeps rising for a while.* The bot tries to ride that short burst and get out quickly.

It does NOT predict the future, read news, or "know" anything. It just checks 7 yes/no conditions every 5 minutes. **All 7 must be yes**, otherwise no trade. That strictness is deliberate — most of the time the answer is "do nothing," which is itself a lesson: good traders wait.

## The 7 checks, translated

Imagine a stock trading around ₹500 at 11 AM:

1. **Breakout — "Is it making a fresh high?"**
   The current price must be above the highest price of the last ~20 five-minute bars (roughly the last hour and a half). A fresh high suggests buyers are in control *right now*.

2. **Volume — "Is the crowd joining in?"**
   The last few minutes must show clearly heavier trading than that stock's recent average (about 1.5×). A price jump *without* volume is often a fake-out — one big order, then nothing. Volume is the crowd confirming the move.

3. **Uptrend — "Is the bigger picture pointing up?"**
   The price must be above its own smoothed 20-period average (EMA). This filters out "dead-cat bounces" — tiny jumps inside a falling stock.

4. **RSI — "Is it energetic but not overheated?" (30–75)**
   RSI is a 0–100 energy meter. Below 30 = lifeless (skip). Above 75 = overheated and likely to snap back (skip). The bot likes the 30–75 middle zone: moving, not manic.

5. **Momentum — "Is this minute still going up?"**
   The latest price must be higher than the previous bar's close. No buying into a stall.

6. **15-minute trend — "Does the bigger chart agree?"**
   The same "price above average" test, but on a slower 15-minute chart. This kills a huge number of false alarms where the 5-minute chart twitches but the real trend is flat or down. (If this data is ever missing, the bot lets the trade through rather than freezing — engineers call this "fail-open.")

7. **Above VWAP — "Am I paying more than the day's fair price?"**
   VWAP is the average price everyone paid today (weighted by volume). The bot only buys *above* it — meaning the stock is genuinely strong today, not just bouncing weakly below average.

Plus one housekeeping rule: **cooldown** — after trading a stock, the bot ignores it for a while so it doesn't keep jumping in and out of the same name.

## What happens the moment all 7 pass?

The bot creates a **signal** — a little plan that says:

- **Entry price:** buy around the current price
- **Stop-loss:** the lower of (a) the lowest price of the last 5 bars, or (b) current price minus 1.5× its normal wiggle-room (ATR). If even that safety net is too wide (more than ~2.5% away), the whole trade is cancelled — too risky.
- **Take-profit:** entry + 2× the risk. Risk ₹2 per share → aim to make ₹4. That's the "1:2 risk-reward" rule.
- **Confidence:** a 0–1 score from volume strength and trend strength. Higher confidence = slightly bigger position (see Risk Management).

Then the signal goes to the safety department (risk manager), which can still say no. A signal is a *proposal*, not an order.

## What the strategy does NOT do (important!)

- **Never sells short** (betting a stock will fall). It only buys rising stocks.
- **Never generates sell signals.** Exits (stop-loss, take-profit, half-profit, scratch, end-of-day) are handled separately — see Operations.
- **Never trades pre-market, after 14:45, or overnight.** No fresh bets late in the day, nothing held while you sleep.

## Beginner takeaways

- Notice how *rare* trades should be: 7 simultaneous conditions is a high bar. If your bot trades 50 times a day, something is misconfigured.
- Every number here (20 bars, 1.5× volume, RSI 30–75, 2:1 reward) is a *choice*, not a law of nature. They're adjustable in `.env` — and the daily report's MFE/MAE section tells you whether they're well chosen.
- Unproven edge, honest scaffolding: this exact recipe has no proven profitability. Treat it as your *first* recipe to test, question, and improve — that's the whole point of the project.
