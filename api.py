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
from pathlib import Path

from db import get_db, get_trades_for_date, get_signals_for_date, get_all_sessions
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
        # Check if database exists
        db_path = Path("trading.db")
        db_exists = db_path.exists()
        
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
    """Get current open positions (only executed trades)."""
    try:
        today = date.today().isoformat()
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get unique symbols from TRADES (executed only), not signals
            cursor.execute("""
                SELECT symbol, side, price, qty, pnl, timestamp
                FROM trades 
                WHERE side = 'BUY' 
                AND DATE(timestamp) = ?
                ORDER BY timestamp DESC
            """, (today,))
            
            rows = cursor.fetchall()
            
            seen = set()
            positions = []
            
            for row in rows:
                symbol = row[0]
                if symbol not in seen:
                    seen.add(symbol)
                    entry_price = float(row[2])
                    qty = int(row[3])
                    
                    positions.append({
                        "symbol": str(symbol),
                        "side": str(row[1]),
                        "entry_price": entry_price,
                        "current_price": entry_price,
                        "qty": qty,
                        "value": entry_price * qty,
                        "entry_time": str(row[5])
                    })
            
            return {
                "count": len(positions),
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
            # Get open positions from trades (BUY minus SELL)
            cursor.execute("""
                SELECT symbol, SUM(qty) as total_qty, AVG(price) as avg_price
                FROM trades 
                WHERE side = 'BUY'
                GROUP BY symbol
                HAVING symbol NOT IN (
                    SELECT symbol FROM trades WHERE side = 'SELL'
                )
            """)
            positions = cursor.fetchall()
            
            # Calculate cash from actual trades
            cursor.execute("SELECT SUM(value) FROM trades WHERE side = 'BUY'")
            buy_total = cursor.fetchone()[0] or 0
            cursor.execute("SELECT SUM(value) FROM trades WHERE side = 'SELL'")
            sell_total = cursor.fetchone()[0] or 0
            cash = start_capital - buy_total + sell_total
        
        # Calculate position value using current prices from entry
        position_value = sum(p[1] * p[2] for p in positions) if positions else 0
        num_positions = len(positions)
        
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
    print("Starting API server on http://localhost:8000")
    print("Documentation: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8002)
