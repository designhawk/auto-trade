# logs.py
"""
Log viewer for trading system.

Usage:
    python logs.py           # View all logs
    python logs.py trader    # View trader logs only
    python logs.py --follow  # Tail logs in real-time
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime


def tail_file(filepath, lines=50, follow=False):
    """Display last lines of a file."""
    try:
        with open(filepath, 'r') as f:
            if follow:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if not line:
                        import time
                        time.sleep(0.5)
                        continue
                    print(line.rstrip())
            else:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    print(line.rstrip())
    except FileNotFoundError:
        print(f"File not found: {filepath}")
    except Exception as e:
        print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Trading Log Viewer")
    parser.add_argument("component", nargs="?", choices=["api", "trader", "dashboard", "all"], default="all")
    parser.add_argument("-n", "--lines", type=int, default=50, help="Number of lines to show")
    parser.add_argument("-f", "--follow", action="store_true", help="Follow log in real-time")
    parser.add_argument("--clear", action="store_true", help="Clear logs")
    
    args = parser.parse_args()
    
    log_dir = Path("logs")
    
    if args.clear:
        for log_file in log_dir.glob("*.log"):
            log_file.unlink()
        print("Logs cleared!")
        return
    
    if args.component == "all":
        files = list(log_dir.glob("*.log"))
        for f in files:
            print(f"\n=== {f.name} ===")
            tail_file(f, args.lines, args.follow)
    elif args.component == "api":
        tail_file(log_dir / "api.log", args.lines, args.follow)
    elif args.component == "trader":
        tail_file(log_dir / "trader.log", args.lines, args.follow)
    elif args.component == "dashboard":
        tail_file(log_dir / "dashboard.log", args.lines, args.follow)


if __name__ == "__main__":
    main()
