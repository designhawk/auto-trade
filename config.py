# config.py
"""
Central configuration for auto trading system.

All settings should be defined here.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _parse_hhmm_list(raw: str) -> list:
    """Parse 'HH:MM,HH:MM' into [(h, m), ...]."""
    out = []
    for tok in (raw or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        h, m = tok.split(":")
        out.append((int(h), int(m)))
    return out


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
    TREND_EMA = int(os.getenv("TREND_EMA", "20"))  # 15m trend filter span
    VWAP_REQUIRED = os.getenv("VWAP_REQUIRED", "true").lower() == "true"

    # Risk
    MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.08"))
    MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "8"))
    DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.03"))
    MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "0.10"))
    MIN_CASH_RESERVE = float(os.getenv("MIN_CASH_RESERVE", "200000"))
    HEAT_CAP_PCT = float(os.getenv("HEAT_CAP_PCT", "0.06"))  # max total open risk
    TARGET_VOL_PCT = float(os.getenv("TARGET_VOL_PCT", "1.5"))  # vol targeting anchor
    THROTTLE_START_MULT = float(os.getenv("THROTTLE_START_MULT", "0.5"))  # halve size past this x daily limit
    MAX_SECTOR_POSITIONS = int(os.getenv("MAX_SECTOR_POSITIONS", "3"))

    # Exits (Phase E)
    PARTIAL_R = float(os.getenv("PARTIAL_R", "1.0"))  # take partial at this R multiple
    PARTIAL_FRAC = float(os.getenv("PARTIAL_FRAC", "0.5"))  # fraction of qty to scale
    SCRATCH_BARS = int(os.getenv("SCRATCH_BARS", "12"))  # max bars without progress
    SCRATCH_R = float(os.getenv("SCRATCH_R", "0.5"))  # progress threshold in R
    TRAIL_TIGHTEN_MULT = float(os.getenv("TRAIL_TIGHTEN_MULT", "0.5"))  # late-day trail factor
    SCALE_1430_R = float(os.getenv("SCALE_1430_R", "1.0"))  # force-scale above this R after 14:30

    # Portfolio (NSE equity-intraday schedule)
    BROKERAGE_PCT = float(os.getenv("BROKERAGE_PCT", "0.0003"))
    STT_PCT = float(os.getenv("STT_PCT", "0.00025"))  # sell side only
    EXCHANGE_PCT = float(os.getenv("EXCHANGE_PCT", "0.0000297"))
    SEBI_PCT = float(os.getenv("SEBI_PCT", "0.000001"))
    STAMP_PCT = float(os.getenv("STAMP_PCT", "0.00002"))  # buy side only
    GST_PCT = float(os.getenv("GST_PCT", "0.18"))
    SLIPPAGE_MAX_PCT = float(os.getenv("SLIPPAGE_MAX_PCT", "0.0004"))
    _SLIP_SEED = os.getenv("SLIPPAGE_SEED", "")
    SLIPPAGE_SEED = int(_SLIP_SEED) if _SLIP_SEED.strip() else None

    # Trading Hours (IST)
    MARKET_START_HOUR = 9
    MARKET_START_MINUTE = 15
    MARKET_END_HOUR = 15
    MARKET_END_MINUTE = 25
    # Session management (Phase E)
    ENTRY_CUTOFF_HOUR = 14
    ENTRY_CUTOFF_MINUTE = 45  # no new entries after this
    SCALE_START_HOUR = 15
    SCALE_START_MINUTE = 0  # staged profit-taking begins
    FULL_EXIT_HOUR = 15
    FULL_EXIT_MINUTE = 20  # square off (force-close at MARKET_END is backstop)
    TIGHTEN_HOUR = 14
    TIGHTEN_MINUTE = 30  # tighten trails / force-scale >= SCALE_1430_R
    RESELECT_TIMES = _parse_hhmm_list(os.getenv("RESELECT_TIMES", "09:30,11:00"))

    # API
    API_PORT = int(os.getenv("API_PORT", "8002"))
    DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8501"))

    # Streaming feed (fail-open: REST fallback when inactive/stale)
    FEED_ENABLED = os.getenv("FEED_ENABLED", "true").lower() == "true"
    FEED_MAX_AGE_S = int(os.getenv("FEED_MAX_AGE_S", "60"))
    INSTRUMENTS_TTL_DAYS = int(os.getenv("INSTRUMENTS_TTL_DAYS", "7"))

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
