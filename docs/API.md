# The Dashboard Numbers, Explained

While the bot runs, a small website on your computer (http://localhost:8002) serves live numbers. `python monitor.py` shows the important ones as a text dashboard; the full list below tells you what each page means. Open http://localhost:8002/docs in your browser for clickable versions.

## What to actually look at

| Page | What it tells you | When to check it |
|---|---|---|
| `/today` | **Your morning briefing:** how many ideas, how many approved, how many trades, today's profit | Anytime — this is the one page that matters |
| `/portfolio` | Cash left, value of open trades, number of positions, today's P&L | Mid-day, to see how the day is going |
| `/positions` | Each open trade: what you paid vs what it's worth now | When you're curious "what do I own right now?" |
| `/trades` | Every completed trade with profit/loss | Evening review |
| `/signals` | Every idea including rejected ones + reasons | When learning *why* trades didn't happen |
| `/sessions` | Past days' report cards + all-time totals | Weekly review: "am I improving?" |
| `/status`, `/health` | Is the system alive, is the diary reachable | When something looks stuck |

## One honest label: `live_prices`

On `/portfolio` and `/positions` you'll see `live_prices: true/false`. **True** = values use this-second streaming prices. **False** = the data feed was unreachable, so values use last-known entry prices instead (safer than showing stale numbers as live). If you see `false` during market hours, check your internet/credentials — trading continues regardless.

## Beginner takeaways

- There is no password on this website — it only listens on *your* computer. Never expose it to the internet as-is.
- If a number looks wrong, it's usually a *timing* thing (page cached mid-update), not a bug. Refresh, then check `/today`.
- Errors show up as plain error text, not crashes. When in doubt: `python logs.py trader -f` shows you what the bot is thinking right now.
