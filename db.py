# db.py
"""
SQLite Database Layer

Stores all trading data:
- Signals (entry/exit decisions)
- Trades (executed transactions)
- Sessions (daily summaries)

Usage:
    init_db()  # Create tables
    insert_signal({...})
    insert_trade({...})
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from paths import DB_PATH, BACKUP_DIR


def get_connection() -> sqlite3.Connection:
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database tables."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Signals table - records all strategy signals
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                confidence REAL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                reason TEXT,
                approved BOOLEAN,
                rejection_reason TEXT,
                adjusted_qty INTEGER,
                strategy TEXT
            )
        """)
        
        # Trades table - records executed trades
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty INTEGER NOT NULL,
                price REAL NOT NULL,
                value REAL NOT NULL,
                pnl REAL,
                pnl_pct REAL,
                exit_reason TEXT,
                session_id TEXT
            )
        """)

        # Migrate older databases: MFE/MAE + cost breakdown columns
        existing_cols = {
            row[1] for row in cursor.execute("PRAGMA table_info(trades)").fetchall()
        }
        for col in ("mfe", "mae", "brokerage", "stt", "other_costs", "slippage_cost"):
            if col not in existing_cols:
                cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} REAL")
        
        # Sessions table - daily summary
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                start_capital REAL NOT NULL,
                end_capital REAL NOT NULL,
                total_pnl REAL,
                total_trades INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER,
                max_drawdown_pct REAL,
                sharpe_ratio REAL,
                notes TEXT
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(date)")
        
        conn.commit()
        print(f"[DB] Database initialized: {DB_PATH}")


def insert_signal(signal_data: dict):
    """Insert a signal into the database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signals (
                timestamp, symbol, action, confidence, entry_price,
                stop_loss, take_profit, reason, approved,
                rejection_reason, adjusted_qty, strategy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal_data.get('timestamp', datetime.now().isoformat()),
            signal_data.get('symbol'),
            signal_data.get('action'),
            signal_data.get('confidence'),
            signal_data.get('entry_price'),
            signal_data.get('stop_loss'),
            signal_data.get('take_profit'),
            signal_data.get('reason'),
            signal_data.get('approved'),
            signal_data.get('rejection_reason'),
            signal_data.get('adjusted_qty'),
            signal_data.get('strategy', 'Unknown')
        ))
        conn.commit()


def insert_trade(trade_data: dict):
    """Insert a trade into the database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trades (
                timestamp, symbol, side, qty, price, value,
                pnl, pnl_pct, exit_reason, session_id,
                mfe, mae, brokerage, stt, other_costs, slippage_cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_data.get('timestamp', datetime.now().isoformat()),
            trade_data.get('symbol'),
            trade_data.get('side'),
            trade_data.get('qty'),
            trade_data.get('price'),
            trade_data.get('value'),
            trade_data.get('pnl'),
            trade_data.get('pnl_pct'),
            trade_data.get('exit_reason'),
            trade_data.get('session_id'),
            trade_data.get('mfe'),
            trade_data.get('mae'),
            trade_data.get('brokerage'),
            trade_data.get('stt'),
            trade_data.get('other_costs'),
            trade_data.get('slippage_cost')
        ))
        conn.commit()


def insert_session(session_data: dict):
    """Insert or update a session summary."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if session exists
        cursor.execute(
            "SELECT id FROM sessions WHERE date = ?",
            (session_data.get('date'),)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Update existing session
            cursor.execute("""
                UPDATE sessions SET
                    start_capital = ?,
                    end_capital = ?,
                    total_pnl = ?,
                    total_trades = ?,
                    winning_trades = ?,
                    losing_trades = ?,
                    max_drawdown_pct = ?,
                    sharpe_ratio = ?,
                    notes = ?
                WHERE date = ?
            """, (
                session_data.get('start_capital'),
                session_data.get('end_capital'),
                session_data.get('total_pnl'),
                session_data.get('total_trades'),
                session_data.get('winning_trades'),
                session_data.get('losing_trades'),
                session_data.get('max_drawdown_pct'),
                session_data.get('sharpe_ratio'),
                session_data.get('notes'),
                session_data.get('date')
            ))
        else:
            # Insert new session
            cursor.execute("""
                INSERT INTO sessions (
                    date, start_capital, end_capital, total_pnl,
                    total_trades, winning_trades, losing_trades,
                    max_drawdown_pct, sharpe_ratio, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_data.get('date'),
                session_data.get('start_capital'),
                session_data.get('end_capital'),
                session_data.get('total_pnl'),
                session_data.get('total_trades'),
                session_data.get('winning_trades'),
                session_data.get('losing_trades'),
                session_data.get('max_drawdown_pct'),
                session_data.get('sharpe_ratio'),
                session_data.get('notes')
            ))
        
        conn.commit()


def get_trades_for_date(trade_date: str) -> list[dict]:
    """Get all trades for a specific date."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM trades WHERE DATE(timestamp) = ? ORDER BY timestamp",
            (trade_date,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_signals_for_date(signal_date: str) -> list[dict]:
    """Get all signals for a specific date."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM signals WHERE DATE(timestamp) = ? ORDER BY timestamp",
            (signal_date,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_session_summary(session_date: str) -> Optional[dict]:
    """Get session summary for a specific date."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM sessions WHERE date = ?",
            (session_date,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_sessions() -> list[dict]:
    """Get all session summaries."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions ORDER BY date DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_cash_flow() -> tuple:
    """
    Total cash outflow (buys) and inflow (sells), costs included.

    BUY rows store gross value + cost columns; legacy rows (NULL costs,
    net value) degrade gracefully to the same totals. Returns
    (buy_outflow, sell_inflow) so cash == initial - outflow + inflow.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN side = 'BUY'
                    THEN value + COALESCE(brokerage, 0) + COALESCE(stt, 0)
                         + COALESCE(other_costs, 0) ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN side = 'SELL'
                    THEN value - COALESCE(brokerage, 0) - COALESCE(stt, 0)
                         - COALESCE(other_costs, 0) ELSE 0 END), 0)
            FROM trades
        """)
        row = cursor.fetchone()
        return float(row[0]), float(row[1])


def backup_db(backup_dir: str = str(BACKUP_DIR)) -> str:
    """
    Create a timestamped backup of the database.
    
    Args:
        backup_dir: Directory to store backups
        
    Returns:
        Path to backup file
    """
    from datetime import datetime
    import shutil
    
    if not DB_PATH.exists():
        return None
    
    Path(backup_dir).mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(backup_dir) / f"trading_{timestamp}.db"
    
    shutil.copy2(DB_PATH, backup_path)
    print(f"[DB] Backed up database to: {backup_path}")
    
    return str(backup_path)


def restore_db(backup_path: str) -> bool:
    """
    Restore database from a backup file.
    
    Args:
        backup_path: Path to backup file
        
    Returns:
        True if successful
    """
    import shutil
    
    backup_file = Path(backup_path)
    if not backup_file.exists():
        print(f"[DB] Backup file not found: {backup_path}")
        return False
    
    shutil.copy2(backup_file, DB_PATH)
    print(f"[DB] Restored database from: {backup_path}")
    return True


def get_backup_list(backup_dir: str = str(BACKUP_DIR)) -> list:
    """Get list of available backups."""
    backup_path = Path(backup_dir)
    if not backup_path.exists():
        return []
    
    backups = sorted(backup_path.glob("trading_*.db"), reverse=True)
    return [{"path": str(b), "name": b.name} for b in backups]


if __name__ == "__main__":
    init_db()
    print("Database tables created successfully!")
