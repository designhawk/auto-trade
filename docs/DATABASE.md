# Your Trading Diary (The Database, in Plain Words)

Everything the bot thinks and does is written into one file on your computer: **`trading.db`**. No cloud, no accounts, no one else sees it. It has three notebooks inside:

## The three notebooks

1. **`signals` — every idea the bot ever had.**
   Each row: date/time, stock, what it proposed, confidence, entry/stop/target prices, *why* (in readable English!), and whether the safety department approved or rejected it — with the rejection reason. This is gold for learning: filter rejected signals and you'll see exactly which safety rule keeps saving you.

2. **`trades` — every pretend trade actually taken.**
   Buys and sells with quantity, price, profit/loss, *how* it exited (`STOP_LOSS`, `TAKE_PROFIT`, `SCALED_1R` for half-profit, `SCRATCH` for dead trades, `EOD_SCALE`/`FORCE_CLOSE_EOD` for end-of-day), plus best/worst moments (MFE/MAE) and the full cost breakdown. This notebook *is* your track record.

3. **`sessions` — one report card per day.**
   Starting money, ending money, total profit, number of trades, wins vs losses. The daily `report.py` reads mostly from here + trades.

## Backups (automatic)

Before the morning session and after the evening close, the bot photocopies the whole diary into `backups/` with a timestamp. If you ever corrupt the database experimenting, grab yesterday's copy. Old databases upgrade themselves automatically when the bot starts (new columns appear without losing your history).

## Looking at your own data (no coding needed)

The easiest window is the dashboard (`python monitor.py`) and the report (`python report.py`). If you're curious enough to peek inside directly, any free "SQLite browser" app can open `trading.db` — try sorting `trades` by `pnl` to find your best and worst trades, then read their `reason` and `exit_reason` columns. That's a full trading lesson in 5 minutes.

## Beginner takeaways

- Real traders keep journals; yours is automatic. The habit of *reviewing* is what separates learning from gambling — schedule 10 minutes with the report every evening.
- `trading.db`, `backups/`, and `.env` never leave your computer (they're excluded from GitHub). Back them up somewhere safe yourself now and then.
- Files live next to the project no matter which folder you start the bot from — one diary, never two.
