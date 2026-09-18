# monitor_tui.py
"""
Full-screen TUI for the trading monitor (Textual).

Layout:
    - Three always-visible panels: SYSTEM (trader/feed/DB/watchlist),
      PORTFOLIO (money), REGIME (clock rules: entries, VIX, trade cap).
    - Tabs: Live Log (streaming trader log, colorized), Positions, Signals,
      Trades, Watchlist.
    - Footer keybindings.

Keys:
    q  quit      p  pause data (log keeps streaming)
    r  refresh   c  clear log panel

Usage:
    python monitor_tui.py [--interval 5] [--log-lines 800]
"""

import argparse
import json
import re
from datetime import datetime

from rich.text import Text

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import (DataTable, Footer, Header, RichLog, Static,
                             TabbedContent, TabPane)

from monitor import (IST, collect, _clean_log_lines, _feed_status,
                     _last_tick_time, _pnl_plain, _rupee, _trade_logs)
from paths import LOG_DIR
from sectors import sector_of

_VIX_RE = re.compile(r"India VIX: ([\d.]+) \(([^)]+)\)")


# --------------------------------------------------------------------------
# Small helpers (unit-testable)
# --------------------------------------------------------------------------
def _pnl_style(value) -> str:
    try:
        return "green" if float(value) >= 0 else "red"
    except (TypeError, ValueError):
        return "grey62"


def _line_style(line: str) -> str:
    if "[ERROR]" in line or "CRITICAL" in line:
        return "red"
    if "[WARNING]" in line:
        return "yellow"
    if "SIGNAL" in line or "TRADE EXECUTED" in line:
        return "bold cyan"
    if "RESELECT" in line or "Selected" in line:
        return "magenta"
    return "grey70"


def _last_vix(logs) -> tuple:
    """(value, note) from the trader log, or (None, None)."""
    for line in reversed(logs or []):
        m = _VIX_RE.search(line)
        if m:
            try:
                return float(m.group(1)), m.group(2)
            except ValueError:
                return None, None
    return None, None


def _entry_state(now) -> str:
    """Human state of the entry window from config + clock."""
    try:
        from config import config

        hm = (now.hour, now.minute)
        if hm < (config.ENTRY_START_HOUR, config.ENTRY_START_MINUTE):
            return f"opens {config.ENTRY_START_HOUR}:{config.ENTRY_START_MINUTE:02d}"
        if hm >= (config.ENTRY_CUTOFF_HOUR, config.ENTRY_CUTOFF_MINUTE):
            return f"closed ({config.ENTRY_CUTOFF_HOUR}:{config.ENTRY_CUTOFF_MINUTE:02d} cutoff)"
        pause_on = (0, 0) < config.ENTRY_PAUSE_START < config.ENTRY_PAUSE_END
        if pause_on and config.ENTRY_PAUSE_START <= hm < config.ENTRY_PAUSE_END:
            return "PAUSED (lunch lull)"
        return "OPEN"
    except Exception:
        return "?"


def system_text(data) -> Text:
    out = Text()
    logs = data.get("logs") or []
    tick = _last_tick_time(logs)
    if tick:
        age = int((datetime.now() - tick).total_seconds())
        style = "green" if age < 150 else ("yellow" if age < 300 else "red")
        out.append("Trader     ", style="grey62")
        out.append(f"last tick {age}s ago\n", style=style)
    else:
        out.append("Trader     ", style="grey62")
        out.append("no ticks yet\n", style="grey62")
    out.append("Feed       ", style="grey62")
    out.append(_feed_status() + "\n")
    status = data.get("status") or {}
    ok = bool(status.get("database_connected")) or data.get("api")
    out.append("Database   ", style="grey62")
    out.append(("ok" if ok else "MISSING") + "\n", style="green" if ok else "red")
    wl = data.get("watchlist") or {}
    out.append("Watchlist  ", style="grey62")
    if wl.get("symbols"):
        updated = str(wl.get("updated", ""))
        stale = bool(updated) and updated[:10] != datetime.now().strftime("%Y-%m-%d")
        note = "  (STALE)" if stale else f"  (updated {updated[11:19]})"
        out.append(f"{wl.get('count', len(wl['symbols']))} names{note}\n",
                   style="yellow" if stale else "white")
    else:
        out.append("not published yet\n", style="grey62")
    out.append("API        ", style="grey62")
    out.append(("up" if data.get("api") else "DOWN") + "\n",
               style="green" if data.get("api") else "red")
    return out


def portfolio_text(data) -> Text:
    pf = data.get("portfolio") or {}
    rows = (data.get("positions") or {}).get("positions") or []
    start = pf.get("start_capital") or 0
    value = pf.get("current_value") or start
    pnl = value - start
    open_pnl = sum((p.get("current_price", 0) - p.get("entry_price", 0))
                   * p.get("qty", 0) for p in rows)

    out = Text()
    for label, val in (("Start", _rupee(start)), ("Cash", _rupee(pf.get("cash"))),
                       ("In positions", _rupee(pf.get("position_value"))),
                       ("Value", _rupee(value))):
        out.append(f"{label:<13}", style="grey62")
        out.append(val + "\n")
    out.append(f"{'Total P&L':<13}", style="grey62")
    pct = pnl / start * 100 if start else 0
    out.append(_pnl_plain(pnl), style=_pnl_style(pnl))
    out.append(f" ({pct:+.2f}%)   ", style=_pnl_style(pnl))
    out.append("Open ", style="grey62")
    out.append(_pnl_plain(open_pnl) + "\n", style=_pnl_style(open_pnl))
    return out


def regime_text(data) -> Text:
    now = datetime.now(IST)
    vix, note = _last_vix(data.get("logs") or [])
    trades = (data.get("today") or {}).get("trades") or []
    buys = sum(1 for t in trades if t.get("side") == "BUY")
    cap = "?"
    try:
        from config import config

        cap = config.MAX_TRADES_PER_DAY or "unlimited"
    except Exception:
        pass

    out = Text()
    out.append(f"{'Entries':<13}", style="grey62")
    out.append(_entry_state(now) + "\n")
    out.append(f"{'India VIX':<13}", style="grey62")
    if vix is not None:
        style = "green" if note == "ok" else "yellow"
        out.append(f"{vix:.2f} ({note})\n", style=style)
    else:
        out.append("unknown (fail-open)\n", style="grey62")
    out.append(f"{'Trade cap':<13}", style="grey62")
    out.append(f"{buys} / {cap} used today\n")
    out.append(f"{'Market':<13}", style="grey62")
    out.append(now.strftime("%H:%M:%S IST") + "\n")
    if data.get("watchlist") and data["watchlist"].get("strategy"):
        out.append(f"{'Strategy':<13}", style="grey62")
        out.append(str(data["watchlist"]["strategy"]) + "\n")
    return out


# --------------------------------------------------------------------------
# Incremental log tailer
# --------------------------------------------------------------------------
class LogTailer:
    """Streams appended lines from the freshest trader log file."""

    def __init__(self, seed_lines: int = 40):
        self.seed_lines = seed_lines
        self._path = None
        self._fh = None
        self._pos = 0
        self._size = 0

    def _pick(self):
        trader = LOG_DIR / "trader.log"  # launcher mode
        if trader.exists():
            return trader
        dated = sorted(LOG_DIR.glob("live_trader_*.log"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        return dated[0] if dated else None

    def _open(self, path, seed=False):
        self._close()
        self._path = path
        self._fh = open(path, "r", encoding="utf-8", errors="replace")
        if seed:
            lines = self._fh.readlines()[-self.seed_lines:]
            self._pos = self._fh.tell()
            return [l.rstrip() for l in lines]
        self._fh.seek(0, 2)
        self._pos = self._fh.tell()
        return []

    def _close(self):
        if self._fh:
            try:
                self._fh.close()
            except OSError:
                pass
        self._fh = None

    def read_new(self):
        """Return newly appended lines (seeding the last N on first open)."""
        path = self._pick()
        if path is None:
            return []
        try:
            if self._path != path:
                return self._open(path, seed=True)
            size = path.stat().st_size
            if size < self._pos:  # truncated (new run overwrote the file)
                return self._open(path, seed=True)
            self._fh.seek(self._pos)
            lines = self._fh.readlines()
            self._pos = self._fh.tell()
            return [l.rstrip() for l in lines]
        except OSError:
            return []

    def close(self):
        self._close()


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
class MonitorApp(App):
    TITLE = "Auto-Trade Monitor"

    CSS = """
    #top { height: 9; }
    #system { width: 1fr; border: round $accent; padding: 0 1; }
    #portfolio { width: 1fr; border: round $accent; padding: 0 1; }
    #regime { width: 1fr; border: round $accent; padding: 0 1; }
    TabbedContent { height: 1fr; }
    DataTable { height: 1fr; }
    RichLog { height: 1fr; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "toggle_pause", "Pause data"),
        Binding("r", "refresh_now", "Refresh"),
        Binding("c", "clear_log", "Clear log"),
    ]

    def __init__(self, interval: int = 5, log_lines: int = 800, collect_fn=None):
        super().__init__()
        self.interval = interval
        self.log_lines = log_lines
        self._collect = collect_fn or collect
        self._data = {"api": False, "logs": []}
        self._paused = False
        self._tailer = LogTailer()

    # --- layout -----------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top"):
            yield Static(id="system")
            yield Static(id="portfolio")
            yield Static(id="regime")
        with TabbedContent(initial="tab-logs"):
            with TabPane("Live Log", id="tab-logs"):
                yield RichLog(id="log", max_lines=self.log_lines, wrap=True,
                              markup=False, highlight=False)
            with TabPane("Positions", id="tab-pos"):
                yield DataTable(id="positions", zebra_stripes=True)
            with TabPane("Signals", id="tab-sig"):
                yield DataTable(id="signals", zebra_stripes=True)
            with TabPane("Trades", id="tab-trades"):
                yield DataTable(id="trades", zebra_stripes=True)
            with TabPane("Watchlist", id="tab-watch"):
                yield DataTable(id="watchlist", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        for wid, title in (("#system", "SYSTEM"), ("#portfolio", "PORTFOLIO"),
                           ("#regime", "REGIME")):
            self.query_one(wid).border_title = title
        self.query_one("#positions", DataTable).add_columns(
            "SYMBOL", "QTY", "ENTRY", "LTP", "CHG%", "P&L", "R")
        self.query_one("#signals", DataTable).add_columns(
            "TIME", "SYMBOL", "VERDICT", "DETAIL")
        self.query_one("#trades", DataTable).add_columns(
            "TIME", "SIDE", "SYMBOL", "QTY", "PRICE", "P&L", "REASON")
        self.query_one("#watchlist", DataTable).add_columns("SYMBOL", "SECTOR")

        self._apply_data(self._data)
        self.set_interval(0.5, self._pump_logs)
        self.set_interval(self.interval, self._schedule_collect)
        self._schedule_collect()
        self.query_one("#log", RichLog).write(
            Text("monitor started - trader log streams below", style="bold cyan"))

    def on_unmount(self) -> None:
        self._tailer.close()

    # --- log streaming ----------------------------------------------------
    def _pump_logs(self) -> None:
        log = self.query_one("#log", RichLog)
        for line in self._tailer.read_new():
            if "Processed " in line and "/" in line:
                continue  # selector progress noise
            log.write(Text(line, style=_line_style(line)))

    # --- data collection (worker thread; never blocks the UI) -------------
    @work(thread=True, exclusive=True)
    def _schedule_collect(self) -> None:
        if self._paused:
            return
        try:
            data = self._collect()
        except Exception as e:
            self.call_from_thread(self._log_event, f"collect failed: {e}", "red")
            return
        self.call_from_thread(self._apply_data, data)

    def _log_event(self, message: str, style: str = "yellow") -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.query_one("#log", RichLog).write(
            Text(f"[monitor {stamp}] {message}", style=style))

    # --- rendering --------------------------------------------------------
    def _apply_data(self, data) -> None:
        self._data = data
        logs = data.get("logs") or []
        self.query_one("#system", Static).update(system_text(data))
        self.query_one("#portfolio", Static).update(portfolio_text(data))
        self.query_one("#regime", Static).update(regime_text(data))

        # positions
        table = self.query_one("#positions", DataTable)
        table.clear()
        for p in (data.get("positions") or {}).get("positions") or []:
            entry = p.get("entry_price") or 0
            ltp = p.get("current_price") or 0
            qty = p.get("qty") or 0
            chg = ((ltp / entry - 1) * 100) if entry else 0
            pnl = (ltp - entry) * qty
            r = p.get("r_multiple")
            table.add_row(
                str(p.get("symbol", "?")), str(qty), f"{entry:.2f}",
                f"{ltp:.2f}", f"{chg:+.2f}%",
                Text(_pnl_plain(pnl), style=_pnl_style(pnl)),
                f"{r:+.1f}" if isinstance(r, (int, float)) else "-")

        # signals
        table = self.query_one("#signals", DataTable)
        table.clear()
        for s in (data.get("today") or {}).get("signals") or []:
            approved = bool(s.get("approved"))
            verdict = (Text("approved", style="green") if approved
                       else Text("rejected", style="grey62"))
            detail = (f"qty {s.get('adjusted_qty')}" if approved
                      else str(s.get("rejection_reason") or ""))
            table.add_row(str(s.get("timestamp", ""))[11:19],
                          str(s.get("symbol", "?")), verdict, detail[:70])

        # trades
        table = self.query_one("#trades", DataTable)
        table.clear()
        for t in (data.get("today") or {}).get("trades") or []:
            side = str(t.get("side", "?"))
            pnl = t.get("pnl")
            pnl_cell = (Text(_pnl_plain(pnl), style=_pnl_style(pnl))
                        if side == "SELL" and pnl is not None else Text(""))
            table.add_row(
                str(t.get("timestamp", ""))[11:19],
                Text(side, style="green" if side == "BUY" else "yellow"),
                str(t.get("symbol", "?")), str(t.get("qty")),
                f"{t.get('price') or 0:.2f}", pnl_cell,
                str(t.get("exit_reason") or ""))

        # watchlist
        table = self.query_one("#watchlist", DataTable)
        table.clear()
        wl = data.get("watchlist") or {}
        for sym in wl.get("symbols") or []:
            table.add_row(str(sym), sector_of(str(sym)))

        # header
        try:
            from monitor import market_status

            mkt, _ = market_status(datetime.now(IST))
        except Exception:
            mkt = "?"
        flags = f" | refresh {self.interval}s"
        if self._paused:
            flags += " | PAUSED"
        if not data.get("api"):
            flags += " | API DOWN"
        self.sub_title = f"market {mkt}{flags}"

    # --- actions ----------------------------------------------------------
    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        self._log_event("data updates paused" if self._paused
                        else "data updates resumed", "yellow")
        if not self._paused:
            self._schedule_collect()

    def action_refresh_now(self) -> None:
        self._paused = False
        self._schedule_collect()
        self._log_event("manual refresh", "cyan")

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()


def main() -> None:
    parser = argparse.ArgumentParser(description="Trading Monitor TUI")
    parser.add_argument("--interval", "-i", type=int, default=5,
                        help="API data refresh interval in seconds (default 5)")
    parser.add_argument("--log-lines", "-n", type=int, default=800,
                        help="Max lines kept in the live log (default 800)")
    args = parser.parse_args()
    MonitorApp(interval=args.interval, log_lines=args.log_lines).run()


if __name__ == "__main__":
    main()
