# The Big Picture (How the Parts Fit Together)

If the other docs are chapters, this is the map on the inside cover. No code knowledge needed — just follow the journey of a single trading day.

## The one-paragraph version

Prices flow in from Groww through three pipes (history charts, quick price checks, live feed). Each morning the **selector** picks 30 stocks. All day, the **trader** asks the **strategy** "should we buy?", the **risk manager** "are we allowed?", and the **portfolio** executes with pretend money while tracking every cost. Everything is written to the **diary** (database), which the **dashboard**, **monitor**, and **report** read back to you. The **launcher** just starts the trader + dashboard together.

## The journey of one trading day, step by step

```
Morning                        All day, every 5 min              Evening
───────                        ───────────────────              ───────
Groww prices ──► SELECTOR ──► watchlist of 30 ──► TRADER ──► sells everything
   (charts)       (grades +       (the squad)        │          (15:00–15:25)
   feed on                             ┌─────────────┴──────────────┐
                                       │  per stock: STRATEGY says  │
                                       │  "buy?" → RISK says        │
                                       │  "allowed?" → PORTFOLIO    │
                                       │  pretend-buys, watches     │
                                       │  stops/targets/partials    │
                                       └─────────────┬──────────────┘
                                                     ▼
                                              DIARY (trading.db)
                                              signals · trades · sessions
                                                     │
                    ┌────────────────────────────────┼───────────────────┐
                    ▼                                ▼                   ▼
              DASHBOARD website               MONITOR terminal      REPORT card
              (watch it live)                 (quick glance)        (learn tonight)
```

## The cast (who does what)

| Part | Job in one line | If it breaks... |
|---|---|---|
| **Launcher** (`run.py`) | Starts the trader + website together | Start pieces manually (`api.py`, `live_trader.py`) |
| **Trader** (`live_trader.py`) | The conductor: morning prep, 5-min loop, evening shutdown | Nothing trades — check logs first |
| **Selector** (`stock_selector.py`) | Picks the 30-stock squad + mid-morning swaps | Falls back to a default list, keeps going |
| **Strategy** (`intraday_strategy.py`) | Proposes buys (7 strict checks) | No signals = quiet day, usually correct |
| **Risk manager** (`risk_manager.py`) | Vetoes anything dangerous (10 gates) | Rejections logged with reasons — read them |
| **Portfolio** (`paper_portfolio.py`) | Pretend wallet + costs + exits | Restart rebuilds from diary (safe defaults) |
| **Broker link** (`groww_broker.py`) | Fetches prices; streaming feed with REST fallback | Degrades to slower data, never freezes |
| **Diary** (`db.py` → `trading.db`) | Remembers everything, backs itself up | Restore from `backups/` |
| **Dashboard/API** (`api.py`) | Website of live numbers | Trader keeps working without it |
| **Monitor / Logs** | Terminal views into the diary | Cosmetic only — data is safe |
| **Report** (`report.py`) | Evening report card | Re-run anytime; reads diary only |
| **Config / Sectors / Paths** | Settings, sector map, file locations | Wrong settings = strange behavior; check `.env` |

## Design choices worth knowing (and why)

- **Read-only broker, always.** There is deliberately no code that can spend real money. Safety by absence, not by flag.
- **One diary, many readers.** Trader writes; dashboard/monitor/report only read. They can never corrupt trading.
- **Fail-open data, fail-closed money.** Missing price data → skip gracefully and keep going. Risky trade proposal → rejected by default. The system is optimistic about *information* and pessimistic about *money*.
- **No overnight positions, ever.** Three layered exits (gradual → square-off → emergency) because overnight gaps are how beginners get destroyed.
- **Everything local.** No cloud, no accounts, no subscriptions. Your data never leaves your computer.

## Beginner takeaways

- When confused, ask "which cast member owns this?" — every symptom traces to one row in the table above.
- The architecture's lesson mirrors trading's lesson: boring reliability (backups, fallbacks, halts) beats cleverness. This bot is 20% strategy, 80% plumbing — and so is real trading success.
