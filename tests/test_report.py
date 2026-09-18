"""Daily report content against seeded data."""
from datetime import datetime

import db
from report import build_report
from report_html import build_html_report


def _seed_day():
    now = datetime.now().isoformat()
    db.insert_trade({"timestamp": now, "symbol": "RELIANCE", "side": "BUY",
                     "qty": 10, "price": 100.0, "value": 1000.0})
    db.insert_trade({"timestamp": now, "symbol": "RELIANCE", "side": "SELL",
                     "qty": 10, "price": 104.0, "value": 1040.0, "pnl": 30.0,
                     "pnl_pct": 3.0, "exit_reason": "TAKE_PROFIT",
                     "mfe": 2.5, "mae": -0.2, "brokerage": 0.3, "stt": 0.26,
                     "other_costs": 0.1, "slippage_cost": 0.05})
    db.insert_trade({"timestamp": now, "symbol": "TCS", "side": "BUY",
                     "qty": 5, "price": 200.0, "value": 1000.0})
    db.insert_trade({"timestamp": now, "symbol": "TCS", "side": "SELL", "qty": 5,
                     "price": 198.0, "value": 990.0, "pnl": -12.0, "pnl_pct": -1.2,
                     "exit_reason": "STOP_LOSS", "mfe": 0.4, "mae": -1.0,
                     "brokerage": 0.3, "stt": 0.25, "other_costs": 0.1,
                     "slippage_cost": 0.05})
    db.insert_signal({"timestamp": now, "symbol": "X", "action": "BUY",
                      "confidence": 0.9, "entry_price": 10.0, "stop_loss": 9.0,
                      "take_profit": 12.0, "reason": "t", "approved": True,
                      "adjusted_qty": 5, "strategy": "S"})
    db.insert_signal({"timestamp": now, "symbol": "Y", "action": "BUY",
                      "confidence": 0.2, "entry_price": 10.0, "stop_loss": 9.0,
                      "take_profit": 12.0, "reason": "t", "approved": False,
                      "rejection_reason": "Weak", "adjusted_qty": 0, "strategy": "S"})


def test_report_sections(tmpdb):
    _seed_day()
    rep = build_report(datetime.now().date().isoformat())
    assert "1W/1L" in rep and "Win rate: 50.0%" in rep
    assert "TAKE_PROFIT" in rep and "STOP_LOSS" in rep
    assert "Avg MFE:" in rep and "Sells reaching 2R MFE: 50%" in rep
    assert "Brokerage: Rs.1" in rep  # 0.3+0.3 rounded
    assert "- ENERGY:" in rep and "- IT:" in rep  # sector attribution
    assert "1 approved, 1 rejected" in rep and "Weak: 1" in rep


def test_report_empty_day(tmpdb):
    rep = build_report("1999-01-01")
    assert "0 buys / 0 sells" in rep and "No excursion data" in rep


def test_html_report_sections(tmpdb):
    _seed_day()
    html = build_html_report(datetime.now().date().isoformat())
    assert "<!doctype html>" in html and "</html>" in html
    assert "<details" in html  # per-trade drill-down
    assert "Round trips (2)" in html and "RELIANCE" in html
    assert "TAKE_PROFIT" in html and "STOP_LOSS" in html
    assert "Profit factor" in html and "Weak" in html
    assert "Sector attribution" in html and "ENERGY" in html
    assert "svg" in html  # charts render


def test_html_report_empty_day(tmpdb):
    html = build_html_report("1999-01-01")
    assert "<!doctype html>" in html
    assert "No trades this day." in html and "No signals this day." in html
