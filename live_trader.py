# live_trader.py
"""
Live Trading Orchestrator

Main trading loop that coordinates:
- Stock selection (top 20 momentum)
- Signal generation
- Risk management
- Paper portfolio execution
- Database logging

Usage:
    python live_trader.py           # Paper trading mode (default)
    python live_trader.py --live    # Live trading (requires confirmation)
"""

import argparse
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

from config import config
from groww_broker import GrowwBroker
from base_strategy import BaseStrategy
from intraday_strategy import IntradayMomentumStrategy
from risk_manager import RiskManager, RiskDecision
from paper_portfolio import PaperPortfolio
from stock_selector import StockSelector
from db import init_db, insert_signal, insert_trade, insert_session, backup_db
from logger import get_logger

log = get_logger("live_trader")


class LiveTrader:
    """
    Main trading orchestrator.

    Manages the complete trading lifecycle:
    1. Pre-market: Select top 20 momentum stocks
    2. On-bar: Generate signals, check risk, execute in paper portfolio
    3. End-of-day: Close all positions, save session summary
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        broker: GrowwBroker,
        initial_capital: float = 2_000_000,
        is_live: bool = False,
    ):
        """
        Initialize live trader.

        Args:
            strategy: Trading strategy (implements BaseStrategy)
            broker: Broker client for market data
            initial_capital: Starting capital
            is_live: If True, uses real broker (requires confirmation)
        """
        self.strategy = strategy
        self.broker = broker
        self.is_live = is_live
        self.initial_capital = initial_capital

        # Initialize components
        self.risk_manager = RiskManager(
            initial_capital,
            max_position_pct=config.MAX_POSITION_PCT,
            max_open_positions=config.MAX_OPEN_POSITIONS,
            daily_loss_limit_pct=config.DAILY_LOSS_LIMIT_PCT,
            max_drawdown_pct=config.MAX_DRAWDOWN_PCT,
            min_risk_reward=config.MIN_RISK_REWARD,
        )
        self.paper_portfolio = PaperPortfolio(initial_capital)
        self.paper_portfolio.load_positions_from_db()  # Load existing positions
        self.stock_selector = StockSelector(broker)

        # Trading state
        self.universe: List[str] = []
        self.watchlist: List[str] = []
        self.session_start_capital = initial_capital

        log.info(f"LiveTrader initialized. Mode: {'LIVE' if is_live else 'PAPER'}")

    def pre_market(self) -> None:
        """
        9:00 AM - Pre-market preparation.

        Selects top 20 momentum stocks for the day.
        """
        backup_db()

        log.info("=" * 60)
        log.info("PRE-MARKET: Selecting top momentum stocks...")
        log.info("=" * 60)

        # Universe of stocks to evaluate
        if not self.universe:
            self.universe = config.NSE_STOCKS

        try:
            # Select top momentum stocks using daily data (works at any time)
            top_stocks = self.stock_selector.select_top_stocks(
                self.universe, top_n=config.TOP_STOCKS, interval="1d", bars=100
            )

            self.watchlist = self.stock_selector.get_watchlist(top_stocks)

            log.info(f"Selected {len(self.watchlist)} stocks for watchlist:")
            for i, symbol in enumerate(self.watchlist[:10], 1):
                log.info(f"  {i}. {symbol}")
            if len(self.watchlist) > 10:
                log.info(f"  ... and {len(self.watchlist) - 10} more")

        except Exception as e:
            log.error(f"Error in pre-market selection: {e}")
            # Fallback to default watchlist
            self.watchlist = self.universe[:20]
            log.info(f"Using fallback watchlist: {len(self.watchlist)} stocks")

    def on_bar(self) -> None:
        """
        Every 5 minutes during market hours.

        For each stock in watchlist:
        1. Fetch OHLCV data
        2. Generate signals
        3. Check risk management
        4. Execute in paper portfolio
        5. Log to database
        """
        log.info("-" * 60)
        log.info(f"ON-BAR: Processing {len(self.watchlist)} stocks...")
        log.info("-" * 60)

        now = datetime.now()

        # First: Check existing positions for stop loss / take profit
        positions = self.paper_portfolio.get_positions()
        for pos in positions:
            try:
                symbol = pos.symbol
                df = self.broker.get_ohlcv(symbol, "5m", 50)
                if len(df) < 2:
                    continue

                current_price = df["close"].iloc[-1]

                stop_loss = pos.stop_loss
                take_profit = pos.take_profit

                if stop_loss <= 0 or take_profit <= 0:
                    continue

                # Check stop loss
                if current_price <= stop_loss:
                    log.info(
                        f"STOP LOSS HIT: {symbol} - Price: {current_price}, SL: {stop_loss}"
                    )
                    result = self.paper_portfolio.execute_sell(
                        symbol, pos.qty, current_price
                    )
                    if result["success"]:
                        log.info(f"CLOSED: {symbol} - P&L: Rs.{result['net_pnl']:.2f}")
                        self.risk_manager.update_daily_pnl(result["net_pnl"])
                        self.risk_manager.update_capital(self.get_portfolio_value())
                        insert_trade(
                            {
                                "timestamp": now.isoformat(),
                                "symbol": symbol,
                                "side": "SELL",
                                "qty": result["qty"],
                                "price": result["price"],
                                "value": result["value"],
                                "pnl": result["net_pnl"],
                                "pnl_pct": result["pnl_pct"],
                                "exit_reason": "STOP_LOSS",
                            }
                        )
                    continue

                # Check take profit
                if current_price >= take_profit:
                    log.info(
                        f"TAKE PROFIT HIT: {symbol} - Price: {current_price}, TP: {take_profit}"
                    )
                    result = self.paper_portfolio.execute_sell(
                        symbol, pos.qty, current_price
                    )
                    if result["success"]:
                        log.info(f"CLOSED: {symbol} - P&L: Rs.{result['net_pnl']:.2f}")
                        self.risk_manager.update_daily_pnl(result["net_pnl"])
                        self.risk_manager.update_capital(self.get_portfolio_value())
                        insert_trade(
                            {
                                "timestamp": now.isoformat(),
                                "symbol": symbol,
                                "side": "SELL",
                                "qty": result["qty"],
                                "price": result["price"],
                                "value": result["value"],
                                "pnl": result["net_pnl"],
                                "pnl_pct": result["pnl_pct"],
                                "exit_reason": "TAKE_PROFIT",
                            }
                        )
                    continue

                # Check trailing stop (if activated)
                if pos.trailing_stop and current_price > take_profit:
                    profit_pct = (current_price - pos.avg_price) / pos.avg_price
                    if profit_pct >= pos.trail_activation_pct:
                        new_stop = current_price * (1 - pos.trail_distance_pct)
                        if new_stop > pos.stop_loss:
                            pos.stop_loss = new_stop
                            log.info(
                                f"TRAILING STOP UPDATED: {symbol} - New SL: {new_stop:.2f} ({profit_pct * 100:.1f}% profit)"
                            )

            except Exception as e:
                log.error(f"Error checking position {symbol}: {e}")

        # Second: Check for new entry signals
        for symbol in self.watchlist:
            try:
                # Skip if already in position
                if self.paper_portfolio.has_position(symbol):
                    continue

                # Fetch OHLCV data
                df = self.broker.get_ohlcv(symbol, "5m", 50)

                if len(df) < self.strategy.required_bars():
                    continue

                # Generate signals
                signals = self.strategy.generate_signals(symbol, df)

                for signal in signals:
                    # Log signal to database
                    signal_data = {
                        "timestamp": now.isoformat(),
                        "symbol": signal.symbol,
                        "action": signal.action,
                        "confidence": signal.confidence,
                        "entry_price": signal.entry_price,
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
                        "reason": signal.reason,
                        "strategy": self.strategy.name,
                    }

                    # Check risk management
                    current_positions = [
                        {"symbol": pos.symbol, "qty": pos.qty}
                        for pos in self.paper_portfolio.get_positions()
                    ]

                    portfolio_value = self.get_portfolio_value()
                    available_cash = self.paper_portfolio.cash

                    decision = self.risk_manager.approve(
                        signal, current_positions, available_cash
                    )

                    # Update signal data with risk decision
                    signal_data.update(
                        {
                            "approved": decision.approved,
                            "rejection_reason": decision.reason
                            if not decision.approved
                            else None,
                            "adjusted_qty": decision.adjusted_qty,
                        }
                    )

                    insert_signal(signal_data)

                    if decision.approved:
                        log.info(f"SIGNAL APPROVED: {symbol} - {decision.reason}")

                        # Execute in paper portfolio with stop loss and take profit
                        result = self.paper_portfolio.execute_buy(
                            symbol,
                            decision.adjusted_qty,
                            signal.entry_price,
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit,
                        )

                        if result["success"]:
                            log.info(
                                f"TRADE EXECUTED: {symbol} - Qty: {result['qty']}, "
                                f"Price: Rs.{result['price']:.2f}, "
                                f"Cost: Rs.{result['total_cost']:,.0f}"
                            )

                            # Save trade to database
                            insert_trade(
                                {
                                    "timestamp": datetime.now().isoformat(),
                                    "symbol": symbol,
                                    "side": "BUY",
                                    "qty": result["qty"],
                                    "price": result["price"],
                                    "value": result["total_cost"],
                                    "pnl": 0,
                                    "pnl_pct": 0,
                                    "exit_reason": "SIGNAL_ENTRY",
                                }
                            )
                        else:
                            log.error(f"TRADE FAILED: {symbol} - {result['error']}")
                    else:
                        log.info(f"SIGNAL REJECTED: {symbol} - {decision.reason}")

            except Exception as e:
                log.error(f"Error processing {symbol}: {e}")
                continue

        # Log portfolio status
        self.log_portfolio_status()

    def get_portfolio_value(self) -> float:
        """Get current portfolio value."""
        try:
            # Get current prices for all positions
            positions = self.paper_portfolio.get_positions()
            if not positions:
                return self.paper_portfolio.cash

            symbols = [pos.symbol for pos in positions]
            prices = self.broker.get_ltp(symbols)

            portfolio_data = self.paper_portfolio.get_portfolio_value(prices)
            return portfolio_data["total_value"]
        except Exception as e:
            log.error(f"Error getting portfolio value: {e}")
            return self.paper_portfolio.cash

    def log_portfolio_status(self) -> None:
        """Log current portfolio status."""
        try:
            portfolio_value = self.get_portfolio_value()
            positions = self.paper_portfolio.get_positions()

            log.info(f"PORTFOLIO STATUS:")
            log.info(f"  Cash: Rs.{self.paper_portfolio.cash:,.0f}")
            log.info(f"  Positions: {len(positions)}")
            log.info(f"  Total Value: Rs.{portfolio_value:,.0f}")

            pnl = portfolio_value - self.initial_capital
            pnl_pct = (pnl / self.initial_capital) * 100
            log.info(f"  P&L: Rs.{pnl:,.0f} ({pnl_pct:+.2f}%)")

        except Exception as e:
            log.error(f"Error logging portfolio status: {e}")

    def force_close_all(self) -> None:
        """
        3:25 PM - Close all open positions.

        Executed regardless of P&L to avoid overnight risk.
        """
        log.info("=" * 60)
        log.info("FORCE CLOSE: Closing all positions at 3:25 PM")
        log.info("=" * 60)

        positions = self.paper_portfolio.get_positions()

        if not positions:
            log.info("No open positions to close")
            return

        try:
            # Get current prices
            symbols = [pos.symbol for pos in positions]
            prices = self.broker.get_ltp(symbols)

            for position in positions:
                symbol = position.symbol
                qty = position.qty

                if symbol in prices:
                    price = prices[symbol]

                    # Execute sell
                    result = self.paper_portfolio.execute_sell(symbol, qty, price)

                    if result["success"]:
                        log.info(
                            f"CLOSED: {symbol} - Qty: {qty}, "
                            f"Price: Rs.{result['price']:.2f}, "
                            f"P&L: Rs.{result['net_pnl']:,.2f}"
                        )

                        # Log trade to database
                        insert_trade(
                            {
                                "timestamp": datetime.now().isoformat(),
                                "symbol": symbol,
                                "side": "SELL",
                                "qty": qty,
                                "price": result["price"],
                                "value": result["value"],
                                "pnl": result["net_pnl"],
                                "pnl_pct": result["pnl_pct"],
                                "exit_reason": "FORCE_CLOSE_EOD",
                            }
                        )

                        # Update risk manager P&L
                        self.risk_manager.update_daily_pnl(result["net_pnl"])
                    else:
                        log.error(f"Failed to close {symbol}: {result['error']}")

        except Exception as e:
            log.error(f"Error during force close: {e}")

    def end_session(self) -> None:
        """End trading session and save summary."""
        log.info("=" * 60)
        log.info("END SESSION: Saving session summary")
        log.info("=" * 60)

        try:
            portfolio_value = self.get_portfolio_value()

            # Calculate session metrics
            total_pnl = portfolio_value - self.session_start_capital
            positions = self.paper_portfolio.get_positions()
            transactions = self.paper_portfolio.get_transactions()

            # Count trades
            buy_trades = [t for t in transactions if t.side == "BUY"]
            sell_trades = [t for t in transactions if t.side == "SELL"]

            # Calculate win/loss - need to calculate P&L from transaction data
            winning_trades = 0
            losing_trades = 0
            for sell in sell_trades:
                # Find corresponding buy
                for buy in buy_trades:
                    if buy.symbol == sell.symbol:
                        # Calculate P&L
                        pnl = sell.net_value - buy.net_value
                        if pnl > 0:
                            winning_trades += 1
                        else:
                            losing_trades += 1
                        break

            # Save session to database
            session_data = {
                "date": date.today().isoformat(),
                "start_capital": self.session_start_capital,
                "end_capital": portfolio_value,
                "total_pnl": total_pnl,
                "total_trades": len(sell_trades),
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "max_drawdown_pct": 0.0,  # Calculate from equity curve
                "sharpe_ratio": 0.0,  # Calculate from returns
                "notes": f"Strategy: {self.strategy.name}, Mode: {'LIVE' if self.is_live else 'PAPER'}",
            }

            insert_session(session_data)

            backup_db()

            log.info(f"SESSION SUMMARY:")
            log.info(f"  Start Capital: Rs.{self.session_start_capital:,.0f}")
            log.info(f"  End Capital: Rs.{portfolio_value:,.0f}")
            log.info(f"  Total P&L: Rs.{total_pnl:,.0f}")
            log.info(
                f"  Trades: {len(sell_trades)} ({winning_trades} wins, {losing_trades} losses)"
            )
            log.info(f"  Remaining Positions: {len(positions)}")

        except Exception as e:
            log.error(f"Error saving session summary: {e}")

    def run(self) -> None:
        """
        Main trading loop.

        Orchestrates the complete trading day:
        - 9:00 AM: Pre-market stock selection
        - 9:15-3:25: Trading every 5 minutes
        - 3:25 PM: Force close all positions
        """
        # Initialize database
        init_db()

        # Connect to broker
        log.info("Connecting to broker...")
        if not self.broker.connect():
            log.error("Failed to connect to broker. Exiting.")
            sys.exit(1)
        log.info("Connected to broker successfully")

        # Record session start capital
        self.session_start_capital = self.get_portfolio_value()

        # Save session start to DB immediately so API can query it
        insert_session(
            {
                "date": date.today().isoformat(),
                "start_capital": self.session_start_capital,
                "end_capital": self.session_start_capital,
                "total_pnl": 0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "max_drawdown_pct": 0,
                "sharpe_ratio": 0,
                "notes": f"Strategy: {self.strategy.name}, Mode: {'LIVE' if self.is_live else 'PAPER'}",
            }
        )

        log.info(f"Starting trading session")
        log.info(f"Initial Capital: Rs.{self.initial_capital:,.0f}")
        log.info(f"Mode: {'LIVE' if self.is_live else 'PAPER'}")
        log.info(f"Strategy: {self.strategy.name}")

        try:
            # Pre-market stock selection (9:00 AM)
            self.pre_market()

            # Trading loop (9:15 AM - 3:25 PM)
            log.info("Starting trading loop...")

            # Run continuously during market hours
            import pytz

            IST = pytz.timezone("Asia/Kolkata")

            while True:
                now = datetime.now(IST)
                current_hour = now.hour
                current_minute = now.minute

                log.info(f"Market check: {current_hour}:{current_minute}")

                # Stop after market close (3:25 PM)
                if current_hour >= 15 and current_minute >= 25:
                    log.info("Market closed. Stopping trading loop.")
                    break

                # Only trade during market hours (9:15 AM - 3:25 PM)
                # Market opens at 9:15, so check: (hour > 9) OR (hour == 9 AND minute >= 15)
                market_open = (current_hour > 9) or (
                    current_hour == 9 and current_minute >= 15
                )
                market_close = current_hour >= 15 and current_minute >= 25

                if market_open and not market_close:
                    log.info("Calling on_bar...")
                    self.on_bar()
                else:
                    log.info(
                        f"Market {'not open yet' if not market_open else 'closed'}, skipping on_bar"
                    )

                # Wait 5 minutes (300 seconds) between iterations
                log.info(f"Waiting 5 minutes until next check...")
                time.sleep(300)  # 5 minutes

            # Force close all positions (3:25 PM)
            self.force_close_all()

            # End session and save summary
            self.end_session()

        except KeyboardInterrupt:
            log.info("\nTrading session interrupted by user")
            self.force_close_all()
            self.end_session()

        except Exception as e:
            log.error(f"Error in trading loop: {e}")
            self.force_close_all()
            self.end_session()

        finally:
            # Disconnect from broker
            self.broker.disconnect()
            log.info("Trading session ended")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Auto Trading Bot")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live trading (requires confirmation)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=config.INITIAL_CAPITAL,
        help=f"Initial capital (default: {int(config.INITIAL_CAPITAL):,})",
    )

    args = parser.parse_args()

    # Live trading confirmation
    if args.live:
        print("=" * 60)
        print("WARNING: LIVE TRADING MODE")
        print("=" * 60)
        confirm = input("Type 'CONFIRM' to proceed with live trading: ")
        if confirm != "CONFIRM":
            print("Aborted.")
            return

    # Initialize components
    broker = GrowwBroker()
    strategy = IntradayMomentumStrategy()  # 5-minute intraday strategy

    # Create trader
    trader = LiveTrader(
        strategy=strategy,
        broker=broker,
        initial_capital=args.capital,
        is_live=args.live,
    )

    # Run trading session
    trader.run()


if __name__ == "__main__":
    main()
