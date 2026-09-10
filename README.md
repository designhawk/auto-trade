# auto-trade — NSE Intraday Paper Trading Bot

Automated intraday trading system for NSE (India) using Groww market data, a 5-minute momentum breakout strategy, strict risk management, and paper-trade execution with realistic costs. Long-only, intraday-only (no overnight positions).

> **Disclaimer:** Educational project. Not financial advice. Intraday trading in India involves STT, brokerage, slippage, and substantial risk of loss. Paper-trade thoroughly before risking real capital. Order placement via broker API is intentionally disabled — this repo is read-only market data + simulation.

## How it works

```
9:00  pre_market()     → rank ~150-stock universe on daily momentum, pick TOP_STOCKS (default 30)
9:15–15:25 on_bar()    → every 5 min, for each watchlist stock:
                           fetch 5m OHLCV → IntradayMomentumStrategy → Signal
                           → RiskManager.approve() → PaperPortfolio.execute_buy()
                           + check SL / TP / trailing stop on open positions
15:25  force_close_all() → square off everything (no overnight risk)
      end_session()     → write session row to SQLite + backup DB
```

* **Universe:** `config.NSE_STOCKS` (~150 NSE cash symbols, verified against Groww).
* **Selection:** daily-factor rank (percentiled, no hand-scale domination) + same-session gap/activity boost from ONE batched snapshot, sector caps (`sectors.py`), mid-morning re-ranks (09:30/11:00 IST, never evicts held).
* **Data:** `GrowwBroker` (`growwapi` + TOTP auth), IST timezone, retry ×3. Streaming LTP feed (sync-poll, 60s freshness watchdog, REST fallback) + batched day-OHLC snapshots.
* **Strategy:** `IntradayMomentumStrategy` — 20-bar high breakout + 5-bar avg volume + price > 20-EMA + RSI 30–75 + 15m trend alignment + above session VWAP. ATR(14)×1.5 or 5-bar low for SL, 2:1 target, max SL 2.5%, cooldown, `volatility_pct` on every signal.
* **Risk (per signal):** 2% capital at risk scaled by volatility targeting (0.5–1.5×) and confidence (0.5–1×), halved past the soft-throttle line; max 8% per position, max 8 open, 6% portfolio heat cap, daily loss halt 3%, all-time drawdown breaker 10%, ₹2L cash reserve, volatility filter 0.3–4%, min R:R 2.0.
* **Exits:** half at 1R + SL-to-breakeven, trailing (tightened after 14:30), scratch after 12 stagnant bars, staged EOD wind-down from 15:00, square-off 15:20, force-close backstop 15:25.
* **Costs (simulated):** brokerage 0.03% + STT 0.025% sell-only + stamp/exchange/SEBI/GST + sampled adverse slippage — full breakdown stored per trade.
* **Storage:** SQLite `trading.db` — `signals`, `trades` (+MFE/MAE + costs, auto-migrated), `sessions` tables + timestamped `backups/`.
* **Observability:** FastAPI (`:8002`, `live_prices` flags) + terminal `monitor.py` + `report.py` daily review + daily rotating logs in `logs/`.

Docs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/STRATEGY.md`](docs/STRATEGY.md) · [`docs/STOCK_SELECTION.md`](docs/STOCK_SELECTION.md) · [`docs/RISK_MANAGEMENT.md`](docs/RISK_MANAGEMENT.md) · [`docs/PORTFOLIO.md`](docs/PORTFOLIO.md) · [`docs/BROKER.md`](docs/BROKER.md) · [`docs/DATABASE.md`](docs/DATABASE.md) · [`docs/API.md`](docs/API.md) · [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) · [`docs/OPERATIONS.md`](docs/OPERATIONS.md)

## Quick start

Requirements: Python ≥ 3.10, Groww Cloud API credentials (TOTP token + secret).

```bash
pip install -r requirements.txt

cp .env.example .env
# edit .env → GROWW_TOTP_TOKEN, GROWW_TOTP_SECRET, INITIAL_CAPITAL, IS_LIVE=false

python -c "import db; db.init_db()"   # optional, live_trader does this anyway
python run.py                          # API (:8002) + trader
```

Open in separate terminals:

```bash
python monitor.py          # live dashboard (or --follow / --once)
python logs.py trader -f   # tail trader logs
```

FastAPI docs: http://localhost:8002/docs

## Commands

| Command | Description |
|---|---|
| `python run.py` | Start API + trader (default). `Ctrl+C` stops both |
| `python run.py --trader-only` | Trader only, no API |
| `python run.py --monitor` | API + trader + live log follow |
| `python run.py --stop` / `--status` | Stop / status (current process only) |
| `python live_trader.py` | Paper trade directly (`--live` asks for `CONFIRM`, still paper-executes — broker is read-only) |
| `python live_trader.py --capital 1000000` | Override starting capital |
| `python monitor.py [--follow] [--once] [-i 5]` | Terminal dashboard / log tail / snapshot |
| `python report.py [--date YYYY-MM-DD]` | Post-session review (expectancy, MFE/MAE, costs, sectors) |
| `python -m pytest tests/ -q` | Unit suite (22 tests, temp DBs, no broker needed) |
| `python logs.py [api\|trader\|dashboard\|all] [-n 50] [-f] [--clear]` | Log viewer |
| `python -c "import db; db.init_db()"` | Init SQLite tables |
| `python stock_selector.py` | Smoke-test selector on 5 symbols |

## Configuration

All in `.env` → `config.Config` (`config.py`). Key knobs:

| Var | Default (code) | `.env.example` | Meaning |
|---|---|---|---|
| `INITIAL_CAPITAL` | 10,00,000 | 20,00,000 | Starting paper capital (`live_trader.py --capital` overrides) |
| `IS_LIVE` | `false` | `false` | Kept `false` — broker has no order methods |
| `TOP_STOCKS` / `MIN_VOLUME` | 30 / 5,00,000 | — / — | Watchlist size / selector pre-filter |
| `LOOKBACK` / `VOLUME_MULTIPLIER` / `COOLDOWN_BARS` | 20 / 1.5 / 15 | 20 / 1.5 / 10 | Strategy breakout window, volumeGate, per-symbol cooldown |
| `MIN_RISK_REWARD` / `MAX_STOP_LOSS_PCT` | 2.0 / 2.5% | 2.0 / 3% | Enforced in strategy *and* risk manager |
| `MAX_POSITION_PCT` / `MAX_OPEN_POSITIONS` | 8% / 8 | 10% / 10 | Position cap + concurrency cap |
| `DAILY_LOSS_LIMIT_PCT` / `MAX_DRAWDOWN_PCT` | 3% / 10% | 2% / 5% | Daily halt / all-time-peak breaker |
| `MIN_CASH_RESERVE` | 2,00,000 | 1,00,000 | Trading halts below this cash |
| `BROKERAGE_PCT` / `STT_PCT` / `SLIPPAGE_MAX_PCT` | 0.03% / 0.025% sell-only / 0.04% sampled | same | Intraday schedule (+stamp/exchange/SEBI/GST); per-trade breakdown stored |
| `API_PORT` | 8002 | 8002 | FastAPI port |
| `GROWW_TOTP_TOKEN` / `GROWW_TOTP_SECRET` | — (required) | placeholder | TOTP auth (recommended). Alt: `GROWW_API_KEY` + `GROWW_API_SECRET` with `GrowwBroker(use_api_key=True)` |

Market hours are hardcoded IST 9:15–15:25 (`config.py`). DB path `trading.db`, backups in `backups/`. Full reference: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

> Note: code defaults and `.env.example` disagree on a few values (capital, SL, loss limits). `.env` wins at runtime. Align them before sharing results.

## Project structure

```
run.py                Launcher (spawns api.py + live_trader.py, writes logs/api.log, logs/trader.log)
live_trader.py        Orchestrator: pre_market → on_bar loop (5 min) → force_close → end_session
intraday_strategy.py  IntradayMomentumStrategy (BaseStrategy impl, 15m + VWAP gates)
base_strategy.py      Signal dataclass + BaseStrategy ABC (generate_signals, required_bars)
stock_selector.py     Pre-market ranker + intraday re-ranker (percentiled, boosted, capped)
sectors.py            NSE sector map (caps + attribution)
feed_manager.py       Streaming LTP (subscribe/diff/cache/watchdog, fail-open)
instruments.py        Symbol→token map for feed (disk cache + weekly refresh)
risk_manager.py       RiskManager.approve() — 10 gates + vol-targeted sizing
paper_portfolio.py    PaperPortfolio — cash/positions/txn + intraday cost schedule
report.py             Daily review (DB-only: expectancy, MFE/MAE, costs, sectors)
tests/                pytest suite (temp DBs, fake brokers, pinned clock)
groww_broker.py       GrowwBroker (growwapi, TOTP) — quotes, OHLCV, LTP, holdings
broker_client.py      BrokerClient ABC + Quote (swap brokers here)
db.py                 SQLite layer: signals / trades / sessions + backup/restore
api.py                FastAPI read-only API (:8002)
monitor.py            Terminal dashboard (polls API + tails logs)
logs.py / logger.py   Log viewer / get_logger(name) + TradeLogger
config.py             Central config + NSE_STOCKS universe
paths.py              Project-root paths (DB / logs / backups)
```

## API (read-only)

`GET /health /status /signals /trades /positions /portfolio /sessions /today` — e.g. `curl "localhost:8002/today"`. Details + query params in [`docs/API.md`](docs/API.md). Interactive: `/docs`.

## Safety notes

* `.env`, `trading.db`, `backups/*.db`, `logs/` are git-ignored — never commit secrets or trade DBs.
* `GrowwBroker` exposes no order methods; `live_trader --live` only flips a label + confirmation prompt.
* Force-close at 15:25 IST avoids overnight gaps but does not guarantee fill prices.

## Development

```bash
pip install -e ".[dev]"   # pytest, black, ruff
ruff check . && black . && pytest
```

To add a strategy: subclass `BaseStrategy` (`base_strategy.py`), implement `name`, `generate_signals(symbol, df) -> list[Signal]`, `required_bars()`; inject into `LiveTrader` in `live_trader.py`. To swap brokers: implement `BrokerClient` and pass to `LiveTrader`/`StockSelector`.
