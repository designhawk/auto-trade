# How the Bot Picks Stocks Every Morning

You can't watch 150 stocks at once — so every morning the bot narrows ~150 large NSE stocks down to a **watchlist of ~30**, then spends the day watching only those. Think of it as a morning shortlist, like a cricket selector picking the match-day squad.

## Step 1: Grade every stock on 5 subjects (daily charts)

Using the last ~100 days of daily prices, each stock gets graded on:

| Subject (weight) | Plain meaning |
|---|---|
| Price vs trend, 30% | Is it trading above its own 20-day average? Above = healthy. |
| RSI energy, 20% | Best marks near RSI 60 (strong but not crazy); punished if overheated (>70) or lifeless (<30). |
| Volume, 15% | Is unusually heavy trading accompanying the move? |
| 5-day return, 20% | Has it actually been going up this week? |
| Trend shape, 15% | Is the short average above the longer average (uptrend shape)? |

Two instant disqualifiers, no matter the grades: **too jumpy or too sleepy** (daily wiggle outside 0.3–4%), and **too thinly traded** (under ~2 lakh shares/day average — beginners should avoid illiquid stocks where you can't exit cleanly).

Clever bit: instead of fixed pass marks, stocks are graded **on a curve** (percentile ranks). If the whole market is sleepy one morning, the *relatively* best still float up — no single factor can dominate just because its numbers run hot.

## Step 2: Adjust for *this* morning (gap + early activity)

Daily grades describe yesterday. So for the top ~60 candidates, the bot takes one fresh snapshot of *today* (a single batched request, not 60 separate ones) and adjusts scores ±15%:

- **Overnight gap:** opened 2% higher than yesterday's close? Small bonus — the market already likes it today. Opened sharply lower? Small penalty — don't catch a falling knife with a long-only strategy.
- **Early activity:** how much of a normal day's price range is already used up, relative to its typical wiggle. A stock that's already moving with purpose scores higher than one that's flat.

If the morning data is missing (before the open, API hiccup), scores stay unchanged — a missing reading never disqualifies a stock.

## Step 3: Don't put all eggs in one basket (sector caps)

Even if 10 banks top the list, the bot takes at most **3 per sector**. Ten bank stocks aren't ten independent bets — one bad banking headline sinks all of them together. Diversification is forced, not suggested.

## Step 4: Re-check at 9:30 and 11:00 (the mid-morning reality check)

The morning list is a prediction; the market is the answer. Twice mid-morning the bot re-scores the watchlist on live 5-minute action (distance from VWAP, fresh trend, live volume, RSI) and swaps dull names for livelier reserves. **One golden rule: stocks you already own are never evicted** — re-ranking only changes *future* entries, never disturbs open trades.

## Beginner takeaways

- Selection is about *where to look*, not *what will win*. A great list with a bad exit plan still loses money.
- Watch the daily report's sector section: if one sector keeps winning, the market is telling you something about regimes.
- The 09:30 re-rank exists because the first 15 minutes of the Indian market are notoriously noisy — beginners lose a lot of money trading the open. The bot mostly watches it.
