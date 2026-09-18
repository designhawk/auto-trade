# tools/update_universe.py
"""
Regenerate universe.py from the official NSE NIFTY 500 constituent list,
intersected with instruments available on Groww (NSE/CASH, EQ series).

Usage:
    python tools/update_universe.py

Sectors are derived from NSE's Industry column; curated entries in
sectors.py override the generated ones. Curated entries in sectors.SECTOR_MAP
are always kept authoritative.

Groww availability comes from the live API when credentials are configured,
with the local instruments.csv cache as a fallback.
"""

import io
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NSE_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

INDUSTRY_TO_SECTOR = {
    "Financial Services": "FINANCE",
    "Capital Goods": "INFRA",
    "Healthcare": "HEALTHCARE",
    "Automobile and Auto Components": "AUTO",
    "Consumer Services": "CONSUMER",
    "Fast Moving Consumer Goods": "FMCG",
    "Information Technology": "IT",
    "Chemicals": "CHEMICALS",
    "Metals & Mining": "METALS",
    "Power": "ENERGY",
    "Oil Gas & Consumable Fuels": "ENERGY",
    "Consumer Durables": "CONSUMER",
    "Services": "SERVICES",
    "Construction": "INFRA",
    "Realty": "REALTY",
    "Construction Materials": "CEMENT",
    "Telecommunication": "TELECOM",
    "Textiles": "TEXTILES",
    "Media Entertainment & Publication": "MEDIA",
    "Diversified": "OTHER",
}


def groww_symbols() -> set:
    """NSE/CASH symbols available on Groww (live API, cache fallback)."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        import pyotp
        from growwapi import GrowwAPI

        api_key = os.getenv("GROWW_TOTP_TOKEN")
        secret = os.getenv("GROWW_TOTP_SECRET")
        if api_key and secret:
            access = GrowwAPI.get_access_token(
                api_key=api_key, totp=pyotp.TOTP(secret).now()
            )
            client = GrowwAPI(access)
            df = client.get_all_instruments()
            syms = set(
                df[(df["exchange"] == "NSE") & (df["segment"] == "CASH")][
                    "trading_symbol"
                ]
            )
            if syms:
                print(f"[groww] live instruments: {len(syms)} NSE/CASH symbols")
                return syms
    except Exception as e:
        print(f"[groww] live fetch unavailable ({str(e)[:80]}), using cache")

    cache = ROOT / "instruments.csv"
    if cache.exists():
        syms = set(pd.read_csv(cache, dtype=str)["trading_symbol"].dropna())
        print(f"[groww] cache instruments: {len(syms)} symbols")
        return syms
    raise SystemExit("No Groww instrument source (connect once to build cache)")


def main() -> None:
    r = requests.get(NSE_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    n500 = pd.read_csv(io.StringIO(r.text))
    n500 = n500[n500["Series"] == "EQ"]

    available = groww_symbols()
    kept = n500[n500["Symbol"].isin(available)].sort_values("Symbol")
    dropped = sorted(set(n500["Symbol"]) - set(kept["Symbol"]))

    try:
        from sectors import SECTOR_MAP as CURATED
    except Exception:
        CURATED = {}

    today = date.today().isoformat()
    lines = [
        "# universe.py",
        '"""',
        "AUTO-GENERATED - do not edit by hand.",
        "",
        "NIFTY 500 universe (official NSE constituent list, EQ series)",
        "intersected with instruments available on Groww (NSE/CASH).",
        "Sectors come from NSE's Industry column; curated entries in",
        "sectors.py always override the generated mapping.",
        "",
        f"Source: {NSE_URL}",
        f"Fetched: {today}",
        "Regenerate: python tools/update_universe.py",
        '"""',
        "",
        f'FETCHED = "{today}"',
        "",
        "NIFTY500 = [",
    ]
    lines += [f'    "{s}",' for s in kept["Symbol"]]
    lines += ["]", "", "SECTORS = {"]
    for _, row in kept.iterrows():
        sym = row["Symbol"]
        sec = CURATED.get(sym) or INDUSTRY_TO_SECTOR.get(row["Industry"], "OTHER")
        lines.append(f'    "{sym}": "{sec}",')
    lines += ["}", ""]

    out = ROOT / "universe.py"
    out.write_text("\n".join(lines), encoding="utf-8")

    unmapped = sorted(
        {row["Industry"] for _, row in kept.iterrows()
         if row["Industry"] not in INDUSTRY_TO_SECTOR}
    )
    print(f"[done] universe.py: {len(kept)} symbols")
    if dropped:
        print(f"[warn] dropped ({len(dropped)}): {dropped}")
    if unmapped:
        print(f"[warn] unmapped industries -> OTHER: {unmapped}")


if __name__ == "__main__":
    main()
