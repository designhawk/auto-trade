# Broker

Abstract `BrokerClient` (`broker_client.py`) + Groww implementation (`groww_broker.py`, `growwapi` + `pyotp`). **Read-only**: quotes, candles, positions, holdings, LTP. No order methods exist on purpose.

## Interface

`connect() -> bool`, `disconnect()`, `get_quote(symbol) -> Quote(symbol, ltp, volume, bid, ask, timestamp)`, `get_ohlcv(symbol, interval, bars) -> DataFrame[open high low close volume]` (IST index), `get_positions()`, `get_holdings()`, `get_ltp(symbols) -> {symbol: price}`. Swap brokers by implementing this ABC and injecting into `LiveTrader`/`StockSelector`.

## Groww details

* **Auth:** default TOTP — `GROWW_TOTP_TOKEN` (API key) + `GROWW_TOTP_SECRET` → `pyotp.TOTP(secret).now()` → `GrowwAPI.get_access_token(api_key, totp)`. Alt `GrowwBroker(use_api_key=True)` uses `GROWW_API_KEY` + `GROWW_API_SECRET`. `connect()` verifies with `get_holdings_for_user(timeout=5)`; `disconnect()` drops client/feed. Token endpoint is limited to 150 requests/24h — we authenticate once per process.
* **Candles:** `get_historical_candles` (the older `get_historical_candle_data` is deprecated upstream) with `groww_symbol="NSE-<SYMBOL>"` and `CANDLE_INTERVAL_*` constants (`"1m 2m 3m 5m 10m 15m 30m 1h 4h 1d 1w 1mo"` all supported — verified against the installed SDK). Per-request windows: 1–5m → 30d, 10/15/30m → 90d, 1h+ → 180d; our fetches (≤2d intraday, 100 daily bars) sit well inside. New rows are `[iso_timestamp, o, h, l, c, vol, oi?]` (IST wall time); `candles_to_df()` also accepts legacy epoch rows. Intraday ranges start at 9:15 of the most recent weekday (up to 7 days back); daily+ ranges are `bars × unit` lookback. Returns last `bars` candles, IST-indexed.
* **LTP:** batch `get_ltp` with `NSE_` prefixing, keys stripped back, auto-chunked at the 50-symbol API cap.
* **Quote:** `last_price/volume/bid_price/offer_price/depth{buy,sell:[{price,quantity}]}`. Parser tolerates missing `depth` and empty books (falls back to LTP).
* **Rate limits (Live Data: 10/s, 300/min):** worst tick is ~70 calls (positions + 30×(5m+15m) + LTP batch); pre-market ~210 sequential calls — comfortably inside. No client-side throttle; `@retry_on_error(3, backoff 1s×attempt)` on quote/candles.
* **Resilience:** all failures raise `RuntimeError("...: {e}")` — callers (`on_bar`, selector) catch-and-continue per symbol.
* **Untapped:** `get_ohlc` batch day-snapshot (could replace 30 session-boost candle calls with 1) and websocket `Feed` (1000 subs) — future optimizations, not wired.

Requires `growwapi pyotp pytz pandas requests`. Install: `pip install growwapi pyotp` (or full `requirements.txt`).
