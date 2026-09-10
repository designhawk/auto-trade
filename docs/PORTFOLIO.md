# Pretend Money, Real Costs (How the Portfolio Works)

The **paper portfolio** is your virtual wallet. It starts with pretend cash (default ₹10,00,000), "buys" and "sells" when told to, and tracks every rupee — including the unglamorous part beginners ignore: **costs**.

## A trade, with all the warts (example)

You buy **10 shares at ₹1,000** (₹10,000 position) and later sell at ₹1,020:

| Line item | Buy | Sell | Why it exists |
|---|---|---|---|
| Share value | ₹10,000 | ₹10,200 | The obvious part |
| Brokerage 0.03% | ₹3.00 | ₹3.06 | Your broker's fee, both sides |
| STT 0.025% | ₹0 | ₹2.55 | Government tax — **sell side only** for intraday |
| Stamp + exchange + SEBI + GST | ~₹3.50 | ~₹3.60 | Tiny fees that add up over hundreds of trades |
| Slippage | ~₹0–4 | ~₹0–4 | You never get exactly the price on screen; the bot rolls dice between 0 and 0.04% against you, like real markets do |
| **You actually pay / receive** | **~₹10,007** | **~₹10,191** | |

Real profit: **~₹184**, not the ₹200 the share prices suggest. Now imagine 200 trades a month — costs quietly eat thousands. *This* is why the report has a Costs section, and why frequent trading is a beginner trap. (Rates follow standard NSE intraday norms — check them against a real broker contract note before trusting absolute rupee figures.)

## How exits work (what happens after you own something)

- **Stop-loss / take-profit:** the two guardrails from the buy plan. Hit either → sell everything in that stock.
- **Half-profit at +1R ("SCALED_1R"):** when profit reaches 1× the original risk, the bot sells **half** and moves the stop-loss to your buying price (**breakeven**). Now the remaining half *cannot lose money*. This single habit smooths results enormously.
- **Trailing stop:** as profit grows past +2%, the safety net ratchets *up* behind the price — locking in gains if the stock turns. After 14:30 it tightens (less time left = less patience).
- **Scratch:** if a trade sits around doing nothing for ~1 hour (12 bars) without reaching even half its risk in profit, the bot sells and moves on. Dead money is usually wrong money.
- **End-of-day wind-down:** from 15:00 the bot sells down gradually; 15:20 everything goes; 15:25 is the emergency backup. You never wake up owning something overnight.

## MFE and MAE — the two most educational numbers

For every closed trade the bot records:

- **MFE (best moment):** how high did profit *ever* reach, in units of your risk? MFE of 2.5R means "at its best, this trade was up two-and-a-half times what you risked."
- **MAE (worst moment):** how deep did it dip against you?

Why beginners should love these: if your winners often touch 3R but you sell at 2R, your targets are too shy. If your stop-outs frequently had +1R of profit first, your safety net is too loose. The report's MFE/MAE section literally tells you how to tune the machine.

## One quirk to know

If you restart the bot mid-day, it rebuilds open positions from its diary — but fine details (like "already took half-profit") are reset to safe defaults. Prefer starting it once in the morning and leaving it alone.
