"""Monitor/log/logger utilities (no network, no broker)."""
import os
import time

import monitor
import logs as logs_mod
from logger import get_logger
from paths import LOG_DIR


def test_candidate_logs_newest_first():
    a = LOG_DIR / "live_trader_probe_old_20990101.log"
    b = LOG_DIR / "live_trader_probe_new_20990101.log"
    try:
        a.write_text("old\n")
        b.write_text("new\n")
        old = time.time() - 100
        os.utime(a, (old, old))
        cands = monitor._candidate_logs()
        names = [p.name for p in cands]
        assert "live_trader_probe_new_20990101.log" in names
        assert "live_trader_probe_old_20990101.log" in names
        assert names.index("live_trader_probe_new_20990101.log") < names.index(
            "live_trader_probe_old_20990101.log")
    finally:
        a.unlink(missing_ok=True)
        b.unlink(missing_ok=True)


def test_get_recent_logs_reads_freshest(tmp_path):
    f = tmp_path / "live_trader_20990101.log"
    f.write_text("\n".join(f"line{i}" for i in range(10)) + "\n")
    import monitor as m
    monkeypatched = m._trade_logs
    try:
        m._trade_logs = lambda: [f]
        assert m.get_recent_logs(lines=3) == ["line7", "line8", "line9"]
    finally:
        m._trade_logs = monkeypatched


def test_market_status():
    from datetime import datetime
    assert monitor.market_status(datetime(2026, 9, 19, 10, 0))[0] == "WEEKEND"
    assert monitor.market_status(datetime(2026, 9, 18, 9, 0))[0] == "PRE-OPEN"
    assert monitor.market_status(datetime(2026, 9, 18, 10, 0)) == ("OPEN", True)
    assert monitor.market_status(datetime(2026, 9, 18, 15, 27))[0] == "SQUARE-OFF"
    assert monitor.market_status(datetime(2026, 9, 18, 16, 0))[0] == "CLOSED"


def test_monitor_log_parsers(tmp_path, monkeypatch):
    from datetime import datetime
    import monitor as m
    f = tmp_path / "live_trader_20990101.log"
    f.write_text(
        "[2026-09-18 09:38:49] [INFO] [live_trader] ON-BAR: Processing 30 stocks...\n"
        "[2026-09-18 09:39:00] [INFO] [live_trader] Waiting ~44s until next check...\n"
        "[FEED] Streaming 30 symbols\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(m, "_trade_logs", lambda: [f])
    lines = m._tail_lines()
    assert m._last_tick_time(lines) == datetime(2026, 9, 18, 9, 38, 49)
    assert m._feed_symbols() == 30
    # noise filtered from display
    noise = "[SELECTOR] Evaluating 498 stocks for momentum..."
    assert noise not in m._clean_log_lines([noise, "keep-me"])


def test_render_dashboard_smoke(tmp_path, monkeypatch):
    import monitor as m
    monkeypatch.setattr(m, "_trade_logs", lambda: [])
    data = {
        "api": True,
        "status": {"database_connected": True},
        "portfolio": {"start_capital": 100_000, "current_value": 100_050,
                      "cash": 90_000, "position_value": 10_050},
        "positions": {"live_prices": True, "positions": [
            {"symbol": "X", "qty": 10, "entry_price": 100.0,
             "current_price": 100.5, "r_multiple": 0.5}]},
        "today": {"signals_total": 2, "signals_approved": 1,
                  "signals_rejected": 1, "trades_total": 1, "trades_buy": 1,
                  "trades_sell": 0, "total_pnl": 0,
                  "signals": [{"timestamp": "2026-09-18T09:30:00", "symbol": "X",
                               "approved": True, "adjusted_qty": 10}],
                  "trades": []},
        "trades": {"trades": []},
        "logs": ["[2026-09-18 09:30:00] [INFO] [live_trader] ON-BAR: x"],
    }
    out = m.render(data, log_lines=3)
    assert "PORTFOLIO (paper)" in out
    assert "X" in out and "+0.5" in out
    assert "Signals 2 (1 approved / 1 rejected)" in out


def _fake_tui_data():
    return {
        "api": True,
        "status": {"database_connected": True},
        "portfolio": {"start_capital": 100_000, "current_value": 100_050,
                      "cash": 90_000, "position_value": 10_050},
        "positions": {"live_prices": True, "positions": [
            {"symbol": "X", "qty": 10, "entry_price": 100.0,
             "current_price": 100.5, "r_multiple": 0.5}]},
        "today": {"signals_total": 2, "signals_approved": 1,
                  "signals_rejected": 1, "trades_total": 1, "trades_buy": 1,
                  "trades_sell": 0, "total_pnl": -12.5,
                  "signals": [
                      {"timestamp": "2026-09-18T09:30:00", "symbol": "X",
                       "approved": True, "adjusted_qty": 10},
                      {"timestamp": "2026-09-18T09:31:00", "symbol": "Y",
                       "approved": False,
                       "rejection_reason": "Volatility too low"}],
                  "trades": [
                      {"timestamp": "2026-09-18T09:32:00", "symbol": "X",
                       "side": "BUY", "qty": 10, "price": 100.0,
                       "exit_reason": "SIGNAL_ENTRY"}]},
        "trades": {"trades": []},
        "logs": ["[2026-09-18 09:30:00] [INFO] [live_trader] ON-BAR: x",
                 "[2026-09-18 09:31:00] [INFO] [live_trader] India VIX: 11.86 (ok)",
                 "[2026-09-18 09:32:00] [ERROR] [live_trader] boom"],
        "watchlist": {"updated": "2026-09-18T09:30:00", "count": 3,
                      "symbols": ["RELIANCE", "PWL", "SYRMA"],
                      "strategy": "IntradayMomentum"},
    }


def test_tui_renderables():
    import pytest
    pytest.importorskip("textual")
    from io import StringIO
    from rich.console import Console
    import monitor_tui as tui

    data = _fake_tui_data()
    console = Console(file=StringIO(), width=160, no_color=True)
    for renderable in (tui.system_text(data),
                       tui.portfolio_text(data),
                       tui.regime_text(data)):
        console.print(renderable)
    out = console.file.getvalue()
    assert "Watchlist" in out and "3 names" in out
    assert "Rs.100,000" in out and "P&L" in out and "Open" in out
    assert "India VIX" in out and "11.86" in out and "Entries" in out


def test_tui_vix_parse_and_entry_state(monkeypatch):
    import pytest
    pytest.importorskip("textual")
    from datetime import datetime

    import config as config_mod
    import monitor_tui as tui

    v, note = tui._last_vix(["[x] India VIX: 11.86 (ok)", "junk"])
    assert v == 11.86 and note == "ok"
    assert tui._last_vix([]) == (None, None)

    assert tui._entry_state(datetime(2026, 9, 18, 10, 0)) == "OPEN"
    assert tui._entry_state(datetime(2026, 9, 18, 15, 0)).startswith("closed")
    monkeypatch.setattr(config_mod.config, "ENTRY_PAUSE_START", (11, 45))
    monkeypatch.setattr(config_mod.config, "ENTRY_PAUSE_END", (13, 30))
    assert "lunch" in tui._entry_state(datetime(2026, 9, 18, 12, 30))


def test_tui_log_tailer(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("textual")
    import monitor_tui as tui

    monkeypatch.setattr(tui, "LOG_DIR", tmp_path)
    f = tmp_path / "trader.log"
    f.write_text("\n".join(f"line{i}" for i in range(100)) + "\n",
                 encoding="utf-8")

    tailer = tui.LogTailer(seed_lines=10)
    assert tailer.read_new() == [f"line{i}" for i in range(90, 100)]
    with open(f, "a", encoding="utf-8") as fh:
        fh.write("new-line\n")
    assert tailer.read_new() == ["new-line"]
    assert tailer.read_new() == []  # nothing new
    # truncation (a new run overwrote the file) -> reseed, don't stall
    f.write_text("fresh1\nfresh2\n", encoding="utf-8")
    assert tailer.read_new() == ["fresh1", "fresh2"]
    tailer.close()


def test_tui_app_lifecycle(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("textual")
    import asyncio

    import monitor
    import monitor_tui as tui

    monkeypatch.setattr(monitor, "_trade_logs", lambda: [])
    monkeypatch.setattr(tui, "LOG_DIR", tmp_path)
    (tmp_path / "trader.log").write_text(
        "[2026-09-18 09:30:00] [INFO] [live_trader] ON-BAR: x\n"
        "[2026-09-18 09:31:00] [ERROR] [live_trader] boom\n",
        encoding="utf-8")

    data = _fake_tui_data()
    app = tui.MonitorApp(interval=60, collect_fn=lambda: data)

    async def run():
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert app._data is data  # collect ran on mount
            assert "market" in app.sub_title
            assert app.query_one("#positions").row_count == 1
            assert app.query_one("#watchlist").row_count == 3
            app._pump_logs()  # stream the seeded log without waiting on timer
            log_lines = " ".join(str(l) for l in app.query_one("#log").lines)
            assert "boom" in log_lines
            await pilot.press("p")
            assert app._paused is True
            await pilot.press("r")
            assert app._paused is False
            await pilot.press("c")
            await pilot.press("q")

    asyncio.run(run())


def test_sdk_noise_loggers_quieted():
    """The SDK's feed client logged raw 'Error:' spam; it must stay quiet."""
    import logging
    import logger  # noqa: F401  (import applies the levels)

    assert logging.getLogger("growwapi").level == logging.CRITICAL
    assert logging.getLogger("nats").level == logging.CRITICAL


def test_feed_status_labels(tmp_path, monkeypatch):
    import monitor as m
    import config as config_mod

    f = tmp_path / "live_trader_20990101.log"
    monkeypatch.setattr(m, "_trade_logs", lambda: [f])

    monkeypatch.setattr(config_mod.config, "FEED_ENABLED", False)
    assert m._feed_status() == "disabled (REST only)"

    monkeypatch.setattr(config_mod.config, "FEED_ENABLED", True)
    f.write_text("[FEED] Streaming 30 symbols\n", encoding="utf-8")
    assert m._feed_status() == "streaming 30 symbols"

    f.write_text("[FEED] setup failed, REST fallback: nats: no servers available\n",
                 encoding="utf-8")
    assert m._feed_status() == "unavailable (REST)"

    f.write_text("nothing feed related\n", encoding="utf-8")
    assert m._feed_status() == "REST only"


def test_tail_file_last_n(tmp_path, capsys):
    f = tmp_path / "t.log"
    f.write_text("\n".join(f"L{i}" for i in range(8)) + "\n")
    logs_mod.tail_file(f, lines=3, follow=False)
    assert capsys.readouterr().out.splitlines() == ["L5", "L6", "L7"]
    logs_mod.tail_file(tmp_path / "missing.log")
    assert "not found" in capsys.readouterr().out.lower()


def test_logger_dedupes_handlers():
    h1 = len(get_logger("_probe_log").handlers)
    h2 = len(get_logger("_probe_log").handlers)
    assert h1 == h2 == 2  # console + file, configured once
