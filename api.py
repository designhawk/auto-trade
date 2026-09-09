# api.py
"""
FastAPI REST Server for Trading System

Provides endpoints to query:
- Current trading status
- Signals and trades
- Portfolio value
- Session summaries

Usage:
    python api.py  # Start server on port 8000
    
Endpoints:
    GET /health - Health check
    GET /status - Current trading status
    GET /signals - Recent signals
    GET /trades - Recent trades
    GET /portfolio - Portfolio summary
    GET /sessions - Session history
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date
from typing import List, Optional
import sqlite3
from contextlib import contextmanager
import json

from db import get_db, get_trades_for_date, get_signals_for_date, get_all_sessions, DB_PATH
from config import config

# Broker for live prices
_broker = None

def get_broker():
    global _broker
    if _broker is None:
        from groww_broker import GrowwBroker
        _broker = GrowwBroker()
        _broker.connect()
    return _broker


def _live_prices(symbols: list[str]) -> tuple[dict[str, float], bool]:
    """
    Best-effort live LTP lookup.

    Returns (prices, live_flag). Falls back to ({}, False) when the broker
    is unreachable (no creds, market closed, trader not running) so endpoints
    stay usable with entry-price valuations. Callers MUST surface live_flag
    as "live_prices" so clients know which they're seeing.
    """
    if not symbols:
        return {}, False
    try:
        prices = get_broker().get_ltp(symbols)
        # Live only if we got a price for EVERY requested symbol;
        # otherwise callers fall back to entry prices per row.
        live = bool(prices) and all(s in prices for s in symbols)
        return (prices if live else {}), live
    except Exception:
        return {}, False

app = FastAPI(
    title="Auto Trading API",
    description="REST API for auto trading system observability",
    version="1.0.0"
)

# Enable CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.get("/status")
def get_status():
    """Get current trading system status."""
    try:
        # Check if database exists (anchored to project root, not cwd)
        db_exists = DB_PATH.exists()
        
        # Get latest session info
        sessions = get_all_sessions()
        latest_session = sessions[0] if sessions else None
        
        # Count today's signals and trades
        today = date.today().isoformat()
        signals_today = len(get_signals_for_date(today))
        trades_today = len(get_trades_for_date(today))
        
        return {
            "status": "running" if db_exists else "error",
            "timestamp": datetime.now().isoformat(),
            "database_connected": db_exists,
            "latest_session": latest_session,
            "today_signals": signals_today,
            "today_trades": trades_today,
            "total_sessions": len(sessions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/signals")
def get_signals(
    limit: int = 50,
    approved_only: bool = False,
    date: Optional[str] = None
):
    """Get trading signals."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM signals"
            params = []
            
            # Filter by date
            if date:
                query += " WHERE DATE(timestamp) = ?"
                params.append(date)
            
            # Filter by approval status
            if approved_only:
                if date:
                    query += " AND approved = 1"
                else:
                    query += " WHERE approved = 1"
            
            # Order and limit
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            signals = [dict(row) for row in rows]
            return {
                "count": len(signals),
                "signals": signals
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trades")
def get_trades(
    limit: int = 50,
    date: Optional[str] = None,
    symbol: Optional[str] = None
):
    """Get executed trades."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM trades"
            conditions = []
            params = []
            
            if date:
                conditions.append("DATE(timestamp) = ?")
                params.append(date)
            
            if symbol:
                conditions.append("symbol = ?")
                params.append(symbol)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            trades = [dict(row) for row in rows]
            
            # Calculate summary stats
            if trades:
                total_pnl = sum(t.get('pnl', 0) or 0 for t in trades)
                winning_trades = len([t for t in trades if (t.get('pnl') or 0) > 0])
            else:
                total_pnl = 0
                winning_trades = 0
            
            return {
                "count": len(trades),
                "total_pnl": total_pnl,
                "winning_trades": winning_trades,
                "trades": trades
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/positions")
def get_positions():
    """Get current open positions (today's trades netted; live prices when available)."""
    try:
        today = date.today().isoformat()

        with get_db() as conn:
            cursor = conn.cursor()

            # Net today's BUYs against SELLs per symbol (partial sells OK)
            cursor.execute("""
                SELECT symbol,
                    SUM(CASE WHEN side = 'BUY' THEN qty ELSE -qty END) as net_qty,
                    SUM(CASE WHEN side = 'BUY' THEN qty * price ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN side = 'BUY' THEN qty ELSE 0 END), 0) as avg_price,
                    MAX(CASE WHEN side = 'BUY' THEN timestamp END) as last_buy_time
                FROM trades
                WHERE DATE(timestamp) = ?
                GROUP BY symbol
                HAVING net_qty > 0
                ORDER BY last_buy_time DESC
            """, (today,))

            rows = cursor.fetchall()

            symbols = [str(row[0]) for row in rows]
            live_prices, live = _live_prices(symbols)

            positions = []

            for row in rows:
                symbol = str(row[0])
                qty = int(row[1])
                entry_price = float(row[2])
                current_price = live_prices.get(symbol, entry_price)

                positions.append({
                    "symbol": symbol,
                    "side": "BUY",
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "qty": qty,
                    "value": current_price * qty,
                    "entry_time": str(row[3])
                })

            return {
                "count": len(positions),
                "live_prices": live,
                "positions": positions
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/portfolio")
def get_portfolio_summary():
    """Get current portfolio summary with real-time values."""
    try:
        # Get latest session
        sessions = get_all_sessions()
        
        if not sessions:
            return {
                "status": "no_sessions",
                "message": "No trading sessions found"
            }
        
        latest = sessions[0]
        start_capital = latest.get('start_capital', config.INITIAL_CAPITAL)
        
        # Get today's approved signals as open positions
        today = date.today().isoformat()
        
        with get_db() as conn:
            cursor = conn.cursor()
            # Net all BUYs against SELLs (partial sells reduce, not erase)
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
            open_positions = [
                (str(r[0]), int(r[1]), float(r[2])) for r in rows
            ]

            # Calculate cash from actual trades
            cursor.execute("SELECT SUM(value) FROM trades WHERE side = 'BUY'")
            buy_total = cursor.fetchone()[0] or 0
            cursor.execute("SELECT SUM(value) FROM trades WHERE side = 'SELL'")
            sell_total = cursor.fetchone()[0] or 0
            cash = start_capital - buy_total + sell_total

        # Value positions at live prices when available, entry prices otherwise
        live_prices, live = _live_prices([s for s, _, _ in open_positions])
        position_value = sum(
            qty * live_prices.get(symbol, avg_price)
            for symbol, qty, avg_price in open_positions
        ) if open_positions else 0
        num_positions = len(open_positions)
        
        current_value = cash + position_value
        
        # Get today's trades for P&L
        today_trades = get_trades_for_date(today)
        today_pnl = sum(t.get('pnl', 0) or 0 for t in today_trades)
        
        return {
            "status": "active",
            "latest_session_date": latest.get('date'),
            "start_capital": start_capital,
            "current_value": current_value,
            "cash": cash,
            "position_value": position_value,
            "live_prices": live,
            "num_positions": num_positions,
            "total_return_pct": (today_pnl / start_capital * 100) if start_capital else 0,
            "total_trades": len(today_trades),
            "win_rate": 0,
            "today_pnl": today_pnl,
            "today_trades": len(today_trades),
            "max_drawdown_pct": 0,
            "sharpe_ratio": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
def get_sessions(limit: int = 30):
    """Get trading session history."""
    try:
        sessions = get_all_sessions()
        
        # Calculate cumulative stats
        if sessions:
            total_pnl = sum(s.get('total_pnl', 0) or 0 for s in sessions)
            total_trades = sum(s.get('total_trades', 0) or 0 for s in sessions)
        else:
            total_pnl = 0
            total_trades = 0
        
        return {
            "count": len(sessions),
            "total_pnl_all_sessions": total_pnl,
            "total_trades_all_sessions": total_trades,
            "sessions": sessions[:limit]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/today")
def get_today_summary():
    """Get today's trading summary."""
    try:
        today = date.today().isoformat()
        
        # Get today's signals
        signals = get_signals_for_date(today)
        approved_signals = [s for s in signals if s.get('approved')]
        rejected_signals = [s for s in signals if not s.get('approved')]
        
        # Get today's trades
        trades = get_trades_for_date(today)
        buy_trades = [t for t in trades if t.get('side') == 'BUY']
        sell_trades = [t for t in trades if t.get('side') == 'SELL']
        
        # Calculate P&L
        total_pnl = sum(t.get('pnl', 0) or 0 for t in trades)
        
        return {
            "date": today,
            "signals_total": len(signals),
            "signals_approved": len(approved_signals),
            "signals_rejected": len(rejected_signals),
            "trades_total": len(trades),
            "trades_buy": len(buy_trades),
            "trades_sell": len(sell_trades),
            "total_pnl": total_pnl,
            "signals": signals[:10],  # Last 10 signals
            "trades": trades[:10]     # Last 10 trades
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    print(f"Starting API server on http://localhost:{config.API_PORT}")
    print(f"Documentation: http://localhost:{config.API_PORT}/docs")
    uvicorn.run(app, host="0.0.0.0", port=config.API_PORT)
