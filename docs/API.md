# API

`api.py` — read-only FastAPI observability layer over `trading.db`. Run: `python api.py` (serves `:8002` regardless of `API_PORT`; banner says `:8000` — stale). Interactive docs: `http://localhost:8002/docs`. CORS open. No auth — bind to localhost / firewall.

| Endpoint | Params | Returns |
|---|---|---|
| `GET /health` | — | `{status, timestamp, version}` |
| `GET /status` | — | running flag (db exists), db_connected, latest_session, today's signal/trade counts, total_sessions |
| `GET /signals` | `limit=50, approved_only=false, date=YYYY-MM-DD` | `{count, signals[]}` newest-first |
| `GET /trades` | `limit=50, date?, symbol?` | `{count, total_pnl, winning_trades, trades[]}` |
| `GET /positions` | — | today's BUY symbols, deduped (entry price as current — **stale by design**) |
| `GET /portfolio` | — | start_capital (latest session), cash (= start − ΣBUY + ΣSELL), position_value at **entry** prices, today's P&L/trades; `win_rate/max_drawdown/sharpe` hardcoded 0 |
| `GET /sessions` | `limit=30` | `{count, total_pnl_all_sessions, total_trades_all_sessions, sessions[]}` |
| `GET /today` | — | signal approve/reject split, buy/sell split, total P&L, last 10 signals + trades |

## Caveats

* Valuations (`/positions`, `/portfolio`) use stored entry prices, not live LTP — the lazy `get_broker()` helper is defined but never called. For live values, use `PaperPortfolio.get_portfolio_value(broker.get_ltp(...))` in-process.
* `/positions` shows symbols with any BUY today even if fully sold (no netting); `/portfolio` nets via `HAVING symbol NOT IN (SELL)` so partial sells drop the symbol entirely.
* Errors → HTTP 500 with raw exception text.
