# Auto Trading India

Automated intraday trading system for NSE (National Stock Exchange of India).

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure .env
cp .env.example .env
# Edit .env with your Groww API credentials

# Start trading
python run.py
```

## Commands

| Command | Description |
|---------|-------------|
| `python run.py` | Start API + Trader |
| `python monitor.py` | Live dashboard |
| `python logs.py` | View logs |

## Configuration

Edit `config.py` or `.env`:

- `INITIAL_CAPITAL` - Starting capital (default: ₹20L)
- `MAX_OPEN_POSITIONS` - Max concurrent positions (default: 8)
- `MIN_RISK_REWARD` - Min risk-reward ratio (default: 2.0)

## Features

- Paper trading with real market data
- Intraday momentum strategy
- Risk management (stop loss, take profit, trailing stop)
- Auto backup

## Files

```
run.py           - Launcher
monitor.py       - Live dashboard  
logs.py          - Log viewer
api.py           - REST API
live_trader.py   - Trading engine
config.py        - Configuration
intraday_strategy.py - Strategy
risk_manager.py  - Risk management
paper_portfolio.py - Portfolio
groww_broker.py  - Groww API
db.py           - Database
```
