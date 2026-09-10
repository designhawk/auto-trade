"""Phase D: heat cap, vol targeting, soft throttle, confidence sizing."""
from base_strategy import Signal
from risk_manager import RiskManager


def _sig(**kw):
    base = dict(symbol="X", action="BUY", confidence=1.0, entry_price=100.0,
                stop_loss=98.0, take_profit=104.0, reason="t", volatility_pct=None)
    base.update(kw)
    return Signal(**base)


def _rm(**kw):
    base = dict(initial_capital=100_000, max_position_pct=1.0,
                max_open_positions=10, daily_loss_limit_pct=0.03,
                max_drawdown_pct=0.10, min_cash_reserve=0,
                heat_cap_pct=99.0)  # heat out of the way unless tested
    base.update(kw)
    return RiskManager(**base)


def test_heat_cap_rejects():
    rm = _rm(heat_cap_pct=0.06)
    # open risk: (100-98)*100 = 200 ... need >= 6000 to trip
    held = [{"symbol": "A", "qty": 100, "avg_price": 1000.0, "stop_loss": 900.0}]
    d = rm.approve(_sig(), held, available_cash=1_000_000)
    assert not d.approved and "heat" in d.reason.lower()


def test_heat_cap_passes_small_book():
    rm = _rm(heat_cap_pct=0.06)
    held = [{"symbol": "A", "qty": 10, "avg_price": 100.0, "stop_loss": 98.0}]
    d = rm.approve(_sig(), held, available_cash=1_000_000)
    assert d.approved


def test_vol_targeting_scales_qty():
    rm = _rm()
    low = rm.approve(_sig(volatility_pct=0.75), [], available_cash=1_000_000)
    high = rm.approve(_sig(volatility_pct=3.0), [], available_cash=1_000_000)
    assert low.approved and high.approved
    assert high.adjusted_qty < low.adjusted_qty  # 0.5x vs 1.5x anchor


def test_soft_throttle_halves():
    rm = _rm()
    full = rm.approve(_sig(), [], available_cash=1_000_000)
    rm.update_daily_pnl(-2_000)  # past 0.5 x 3% x 100k = 1500 throttle line
    half = rm.approve(_sig(), [], available_cash=1_000_000)
    assert half.approved
    assert half.adjusted_qty == full.adjusted_qty // 2
    assert "throttled" in half.reason


def test_confidence_scales_qty():
    rm = _rm()
    hi = rm.approve(_sig(confidence=1.0), [], available_cash=1_000_000)
    lo = rm.approve(_sig(confidence=0.0), [], available_cash=1_000_000)
    assert hi.approved and lo.approved
    assert lo.adjusted_qty == hi.adjusted_qty // 2  # 0.5x vs 1.0x
