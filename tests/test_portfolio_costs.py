"""A2: intraday cost schedule + sampled slippage + averaging SL/TP."""
from paper_portfolio import PaperPortfolio


def test_buy_costs_sell_side_stt_only():
    p = PaperPortfolio(initial_capital=1_000_000, slippage_max_pct=0,
                       slippage_seed=1)
    r = p.execute_buy("X", 10, 100.0, stop_loss=98.0, take_profit=104.0)
    assert r["success"]
    assert r["stt"] == 0.0  # no STT on intraday buys
    assert r["stamp"] > 0 and r["other_costs"] > 0
    assert r["slippage_cost"] == 0.0
    assert abs(r["total_cost"] - (r["value"] + r["brokerage"] + r["other_costs"])) < 1e-6


def test_sell_costs_include_stt():
    p = PaperPortfolio(initial_capital=1_000_000, slippage_max_pct=0,
                       slippage_seed=1)
    p.execute_buy("X", 10, 100.0, stop_loss=98.0, take_profit=104.0)
    r = p.execute_sell("X", 10, 102.0)
    assert r["success"]
    assert r["stt"] > 0
    assert abs(r["net_proceeds"] - (r["value"] - r["brokerage"] - r["stt"] - r["other_costs"])) < 1e-6


def test_slippage_seeded_and_bounded():
    a = PaperPortfolio(initial_capital=1_000_000, slippage_seed=42)
    b = PaperPortfolio(initial_capital=1_000_000, slippage_seed=42)
    ra = a.execute_buy("X", 10, 100.0)
    rb = b.execute_buy("X", 10, 100.0)
    assert ra["price"] == rb["price"]  # reproducible
    assert 100.0 <= ra["price"] <= 100.0 * (1 + 0.0004)
    assert ra["slippage_cost"] >= 0


def test_averaging_refreshes_levels_and_risk():
    p = PaperPortfolio(initial_capital=1_000_000, slippage_max_pct=0,
                       slippage_seed=1)
    p.execute_buy("X", 10, 100.0, stop_loss=98.0, take_profit=104.0)
    p.execute_buy("X", 10, 102.0, stop_loss=100.0, take_profit=106.0)
    pos = p.positions["X"]
    assert pos.qty == 20
    assert pos.stop_loss == 100.0 and pos.take_profit == 106.0
    assert abs(pos.initial_risk - (pos.avg_price - 100.0)) < 1e-9


def test_partial_sell_keeps_position():
    p = PaperPortfolio(initial_capital=1_000_000, slippage_max_pct=0,
                       slippage_seed=1)
    p.execute_buy("X", 10, 100.0, stop_loss=98.0, take_profit=104.0)
    r = p.execute_sell("X", 4, 102.0)
    assert r["success"] and p.positions["X"].qty == 6
