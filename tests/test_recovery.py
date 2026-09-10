"""Restart recovery: fresh portfolio on the same DB must match to the paisa."""
from datetime import datetime

import db
from paper_portfolio import PaperPortfolio


def _live_buy_row(symbol, result):
    return {"timestamp": datetime.now().isoformat(), "symbol": symbol, "side": "BUY",
            "qty": result["qty"], "price": result["price"], "value": result["value"],
            "pnl": 0, "pnl_pct": 0, "exit_reason": "SIGNAL_ENTRY",
            "brokerage": result.get("brokerage"), "stt": result.get("stt"),
            "other_costs": result.get("other_costs"),
            "slippage_cost": result.get("slippage_cost")}


def test_restart_recovery_exact(tmpdb):
    p1 = PaperPortfolio(initial_capital=500_000)
    r1 = p1.execute_buy("A", 10, 100.0, stop_loss=98.0, take_profit=104.0)
    r2 = p1.execute_buy("B", 5, 200.0, stop_loss=196.0, take_profit=208.0)
    db.insert_trade(_live_buy_row("A", r1))
    db.insert_trade(_live_buy_row("B", r2))
    rs = p1.execute_sell("A", 4, 102.0)  # partial
    db.insert_trade({"timestamp": datetime.now().isoformat(), "symbol": "A",
                     "side": "SELL", "qty": rs["qty"], "price": rs["price"],
                     "value": rs["value"], "pnl": rs["net_pnl"], "pnl_pct": rs["pnl_pct"],
                     "exit_reason": "SCALED_1R", "mfe": 1.2, "mae": -0.1,
                     "brokerage": rs.get("brokerage"), "stt": rs.get("stt"),
                     "other_costs": rs.get("other_costs"),
                     "slippage_cost": rs.get("slippage_cost")})

    p2 = PaperPortfolio(initial_capital=500_000)
    p2.load_positions_from_db()

    assert abs(p2.cash - p1.cash) < 1e-6, (p2.cash, p1.cash)
    assert set(p2.positions) == set(p1.positions)
    for s in p1.positions:
        assert p2.positions[s].qty == p1.positions[s].qty
        assert abs(p2.positions[s].avg_price - p1.positions[s].avg_price) < 1e-9
    print(f"RECOVERY-OK: cash={p2.cash:.2f} positions={sorted(p2.positions)}")
