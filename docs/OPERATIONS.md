# Your Daily Routine (Running the Bot)

## The 2-minute morning start

```bash
python run.py
```

That's the whole job. It starts two things: the **dashboard website** (http://localhost:8002) and the **trader** (the bit that watches prices and pretend-trades). Leave that window open all day. Press `Ctrl+C` in the evening to stop everything.

Want to watch along? Open a second terminal:

```bash
python monitor.py          # live dashboard: cash, open trades, today's profit
python monitor.py --once   # one snapshot, then exit
python logs.py trader -f   # the trader's live diary, line by line
```

## What a normal day looks like (IST)

| Time | The bot... | You... |
|---|---|---|
| ~9:00 | Photocopies yesterday's diary (backup), picks 30 stocks, subscribes to their live price feed | Start `run.py`, get chai |
| 9:15–14:30 | Checks all 30 stocks every 5 min; buys breakouts, manages open trades | Nothing. Seriously — don't touch it. Watching every tick teaches anxiety, not skill. |
| 9:30, 11:00 | Quietly swaps dull stocks for livelier ones | Nothing |
| 14:30–15:20 | Tightens safety nets, stops new entries (14:45), sells down gradually | Start paying attention — this is when the day's result locks in |
| 15:25 | Emergency sell-all if anything remains | Nothing left to do |
| Evening | Writes report card | **This is your real job:** `python report.py` + 10 minutes of review |

## The evening review (the habit that makes you better)

```bash
python report.py                # today
python report.py --date 2026-09-10   # any past day
```

Read in this order: (1) Total P&L — the score. (2) Win rate + profit factor — *how* you scored. (3) By exit reason — *where* the money came from/went. (4) MFE/MAE — what to tune next. (5) Costs — the quiet tax. (6) Rejected signals — what the safety rules caught. One insight per day, written down somewhere, beats any new feature.

## When something looks wrong (troubleshooting for beginners)

| Symptom | Most likely cause | Fix |
|---|---|---|
| Bot exits immediately on start | Wrong/missing Groww keys in `.env` | Re-check token + secret, no extra spaces |
| Dashboard shows `live_prices: false` | Feed unreachable (internet/credentials) | Trading continues on backup data; fix net/keys |
| "No log files found" | Nothing has run yet today | Start `run.py` first |
| Numbers look frozen | Market closed (evenings/weekends/holidays) | Normal — the bot only works 9:15–15:25 on trading days |
| First-ever start crashes | Old diary from an incompatible version | The bot auto-upgrades its database; if truly stuck, rename `trading.db` to reset (you lose history) |
| Python says "no module named X" | Dependencies missing | `pip install -r requirements.txt` again |

## The other commands (rarely needed)

- `python run.py --trader-only` — trader without the dashboard website.
- `python run.py --monitor` — everything plus a live log tail in the same window.
- `python live_trader.py --capital 100000` — run the trader directly with custom pretend capital. (`--live` asks for typed CONFIRM but still only paper-trades — the read-only design guarantees it.)
- `python logs.py [api|trader|all] [-n 50] [-f] [--clear]` — browse or clear old diaries.
- `python -m pytest tests/ -q` — 41 self-tests. Run after any change you make to the code.
- `python stock_selector.py` — tiny demo: ranks 5 famous stocks so you can see scoring work.

## Beginner takeaways

- Your two jobs: start it in the morning, review it in the evening. Everything between is the bot's job — hovering teaches nothing.
- Never edit code mid-day to "fix" a losing day. Change settings in the evening, one at a time, and let paper results judge over weeks.
- Weekends are for learning: re-read one doc file per weekend and one month of reports. That's a genuine trading education, free.
