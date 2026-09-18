# monitor.py
"""
Live Trading Monitor.

Terminal dashboard: portfolio, open positions (with R multiples), today's
signals and trades, feed/tick health, and recent logs.

Reads the local API (http://localhost:8002) plus log files. No Groww calls.

Usage:
    python monitor.py                  # dashboard, refresh every 5s
    python monitor.py --interval 2     # faster refresh
    python monitor.py --once           # single snapshot, then exit
    python monitor.py --follow         # raw log tail only
    python monitor.py --logs 12        # log lines on the dashboard
    python monitor.py --no-color       # plain text (also NO_COLOR=1)
"""

import argparse
import os
import re
import time
from datetime import datetime

import requests

from paths import LOG_DIR

try:
    import pytz

    IST = pytz.timezone("Asia/Kolkata")
except ImportError:  # pragma: no cover - pytz is a hard dependency in practice
    IST = None

API = "http://localhost:8002"
WIDTH = 78


# --------------------------------------------------------------------------
# Colors
# --------------------------------------------------------------------------
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    GREY = "\033[90m"


_COLOR = True


def _paint(code: str, text) -> str:
    if not _COLOR:
        return str(text)
    return f"{code}{text}{C.RESET}"


def _enable_ansi() -> bool:
    """Enable ANSI escape processing on Windows terminals."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        k = ctypes.windll.kernel32
        handle = k.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if not k.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(k.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


# --------------------------------------------------------------------------
# Small formatting helpers
# --------------------------------------------------------------------------
def _rupee(x) -> str:
    try:
        return f"Rs.{x:,.0f}"
    except (TypeError, ValueError):
        return "-"


def _pnl_plain(value, suffix="") -> str:
    try:
        return f"{float(value):+,.0f}{suffix}"
    except (TypeError, ValueError):
        return "-"


def _pnl(value, suffix="") -> str:
    text = _pnl_plain(value, suffix)
    if text == "-":
        return text
    if not _COLOR:
        return text
    return _paint(C.GREEN if float(value) >= 0 else C.RED, text)


def _pnl_field(value, width=10) -> str:
    """Right-aligned P&L field: pad first, then color (keeps columns lined up)."""
    text = f"{_pnl_plain(value):>{width}}"
    if text.strip() == "-":
        return text
    if not _COLOR:
        return text
    return _paint(C.GREEN if float(value) >= 0 else C.RED, text)


def market_status(now=None):
    """(label, is_trading) for the given IST datetime (default: now)."""
    now = now or datetime.now(IST)
    if now.weekday() >= 5:
        return "WEEKEND", False
    hm = (now.hour, now.minute)
    if hm < (9, 15):
        return "PRE-OPEN", False
    if hm >= (15, 30):
        return "CLOSED", False
    if hm >= (15, 25):
        return "SQUARE-OFF", True
    return "OPEN", True


# --------------------------------------------------------------------------
# Logs
# --------------------------------------------------------------------------
_NOISE = re.compile(r"Processed \d+/\d+ stocks|\[SELECTOR\] Evaluating")
_TS = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")


def _candidate_logs():
    """All runnable log files, newest first (launcher + logger output)."""
    files = list(LOG_DIR.glob("live_trader_*.log"))
    files += [LOG_DIR / "trader.log", LOG_DIR / "api.log"]
    files = [f for f in files if f.exists()]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files


def _trade_logs():
    """Trader logs first (newest first); api.log only as a last resort.

    api.log is written on every monitor poll, so a plain mtime sort would
    always pick it and hide the trader's activity.
    """
    files = list(LOG_DIR.glob("live_trader_*.log")) + [LOG_DIR / "trader.log"]
    files = [f for f in files if f.exists()]
    if files:
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return files
    api = LOG_DIR / "api.log"
    return [api] if api.exists() else []


def _tail_lines(n=600):
    """Last n raw lines of the freshest trader log file."""
    files = _trade_logs()
    if not files:
        return []
    try:
        with open(files[0], "r", encoding="utf-8", errors="replace") as f:
            return [l.rstrip() for l in f.readlines()[-n:]]
    except OSError:
        return []


def _clean_log_lines(lines):
    """Drop progress noise and blanks."""
    return [l for l in lines if l.strip() and not _NOISE.search(l)]


def get_recent_logs(lines=15):
    """Recent (noise-filtered) log lines from the freshest log file."""
    return _clean_log_lines(_tail_lines())[-lines:]


def _last_tick_time(logs):
    """Timestamp of the last ON-BAR/Market-check line, or None."""
    for line in reversed(logs):
        if "ON-BAR" in line or "Market check:" in line:
            m = _TS.search(line)
            if m:
                try:
                    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return None
    return None


def _feed_symbols():
    """Last '[FEED] Streaming N symbols' count across trader logs, or None.

    The launch-time feed print lands in trader.log while most activity goes
    to the dated logger file, so scan every trader log.
    """
    for path in _trade_logs():
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in reversed(f.readlines()[-400:]):
                    m = re.search(r"\[FEED\] Streaming (\d+) symbols", line)
                    if m:
                        return int(m.group(1))
        except OSError:
            continue
    return None


def _colored_log_line(line):
    if "[ERROR]" in line or "CRITICAL" in line:
        return _paint(C.RED, line)
    if "[WARNING]" in line:
        return _paint(C.YELLOW, line)
    return _paint(C.GREY, line)


def follow_logs():
    """Follow the freshest log in real-time (raw tail)."""
    log_files = _candidate_logs()
    if not log_files:
        print("No log files found")
        return
    log_file = log_files[0]
    last_size = 0
    print(f"Following {log_file.name} (Ctrl+C to exit)")
    while True:
        try:
            if log_file.exists():
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    if size < last_size:
                        last_size = 0
                    if size > last_size:
                        f.seek(last_size)
                        new_lines = f.readlines()
                        last_size = f.tell()
                        for line in new_lines:
                            print(line.rstrip())
            time.sleep(1)
        except KeyboardInterrupt:
            break


# --------------------------------------------------------------------------
# API access
# --------------------------------------------------------------------------
def _fetch(path, **params):
    try:
        r = requests.get(f"{API}{path}", params=params, timeout=2)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def collect():
    """Snapshot of everything the dashboard shows."""
    logs = _tail_lines()
    if _fetch("/health") is None:
        return {"api": False, "logs": logs}
    today = datetime.now(IST).strftime("%Y-%m-%d")
    return {
        "api": True,
        "status": _fetch("/status"),
        "portfolio": _fetch("/portfolio"),
        "positions": _fetch("/positions"),
        "today": _fetch("/today"),
        "trades": _fetch("/trades", date=today, limit=500),
        "logs": logs,
    }


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
def _render_positions(positions_data):
    lines = []
    rows = (positions_data or {}).get("positions") or []
    if not rows:
        lines.append("   (none open)")
        return lines
    lines.append(
        f"   {'SYMBOL':<12} {'QTY':>5} {'ENTRY':>9} {'LTP':>9} "
        f"{'CHG%':>7} {'P&L':>10} {'R':>6}"
    )
    for p in rows:
        entry = p.get("entry_price") or 0
        ltp = p.get("current_price") or 0
        qty = p.get("qty") or 0
        chg = ((ltp / entry - 1) * 100) if entry else 0
        pnl = (ltp - entry) * qty
        r = p.get("r_multiple")
        r_txt = f"{r:+.1f}" if isinstance(r, (int, float)) else "-"
        lines.append(
            f"   {p.get('symbol', '?'):<12} {qty:>5} {entry:>9.2f} {ltp:>9.2f} "
            f"{chg:>+6.2f}% {_pnl_field(pnl)} {r_txt:>6}"
        )
    return lines


def _render_signals(today_data):
    lines = []
    signals = (today_data or {}).get("signals") or []
    if not signals:
        lines.append("   (none yet today)")
        return lines
    for s in signals[:5]:
        ts = str(s.get("timestamp", ""))[11:19]
        sym = str(s.get("symbol", "?"))
        if s.get("approved"):
            verdict = _paint(C.GREEN, "approved")
            detail = f"qty {s.get('adjusted_qty')}"
        else:
            verdict = _paint(C.GREY, "rejected")
            detail = str(s.get("rejection_reason") or "")[:44]
        lines.append(f"   {ts}  {sym:<12} {verdict}  {detail}")
    return lines


def _render_trades(today_data):
    lines = []
    trades = (today_data or {}).get("trades") or []
    if not trades:
        lines.append("   (none yet today)")
        return lines
    for t in trades[:5]:
        ts = str(t.get("timestamp", ""))[11:19]
        sym = str(t.get("symbol", "?"))
        side = str(t.get("side", "?"))
        qty = t.get("qty")
        price = t.get("price") or 0
        reason = str(t.get("exit_reason") or "")
        pnl = t.get("pnl")
        pnl_txt = _pnl(pnl) if side == "SELL" and pnl is not None else ""
        lines.append(
            f"   {ts}  {side:<4} {sym:<12} x{qty:<5} @ {price:>8.2f}  "
            f"{pnl_txt}  {reason}"
        )
    return lines


def render(data, log_lines=8):
    """Render the dashboard to a string."""
    now = datetime.now(IST)
    mkt, is_open = market_status(now)
    out = ["=" * WIDTH]
    out.append(f" AUTO-TRADE MONITOR    {now.strftime('%Y-%m-%d %H:%M:%S')}    "
               f"MARKET: {mkt}")
    out.append("=" * WIDTH)

    logs = data.get("logs") or []

    if not data.get("api"):
        out.append(_paint(C.RED, " API DOWN") +
                   "  - is the bot running?  (python run.py)")
        out.append("")
        out.append(f" Recent log  ({_candidate_logs()[0].name if _candidate_logs() else 'none'})")
        for line in _clean_log_lines(logs)[-10:]:
            out.append("   " + _colored_log_line(line[:WIDTH - 4]))
        out.append("=" * WIDTH)
        return "\n".join(out)

    status = data.get("status") or {}
    pf = data.get("portfolio") or {}
    positions_data = data.get("positions") or {}
    today_data = data.get("today") or {}
    trades_data = data.get("trades") or {}
    rows = positions_data.get("positions") or []

    # --- SYSTEM ---------------------------------------------------------
    tick = _last_tick_time(logs)
    tick_txt = "no ticks yet"
    tick_color = C.GREY
    if tick:
        age = int((datetime.now() - tick).total_seconds())
        tick_txt = f"last tick {age}s ago"
        tick_color = C.GREEN if age < 150 else C.YELLOW
        if age >= 300 and is_open:
            tick_color = C.RED
    feed_n = _feed_symbols()
    if feed_n is not None:
        feed_txt = f"streaming {feed_n} symbols"
    elif rows and positions_data.get("live_prices"):
        feed_txt = "live prices ON"
    elif rows:
        feed_txt = "REST fallback (feed idle)"
    else:
        feed_txt = "idle (no positions)"
    db_txt = "ok" if status.get("database_connected") else "MISSING"
    out.append(" SYSTEM")
    out.append(f"   Trader: {_paint(tick_color, tick_txt)}    "
               f"Feed: {feed_txt}    DB: {db_txt}")

    # --- PORTFOLIO ------------------------------------------------------
    start = pf.get("start_capital") or 0
    value = pf.get("current_value") or 0
    pnl = value - start
    open_pnl = sum((p.get("current_price", 0) - p.get("entry_price", 0)) * p.get("qty", 0)
                   for p in rows)
    out.append("")
    out.append(" PORTFOLIO (paper)")
    out.append(f"   Start {_rupee(start)}   Cash {_rupee(pf.get('cash'))}   "
               f"In positions {_rupee(pf.get('position_value'))}")
    out.append(f"   Value {_rupee(value)}   "
               f"Total P&L {_pnl(pnl)} ({_pnl(pnl / start * 100 if start else 0, '%')})   "
               f"Open P&L {_pnl(open_pnl)}")

    # --- POSITIONS ------------------------------------------------------
    out.append("")
    out.append(f" POSITIONS ({len(rows)})")
    out.extend(_render_positions(positions_data))

    # --- TODAY ----------------------------------------------------------
    buys = today_data.get("trades_buy", 0)
    sells = today_data.get("trades_sell", 0)
    trade_rows = trades_data.get("trades") or []
    sell_rows = [t for t in trade_rows if t.get("side") == "SELL"
                 and t.get("pnl") is not None]
    wins = sum(1 for t in sell_rows if (t.get("pnl") or 0) > 0)
    losses = len(sell_rows) - wins
    realized = today_data.get("total_pnl", 0)
    out.append("")
    out.append(" TODAY")
    out.append(f"   Signals {today_data.get('signals_total', 0)} "
               f"({today_data.get('signals_approved', 0)} approved / "
               f"{today_data.get('signals_rejected', 0)} rejected)   "
               f"Trades {today_data.get('trades_total', 0)} "
               f"({buys} buys / {sells} sells)")
    out.append(f"   Realized P&L {_pnl(realized)}   "
               f"Closed {wins}W/{losses}L")

    # --- RECENT SIGNALS / TRADES ---------------------------------------
    out.append("")
    out.append(" RECENT SIGNALS")
    out.extend(_render_signals(today_data))
    out.append("")
    out.append(" RECENT TRADES")
    out.extend(_render_trades(today_data))

    # --- LOG ------------------------------------------------------------
    out.append("")
    log_name = _trade_logs()[0].name if _trade_logs() else "none"
    out.append(f" LOG  ({log_name}, newest last, noise filtered)")
    for line in _clean_log_lines(logs)[-log_lines:]:
        out.append("   " + _colored_log_line(line[:WIDTH - 4]))

    out.append("=" * WIDTH)
    out.append(" Ctrl+C to exit    --once for a snapshot    --follow for raw tail")
    return "\n".join(out)


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Trading Monitor")
    parser.add_argument("--follow", "-f", action="store_true",
                        help="Follow raw logs (no dashboard)")
    parser.add_argument("--once", "-1", action="store_true",
                        help="Show one snapshot and exit")
    parser.add_argument("--interval", "-i", type=int, default=5,
                        help="Refresh interval in seconds (default 5)")
    parser.add_argument("--logs", "-n", type=int, default=8,
                        help="Log lines on the dashboard (default 8)")
    parser.add_argument("--no-color", action="store_true",
                        help="Disable ANSI colors")
    args = parser.parse_args()

    global _COLOR
    if args.no_color or os.environ.get("NO_COLOR"):
        _COLOR = False
    else:
        _COLOR = _enable_ansi()

    if args.follow:
        follow_logs()
        return

    while True:
        data = collect()
        output = render(data, log_lines=args.logs)
        if args.once:
            print(output)
            break
        clear_screen()
        print(output)
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nExiting...")
            break


if __name__ == "__main__":
    main()
