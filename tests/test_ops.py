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
    monkeypatched = m._candidate_logs
    try:
        m._candidate_logs = lambda: [f]
        assert m.get_recent_logs(lines=3) == ["line7", "line8", "line9"]
    finally:
        m._candidate_logs = monkeypatched


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
