# run.py
"""
Unified launcher for auto trading system.

Usage:
    python run.py           # Start API + Trader
    python run.py --trader-only   # Trader only
    python run.py --stop         # Stop all processes
    python run.py --monitor      # Start with live monitor
"""

import argparse
import os
import sys
import subprocess
import time
from pathlib import Path


class Launcher:
    """Manages all trading system processes."""
    
    def __init__(self):
        self.processes = {}
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
    
    def log(self, msg):
        print(f"[LAUNCHER] {msg}")
    
    def start_api(self):
        """Start API server."""
        self.log("Starting API server...")
        log_file = self.log_dir / "api.log"
        proc = subprocess.Popen(
            [sys.executable, "api.py"],
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        self.processes["api"] = proc
        self.log(f"API started (PID: {proc.pid})")
    
    def start_trader(self):
        """Start live trader."""
        self.log("Starting live trader...")
        log_file = self.log_dir / "trader.log"
        proc = subprocess.Popen(
            [sys.executable, "live_trader.py"],
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        self.processes["trader"] = proc
        self.log(f"Trader started (PID: {proc.pid})")
    
    def stop_all(self):
        """Stop all processes."""
        self.log("Stopping all processes...")
        for name, proc in self.processes.items():
            try:
                proc.terminate()
                proc.wait(timeout=5)
                self.log(f"Stopped {name}")
            except:
                try:
                    proc.kill()
                    self.log(f"Killed {name}")
                except:
                    pass
        self.processes.clear()
    
    def status(self):
        """Check process status."""
        for name, proc in self.processes.items():
            if proc.poll() is None:
                print(f"  {name}: RUNNING (PID: {proc.pid})")
            else:
                print(f"  {name}: STOPPED (exit code: {proc.returncode})")


def main():
    parser = argparse.ArgumentParser(description="Auto Trading Launcher")
    parser.add_argument("--trader-only", action="store_true", help="Start trader only")
    parser.add_argument("--stop", action="store_true", help="Stop all processes")
    parser.add_argument("--status", action="store_true", help="Check status")
    parser.add_argument("--monitor", action="store_true", help="Start with live monitor")
    
    args = parser.parse_args()
    
    launcher = Launcher()
    
    if args.stop:
        launcher.stop_all()
        return
    
    if args.status:
        launcher.status()
        return
    
    if args.monitor:
        launcher.start_api()
        time.sleep(2)
        launcher.start_trader()
        time.sleep(2)
        print("\n[LAUNCHER] Starting live monitor... (Ctrl+C to exit)")
        os.system(f"{sys.executable} monitor.py --follow")
        launcher.stop_all()
        return
    
    # Default: start api + trader
    launcher.start_api()
    time.sleep(2)
    
    if not args.trader_only:
        launcher.start_trader()
    
    launcher.log("All systems started!")
    launcher.log("API: http://localhost:8002")
    launcher.log("Monitor: python monitor.py")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        launcher.log("Shutting down...")
        launcher.stop_all()


if __name__ == "__main__":
    main()
