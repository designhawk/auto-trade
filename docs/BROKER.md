# Broker

Abstract `BrokerClient` (`broker_client.py`) + Groww implementation (`groww_broker.py`, `growwapi` + `pyotp`). **Read-only**: quotes, candles, positions, holdings, LTP. No order methods exist on purpose.

## Interface

`connect() -> bool`, `disconnect()`, `get_quote(symbol) -> Quote(symbol, ltp, volume, bid, ask, timestamp)`, `get_ohlcv(symbol, interval, bars) -> DataFrame[open high low close volume]` (IST index), `get_positions()`, `get_holdings()`, `get_ltp(symbols) -> {symbol: price}`. Swap brokers by implementing this ABC and injecting into `LiveTrader`/`StockSelector`.

## Groww details

* **Auth:** default TOTP — `GROWW_TOTP_TOKEN` (API key) + `GROWW_TOTP_SECRET` → `pyotp.TOTP(secret).now()` → `GrowwAPI.get_access_token(api_key, totp)`. Alt `GrowwBroker(use_api_key=True)` uses `GROWW_API_KEY` + `GROWW_API_SECRET`. `connect()` verifies with `get_holdings_for_user(timeout=5)`; `disconnect()` drops client/feed.
* **Intervals:** `"1m 2m 3m 5m 10m 15m 30m 1h 4h 1d 1w 1mo"` → minutes for `get_historical_candle_data` (`EXCHANGE_NSE`, `SEGMENT_CASH`). Intraday ranges start at 9:15 of the most recent weekday (up to 7 days back); daily+ ranges are `bars × unit` lookback. Returns last `bars` candles, epoch-sec → IST.
* **LTP:** batch `get_ltp` with `NSE_` prefixing, keys stripped back.
* **Resilience:** `@retry_on_error(3, backoff 1s×attempt)` on `get_quote`/`get_ohlcv`. Quote parsing tolerates `None`/missing depth (falls back to LTP). All failures raise `RuntimeError("...: {e}")` — callers (`on_bar`, selector) catch-and-continue per symbol.
* **Doc quirk:** `.env.example` writes `GROWw_*` (lowercase `w`) but code reads `GROWW_*` — env vars are case-sensitive; use uppercase.

Requires `growwapi pyotp pytz pandas requests`. Install: `pip install growwapi pyotp` (or full `requirements.txt`).
