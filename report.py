# report.py
"""
Daily trading report.

Reads trading.db (no broker connection needed) and prints a session review:
P&L by exit reason, win rate, MFE/MAE bands, cost totals, sector attribution,
and signal approve/reject breakdown.

Usage:
    python report.py                # today's report
    python report.py --date 2026-09-01
"""

import argparse
from collections import Counter, defaultdict
from datetime import date

from db import get_trades_for_date, get_signals_for_date
from sectors import sector_of


def _fmt_rs(x):
    return f"Rs.{x:,.0f}"


def build_report(day: str) -> str:
    trades = get_trades_for_date(day)
    signals = get_signals_for_date(day)
    buys = [t for t in trades if t.get("side") == "BUY"]
    sells = [t for t in trades if t.get("side") == "SELL"]

    lines = [f"# Trading report - {day}", ""]

    # --- P&L by exit reason ---
    by_exit = defaultdict(lambda: {"n": 0, "pnl": 0.0})
    for t in sells:
        e = by_exit[t.get("exit_reason") or "UNKNOWN"]
        e["n"] += 1
        e["pnl"] += t.get("pnl") or 0
    total_pnl = sum(t.get("pnl") or 0 for t in sells)
    lines.append(f"Trades: {len(buys)} buys / {len(sells)} sells | "
                 f"Total P&L: {_fmt_rs(total_pnl)}")
    lines.append("")
    lines.append("## By exit reason")
    for reason, e in sorted(by_exit.items(), key=lambda kv: -kv[1]["pnl"]):
        lines.append(f"- {reason}: n={e['n']} pnl={_fmt_rs(e['pnl'])}")

    # --- Win rate / payoff ---
    wins = [t for t in sells if (t.get("pnl") or 0) > 0]
    losses = [t for t in sells if (t.get("pnl") or 0) <= 0]
    win_rate = len(wins) / len(sells) * 100 if sells else 0
    avg_win = sum(t.get("pnl") or 0 for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.get("pnl") or 0 for t in losses) / len(losses) if losses else 0
    gross_win = sum(t.get("pnl") or 0 for t in wins)
    gross_loss = abs(sum(t.get("pnl") or 0 for t in losses))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    lines.append("")
    lines.append(f"## Expectancy\n- Win rate: {win_rate:.1f}% ({len(wins)}W/{len(losses)}L)")
    lines.append(f"- Avg win: {_fmt_rs(avg_win)} | Avg loss: {_fmt_rs(avg_loss)}")
    lines.append(f"- Profit factor: {pf:.2f}")

    # --- MFE/MAE bands ---
    mfe_vals = [t["mfe"] for t in sells if t.get("mfe") is not None]
    mae_vals = [t["mae"] for t in sells if t.get("mae") is not None]
    lines.append("")
    lines.append("## MFE / MAE (R multiples)")
    if mfe_vals:
        lines.append(f"- Avg MFE: {sum(mfe_vals) / len(mfe_vals):.2f}R | "
                     f"Avg MAE: {sum(mae_vals) / len(mae_vals):.2f}R")
        reach2 = sum(1 for v in mfe_vals if v >= 2.0) / len(mfe_vals) * 100
        lines.append(f"- Sells reaching 2R MFE: {reach2:.0f}% "
                     f"(targets too far if high but win rate low)")
        stopped_tight = sum(
            1 for t in sells
            if t.get("exit_reason") == "STOP_LOSS"
            and (t.get("mfe") or 0) >= 1.0
        )
        lines.append(f"- Stop-outs that had >=1R MFE: {stopped_tight} "
                     f"(trail too loose if high)")
    else:
        lines.append("- No excursion data (pre-migration trades)")

    # --- Costs ---
    brok = sum((t.get("brokerage") or 0) for t in trades)
    stt = sum((t.get("stt") or 0) for t in trades)
    other = sum((t.get("other_costs") or 0) for t in trades)
    slip = sum((t.get("slippage_cost") or 0) for t in trades)
    lines.append("")
    lines.append(f"## Costs\n- Brokerage: {_fmt_rs(brok)} | STT: {_fmt_rs(stt)} | "
                 f"Other: {_fmt_rs(other)} | Slippage: {_fmt_rs(slip)} | "
                 f"Total: {_fmt_rs(brok + stt + other + slip)}")

    # --- Sector attribution ---
    sec_pnl = defaultdict(float)
    for t in sells:
        sec_pnl[sector_of(t.get("symbol") or "")] += t.get("pnl") or 0
    lines.append("")
    lines.append("## Sector P&L")
    for sec, pnl in sorted(sec_pnl.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {sec}: {_fmt_rs(pnl)}")

    # --- Signals ---
    approved = [s for s in signals if s.get("approved")]
    rejected = [s for s in signals if not s.get("approved")]
    lines.append("")
    lines.append(f"## Signals: {len(signals)} total, "
                 f"{len(approved)} approved, {len(rejected)} rejected")
    rej_reasons = Counter(s.get("rejection_reason") or "?" for s in rejected)
    for reason, n in rej_reasons.most_common(5):
        lines.append(f"- {reason}: {n}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Daily trading report")
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="Session date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    print(build_report(args.date))


if __name__ == "__main__":
    main()
