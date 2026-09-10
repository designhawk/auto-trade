# auto-trade — Learn Intraday Trading With a Paper-Trading Bot (NSE)

A robot that **pretends to trade** Indian stocks (NSE) during market hours so you can learn how intraday trading works — **without risking a single rupee**. It uses live market prices, follows a fixed set of rules, and keeps a full diary of everything it did so you can review and learn.

> **Please read this first:** This is a learning tool, **not financial advice**, and it has **not been proven to make money**. Intraday trading is risky — most beginners lose money doing it for real. This bot only *simulates* trades (called **paper trading**). It cannot place real orders, even if you ask it to.

## What does it actually do?

Think of it as a very disciplined trainee trader that works for you every market day:

- **Morning (~9:00):** It looks at ~150 large Indian stocks and picks the ~30 showing the strongest recent momentum (rising price + healthy trading activity).
- **During market hours (9:15–15:25):** Every 5 minutes it checks each picked stock. If a stock suddenly jumps above its recent highest price *with strong volume* and passes 6 more safety checks, the bot "buys" it with virtual money.
- **After buying:** It watches the stock. If the price falls to a pre-decided danger level (**stop-loss**), it sells to limit the damage. If it rises to the profit goal (**take-profit**), it sells and banks the virtual profit. It also takes half-profit midway and gives up on stocks that go nowhere (**scratch**).
- **End of day (15:00–15:25):** It sells everything. It never holds stocks overnight, so a bad overnight news event can never hurt it.
- **After market close:** It writes you a **report card** — profit/loss, win rate, costs paid, what worked and what didn't.

All of this is recorded in a small database file on your computer, and you can watch it live on a dashboard or read the daily report.

## Quick words you'll see everywhere (mini-glossary)

| Word | What it means |
|---|---|
| **Paper trading** | Pretend trading with virtual money but real prices. Mistakes cost you nothing. |
| **P&L** | Profit & Loss — how much money you made or lost. |
| **Stop-loss (SL)** | A pre-decided price where you sell to stop a small loss becoming a big one. Example: buy at ₹100, stop-loss at ₹98 = you risk ₹2 per share. |
| **Take-profit (TP)** | A pre-decided price where you sell to lock in profit. |
| **Risk-reward (R:R)** | Comparing what you risk vs what you aim to gain. Risk ₹2 to make ₹4 = 1:2. This bot wants at least 1:2. |
| **Brokerage / STT / slippage** | The unavoidable costs of trading: broker's fee, government tax, and the tiny price difference between what you see and what you get. They eat into profits on every trade. |
| **VWAP** | The day's average traded price (weighted by volume). Think of it as the "fair price so far today" — buying above it means paying more than average. |
| **RSI / ATR / EMA** | Standard chart indicators: RSI = is the stock overheated or cold; ATR = how much it normally wiggles (volatility); EMA = the smoothed trend direction. |
| **Drawdown** | How far your money has fallen from its highest point. A 10% drawdown on ₹10L = you're down to ₹9L. |
| **Cooldown** | After the bot trades a stock once, it waits a while before trading it again (avoids over-trading the same name). |

## A day in the life of the bot

| Time (IST) | What happens | What it means for you |
|---|---|---|
| ~9:00 | Picks the 30 most promising stocks | Your watchlist for the day is ready |
| 9:15 | Market opens, checking starts | Nothing for you to do — just watch if you like |
| 9:30, 11:00 | Re-checks the list, swaps out dull stocks | The bot adapts to how the morning actually played out |
| 14:30 | Tightens safety nets on open trades | Late-day caution: less time left to recover |
| 14:45 | Stops opening new trades | No last-minute gambles |
| 15:00–15:20 | Gradually sells everything | Goes home flat, no overnight risk |
| 15:25 | Emergency sell-all (backup) | Guarantees nothing is held overnight |
| After close | Writes your report card | Read it with `python report.py` |

## Getting started

You need: a computer with **Python 3.10 or newer**, and free **Groww API credentials** (used only to *read* live prices — the bot cannot trade with them).

```bash
pip install -r requirements.txt

cp .env.example .env
# open .env in any text editor and fill in your Groww details
# (GROWW_TOTP_TOKEN and GROWW_TOTP_SECRET)

python run.py
```

That's it — the bot starts its website (for the dashboard) and the trader. In other terminals you can run:

| Command | What it does |
|---|---|
| `python run.py` | Start everything (website + trader). Press `Ctrl+C` to stop. |
| `python monitor.py` | Live text dashboard — cash, open trades, today's profit. |
| `python logs.py trader -f` | Watch the trader's diary in real time. |
| `python report.py` | Yesterday's/today's report card (profit, win rate, costs, lessons). |
| `python -m pytest tests/ -q` | Self-check: 41 automated tests proving the parts work. |

Dashboard in your browser: http://localhost:8002/docs

## The honest money talk

- **Costs are real, even on paper.** Every pretend trade pays pretend brokerage, taxes, and slippage — exactly to teach you that frequent trading bleeds money. Read any report's "Costs" section and notice how much of the gross profit they eat.
- **Defaults assume ₹10–20 lakh capital** with up to 8 open trades. Don't compare its rupee profits to your own savings — compare *percentages* and *win rate*.
- **Capital protection rules are strict on purpose:** it risks ~2% per trade, stops the day at −3%, and refuses to trade if total open risk crosses 6%. These numbers exist to teach you the #1 beginner lesson: *surviving matters more than winning*.
- **Past paper profit ≠ future real profit.** Prices here are real, but pretend fills are always kinder than real ones (no queues, no market impact, no emotions).

## How your money is protected (the short version)

Full detail in [`docs/RISK_MANAGEMENT.md`](docs/RISK_MANAGEMENT.md). The 10-second version: no single trade can lose more than ~2%, no day can lose more than 3%, the whole account halts at a 10% fall from its peak, and at least ₹2 lakh cash is always kept aside untouched.

## Where to read next

Written for learners, start anywhere:

- [`docs/STRATEGY.md`](docs/STRATEGY.md) — what makes the bot buy, in plain words
- [`docs/STOCK_SELECTION.md`](docs/STOCK_SELECTION.md) — how it picks the morning list
- [`docs/RISK_MANAGEMENT.md`](docs/RISK_MANAGEMENT.md) — the 10 safety rules with rupee examples
- [`docs/PORTFOLIO.md`](docs/PORTFOLIO.md) — how pretend money, costs, and profit-taking work
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — your daily routine: commands, timeline, report
- [`docs/BROKER.md`](docs/BROKER.md) — how live prices arrive (Groww connection + data feed)
- [`docs/DATABASE.md`](docs/DATABASE.md) — your trading diary: what's recorded and where
- [`docs/API.md`](docs/API.md) — what each dashboard number means
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — every setting explained ("if I change X, what happens?")
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the big picture: how the parts fit together

## Safety notes (boring but important)

- Your secret `.env` file, the database, and backups are never uploaded to GitHub (they're in `.gitignore`). Never share your `.env` with anyone.
- The bot has **no ability to place real orders** — the broker connection is read-only by design.
- This repo is MIT-licensed (free to learn from and reuse), but that license covers the *code*, not trading outcomes. There are no warranties — see `LICENSE`.
