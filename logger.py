# logger.py
"""
Structured Logging Module

Provides consistent logging across the application.
Logs to both console and file.

Usage:
    log = get_logger("live_trader")
    log.info("Starting trading session")
    log.error("Connection failed")
"""

import logging
import sys
from datetime import datetime

from paths import LOG_DIR

# Create logs directory
LOG_DIR.mkdir(exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger.
    
    Args:
        name: Logger name (e.g., 'live_trader', 'strategy')
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Format: [TIMESTAMP] [LEVEL] [NAME] Message
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # File handler - daily rotation
        today = datetime.now().strftime('%Y%m%d')
        log_file = LOG_DIR / f"{name}_{today}.log"
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


class TradeLogger:
    """Specialized logger for trade events."""
    
    def __init__(self):
        self.logger = get_logger("trades")
    
    def log_signal(self, signal, approved: bool, reason: str = None):
        """Log a trading signal."""
        status = "APPROVED" if approved else "REJECTED"
        msg = f"SIGNAL: {signal.symbol} {signal.action} @ {signal.entry_price:.2f} [{status}]"
        if reason:
            msg += f" - {reason}"
        self.logger.info(msg)
    
    def log_trade(self, symbol: str, side: str, qty: int, price: float, pnl: float = None):
        """Log a trade execution."""
        msg = f"TRADE: {side} {qty} {symbol} @ {price:.2f}"
        if pnl is not None:
            msg += f" P&L: Rs.{pnl:,.2f}"
        self.logger.info(msg)
    
    def log_portfolio(self, cash: float, positions_value: float, total_value: float):
        """Log portfolio status."""
        self.logger.info(
            f"PORTFOLIO: Cash=Rs.{cash:,.0f}, Positions=Rs.{positions_value:,.0f}, "
            f"Total=Rs.{total_value:,.0f}"
        )


# Convenience function
def log_trade_event(event_type: str, **kwargs):
    """Quick log function for trade events."""
    logger = get_logger("events")
    logger.info(f"{event_type}: {kwargs}")
