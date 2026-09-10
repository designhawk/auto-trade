# Architecture

Single-process orchestrator + sidecar API, glued by SQLite.

```
               ┌──────────────┐  OHLCV/LTP/quotes  ┌─────────────┐
               │ GrowwBroker  │◄──────────────────►│ Groww Cloud │
               │(growwapi+TOTP)│                    │  API        │
               └──────┬───────┘                    └─────────────┘
                      │ DataFrame [open high low close volume], IST
        ┌─────────────▼──────────────┐
        │ StockSelector (pre-market) │  daily ×100 bars → momentum score → watchlist (TOP_STOCKS)
        └─────────────┬──────────────┘
                      │ 5m ×50 bars per symbol, every 5 min
        ┌─────────────▼──────────────┐      ┌──────────────┐
        │ IntradayMomentumStrategy   │─Signal→│ RiskManager  │─RiskDecision(qty)→ PaperPortfolio
        │ (BaseStrategy)             │      │ .approve()   │   execute_buy/sell + costs
        └────────────────────────────┘      └──────────────┘         │
                      │ on_bar also checks SL/TP/trailing on opens   │
        ┌─────────────▼──────────────────────────────────────────────▼─┐
        │ db.py (SQLite trading.db): signals / trades / sessions tables │
        └─────────────┬────────────────────────────────────────────────┘
                      │ reads
        ┌─────────────▼──────────────┐      ┌──────────────┐
        │ api.py (FastAPI :8002)     │◄────►│ monitor.py   │ terminal dashboard
        └────────────────────────────┘      └──────────────┘
        run.py spawns api.py + live_trader.py as subprocesses (logs/api.log, logs/trader.log)
        logger.py → logs/{name}_YYYYMMDD.log ; logs.py tails them
```

## Components

| File | Role | Depends on |
|---|---|---|
| `live_trader.py` | `LiveTrader` lifecycle: `pre_market → on_bar loop → force_close_all → end_session`, portfolio valuation, session row | strategy, broker, risk, portfolio, selector, db |
| `base_strategy.py` | `Signal` dataclass + `BaseStrategy` ABC | pandas |
| `intraday_strategy.py` | `IntradayMomentumStrategy` | `BaseStrategy` |
| `stock_selector.py` | `StockSelector` momentum ranker | `GrowwBroker` |
| `risk_manager.py` | `RiskManager` + `RiskDecision` | `Signal` |
| `paper_portfolio.py` | `PaperPortfolio`, `Position`, `Transaction` | `db` (load only) |
| `groww_broker.py` | `GrowwBroker` | `BrokerClient`, `growwapi`, `pyotp` |
| `broker_client.py` | `BrokerClient` ABC + `Quote` | pandas |
| `db.py` | SQLite CRUD + backup/restore | sqlite3 |
| `api.py` | Read-only FastAPI | `db`, `config` |
| `run.py` / `monitor.py` / `logs.py` / `logger.py` | Launcher / dashboard / viewer / logging setup | subprocess, requests |
| `config.py` | `Config` + `NSE_STOCKS` universe | `dotenv` |
| `sectors.py` | `SECTOR_MAP` + `sector_of` (caps + attribution) | — |
| `report.py` | Post-session review from `trading.db` | `db`, `sectors` |
| `feed_manager.py` | Streaming LTP: subscribe/diff/cache/watchdog (sync-poll, fail-open) | `growwapi.GrowwFeed` |
| `instruments.py` | Symbol→token map (disk cache + weekly refresh) | `pandas` |
| `paths.py` | Project-root `DB_PATH`/`LOG_DIR`/`BACKUP_DIR` | `pathlib` |
| `tests/` | pytest suite (temp-DB, broker fakes, pinned clock) | `pytest` |

        ## Data flow (one `on_bar` tick)

1. IST clock + `maybe_reselect()` (09:30/11:00 re-rank).
2. For each open position (5m×50): update MFE/MAE → staged EOD wind-down (≥15:00) → trailing ratchet (tightened after 14:30) → 1R partial + breakeven move → scratch check → SL → TP. Every SELL writes costs + MFE/MAE via `_sell_row`.
3. For each watchlist symbol not held (skip after 14:45 cutoff): fetch `5m×50` + `15m×60` → `generate_signals(df, df_15m)` → `insert_signal` (with approve/reject + `adjusted_qty`) → if approved `execute_buy` → `insert_trade(BUY)` with cost breakdown.
4. `log_portfolio_status()` (cash, count, total, P&L vs initial).

## Key design decisions

* **Broker is read-only by construction.** `BrokerClient` has no order methods; live money can't flow through this code path.
* **SQLite as IPC.** Trader writes, API/monitor read. Simple, but no live position push — API reconstructs positions from `trades`.
* **IST hardcoded.** Market window 9:15–15:25 in `config.py` + `pytz Asia/Kolkata` in trader/broker. Running the host clock in another TZ still works (explicit TZ), but DST-free IST is assumed.
* **Fail-open watchlist.** If selection crashes, trader falls back to `universe[:20]`.
* **Process model is launcher-local.** `run.py --stop/--status` only affect processes spawned by that same `Launcher` instance — not a real supervisor.

## Extension points

* New strategy → subclass `BaseStrategy`, inject into `LiveTrader` (`live_trader.py:627`).
* New broker → implement `BrokerClient` (`broker_client.py`), pass to `LiveTrader`/`StockSelector`.
* New risk rule → add a gate in `RiskManager.approve()` before sizing.
