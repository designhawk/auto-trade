# Operations

## Launcher — `run.py`

`Launcher` spawns `api.py` → `logs/api.log` and `live_trader.py` → `logs/trader.log` (`CREATE_NEW_PROCESS_GROUP` on Windows).

* `python run.py` — API, wait 2s, trader; block until `Ctrl+C` → terminate/kill.
* `python run.py --trader-only` — trader only, skips the API.
* `python run.py --monitor` — API + trader, then `monitor.py --follow` in foreground; stops both on exit.
* `--stop/--status` — only affect the current `Launcher`'s dict (fresh each invocation, so effectively no-ops across runs). To stop, `Ctrl+C` the launcher or kill PIDs; to inspect, use `monitor.py` / `http://localhost:8002/status`.

## Trading loop — `live_trader.py`

`python live_trader.py [--live] [--capital N]`. `--live` prompts `CONFIRM` but execution stays paper (broker is read-only). Flow: `init_db → broker.connect (exit 1 on fail) → insert opening session row → pre_market → 5-min loop while IST < 15:25 → force_close_all → end_session → disconnect`. `KeyboardInterrupt`/exception also force-closes first.

## Monitor — `monitor.py`

Polls `localhost:8002/health` + `/portfolio` and tails the most recently modified of `logs/live_trader_*.log`, `logs/trader.log`, `logs/api.log` — covering both launcher runs and direct runs. Modes: default refresh `-i 5`s, `--once`, `--follow` (raw tail).

## Logs — `logger.py` + `logs.py`

`get_logger(name)` → console + `logs/{name}_YYYYMMDD.log` (`[ts] [level] [name] msg`), handler-deduped. `TradeLogger` formats signal/trade/portfolio lines. View: `python logs.py [api|trader|dashboard|all] [-n 50] [-f] [--clear]` (targets `logs/{component}.log`, i.e. launcher files — use `monitor.py` for dated trader logs). `logs/` is git-ignored.

## Backups

`backup_db()` copies `trading.db` → `backups/trading_YYYYMMDD_HHMMSS.db` pre-market and end-session. Restore: `db.restore_db(path)` / list via `get_backup_list()`. `backups/` is git-ignored since the `.gitignore` fix — old clones may still carry committed DBs; purge if needed.
