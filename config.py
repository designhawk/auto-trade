# config.py
"""
Central configuration for auto trading system.

All settings should be defined here.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Trading system configuration."""

    # Broker
    GROWW_TOTP_TOKEN = os.getenv("GROWW_TOTP_TOKEN", "")
    GROWW_TOTP_SECRET = os.getenv("GROWW_TOTP_SECRET", "")
    GROWW_API_KEY = os.getenv("GROWW_API_KEY", "")
    GROWW_API_SECRET = os.getenv("GROWW_API_SECRET", "")

    # Trading
    INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "1000000"))
    IS_LIVE = os.getenv("IS_LIVE", "false").lower() == "true"

    # Strategy
    LOOKBACK = int(os.getenv("LOOKBACK", "20"))
    VOLUME_MULTIPLIER = float(os.getenv("VOLUME_MULTIPLIER", "1.5"))
    MIN_RISK_REWARD = float(os.getenv("MIN_RISK_REWARD", "2.0"))
    MAX_STOP_LOSS_PCT = float(os.getenv("MAX_STOP_LOSS_PCT", "0.025"))
    COOLDOWN_BARS = int(os.getenv("COOLDOWN_BARS", "15"))

    # Risk
    MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.08"))
    MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "8"))
    DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.03"))
    MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "0.10"))
    MIN_CASH_RESERVE = float(os.getenv("MIN_CASH_RESERVE", "200000"))

    # Portfolio
    BROKERAGE_PCT = float(os.getenv("BROKERAGE_PCT", "0.0003"))
    STT_PCT = float(os.getenv("STT_PCT", "0.00025"))
    SLIPPAGE_PCT = float(os.getenv("SLIPPAGE_PCT", "0.0002"))

    # Trading Hours (IST)
    MARKET_START_HOUR = 9
    MARKET_START_MINUTE = 15
    MARKET_END_HOUR = 15
    MARKET_END_MINUTE = 25

    # API
    API_PORT = int(os.getenv("API_PORT", "8002"))
    DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8501"))

    # Database
    DB_PATH = "trading.db"
    BACKUP_DIR = "backups"

    # Stock Universe - Nifty 200 (verified with Groww API)
    NSE_STOCKS = [
        "RELIANCE",
        "TCS",
        "HDFCBANK",
        "ICICIBANK",
        "INFY",
        "HINDUNILVR",
        "ITC",
        "SBIN",
        "BHARTIARTL",
        "KOTAKBANK",
        "LT",
        "HCLTECH",
        "AXISBANK",
        "BAJFINANCE",
        "ASIANPAINT",
        "MARUTI",
        "SUNPHARMA",
        "TITAN",
        "ULTRACEMCO",
        "NESTLEIND",
        "POWERGRID",
        "WIPRO",
        "NTPC",
        "BAJAJFINSV",
        "ADANIENT",
        "GRASIM",
        "TATASTEEL",
        "JSWSTEEL",
        "TECHM",
        "COALINDIA",
        "ONGC",
        "HINDALCO",
        "DIVISLAB",
        "CIPLA",
        "DRREDDY",
        "BPCL",
        "EICHERMOT",
        "BRITANNIA",
        "SHREECEM",
        "HEROMOTOCO",
        "APOLLOHOSP",
        "UPL",
        "TATACONSUM",
        "INDUSINDBK",
        "M&M",
        "SBILIFE",
        "HDFCLIFE",
        "ADANIPORTS",
        "DLF",
        "COFORGE",
        "CROMPTON",
        "RECLTD",
        "CANBK",
        "SBICARD",
        "ICICIGI",
        "ICICIPRULI",
        "AUBANK",
        "FEDERALBNK",
        "IDFCFIRSTB",
        "INDHOTEL",
        "JINDALSTEL",
        "JUBLFOOD",
        "LICHSGFIN",
        "LTTS",
        "MUTHOOTFIN",
        "PERSISTENT",
        "RBLBANK",
        "TATACHEM",
        "TORNTPHARM",
        "TRENT",
        "UNIONBANK",
        "VEDL",
        "VOLTAS",
        "ZYDUSLIFE",
        "CHOLAFIN",
        "PFC",
        "GUJGASLTD",
        "IRCTC",
        "JKCEMENT",
        "JKLAKSHMI",
        "JSL",
        "KIRLOSENG",
        "LALPATHLAB",
        "LAURUSLABS",
        "LINDEINDIA",
        "METROBRAND",
        "NAVINFLUOR",
        "OIL",
        "PHOENIXLTD",
        "POLICYBZR",
        "PRAJIND",
        "RATNAMANI",
        "RELAXO",
        "SHRIRAMFIN",
        "TITAGARH",
        "TRITURBINE",
        "UNITDSPR",
        "VGUARD",
        "VINATIORGA",
        "WESTLIFE",
        "ZENSARTECH",
        "AWL",
        "SUNTECK",
        "ADFFOODS",
        "BECTORFOOD",
        "BIKAJI",
        "AMBER",
        "FACT",
        "SWSOLAR",
        "CREATIVEYE",
        "INOXWIND",
        "GODREJPROP",
        "TATAPOWER",
        "TATAELXSI",
        "MFSL",
        "RAILTEL",
        "MANKIND",
        "ALKYLAMINE",
        "APLAPOLLO",
        "BAYERCROP",
        "BSE",
        "CAMS",
        "CAPLIPOINT",
        "CDSL",
        "CLEAN",
        "ABB",
        "ADANIGREEN",
        "AMBUJACEM",
        "APOLLOTYRE",
        "BANKBARODA",
        "DABUR",
        "GAIL",
        "GODREJCP",
        "HAVELLS",
        "IOC",
        "MPHASIS",
        "MARICO",
        "SIEMENS",
        "SUNTV",
        "CYIENT",
        "DEVYANI",
        "EIHOTEL",
        "ENDURANCE",
        "ESCORTS",
        "FORTIS",
        "GRAPHITE",
        "M&MFIN",
        "MANAPPURAM",
        "TATAINVEST",
    ]

    # Selection settings
    TOP_STOCKS = int(os.getenv("TOP_STOCKS", "30"))  # Select top 30 from universe
    MIN_VOLUME = int(os.getenv("MIN_VOLUME", "500000"))  # Min average volume


config = Config()
