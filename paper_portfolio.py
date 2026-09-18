# paper_portfolio.py
"""
Paper Portfolio Simulation

Simulates trading without real money:
- Tracks virtual positions
- Calculates P&L
- Enforces realistic transaction costs
- Provides portfolio valuation

Usage:
    portfolio = PaperPortfolio(initial_capital=1000000)
    portfolio.execute_buy("RELIANCE", qty=10, price=2500.0)
    portfolio.execute_sell("RELIANCE", qty=10, price=2600.0)
    value = portfolio.get_portfolio_value(current_prices)
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional
import random
import pandas as pd

try:
    from logger import get_logger
    log = get_logger("paper_portfolio")
except:
    import logging
    log = logging.getLogger("paper_portfolio")


@dataclass
class Position:
    """Paper trading position."""
    symbol: str
    qty: int
    avg_price: float
    side: str = "LONG"
    entry_time: datetime = field(default_factory=datetime.now)
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop: bool = False
    trail_activation_pct: float = 0.02
    trail_distance_pct: float = 0.015
    # Exit management (Phase E): partials + diagnostics
    scaled: bool = False          # True once the 1R partial is taken
    initial_risk: float = 0.0     # avg_price - stop_loss at entry (R reference)
    mfe: float = 0.0              # max favorable excursion, in R multiples
    mae: float = 0.0              # max adverse excursion, in R multiples (<= 0)
    # Landed cost of currently-held shares (gross + buy-side costs). Sell P&L
    # subtracts this so each trade carries the full round-trip cost.
    cost_basis_total: float = 0.0


@dataclass
class Transaction:
    """Paper trading transaction record."""
    timestamp: datetime
    symbol: str
    side: str  # "BUY" or "SELL"
    qty: int
    price: float
    value: float
    brokerage: float
    stt: float
    net_value: float
    stamp: float = 0.0
    other_costs: float = 0.0   # exchange + SEBI + GST combined
    slippage_cost: float = 0.0


class PaperPortfolio:
    """
    Paper trading portfolio simulator.
    
    Simulates real trading with:
    - Transaction costs (brokerage, STT)
    - Position tracking
    - P&L calculation
    - Portfolio valuation
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000,
        brokerage_pct: float = 0.001,     # Groww: 0.1% per order ...
        brokerage_cap: float = 20.0,      # ... or Rs.20, whichever is lower ...
        brokerage_min: float = 5.0,       # ... floor Rs.5 (or 2.5% for tiny orders, SEBI cap)
        stt_pct: float = 0.00025,         # 0.025% SELL side only (equity intraday)
        exchange_pct: float = 0.000030699,  # NSE 0.0030699% each side (Apr 2026)
        sebi_pct: float = 0.000001,       # Rs.10/crore each side
        stamp_pct: float = 0.00003,       # 0.003% BUY side only (intraday, non-delivery)
        gst_pct: float = 0.18,            # 18% on brokerage+exchange+SEBI
        slippage_max_pct: float = 0.0004, # adverse slippage sampled U[0, max]
        slippage_seed: Optional[int] = None,
    ):
        """
        Initialize paper portfolio.

        Defaults follow Groww (the broker this bot trades through) and NSE
        statutory rates as of April 2026 - verify against your broker's
        contract note before trusting absolute P&L.

        Args:
            initial_capital: Starting virtual capital
            brokerage_pct: Brokerage fee as decimal (Groww 0.1%)
            brokerage_cap: Per-order brokerage ceiling in Rs. (Groww Rs.20)
            brokerage_min: Per-order brokerage floor in Rs. (Groww Rs.5)
            stt_pct: Securities transaction tax as decimal (sell only)
            exchange_pct: Exchange transaction charges as decimal
            sebi_pct: SEBI turnover fee as decimal
            stamp_pct: Stamp duty as decimal (buy only)
            gst_pct: GST on brokerage+exchange+SEBI
            slippage_max_pct: Max adverse slippage sampled per fill
            slippage_seed: Seed for reproducible slippage (None = random)
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.transactions: List[Transaction] = []
        self.brokerage_pct = brokerage_pct
        self.brokerage_cap = brokerage_cap
        self.brokerage_min = brokerage_min
        self.stt_pct = stt_pct
        self.exchange_pct = exchange_pct
        self.sebi_pct = sebi_pct
        self.stamp_pct = stamp_pct
        self.gst_pct = gst_pct
        self.slippage_max_pct = slippage_max_pct
        self._rng = random.Random(slippage_seed)
        self.total_brokerage = 0.0
        self.total_stt = 0.0
        self.total_other = 0.0
        self.total_slippage = 0.0

    def _brokerage(self, gross_value: float) -> float:
        """Per-order brokerage: lower of pct or cap, floored at min
        (with the SEBI 2.5%-of-value cap for very small orders)."""
        b = min(gross_value * self.brokerage_pct, self.brokerage_cap)
        return max(b, min(self.brokerage_min, gross_value * 0.025))

    def _buy_costs(self, gross_value: float) -> tuple:
        """Return (brokerage, stt, stamp, exchange, sebi, gst) for a BUY."""
        brokerage = self._brokerage(gross_value)
        exchange = gross_value * self.exchange_pct
        sebi = gross_value * self.sebi_pct
        stamp = gross_value * self.stamp_pct
        gst = (brokerage + exchange + sebi) * self.gst_pct
        return brokerage, 0.0, stamp, exchange, sebi, gst

    def _sell_costs(self, gross_value: float) -> tuple:
        """Return (brokerage, stt, stamp, exchange, sebi, gst) for a SELL."""
        brokerage = self._brokerage(gross_value)
        stt = gross_value * self.stt_pct
        exchange = gross_value * self.exchange_pct
        sebi = gross_value * self.sebi_pct
        gst = (brokerage + exchange + sebi) * self.gst_pct
        return brokerage, stt, 0.0, exchange, sebi, gst
    
    def load_positions_from_db(self):
        """Load open positions from trades table on startup."""
        from db import get_db, get_cash_flow
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Net BUYs against SELLs so partial sells reduce (not erase) the position
            cursor.execute("""
                SELECT symbol,
                    SUM(CASE WHEN side = 'BUY' THEN qty ELSE -qty END) as net_qty,
                    SUM(CASE WHEN side = 'BUY' THEN qty * price ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN side = 'BUY' THEN qty ELSE 0 END), 0) as avg_price
                FROM trades
                GROUP BY symbol
                HAVING net_qty > 0
            """)
            
            rows = cursor.fetchall()
            for row in rows:
                symbol = row[0]
                qty = int(row[1])
                entry_price = float(row[2])
                
                pos = Position(
                    symbol=symbol,
                    qty=qty,
                    avg_price=entry_price,
                    side="LONG",
                    entry_time=datetime.now(),
                    stop_loss=entry_price * 0.98,
                    take_profit=entry_price * 1.02,
                    trailing_stop=True,
                    trail_activation_pct=0.02,
                    trail_distance_pct=0.015,
                    initial_risk=entry_price * 0.02,
                    # Historical buy costs aren't reconstructable per net
                    # position here; price basis is the best approximation.
                    cost_basis_total=entry_price * qty,
                )
                self.positions[symbol] = pos
        
        # Cash from gross flows + cost columns (exact, incl. sell-side costs)
        buy_out, sell_in = get_cash_flow()
        self.cash = self.initial_capital - buy_out + sell_in
        log.info(f"Loaded {len(self.positions)} positions from trades table, cash: {self.cash}")
    
    def execute_buy(self, symbol: str, qty: int, price: float, stop_loss: float = None, take_profit: float = None) -> dict:
        """
        Execute a buy order in paper trading.
        
        Args:
            symbol: Stock symbol
            qty: Quantity to buy
            price: Execution price
            
        Returns:
            Transaction details
        """
        # Sampled adverse slippage (worse price for buyer)
        slip = self._rng.uniform(0, self.slippage_max_pct)
        executed_price = price * (1 + slip)

        # NSE equity-intraday schedule (STT on sell side only)
        gross_value = executed_price * qty
        brokerage, stt, stamp, exchange, sebi, gst = self._buy_costs(gross_value)
        other_costs = stamp + exchange + sebi + gst
        slippage_cost = (executed_price - price) * qty
        net_value = gross_value + brokerage + stt + other_costs

        # Check if sufficient cash
        if net_value > self.cash:
            return {
                "success": False,
                "error": f"Insufficient cash: need Rs.{net_value:,.0f}, have Rs.{self.cash:,.0f}"
            }

        # Update cash
        self.cash -= net_value
        self.total_brokerage += brokerage
        self.total_stt += stt
        self.total_other += other_costs
        self.total_slippage += slippage_cost
        
        # Update or create position
        if symbol in self.positions:
            # Average down/up
            existing = self.positions[symbol]
            total_qty = existing.qty + qty
            total_cost = (existing.avg_price * existing.qty) + (executed_price * qty)
            existing.qty = total_qty
            existing.avg_price = total_cost / total_qty
            # Refresh protective levels to the latest signal's levels so the
            # stop/target reflect current market structure, not the first fill
            if stop_loss:
                existing.stop_loss = stop_loss
            if take_profit:
                existing.take_profit = take_profit
            existing.initial_risk = existing.avg_price - existing.stop_loss
            existing.cost_basis_total += net_value
        else:
            sl = stop_loss if stop_loss else executed_price * 0.98
            tp = take_profit if take_profit else executed_price * 1.02
            self.positions[symbol] = Position(
                symbol=symbol,
                qty=qty,
                avg_price=executed_price,
                stop_loss=sl,
                take_profit=tp,
                trailing_stop=True,
                trail_activation_pct=0.02,
                trail_distance_pct=0.015,
                initial_risk=executed_price - sl,
                cost_basis_total=net_value,
            )

        # Record transaction
        txn = Transaction(
            timestamp=datetime.now(),
            symbol=symbol,
            side="BUY",
            qty=qty,
            price=executed_price,
            value=gross_value,
            brokerage=brokerage,
            stt=stt,
            net_value=net_value,
            stamp=stamp,
            other_costs=other_costs,
            slippage_cost=slippage_cost
        )
        self.transactions.append(txn)

        return {
            "success": True,
            "symbol": symbol,
            "qty": qty,
            "price": executed_price,
            "value": gross_value,
            "brokerage": brokerage,
            "stt": stt,
            "stamp": stamp,
            "other_costs": other_costs,
            "slippage_cost": slippage_cost,
            "total_cost": net_value,
            "remaining_cash": self.cash
        }

    def execute_sell(self, symbol: str, qty: int, price: float) -> dict:
        """
        Execute a sell order in paper trading.
        
        Args:
            symbol: Stock symbol
            qty: Quantity to sell
            price: Execution price
            
        Returns:
            Transaction details with P&L
        """
        if symbol not in self.positions:
            return {
                "success": False,
                "error": f"No position in {symbol}"
            }
        
        position = self.positions[symbol]
        if qty > position.qty:
            return {
                "success": False,
                "error": f"Insufficient quantity: have {position.qty}, want to sell {qty}"
            }
        
        # Sampled adverse slippage (worse price for seller)
        slip = self._rng.uniform(0, self.slippage_max_pct)
        executed_price = price * (1 - slip)

        # NSE equity-intraday schedule (STT on sell side)
        gross_value = executed_price * qty
        brokerage, stt, stamp, exchange, sebi, gst = self._sell_costs(gross_value)
        other_costs = stamp + exchange + sebi + gst
        slippage_cost = (price - executed_price) * qty
        net_value = gross_value - brokerage - stt - other_costs

        # P&L: allocate the position's landed cost (buy-side costs included)
        # to the shares being sold, so net P&L carries the full round trip.
        # Without this, sell-only costs made every trade look ~0.04% better.
        cost_basis = position.avg_price * qty
        basis_alloc = position.cost_basis_total * (qty / position.qty)
        gross_pnl = gross_value - cost_basis
        net_pnl = net_value - basis_alloc
        pnl_pct = (net_pnl / basis_alloc) * 100 if basis_alloc else 0.0

        # Update cash
        self.cash += net_value
        self.total_brokerage += brokerage
        self.total_stt += stt
        self.total_other += other_costs
        self.total_slippage += slippage_cost
        
        # Update position
        position.qty -= qty
        position.cost_basis_total -= basis_alloc
        if position.qty == 0:
            del self.positions[symbol]
        
        # Record transaction
        txn = Transaction(
            timestamp=datetime.now(),
            symbol=symbol,
            side="SELL",
            qty=qty,
            price=executed_price,
            value=gross_value,
            brokerage=brokerage,
            stt=stt,
            net_value=net_value,
            stamp=stamp,
            other_costs=other_costs,
            slippage_cost=slippage_cost
        )
        self.transactions.append(txn)

        return {
            "success": True,
            "symbol": symbol,
            "qty": qty,
            "price": executed_price,
            "value": gross_value,
            "brokerage": brokerage,
            "stt": stt,
            "stamp": stamp,
            "other_costs": other_costs,
            "slippage_cost": slippage_cost,
            "net_proceeds": net_value,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "pnl_pct": pnl_pct,
            "remaining_cash": self.cash
        }

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> dict:
        """
        Calculate current portfolio value.
        
        Args:
            current_prices: Dictionary of symbol -> current price
            
        Returns:
            Portfolio valuation details
        """
        positions_value = 0.0
        unrealized_pnl = 0.0
        position_details = []
        
        for symbol, position in self.positions.items():
            if symbol in current_prices:
                current_price = current_prices[symbol]
                market_value = current_price * position.qty
                cost_basis = position.avg_price * position.qty
                pnl = market_value - cost_basis
                pnl_pct = (pnl / cost_basis) * 100
                
                positions_value += market_value
                unrealized_pnl += pnl
                
                position_details.append({
                    "symbol": symbol,
                    "qty": position.qty,
                    "avg_price": position.avg_price,
                    "current_price": current_price,
                    "market_value": market_value,
                    "unrealized_pnl": pnl,
                    "unrealized_pnl_pct": pnl_pct
                })
        
        total_value = self.cash + positions_value
        total_return = ((total_value - self.initial_capital) / self.initial_capital) * 100
        
        return {
            "cash": self.cash,
            "positions_value": positions_value,
            "total_value": total_value,
            "initial_capital": self.initial_capital,
            "total_return_pct": total_return,
            "unrealized_pnl": unrealized_pnl,
            "num_positions": len(self.positions),
            "positions": position_details,
            "total_brokerage": self.total_brokerage,
            "total_stt": self.total_stt,
            "total_other": self.total_other,
            "total_slippage": self.total_slippage
        }

    def get_positions(self) -> List[Position]:
        """Get list of current positions."""
        return list(self.positions.values())

    def has_position(self, symbol: str) -> bool:
        """Check if portfolio has position in symbol."""
        return symbol in self.positions

    def get_position_qty(self, symbol: str) -> int:
        """Get quantity held for a symbol."""
        if symbol in self.positions:
            return self.positions[symbol].qty
        return 0

    def get_transactions(self) -> List[Transaction]:
        """Get all transactions."""
        return self.transactions

    def get_summary(self) -> dict:
        """Get portfolio summary."""
        return {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "num_positions": len(self.positions),
            "symbols": list(self.positions.keys()),
            "total_transactions": len(self.transactions),
            "total_brokerage": self.total_brokerage,
            "total_stt": self.total_stt,
            "total_other": self.total_other,
            "total_slippage": self.total_slippage
        }
