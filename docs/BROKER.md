# Where Live Prices Come From (Groww, in Plain Words)

The bot needs live prices to think with. It gets them from **Groww** (a real Indian stockbroker) through their official developer pipe (API). Two things to understand deeply:

**1. It can only LOOK, never TOUCH.** The connection is deliberately read-only: prices, charts, holdings — yes. Placing orders — the code for that doesn't even exist here. Even the scary-sounding `--live` flag only changes a label. Your real Groww money cannot be spent by this project. That's a design choice, not an accident.

**2. You need free API credentials.** In your Groww account settings there's a Cloud API Keys page. The recommended login uses a **TOTP token + secret** (the same rotating-code idea as Google Authenticator — it never expires, unlike the API-key method which needs daily approval). You paste these into your `.env` file once. Never share that file — it's your account's key.

## The three ways prices arrive (and why three)

| Pipe | What it does | Beginner analogy |
|---|---|---|
| **Candle history** (the workhorse) | Downloads past price charts: every 5-minute bar, 15-minute bar, or daily bar for a stock | Ordering yesterday's newspapers to study |
| **LTP batch** (the quick check) | "What are these 30 stocks worth *right now*?" — one request, up to 50 answers | One phone call asking 30 prices |
| **Streaming feed** (the live wire) | Stays subscribed to your watchlist and receives price ticks as they happen | A ticker tape running on your desk |

The bot prefers the live wire, but with a strict rule: ticks must be **fresh** (under ~60 seconds old). Stale wire? It silently falls back to quick-check calls. A dead internet connection degrades the bot to slower data — it never freezes or hallucinates prices. Subscriptions follow your watchlist automatically (morning list + mid-morning swaps), and everything unsubscribes cleanly on shutdown.

One technical footnote you'll appreciate later: the exchange identifies stocks by **numbers** (tokens like `2885`), not names like RELIANCE. A small cached map translates between them, refreshed weekly — you never touch it.

## Limits (why the bot is polite)

Groww allows ~300 data requests per minute. The bot's busiest moment uses ~70, mornings ~210 spread over minutes. Well within limits — it will never get your key banned. Price charts come with per-request history caps (e.g., 30 days of 5-minute bars), and the bot's requests sit comfortably inside them.

## Beginner takeaways

- If prices ever look "stuck," the cause is almost always credentials (expired/typo'd key) or no internet — check those before anything exotic.
- The read-only design is your safety blanket. Any trading bot you *ever* run with real money should earn this level of paranoia first.
- Requires `growwapi pyotp pytz pandas requests` — all installed automatically by `pip install -r requirements.txt`.
