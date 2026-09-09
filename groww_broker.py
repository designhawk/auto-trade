# groww_broker.py
"""
Groww broker implementation for paper trading using the official growwapi package.

This module provides read-only market data access for paper trading.
Order placement is intentionally disabled to prevent accidental live trading.

Required environment variables:
- GROWW_TOTP_TOKEN: Your TOTP token from Groww Cloud API Keys page
- GROWW_TOTP_SECRET: Your TOTP secret (QR code secret)

Optional:
- GROWW_API_KEY: Alternative authentication method
- GROWW_API_SECRET: Alternative authentication method

Documentation: https://groww.in/trade-api/docs/python-sdk
"""

import os
import time
from typing import Optional
from datetime import datetime
from functools import wraps
import pytz
import pandas as pd
import pyotp
from dotenv import load_dotenv

from broker_client import BrokerClient, Quote


def retry_on_error(max_retries: int = 3, delay: float = 1.0):
    """Decorator to retry API calls on failure."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
            raise last_error
        return wrapper
    return decorator

# Import growwapi
try:
    from growwapi import GrowwAPI, GrowwFeed
except ImportError:
    raise ImportError(
        "growwapi package not installed. Run: pip install growwapi pyotp"
    )

load_dotenv()


class GrowwBroker(BrokerClient):
    """
    Groww implementation of BrokerClient for paper trading.
    
    Provides read-only access to market data:
    - Real-time quotes
    - Historical OHLCV data
    - Portfolio positions and holdings
    - Live market prices (LTP)
    
    Note: Order placement is disabled for safety in paper trading mode.
    
    Supports both TOTP and API Key authentication methods.
    Default is TOTP authentication (recommended - no daily approval required).
    """

    def __init__(self, use_api_key: bool = False):
        """
        Initialize Groww broker.
        
        Args:
            use_api_key: If True, use API Key + Secret authentication.
                        If False (default), use TOTP authentication.
        """
        self._client: Optional[GrowwAPI] = None
        self._feed: Optional[GrowwFeed] = None
        self._use_api_key = use_api_key
        self._access_token: Optional[str] = None
        
    def _get_access_token(self) -> str:
        """
        Generate access token based on authentication method.
        
        Returns:
            Access token string
            
        Raises:
            ValueError: If required credentials are missing
        """
        if self._use_api_key:
            # API Key + Secret method
            api_key = os.getenv("GROWW_API_KEY")
            api_secret = os.getenv("GROWW_API_SECRET")
            
            if not api_key or not api_secret:
                raise ValueError(
                    "API Key authentication requires GROWW_API_KEY and GROWW_API_SECRET "
                    "environment variables"
                )
            
            return GrowwAPI.get_access_token(api_key=api_key, secret=api_secret)
        else:
            # TOTP method (recommended)
            api_key = os.getenv("GROWW_TOTP_TOKEN")
            totp_secret = os.getenv("GROWW_TOTP_SECRET")
            
            if not api_key or not totp_secret:
                raise ValueError(
                    "TOTP authentication requires GROWW_TOTP_TOKEN and GROWW_TOTP_SECRET "
                    "environment variables"
                )
            
            # Generate current TOTP
            totp = pyotp.TOTP(totp_secret).now()
            return GrowwAPI.get_access_token(api_key=api_key, totp=totp)

    def connect(self) -> bool:
        """
        Authenticate and establish connection to Groww API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            print("[CONNECT] Connecting to Groww API...")
            
            # Get access token
            self._access_token = self._get_access_token()
            
            # Initialize Groww API client
            self._client = GrowwAPI(self._access_token)
            
            # Initialize feed client
            self._feed = GrowwFeed(self._client)
            
            # Test connection by fetching holdings
            self._client.get_holdings_for_user(timeout=5)
            
            print("[SUCCESS] Successfully connected to Groww API")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to connect to Groww: {e}")
            return False

    def disconnect(self) -> None:
        """Clean up session and disconnect."""
        if self._client:
            # Clean up feed if active
            if self._feed:
                # Note: growwapi doesn't have explicit disconnect, 
                # but we should unsubscribe from any active feeds
                self._feed = None
            
            self._client = None
            self._access_token = None
            print("[DISCONNECT] Disconnected from Groww API")

    @retry_on_error(max_retries=3, delay=1.0)
    def get_quote(self, symbol: str) -> Quote:
        """
        Get latest quote for a symbol.
        
        Args:
            symbol: NSE trading symbol (e.g., "RELIANCE", "TCS")
            
        Returns:
            Quote object with LTP, volume, bid/ask prices
            
        Raises:
            RuntimeError: If not connected
            Exception: If API call fails
        """
        if not self._client:
            raise RuntimeError("Not connected. Call connect() first.")
        
        try:
            # Fetch quote from Groww API
            response = self._client.get_quote(
                exchange=self._client.EXCHANGE_NSE,
                segment=self._client.SEGMENT_CASH,
                trading_symbol=symbol
            )
            
            # Handle None values gracefully (depth itself may be None)
            ltp = response.get('last_price') or response.get('ltp') or 0.0
            volume = response.get('volume') or 0
            depth = response.get('depth') or {}
            bid = response.get('bid_price') or depth.get('buy', [{}])[0].get('price', ltp)
            ask = response.get('offer_price') or depth.get('sell', [{}])[0].get('price', ltp)
            
            return Quote(
                symbol=symbol,
                ltp=float(ltp) if ltp else 0.0,
                volume=int(volume) if volume else 0,
                bid=float(bid) if bid else 0.0,
                ask=float(ask) if ask else 0.0,
                timestamp=pd.Timestamp.now(tz=pytz.timezone("Asia/Kolkata"))
            )
            
        except Exception as e:
            raise RuntimeError(f"Failed to get quote for {symbol}: {e}")

    @retry_on_error(max_retries=3, delay=1.0)
    def get_ohlcv(self, symbol: str, interval: str, bars: int) -> pd.DataFrame:
        """
        Get OHLCV data for a symbol.
        
        Args:
            symbol: NSE trading symbol
            interval: Time interval - "1m", "5m", "15m", "1h", "1d", etc.
            bars: Number of bars to fetch
            
        Returns:
            DataFrame with columns [open, high, low, close, volume]
            
        Raises:
            RuntimeError: If not connected
            ValueError: If interval format is invalid
        """
        if not self._client:
            raise RuntimeError("Not connected. Call connect() first.")
        
        try:
            # Map interval string to minutes (integer)
            interval_map = {
                "1m": 1,
                "2m": 2,
                "3m": 3,
                "5m": 5,
                "10m": 10,
                "15m": 15,
                "30m": 30,
                "1h": 60,
                "4h": 240,
                "1d": 1440,
                "1w": 10080,
                "1mo": 43200,
            }
            
            if interval not in interval_map:
                raise ValueError(f"Invalid interval: {interval}. Use: {list(interval_map.keys())}")
            
            groww_interval = interval_map[interval]
            
            # Calculate time range based on interval and bars
            IST = pytz.timezone("Asia/Kolkata")
            end_time = datetime.now(IST)
            
            # For intraday intervals, always fetch extra historical data to ensure we have enough
            if interval in ["1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h"]:
                # Fetch from last trading day to ensure we have enough data
                days_back = 1
                while days_back < 7:
                    test_date = end_time - pd.Timedelta(days=days_back)
                    if test_date.weekday() < 5:  # Monday = 0, Friday = 4
                        start_time = test_date.replace(hour=9, minute=15, second=0, microsecond=0)
                        break
                    days_back += 1
            else:
                # Daily/weekly intervals
                if interval.endswith("m"):
                    minutes = int(interval[:-1]) * bars
                    start_time = end_time - pd.Timedelta(minutes=minutes)
                elif interval.endswith("h"):
                    hours = int(interval[:-1]) * bars
                    start_time = end_time - pd.Timedelta(hours=hours)
                elif interval == "1d":
                    start_time = end_time - pd.Timedelta(days=bars)
                elif interval == "1w":
                    start_time = end_time - pd.Timedelta(weeks=bars)
                else:
                    start_time = end_time - pd.Timedelta(days=bars)
            
            # Fetch historical data
            response = self._client.get_historical_candle_data(
                trading_symbol=symbol,
                exchange=self._client.EXCHANGE_NSE,
                segment=self._client.SEGMENT_CASH,
                start_time=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=end_time.strftime("%Y-%m-%d %H:%M:%S"),
                interval_in_minutes=groww_interval
            )
            
            # Convert to DataFrame
            candles = response['candles']
            
            # Take only the requested number of bars
            candles = candles[-bars:] if len(candles) > bars else candles
            
            df = pd.DataFrame(
                candles,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')
            df.set_index('timestamp', inplace=True)
            df = df[['open', 'high', 'low', 'close', 'volume']]
            
            return df
            
        except Exception as e:
            raise RuntimeError(f"Failed to get OHLCV for {symbol}: {e}")

    def get_positions(self) -> list[dict]:
        """
        Return list of open positions.
        
        Returns:
            List of position dictionaries
        """
        if not self._client:
            raise RuntimeError("Not connected. Call connect() first.")
        
        try:
            response = self._client.get_positions_for_user(
                segment=self._client.SEGMENT_CASH
            )
            
            # Filter only positions with non-zero quantity
            positions = [
                pos for pos in response['positions']
                if pos['quantity'] != 0
            ]
            
            return positions
            
        except Exception as e:
            raise RuntimeError(f"Failed to get positions: {e}")

    def get_holdings(self) -> list[dict]:
        """
        Return list of holdings (delivery stocks).
        
        Returns:
            List of holding dictionaries
        """
        if not self._client:
            raise RuntimeError("Not connected. Call connect() first.")
        
        try:
            response = self._client.get_holdings_for_user(timeout=5)
            return response['holdings']
        except Exception as e:
            raise RuntimeError(f"Failed to get holdings: {e}")

    def get_ltp(self, symbols: list[str]) -> dict[str, float]:
        """
        Get Last Traded Price for multiple symbols.
        
        Args:
            symbols: List of NSE trading symbols
            
        Returns:
            Dictionary mapping symbol to LTP
        """
        if not self._client:
            raise RuntimeError("Not connected. Call connect() first.")
        
        try:
            # Format symbols for API
            symbol_strings = [f"NSE_{s}" for s in symbols]
            
            response = self._client.get_ltp(
                segment=self._client.SEGMENT_CASH,
                exchange_trading_symbols=tuple(symbol_strings)
            )
            
            # Convert keys back to simple symbols
            return {
                k.replace("NSE_", ""): float(v)
                for k, v in response.items()
            }
            
        except Exception as e:
            raise RuntimeError(f"Failed to get LTP: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if broker is connected."""
        return self._client is not None

    @property
    def client(self) -> Optional[GrowwAPI]:
        """Access the underlying GrowwAPI client (for advanced usage)."""
        return self._client
