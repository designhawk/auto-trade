# sectors.py
"""
NSE sector mapping for diversification caps.

Coarse sectors only - used by the stock selector (max positions per sector)
and the daily report (sector attribution). Unknown symbols map to "MISC".
"""

SECTOR_MAP = {
    # Energy / Oil & Gas / Power
    "RELIANCE": "ENERGY", "ONGC": "ENERGY", "BPCL": "ENERGY", "IOC": "ENERGY",
    "GAIL": "ENERGY", "COALINDIA": "ENERGY", "NTPC": "ENERGY", "POWERGRID": "ENERGY",
    "TATAPOWER": "ENERGY", "ADANIGREEN": "ENERGY", "GUJGASLTD": "ENERGY",
    "OIL": "ENERGY", "INOXWIND": "ENERGY", "SWSOLAR": "ENERGY",
    # Banks
    "HDFCBANK": "BANK", "ICICIBANK": "BANK", "SBIN": "BANK", "KOTAKBANK": "BANK",
    "AXISBANK": "BANK", "INDUSINDBK": "BANK", "AUBANK": "BANK", "FEDERALBNK": "BANK",
    "IDFCFIRSTB": "BANK", "RBLBANK": "BANK", "UNIONBANK": "BANK", "CANBK": "BANK",
    "BANKBARODA": "BANK",
    # Finance / NBFC / Exchanges
    "BAJFINANCE": "FINANCE", "BAJAJFINSV": "FINANCE", "RECLTD": "FINANCE",
    "SBICARD": "FINANCE", "LICHSGFIN": "FINANCE", "MUTHOOTFIN": "FINANCE",
    "CHOLAFIN": "FINANCE", "PFC": "FINANCE", "SHRIRAMFIN": "FINANCE",
    "M&MFIN": "FINANCE", "MANAPPURAM": "FINANCE", "POLICYBZR": "FINANCE",
    "BSE": "FINANCE", "CAMS": "FINANCE", "CDSL": "FINANCE",
    "TATAINVEST": "FINANCE",
    # Insurance
    "SBILIFE": "INSURANCE", "HDFCLIFE": "INSURANCE", "ICICIGI": "INSURANCE",
    "ICICIPRULI": "INSURANCE", "MFSL": "INSURANCE",
    # IT
    "TCS": "IT", "INFY": "IT", "HCLTECH": "IT", "WIPRO": "IT", "TECHM": "IT",
    "COFORGE": "IT", "LTTS": "IT", "PERSISTENT": "IT", "MPHASIS": "IT",
    "TATAELXSI": "IT", "CYIENT": "IT", "ZENSARTECH": "IT",
    # FMCG / Food
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG",
    "TATACONSUM": "FMCG", "DABUR": "FMCG", "GODREJCP": "FMCG", "MARICO": "FMCG",
    "AWL": "FMCG", "ADFFOODS": "FMCG", "BECTORFOOD": "FMCG", "BIKAJI": "FMCG",
    # Pharma
    "SUNPHARMA": "PHARMA", "DIVISLAB": "PHARMA", "CIPLA": "PHARMA",
    "DRREDDY": "PHARMA", "TORNTPHARM": "PHARMA", "ZYDUSLIFE": "PHARMA",
    "LAURUSLABS": "PHARMA", "MANKIND": "PHARMA", "CAPLIPOINT": "PHARMA",
    # Healthcare (hospitals / diagnostics)
    "APOLLOHOSP": "HEALTHCARE", "LALPATHLAB": "HEALTHCARE", "FORTIS": "HEALTHCARE",
    # Auto + Ancillaries
    "MARUTI": "AUTO", "M&M": "AUTO", "EICHERMOT": "AUTO", "HEROMOTOCO": "AUTO",
    "APOLLOTYRE": "AUTO", "ENDURANCE": "AUTO", "ESCORTS": "AUTO",
    # Metals
    "TATASTEEL": "METALS", "JSWSTEEL": "METALS", "HINDALCO": "METALS",
    "JINDALSTEL": "METALS", "VEDL": "METALS", "JSL": "METALS",
    "RATNAMANI": "METALS", "GRAPHITE": "METALS", "APLAPOLLO": "METALS",
    # Cement
    "ULTRACEMCO": "CEMENT", "SHREECEM": "CEMENT", "GRASIM": "CEMENT",
    "JKCEMENT": "CEMENT", "JKLAKSHMI": "CEMENT", "AMBUJACEM": "CEMENT",
    # Infra / Capital goods / Rail
    "LT": "INFRA", "ADANIENT": "INFRA", "ADANIPORTS": "INFRA", "SIEMENS": "INFRA",
    "ABB": "INFRA", "KIRLOSENG": "INFRA", "PRAJIND": "INFRA", "TITAGARH": "INFRA",
    "TRITURBINE": "INFRA",
    # Telecom
    "BHARTIARTL": "TELECOM", "RAILTEL": "TELECOM",
    # Realty
    "DLF": "REALTY", "PHOENIXLTD": "REALTY", "GODREJPROP": "REALTY",
    "SUNTECK": "REALTY",
    # Chemicals / Fertilisers / Paints
    "ASIANPAINT": "CHEMICALS", "UPL": "CHEMICALS", "TATACHEM": "CHEMICALS",
    "NAVINFLUOR": "CHEMICALS", "LINDEINDIA": "CHEMICALS", "VINATIORGA": "CHEMICALS",
    "ALKYLAMINE": "CHEMICALS", "BAYERCROP": "CHEMICALS", "CLEAN": "CHEMICALS",
    "FACT": "CHEMICALS",
    # Consumer (durables, retail, travel, food services)
    "TITAN": "CONSUMER", "TRENT": "CONSUMER", "VOLTAS": "CONSUMER",
    "CROMPTON": "CONSUMER", "JUBLFOOD": "CONSUMER", "INDHOTEL": "CONSUMER",
    "RELAXO": "CONSUMER", "VGUARD": "CONSUMER", "WESTLIFE": "CONSUMER",
    "AMBER": "CONSUMER", "HAVELLS": "CONSUMER", "DEVYANI": "CONSUMER",
    "EIHOTEL": "CONSUMER", "IRCTC": "CONSUMER", "METROBRAND": "CONSUMER",
    "UNITDSPR": "CONSUMER",
    # Media
    "SUNTV": "MEDIA", "CREATIVEYE": "MEDIA",
}


def sector_of(symbol: str) -> str:
    """Return the coarse sector for a symbol (MISC if unmapped)."""
    return SECTOR_MAP.get(symbol, "MISC")
