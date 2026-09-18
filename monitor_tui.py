# monitor_tui.py
"""
Full-screen TUI for the trading monitor (Textual).

Panels: system health, portfolio, open positions (with R multiples),
today's signals and trades, and a color-coded log tail.

Keys:
    q  quit        p  pause/resume        r  refresh now

Usage:
    python monitor_tui.py [--interval 5] [--logs 10]
"""

import argparse
import time
from datetime import datetime

from rich.table import Table
from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from monitor import (IST, collect, market_status, _clean_log_lines,
                     _feed_status, _last_tick_time, _pnl_plain, _rupee)


# --------------------------------------------------------------------------
# Pure renderables (unit-testable via rich Console)
# --------------------------------------------------------------------------
def _pnl_style(value) -> str:
    try:
        return "green" if float(value) >= 0 else "red"
    except (TypeError, ValueError):
        return "grey62"


def system_text(data, logs) -> Text:
    out = Text()
    tick = _last_tick_time(logs)
    if tick:
        age = int((datetime.now() - tick).total_seconds())
        style = "green" if age < 150 else ("yellow" if age < 300 else "red")
        out.append("Trader  ", style="grey62")
        out.append(f"last tick {age}s ago", style=style)
    else:
        out.append("Trader  ", style="grey62")
        out.append("no ticks yet", style="grey62")
    out.append("\n")

    out.append("Feed    ", style="grey62")
    out.append(_feed_status())
    out.append("\n")

    status = data.get("status") or {}
    ok = bool(status.get("database_connected"))
    out.append("DB      ", style="grey62")
    out.append("ok" if ok else "MISSING", style="green" if ok else "red")
    out.append("\n")

    today = data.get("today") or {}
    out.append("\n")
    out.append("Signals ", style="grey62")
    out.append(f"{today.get('signals_total', 0)} "
               f"({today.get('signals_approved', 0)} ok / "
               f"{today.get('signals_rejected', 0)} rej)")
    out.append("   Trades ", style="grey62")
    out.append(str(today.get("trades_total", 0)))
    realized = today.get("total_pnl", 0) or 0
    out.append("   Realized ", style="grey62")
    out.append(_pnl_plain(realized), style=_pnl_style(realized))
    return out


def portfolio_text(data) -> Text:
    pf = data.get("portfolio") or {}
    rows = (data.get("positions") or {}).get("positions") or []
    start = pf.get("start_capital") or 0
    value = pf.get("current_value") or 0
    pnl = value - start
    open_pnl = sum((p.get("current_price", 0) - p.get("entry_price", 0))
                   * p.get("qty", 0) for p in rows)

    out = Text()
    out.append("Start ", style="grey62")
    out.append(_rupee(start))
    out.append("   Cash ", style="grey62")
    out.append(_rupee(pf.get("cash")))
    out.append("   In positions ", style="grey62")
    out.append(_rupee(pf.get("position_value")))
    out.append("\n\n")
    out.append("Value ", style="grey62")
    out.append(_rupee(value))
    out.append("\n")
    out.append("Total P&L ", style="grey62")
    out.append(_pnl_plain(pnl), style=_pnl_style(pnl))
    pct = pnl / start * 100 if start else 0
    out.append(f" ({pct:+.2f}%)", style=_pnl_style(pnl))
    out.append("   Open P&L ", style="grey62")
    out.append(_pnl_plain(open_pnl), style=_pnl_style(open_pnl))
    return out


def positions_table(data) -> Table | Text:
    rows = (data.get("positions") or {}).get("positions") or []
    if not rows:
        return Text("(none open)", style="grey62")
    table = Table(expand=True, box=None, pad_edge=False, show_edge=False)
    for name, justify in (("SYMBOL", "left"), ("QTY", "right"), ("ENTRY", "right"),
                          ("LTP", "right"), ("CHG%", "right"), ("P&L", "right"),
                          ("R", "right")):
        table.add_column(name, justify=justify, no_wrap=True)
    for p in rows:
        entry = p.get("entry_price") or 0
        ltp = p.get("current_price") or 0
        qty = p.get("qty") or 0
        chg = ((ltp / entry - 1) * 100) if entry else 0
        pnl = (ltp - entry) * qty
        r = p.get("r_multiple")
        table.add_row(
            str(p.get("symbol", "?")), str(qty), f"{entry:.2f}", f"{ltp:.2f}",
            f"{chg:+.2f}%",
            Text(_pnl_plain(pnl), style=_pnl_style(pnl)),
            f"{r:+.1f}" if isinstance(r, (int, float)) else "-",
        )
    return table


def signals_table(data) -> Table | Text:
    signals = (data.get("today") or {}).get("signals") or []
    if not signals:
        return Text("(none yet today)", style="grey62")
    table = Table(expand=True, box=None, pad_edge=False, show_edge=False)
    table.add_column("TIME", no_wrap=True)
    table.add_column("SYMBOL", no_wrap=True)
    table.add_column("VERDICT", no_wrap=True)
    table.add_column("DETAIL", overflow="ellipsis", no_wrap=True)
    for s in signals[:6]:
        ts = str(s.get("timestamp", ""))[11:19]
        if s.get("approved"):
            verdict = Text("approved", style="green")
            detail = f"qty {s.get('adjusted_qty')}"
        else:
            verdict = Text("rejected", style="grey62")
            detail = str(s.get("rejection_reason") or "")
        table.add_row(ts, str(s.get("symbol", "?")), verdict, detail[:48])
    return table


def trades_table(data) -> Table | Text:
    trades = (data.get("today") or {}).get("trades") or []
    if not trades:
        return Text("(none yet today)", style="grey62")
    table = Table(expand=True, box=None, pad_edge=False, show_edge=False)
    table.add_column("TIME", no_wrap=True)
    table.add_column("SIDE", no_wrap=True)
    table.add_column("SYMBOL", no_wrap=True)
    table.add_column("QTY", justify="right", no_wrap=True)
    table.add_column("PRICE", justify="right", no_wrap=True)
    table.add_column("P&L", justify="right", no_wrap=True)
    table.add_column("REASON", no_wrap=True)
    for t in trades[:6]:
        ts = str(t.get("timestamp", ""))[11:19]
        side = str(t.get("side", "?"))
        pnl = t.get("pnl")
        pnl_cell = (Text(_pnl_plain(pnl), style=_pnl_style(pnl))
                    if side == "SELL" and pnl is not None else Text(""))
        table.add_row(ts,
                      Text(side, style="green" if side == "BUY" else "yellow"),
                      str(t.get("symbol", "?")), str(t.get("qty")),
                      f"{t.get('price') or 0:.2f}", pnl_cell,
                      str(t.get("exit_reason") or ""))
    return table


def log_text(data, lines=10) -> Text:
    out = Text(overflow="fold")
    for line in _clean_log_lines(data.get("logs") or [])[-lines:]:
        style = "grey62"
        if "[ERROR]" in line or "CRITICAL" in line:
            style = "red"
        elif "[WARNING]" in line:
            style = "yellow"
        out.append(line[:240] + "\n", style=style)
    if not out:
        out.append("(no logs found)", style="grey62")
    return out


# --------------------------------------------------------------------------
# Textual app
# --------------------------------------------------------------------------
class MonitorApp(App):
    """Live trading monitor."""

    TITLE = "Auto-Trade Monitor"

    CSS = """
    #top { height: 6; }
    #mid { height: 1fr; }
    #system { width: 1fr; border: round $accent; padding: 0 1; }
    #portfolio { width: 1fr; border: round $accent; padding: 0 1; }
    #positions { width: 3fr; border: round $accent; padding: 0 1; }
    #right { width: 2fr; }
    #signals { height: 1fr; border: round $accent; padding: 0 1; }
    #trades { height: 1fr; border: round $accent; padding: 0 1; }
    #logs { height: 1fr; border: round $accent; padding: 0 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "toggle_pause", "Pause"),
        Binding("r", "refresh_now", "Refresh"),
    ]

    def __init__(self, interval: int = 5, log_lines: int = 10, collect_fn=None):
        super().__init__()
        self.interval = interval
        self.log_lines = log_lines
        self._collect = collect_fn or collect
        self._data = {"api": False, "logs": []}
        self._paused = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top"):
            yield Static(id="system")
            yield Static(id="portfolio")
        with Horizontal(id="mid"):
            yield Static(id="positions")
            with Vertical(id="right"):
                yield Static(id="signals")
                yield Static(id="trades")
        yield Static(id="logs")
        yield Footer()

    def on_mount(self) -> None:
        self._render_all()
        self._tick()  # first fetch immediately
        self.set_interval(self.interval, self._tick)

    # --- data -------------------------------------------------------------
    def _tick(self) -> None:
        if self._paused:
            return
        try:
            self._data = self._collect()
        except Exception as e:  # never crash the UI on a bad poll
            self._data = {"api": False, "logs":
                          [f"[ERROR] monitor collect failed: {e}"]}
        self._render_all()

    def _render_all(self) -> None:
        data = self._data
        logs = data.get("logs") or []
        self.query_one("#system", Static).update(system_text(data, logs))
        self.query_one("#portfolio", Static).update(portfolio_text(data))
        self.query_one("#positions", Static).update(positions_table(data))
        self.query_one("#signals", Static).update(signals_table(data))
        self.query_one("#trades", Static).update(trades_table(data))
        self.query_one("#logs", Static).update(log_text(data, self.log_lines))
        mkt, _ = market_status(datetime.now(IST))
        paused = " | PAUSED" if self._paused else ""
        api = "" if data.get("api") else " | API DOWN"
        self.sub_title = f"market {mkt} | refresh {self.interval}s{paused}{api}"

    # --- actions ----------------------------------------------------------
    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        self._render_all()

    def action_refresh_now(self) -> None:
        self._paused = False
        self._tick()


def main() -> None:
    parser = argparse.ArgumentParser(description="Trading Monitor TUI")
    parser.add_argument("--interval", "-i", type=int, default=5,
                        help="Refresh interval in seconds (default 5)")
    parser.add_argument("--logs", "-n", type=int, default=10,
                        help="Log lines to show (default 10)")
    args = parser.parse_args()
    MonitorApp(interval=args.interval, log_lines=args.logs).run()


if __name__ == "__main__":
    main()
