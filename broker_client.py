# broker_client.py
"""
Abstract broker interface for paper trading.
This module provides read-only access to market data and positions.
Order placement is intentionally disabled for paper trading safety.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import pandas as pd


@dataclass
class Quote:
    """Market quote data for a symbol."""
    symbol: str
    ltp: float           # Last traded price
    volume: int
    bid: float
    ask: float
    timestamp: pd.Timestamp


class BrokerClient(ABC):
    """
    Abstract broker interface for paper trading.
    
    All broker implementations must subclass this.
    Note: Order placement methods are intentionally excluded
    to prevent accidental live trading in paper mode.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Authenticate and establish session. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up session."""
        ...

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """Return latest quote for a symbol."""
        ...

    @abstractmethod
    def get_ohlcv(self, symbol: str, interval: str, bars: int) -> pd.DataFrame:
        """
        Return OHLCV DataFrame with columns [open, high, low, close, volume].
        
        Args:
            symbol: Trading symbol
            interval: Time interval (e.g., "5m", "1h", "1d")
            bars: Number of bars to fetch
            
        Returns:
            DataFrame with OHLCV data
        """
        ...

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Return list of open positions (for monitoring, not trading)."""
        ...

    @abstractmethod
    def get_holdings(self) -> list[dict]:
        """Return list of holdings/delivery stocks."""
        ...

    @abstractmethod
    def get_ltp(self, symbols: list[str]) -> dict[str, float]:
        """
        Get Last Traded Price for multiple symbols.
        
        Args:
            symbols: List of trading symbols
            
        Returns:
            Dictionary mapping symbol to LTP
        """
        ...
