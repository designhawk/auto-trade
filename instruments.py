# instruments.py
"""
NSE/CASH trading_symbol -> exchange_token resolution for the streaming feed.

Feed subscriptions require exchange tokens, not symbols. Tokens come from
Groww's instruments universe, cached on disk (instruments.csv, gitignored)
and refreshed weekly to avoid a ~150-call lookup on every start.
"""

import time
from pathlib import Path

import pandas as pd

from paths import INSTRUMENTS_CACHE


def _norm_token(raw) -> str | None:
    """Normalize a token to its canonical string form (e.g. 2885 -> '2885')."""
    try:
        if pd.isna(raw):
            return None
        return str(int(float(raw)))
    except (TypeError, ValueError):
        return None


def build_token_map(df: pd.DataFrame) -> dict:
    """
    Build {trading_symbol: exchange_token} for NSE CASH equities.

    Prefers EQ-series rows when a series column exists; first occurrence wins.
    """
    needed = {"exchange", "segment", "trading_symbol", "exchange_token"}
    if not needed.issubset(set(df.columns)):
        return {}

    sub = df[(df["exchange"] == "NSE") & (df["segment"] == "CASH")].copy()
    if "series" in sub.columns:
        sub["_eq"] = (sub["series"] == "EQ").astype(int)
        sub = sub.sort_values("_eq", ascending=False)

    out = {}
    for _, row in sub.iterrows():
        sym = row["trading_symbol"]
        if sym in out:
            continue
        tok = _norm_token(row["exchange_token"])
        if tok:
            out[str(sym)] = tok
    return out


def _cache_fresh(cache_path: Path, ttl_days: int) -> bool:
    return (
        cache_path.exists()
        and (time.time() - cache_path.stat().st_mtime) < ttl_days * 86400
    )


def ensure_tokens(client, symbols: list, ttl_days: int = 7) -> dict:
    """
    Resolve {symbol: token} for the requested symbols.

    Reads the disk cache when fresh; otherwise pulls get_all_instruments()
    once, rebuilds the map, and rewrites the cache. Symbols that cannot be
    resolved are omitted (callers fall back to REST for those).
    Never raises - returns whatever resolved (possibly {}).
    """
    symbols = list(symbols)
    resolved: dict = {}
    try:
        if _cache_fresh(INSTRUMENTS_CACHE, ttl_days):
            try:
                cached = pd.read_csv(
                    INSTRUMENTS_CACHE, usecols=["trading_symbol", "exchange_token"],
                    dtype=str,
                )
                for _, row in cached.iterrows():
                    tok = _norm_token(row["exchange_token"])
                    if tok:
                        resolved[str(row["trading_symbol"])] = tok
            except Exception:
                resolved = {}
    except Exception:
        resolved = {}

    missing = [s for s in symbols if s not in resolved]
    if missing:
        try:
            df = client.get_all_instruments()
            fresh = build_token_map(df)
            # Rewrite cache with the NSE/CASH/EQ slice (small file)
            try:
                keep = df[(df["exchange"] == "NSE") & (df["segment"] == "CASH")]
                cols = [c for c in ("trading_symbol", "exchange_token") if c in keep.columns]
                keep[cols].to_csv(INSTRUMENTS_CACHE, index=False)
            except Exception:
                pass
            for s in missing:
                if s in fresh:
                    resolved[s] = fresh[s]
        except Exception:
            pass

    return {s: resolved[s] for s in symbols if s in resolved}
