# Database

`db.py` — SQLite (`trading.db`, `sqlite3.Row` factory) + `get_db()` context manager. Three tables, created by `init_db()` (auto-run in `LiveTrader.run`):

## Schema

* **`signals`** — every strategy firing: `timestamp, symbol, action, confidence, entry_price, stop_loss, take_profit, reason, approved, rejection_reason, adjusted_qty, strategy`. Indexes on `(symbol)`, `(timestamp)`.
* **`trades`** — paper executions: `timestamp, symbol, side(BUY/SELL), qty, price, value, pnl, pnl_pct, exit_reason, session_id`. Exit reasons: `SIGNAL_ENTRY, STOP_LOSS, TAKE_PROFIT, FORCE_CLOSE_EOD`. Indexes on `(symbol)`, `(timestamp)`.
* **`sessions`** — one row per date (`UNIQUE(date)`): `start/end_capital, total_pnl, total_trades, winning_trades, losing_trades, max_drawdown_pct, sharpe_ratio, notes`. `insert_session` upserts on `date`. `max_drawdown/sharpe` are currently written as `0.0` (placeholders).

## Helpers

`insert_signal/insert_trade/insert_session`, `get_trades_for_date / get_signals_for_date / get_session_summary / get_all_sessions (date DESC)`, `backup_db("backups")` → `trading_YYYYMMDD_HHMMSS.db` (run pre-market + end-session), `restore_db(path)`, `get_backup_list()`. `python db.py` inits tables.

## Notes

* DB file + `backups/` are git-ignored; `trading.db` ships absent — first run creates it.
* Paths are anchored to the project root (`paths.DB_PATH`, `paths.BACKUP_DIR`), not the cwd — launching from any directory uses the same database and backup folder.
* API/monitor are read-only consumers; no migrations — schema changes need manual `DROP`/recreate.
* Session win/loss counting in `end_session` pairs sells to buys by symbol (approximate, not FIFO-matched).
