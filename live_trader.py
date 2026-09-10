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

        # Initialize components (init_db first: fresh clones have no
        # trading.db yet, and load_positions_from_db() below queries it)
        init_db()
        self.risk_manager = RiskManager(
            initial_capital,
            max_position_pct=config.MAX_POSITION_PCT,
            max_open_positions=config.MAX_OPEN_POSITIONS,
            daily_loss_limit_pct=config.DAILY_LOSS_LIMIT_PCT,
            max_drawdown_pct=config.MAX_DRAWDOWN_PCT,
            min_risk_reward=config.MIN_RISK_REWARD,
            heat_cap_pct=config.HEAT_CAP_PCT,
            target_vol_pct=config.TARGET_VOL_PCT,
            throttle_start_mult=config.THROTTLE_START_MULT,
        )
        self.paper_portfolio = PaperPortfolio(
            initial_capital,
            brokerage_pct=config.BROKERAGE_PCT,
            stt_pct=config.STT_PCT,
            exchange_pct=config.EXCHANGE_PCT,
            sebi_pct=config.SEBI_PCT,
            stamp_pct=config.STAMP_PCT,
            gst_pct=config.GST_PCT,
            slippage_max_pct=config.SLIPPAGE_MAX_PCT,
            slippage_seed=config.SLIPPAGE_SEED,
        )
        self.paper_portfolio.load_positions_from_db()  # Load existing positions
        self.stock_selector = StockSelector(broker)

        # Trading state
        self.universe: List[str] = []
        self.watchlist: List[str] = []
        self.ranked_all: List[dict] = []  # full pre-market ranking (reserves live here)
        self._reselect_done: set = set()  # (date, hh, mm) already re-ranked
        self.session_start_capital = initial_capital

        log.info(f"LiveTrader initialized. Mode: {'LIVE' if is_live else 'PAPER'}")

    @staticmethod
    def _ist_now():
        """Current time in IST (market timezone)."""
        import pytz

        return datetime.now(pytz.timezone("Asia/Kolkata"))

    @staticmethod
    def _eod_exit_frac(now_ist) -> float:
        """Fraction of each position to liquidate this tick in the EOD window."""
        hm = (now_ist.hour, now_ist.minute)
        if hm >= (config.FULL_EXIT_HOUR, config.FULL_EXIT_MINUTE):
            return 1.0
        if hm >= (config.SCALE_START_HOUR, config.SCALE_START_MINUTE):
            return 0.5
        return 0.0

    @staticmethod
    def _sell_row(symbol, result, exit_reason, pos=None):
        """Build a trades-table row for a SELL (costs + MFE/MAE included)."""
        row = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": "SELL",
            "qty": result["qty"],
            "price": result["price"],
            "value": result["value"],
            "pnl": result["net_pnl"],
            "pnl_pct": result["pnl_pct"],
            "exit_reason": exit_reason,
            "brokerage": result.get("brokerage"),
            "stt": result.get("stt"),
            "other_costs": result.get("other_costs"),
            "slippage_cost": result.get("slippage_cost"),
        }
        if pos is not None:
            row["mfe"] = pos.mfe
            row["mae"] = pos.mae
        return row

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
            # Rank the full universe on daily data (works at any time),
            # then take the sector-capped top_n as the watchlist
            self.ranked_all = self.stock_selector.rank_stocks(
                self.universe, interval="1d", bars=100
            )
            top_stocks = self.stock_selector.apply_sector_caps(
                self.ranked_all, config.TOP_STOCKS
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

        self._subscribe_feed()

    def _subscribe_feed(self) -> None:
        """Subscribe the watchlist to streaming LTP (no-op if unsupported)."""
        starter = getattr(self.broker, "start_feed", None)
        if starter is not None:
            try:
                starter(self.watchlist)
            except Exception as e:
                log.error(f"Feed subscribe failed: {e}")

    def maybe_reselect(self) -> None:
        """Re-rank watchlist at configured times (default 09:30, 11:00 IST)."""
        now = self._ist_now()
        key = (now.date().isoformat(), now.hour, now.minute)
        for hh, mm in config.RESELECT_TIMES:
            slot = (now.date().isoformat(), hh, mm)
            if (now.hour, now.minute) >= (hh, mm) and slot not in self._reselect_done:
                self._reselect_done.add(slot)
                self._do_reselect()
                break

    def _do_reselect(self) -> None:
        """Score watchlist + reserves on 5m action; keep the best top_n."""
        if not self.ranked_all:
            return
        reserve_syms = [
            m["symbol"] for m in self.ranked_all if m["symbol"] not in self.watchlist
        ][:20]
        # Never evict symbols we hold - re-ranking only affects entries
        held = {pos.symbol for pos in self.paper_portfolio.get_positions()}
        candidates = [s for s in self.watchlist if s not in held] + reserve_syms

        scored = []
        for symbol in candidates:
            try:
                df = self.broker.get_ohlcv(symbol, "5m", 60)
                score, _ = self.stock_selector.score_intraday(symbol, df)
                if score > 0:
                    scored.append((score, symbol))
            except Exception as e:
                log.error(f"Reselect: skipping {symbol}: {e}")
        scored.sort(reverse=True)

        keep = [s for s in self.watchlist if s in held]
        for _, symbol in scored:
            if symbol not in keep:
                keep.append(symbol)
            if len(keep) >= config.TOP_STOCKS:
                break
        dropped = [s for s in self.watchlist if s not in keep]
        added = [s for s in keep if s not in self.watchlist]
        self.watchlist = keep[: config.TOP_STOCKS]
        log.info(f"RESELECT: dropped={dropped} added={added} watchlist={len(self.watchlist)}")
        self._subscribe_feed()

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
        now_ist = self._ist_now()
        self.maybe_reselect()

        # First: Manage existing positions (MFE/MAE, EOD wind-down, trail,
        # partials, scratch, SL/TP)
        positions = self.paper_portfolio.get_positions()
        for pos in positions:
            try:
                symbol = pos.symbol
                df = self.broker.get_ohlcv(symbol, "5m", 50)
                if len(df) < 2:
                    continue

                current_price = df["close"].iloc[-1]
                bar_high = df["high"].iloc[-1]
                bar_low = df["low"].iloc[-1]

                # MFE/MAE tracking (R multiples vs initial entry risk)
                if pos.initial_risk > 0:
                    pos.mfe = max(
                        pos.mfe, (bar_high - pos.avg_price) / pos.initial_risk)
                    pos.mae = min(
                        pos.mae, (bar_low - pos.avg_price) / pos.initial_risk)

                late_day = (now_ist.hour, now_ist.minute) >= (
                    config.TIGHTEN_HOUR, config.TIGHTEN_MINUTE)
                trail_dist = pos.trail_distance_pct * (
                    config.TRAIL_TIGHTEN_MULT if late_day else 1.0)

                # Staged EOD wind-down: half of qty per tick from 15:00, all at 15:20
                eod_frac = self._eod_exit_frac(now_ist)
                if eod_frac > 0 and pos.qty > 0:
                    sell_qty = (pos.qty if eod_frac >= 1.0
                                else max(1, int(pos.qty * eod_frac)))
                    sell_qty = min(sell_qty, pos.qty)
                    result = self.paper_portfolio.execute_sell(
                        symbol, sell_qty, current_price
                    )
                    if result["success"]:
                        log.info(
                            f"EOD SCALE: {symbol} - Qty: {sell_qty}, "
                            f"P&L: Rs.{result['net_pnl']:.2f}"
                        )
                        self.risk_manager.update_daily_pnl(result["net_pnl"])
                        self.risk_manager.update_capital(self.get_portfolio_value())
                        insert_trade(self._sell_row(symbol, result, "EOD_SCALE", pos))
                    else:
                        log.error(f"EOD SCALE FAILED: {symbol} - {result['error']}")
                    continue

                # Trailing stop: ratchet SL up once profit >= activation.
                # Must run BEFORE the SL/TP checks (and without requiring
                # price > take_profit) so gains are locked in on pullbacks.
                if pos.trailing_stop and pos.avg_price > 0:
                    profit_pct = (current_price - pos.avg_price) / pos.avg_price
                    if profit_pct >= pos.trail_activation_pct:
                        new_stop = current_price * (1 - trail_dist)
                        if new_stop > pos.stop_loss:
                            pos.stop_loss = new_stop
                            log.info(
                                f"TRAILING STOP UPDATED: {symbol} - New SL: {new_stop:.2f} ({profit_pct * 100:.1f}% profit)"
                            )

                stop_loss = pos.stop_loss
                take_profit = pos.take_profit

                if stop_loss <= 0 or take_profit <= 0:
                    continue

                # R multiple vs live target (TP can move after averaging)
                r_mult = None
                if take_profit > pos.avg_price and pos.initial_risk > 0:
                    r_mult = (current_price - pos.avg_price) / pos.initial_risk

                # Partials: sell PARTIAL_FRAC at PARTIAL_R, SL to breakeven.
                # Late-day the threshold drops to SCALE_1430_R.
                partial_at = config.SCALE_1430_R if late_day else config.PARTIAL_R
                if (not pos.scaled and r_mult is not None and r_mult >= partial_at
                        and pos.qty >= 2):
                    sell_qty = min(max(1, int(pos.qty * config.PARTIAL_FRAC)),
                                   pos.qty - 1)
                    result = self.paper_portfolio.execute_sell(
                        symbol, sell_qty, current_price
                    )
                    if result["success"]:
                        pos.scaled = True
                        pos.stop_loss = max(pos.stop_loss, pos.avg_price)
                        stop_loss = pos.stop_loss
                        log.info(
                            f"SCALED 1R: {symbol} - Qty: {sell_qty}, "
                            f"P&L: Rs.{result['net_pnl']:.2f}"
                        )
                        self.risk_manager.update_daily_pnl(result["net_pnl"])
                        self.risk_manager.update_capital(self.get_portfolio_value())
                        insert_trade(self._sell_row(symbol, result, "SCALED_1R", pos))
                    else:
                        log.error(f"SCALE FAILED: {symbol} - {result['error']}")

                # Scratch: no progress within SCRATCH_BARS (unscaled only)
                age_min = ((now - pos.entry_time).total_seconds() / 60
                           if pos.entry_time else 0)
                if (not pos.scaled and r_mult is not None
                        and age_min >= config.SCRATCH_BARS * 5
                        and r_mult < config.SCRATCH_R):
                    result = self.paper_portfolio.execute_sell(
                        symbol, pos.qty, current_price
                    )
                    if result["success"]:
                        log.info(
                            f"SCRATCHED: {symbol} - R: {r_mult:.2f}, "
                            f"P&L: Rs.{result['net_pnl']:.2f}"
                        )
                        self.risk_manager.update_daily_pnl(result["net_pnl"])
                        self.risk_manager.update_capital(self.get_portfolio_value())
                        insert_trade(self._sell_row(symbol, result, "SCRATCH", pos))
                    else:
                        log.error(f"SCRATCH FAILED: {symbol} - {result['error']}")
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
                        insert_trade(self._sell_row(symbol, result, "STOP_LOSS", pos))
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
                        insert_trade(self._sell_row(symbol, result, "TAKE_PROFIT", pos))
                    continue

            except Exception as e:
                log.error(f"Error checking position {symbol}: {e}")

        # Second: Check for new entry signals (closed after ENTRY_CUTOFF)
        entries_open = (now_ist.hour, now_ist.minute) < (
            config.ENTRY_CUTOFF_HOUR, config.ENTRY_CUTOFF_MINUTE)
        if not entries_open:
            log.info("Past entry cutoff - no new entries this bar")
        for symbol in self.watchlist:
            try:
                if not entries_open:
                    break
                # Skip if already in position
                if self.paper_portfolio.has_position(symbol):
                    continue

                # Fetch OHLCV data (5m for signals, 15m for trend filter)
                df = self.broker.get_ohlcv(symbol, "5m", 50)

                if len(df) < self.strategy.required_bars():
                    continue

                df_15m = None
                try:
                    df_15m = self.broker.get_ohlcv(symbol, "15m", 60)
                except Exception as e:
                    log.error(f"15m data unavailable for {symbol}: {e}")

                # Generate signals
                signals = self.strategy.generate_signals(symbol, df, df_15m)

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
                        {
                            "symbol": pos.symbol,
                            "qty": pos.qty,
                            "avg_price": pos.avg_price,
                            "stop_loss": pos.stop_loss,
                        }
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
                                    "brokerage": result.get("brokerage"),
                                    "stt": result.get("stt"),
                                    "other_costs": result.get("other_costs"),
                                    "slippage_cost": result.get("slippage_cost"),
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

                price = prices.get(symbol)
                if price is None:
                    # LTP missing: fall back to the last 5m close so the
                    # intraday-only invariant (never hold overnight) holds.
                    log.error(f"LTP missing for {symbol}, trying last 5m close")
                    try:
                        df = self.broker.get_ohlcv(symbol, "5m", 5)
                        price = float(df["close"].iloc[-1]) if len(df) else None
                    except Exception as e:
                        price = None
                        log.error(f"Fallback price failed for {symbol}: {e}")
                    if price is None:
                        log.error(
                            f"CRITICAL: could not close {symbol} x{qty} - left open overnight"
                        )
                        continue

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
                        self._sell_row(symbol, result, "FORCE_CLOSE_EOD", position)
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
    strategy = IntradayMomentumStrategy(
        lookback=config.LOOKBACK,
        volume_multiplier=config.VOLUME_MULTIPLIER,
        min_risk_reward=config.MIN_RISK_REWARD,
        max_stop_loss_pct=config.MAX_STOP_LOSS_PCT,
        cooldown_bars=config.COOLDOWN_BARS,
        trend_ema=config.TREND_EMA,
        vwap_required=config.VWAP_REQUIRED,
    )

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
