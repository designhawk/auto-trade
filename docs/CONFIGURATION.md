# Configuration

Single source: `.env` → `Config` (`config.py`, `load_dotenv()`). No validation — bad values raise `ValueError` at import/first use.

## Reference

| Var | Code default | Example | Used by |
|---|---|---|---|
| `GROWW_TOTP_TOKEN` / `GROWW_TOTP_SECRET` | `""` (required) | placeholder | `GrowwBroker._get_access_token` (TOTP path) |
| `GROWW_API_KEY` / `GROWW_API_SECRET` | `""` | commented | `GrowwBroker(use_api_key=True)` only |
| `INITIAL_CAPITAL` | 10,00,000 | 20,00,000 | `live_trader --capital` default; `RiskManager`, `PaperPortfolio`, `/portfolio` fallback |
| `IS_LIVE` | `false` | `false` | label only — no live execution exists |
| `TOP_STOCKS` / `MIN_VOLUME` | 30 / 5,00,000 | — | selector (`MIN_VOLUME` currently unused — floor is 2L hardcoded) |
| `LOOKBACK` / `VOLUME_MULTIPLIER` / `COOLDOWN_BARS` | 20 / 1.5 / 15 | 20 / 1.5 / 10 | **not wired to strategy** (constructed with defaults 20/1.2/10) — only effective if you pass them in `live_trader.py:627` |
| `MIN_RISK_REWARD` / `MAX_STOP_LOSS_PCT` | 2.0 / 2.5% | 2.0 / 3% | strategy reject + risk gate (strategy uses its own copies) |
| `MAX_POSITION_PCT` / `MAX_OPEN_POSITIONS` | 8% / 8 | 10% / 10 | `RiskManager` (2%-risk sizing capped by position %) |
| `DAILY_LOSS_LIMIT_PCT` / `MAX_DRAWDOWN_PCT` | 3% / 10% | 2% / 5% | daily halt / all-time breaker |
| `MIN_CASH_RESERVE` | 2,00,000 | 1,00,000 | cash gate |
| `BROKERAGE_PCT` / `STT_PCT` / `SLIPPAGE_PCT` | 0.03% / 0.025% / 0.02% | same | `PaperPortfolio` defaults (trader doesn't forward config values) |
| `API_PORT` / `DASHBOARD_PORT` | 8002 / 8501 | 8002 / 8501 | `API_PORT` unused by `api.py` (hardcoded 8002); dashboard port unused (no Streamlit app — `requirements/pyproject` list it but no code uses it) |
| Market hours | 9:15–15:25 hardcoded | — | `config.MARKET_*` + `live_trader.run` loop (300s sleep, force-close ≥15:25) |
| `DB_PATH` / `BACKUP_DIR` | `trading.db` / `backups` | — | `db.py` (env can't override) |
| `NSE_STOCKS` | ~150 symbols hardcoded | — | selector universe |

## Setup

```bash
cp .env.example .env   # then fill uppercase GROWW_TOTP_TOKEN / GROWW_TOTP_SECRET
```

Keep `.env` git-ignored (it is).
