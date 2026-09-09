# monitor.py
"""
Live Trading Monitor.

Real-time monitoring in terminal with auto-refresh.

Usage:
    python monitor.py           # Standard mode
    python monitor.py --follow   # Follow logs
    python monitor.py --once     # Single snapshot
"""

import os
import sys
import time
import requests
import argparse
from datetime import datetime
from pathlib import Path


def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_status():
    """Get all system status."""
    status = {
        "api": {"status": "[X] Down", "positions": "-", "cash": "-", "pnl": "-"},
        "trader": "[X] Not running"
    }
    
    try:
        resp = requests.get("http://localhost:8002/health", timeout=2)
        if resp.status_code == 200:
            status["api"]["status"] = "[OK] Running"
    except:
        pass
    
    try:
        resp = requests.get("http://localhost:8002/portfolio", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            status["api"]["positions"] = str(data.get("num_positions", 0))
            status["api"]["cash"] = f"Rs.{data.get('cash', 0):,.0f}"
            status["api"]["pnl"] = f"Rs.{data.get('today_pnl', 0):,.0f}"
            status["trader"] = "[OK] Running"
    except:
        pass
    
    return status


def get_recent_logs(lines=15):
    """Get recent log lines."""
    log_files = sorted(Path("logs").glob("live_trader_*.log"), reverse=True)
    if not log_files:
        return []
    
    with open(log_files[0], "r") as f:
        all_lines = f.readlines()
        return [l.rstrip() for l in all_lines[-lines:]]


def print_status(status, logs):
    """Print status dashboard."""
    clear_screen()
    
    print("=" * 70)
    print(f"  AUTO TRADING MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    print("\n[SYSTEM STATUS]")
    print("-" * 40)
    print(f"  API Server:     {status['api']['status']}")
    print(f"  Trader:        {status['trader']}")
    print(f"  Positions:     {status['api']['positions']}")
    print(f"  Cash:          {status['api']['cash']}")
    print(f"  Today's P&L:   {status['api']['pnl']}")
    
    print("\n[RECENT LOGS]")
    print("-" * 40)
    for line in logs[-15:]:
        print(f"  {line[:70]}")
    
    print("\n" + "=" * 70)
    print("  Press Ctrl+C to exit | Press R to refresh")
    print("=" * 70)


def follow_logs():
    """Follow logs in real-time."""
    log_files = sorted(Path("logs").glob("live_trader_*.log"), reverse=True)
    if not log_files:
        print("No log files found")
        return
    log_file = log_files[0]
    last_size = 0
    
    while True:
        try:
            if log_file.exists():
                with open(log_file, "r") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    
                    if size < last_size:
                        last_size = 0
                    
                    if size > last_size:
                        f.seek(last_size)
                        new_lines = f.readlines()
                        last_size = f.tell()
                        
                        for line in new_lines:
                            print(line.rstrip())
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            break


def main():
    parser = argparse.ArgumentParser(description="Trading Monitor")
    parser.add_argument("--follow", "-f", action="store_true", help="Follow logs")
    parser.add_argument("--once", "-1", action="store_true", help="Show once and exit")
    parser.add_argument("--interval", "-i", type=int, default=5, help="Refresh interval")
    
    args = parser.parse_args()
    
    if args.follow:
        follow_logs()
        return
    
    while True:
        status = get_status()
        logs = get_recent_logs()
        print_status(status, logs)
        
        if args.once:
            break
        
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nExiting...")
            break


if __name__ == "__main__":
    main()
