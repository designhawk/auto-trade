# risk_manager.py
"""
Risk Management Module

Enforces trading rules before any signal is executed:
- Position sizing (max % per stock)
- Max open positions
- Daily loss limit (% of current capital)
- Drawdown circuit breaker (all-time peak)
- Cash reserve requirement

Usage:
    risk_manager = RiskManager(initial_capital=1000000)
    decision = risk_manager.approve(signal, current_positions, available_cash)
    if decision.approved:
        execute_trade(decision.adjusted_qty)
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from base_strategy import Signal


@dataclass
class RiskDecision:
    """Risk manager decision for a trading signal."""

    approved: bool
    adjusted_qty: int
    reason: Optional[str] = None


class RiskManager:
    """
    Enforces risk rules before any order is placed.

    All position sizing and risk checks happen here.
    The trading loop MUST call approve() before every order.
    """

    def __init__(
        self,
        initial_capital: float,
        max_position_pct: float = 0.10,  # 10% per stock
        max_open_positions: int = 50,
        daily_loss_limit_pct: float = 0.02,  # 2% daily stop
        max_drawdown_pct: float = 0.10,  # 10% circuit breaker
        min_risk_reward: float = 2.0,
        min_cash_reserve: float = 100000,  # ₹1L minimum cash
        heat_cap_pct: float = 0.06,  # max total open risk (adverse excursion)
        target_vol_pct: float = 1.5,  # volatility-targeting anchor (ATR%)
        throttle_start_mult: float = 0.5,  # halve size past this x daily limit
    ):
        """
        Initialize risk manager.

        Args:
            initial_capital: Starting capital
            max_position_pct: Max % of capital per position
            max_open_positions: Max number of open positions
            daily_loss_limit_pct: Daily loss limit as % of current capital
            max_drawdown_pct: Circuit breaker drawdown % (from all-time peak)
            min_risk_reward: Minimum risk-reward ratio required
            min_cash_reserve: Minimum cash to keep in reserve
            heat_cap_pct: Max total open risk across positions (% of capital)
            target_vol_pct: Anchor ATR% for volatility targeting
            throttle_start_mult: Fraction of daily limit where sizing halves
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_position_pct = max_position_pct
        self.max_open_positions = max_open_positions
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.min_risk_reward = min_risk_reward
        self.min_cash_reserve = min_cash_reserve
        self.heat_cap_pct = heat_cap_pct
        self.target_vol_pct = target_vol_pct
        self.throttle_start_mult = throttle_start_mult

        # Track daily P&L
        self.daily_pnl: dict[date, float] = {}
        self.current_date: Optional[date] = None

        # Track peak capital for drawdown
        self.peak_capital = initial_capital  # Today's peak (resets daily)
        self.all_time_peak = initial_capital  # All-time peak (never resets)

    def approve(
        self, signal: Signal, current_positions: list[dict], available_cash: float
    ) -> RiskDecision:
        """
        Approve or reject a trading signal based on risk rules.

        Args:
            signal: Trading signal to evaluate
            current_positions: List of current open positions
            available_cash: Cash available for trading

        Returns:
            RiskDecision with approval status and adjusted quantity
        """
        today = date.today()

        # Reset daily tracking at start of new day
        if self.current_date != today:
            self.current_date = today
            self.peak_capital = self.current_capital  # Reset today's peak
            self.daily_pnl[today] = 0

        # Update peak capitals
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital
        if self.current_capital > self.all_time_peak:
            self.all_time_peak = self.current_capital

        # Check 1: Daily loss limit (based on CURRENT capital)
        daily_loss = self.daily_pnl.get(today, 0)
        daily_loss_limit = self.current_capital * self.daily_loss_limit_pct
        if daily_loss < -daily_loss_limit:
            return RiskDecision(
                approved=False,
                adjusted_qty=0,
                reason=f"Daily loss limit: Rs.{abs(daily_loss):,.0f} > Rs.{daily_loss_limit:,.0f}",
            )

        # Check 2: Circuit breaker - uses ALL-TIME peak (never resets)
        overall_drawdown = (
            self.all_time_peak - self.current_capital
        ) / self.all_time_peak

        if overall_drawdown > self.max_drawdown_pct:
            return RiskDecision(
                approved=False,
                adjusted_qty=0,
                reason=f"Circuit breaker: Overall drawdown {overall_drawdown * 100:.1f}% > {self.max_drawdown_pct * 100:.1f}%",
            )

        # Check 3: Max open positions
        if len(current_positions) >= self.max_open_positions:
            return RiskDecision(
                approved=False,
                adjusted_qty=0,
                reason=f"Max positions reached: {len(current_positions)}/{self.max_open_positions}",
            )

        # Check 4: Already in position for this symbol? (MOVE UP - before expensive math)
        symbol_in_position = any(
            pos.get("symbol") == signal.symbol for pos in current_positions
        )
        if symbol_in_position:
            return RiskDecision(
                approved=False,
                adjusted_qty=0,
                reason=f"Already have position in {signal.symbol}",
            )

        # Check 5: Sufficient cash reserve
        if available_cash < self.min_cash_reserve:
            return RiskDecision(
                approved=False,
                adjusted_qty=0,
                reason=f"Cash reserve: Rs.{available_cash:,.0f} < Rs.{self.min_cash_reserve:,.0f}",
            )

        # Check 6: Risk-reward ratio (direction-aware for LONG only for now)
        risk = signal.entry_price - signal.stop_loss
        reward = signal.take_profit - signal.entry_price

        if risk <= 0:
            return RiskDecision(
                approved=False, adjusted_qty=0, reason="Invalid stop loss (risk <= 0)"
            )

        risk_reward = reward / risk
        if risk_reward < self.min_risk_reward:
            return RiskDecision(
                approved=False,
                adjusted_qty=0,
                reason=f"Risk-reward {risk_reward:.1f} < {self.min_risk_reward}",
            )

        # Check 7: Volatility check (must have reasonable volatility for momentum)
        if signal.volatility_pct is not None:
            if signal.volatility_pct > 4.0:
                return RiskDecision(
                    approved=False,
                    adjusted_qty=0,
                    reason=f"Volatility too high: {signal.volatility_pct:.1f}% > 4%",
                )
            if signal.volatility_pct < 0.3:
                return RiskDecision(
                    approved=False,
                    adjusted_qty=0,
                    reason=f"Volatility too low: {signal.volatility_pct:.1f}% < 0.3%",
                )

        # Check 8: Portfolio heat cap (total open risk across positions)
        # Needs avg_price/stop_loss in current_positions (live_trader provides them)
        open_risk = 0.0
        for pos in current_positions:
            avg = pos.get("avg_price", 0) or 0
            sl = pos.get("stop_loss", 0) or 0
            open_risk += max(0.0, avg - sl) * pos.get("qty", 0)
        heat_cap = self.current_capital * self.heat_cap_pct
        if open_risk >= heat_cap:
            return RiskDecision(
                approved=False,
                adjusted_qty=0,
                reason=f"Portfolio heat: Rs.{open_risk:,.0f} >= Rs.{heat_cap:,.0f}",
            )

        # Check 9: Position sizing - risk-based sizing with volatility
        # targeting, soft throttle, and confidence scaling
        risk_amount = self.current_capital * 0.02
        if signal.volatility_pct is not None and signal.volatility_pct > 0:
            vol_scale = self.target_vol_pct / signal.volatility_pct
            risk_amount *= max(0.5, min(1.5, vol_scale))
        # Soft throttle: halve size once daily loss passes the throttle line
        throttle_line = (
            self.current_capital * self.daily_loss_limit_pct * self.throttle_start_mult
        )
        throttled = daily_loss < -throttle_line
        if throttled:
            risk_amount *= 0.5
        risk_per_share = signal.entry_price - signal.stop_loss

        qty = 0  # Initialize to fix bug #1
        if risk_per_share > 0:
            risk_based_qty = int(risk_amount / risk_per_share)
            max_position_value = self.current_capital * self.max_position_pct
            max_qty = int(max_position_value / signal.entry_price)
            qty = min(risk_based_qty, max_qty)
            # Confidence scaling: 0.5x (no conviction) to 1.0x (full)
            qty = int(qty * (0.5 + 0.5 * max(0.0, min(1.0, signal.confidence))))

        if qty < 1:
            return RiskDecision(
                approved=False,
                adjusted_qty=0,
                reason="Insufficient capital for minimum position",
            )

        # Check 10: Can afford the position?
        position_cost = qty * signal.entry_price
        if position_cost > available_cash:
            # Adjust qty to what we can afford
            qty = int(available_cash / signal.entry_price)
            if qty < 1:
                return RiskDecision(
                    approved=False,
                    adjusted_qty=0,
                    reason="Insufficient cash for position",
                )

        # All checks passed
        return RiskDecision(
            approved=True,
            adjusted_qty=qty,
            reason=f"Approved: R:R {risk_reward:.1f}, Qty {qty}"
            + (" (throttled)" if throttled else ""),
        )

    def update_daily_pnl(self, pnl: float):
        """Update daily P&L tracking."""
        today = date.today()
        if today not in self.daily_pnl:
            self.daily_pnl[today] = 0
        self.daily_pnl[today] += pnl

    def update_capital(self, current_value: float):
        """Update current capital (call after each trade)."""
        self.current_capital = current_value

    def reset_daily(self):
        """Reset daily P&L (called at start of new day)."""
        today = date.today()
        self.daily_pnl[today] = 0

    def get_status(self) -> dict:
        """Get current risk manager status."""
        today = date.today()
        daily_pnl = self.daily_pnl.get(today, 0)
        overall_drawdown = (
            self.all_time_peak - self.current_capital
        ) / self.all_time_peak
        daily_loss_limit = self.current_capital * self.daily_loss_limit_pct

        return {
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
            "peak_capital": self.peak_capital,
            "all_time_peak": self.all_time_peak,
            "overall_drawdown_pct": overall_drawdown * 100,
            "daily_pnl": daily_pnl,
            "daily_loss_limit": daily_loss_limit,
            "circuit_breaker_triggered": overall_drawdown > self.max_drawdown_pct,
            "daily_limit_triggered": daily_pnl < -daily_loss_limit,
        }
