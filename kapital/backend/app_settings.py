"""Zentrale App-Einstellungen + Ticker-Normalisierung.

Single source of truth für:
- data/settings.json (z. B. Twelve-Data API-Key)
- Mapping von Börsen-Codes (Twelve Data / yf.Search) auf yfinance-Ticker-Suffixe
"""
from __future__ import annotations

import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent.parent / "data" / "settings.json"


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except Exception:
            pass
    return {}


def save_settings(data: dict) -> None:
    from kapital.finance.storage import write_json_atomic
    write_json_atomic(SETTINGS_PATH, data)


def get_twelve_data_key() -> str:
    return load_settings().get("twelve_data_api_key", "")


# ── Börsen-Code → yfinance-Suffix ─────────────────────────────────────────────
# Twelve Data und yf.Search liefern Börsen-Codes wie "XETRA"/"EPA"; yfinance
# erwartet Suffixe wie ".DE"/".PA". US-Börsen haben kein Suffix ("").
EXCHANGE_SUFFIX: dict[str, str] = {
    # Deutschland
    "XETRA": ".DE", "GER": ".DE", "ETR": ".DE", "IBIS": ".DE",
    "FSX": ".F", "FRA": ".F", "FWB": ".F",
    "STU": ".SG", "MUN": ".MU", "BER": ".BE", "HAM": ".HM", "DUS": ".DU",
    # Euronext
    "EPA": ".PA", "PAR": ".PA", "EURONEXT": ".PA",
    "AMS": ".AS", "AEX": ".AS",
    "EBR": ".BR", "BRU": ".BR",
    "ELI": ".LS", "LIS": ".LS",
    # UK / Irland
    "LSE": ".L", "LON": ".L",
    "ISE": ".IR",
    # Südeuropa
    "BME": ".MC", "MCE": ".MC", "MAD": ".MC",
    "MIL": ".MI", "BIT": ".MI", "MTA": ".MI",
    # Schweiz / Nordics
    "SIX": ".SW", "EBS": ".SW", "VTX": ".SW",
    "STO": ".ST", "OMX": ".ST",
    "CPH": ".CO", "HEL": ".HE", "OSL": ".OL",
    # Nordamerika (kein Suffix bei yfinance)
    "NYSE": "", "NASDAQ": "", "AMEX": "", "ARCA": "", "BATS": "",
    "NMS": "", "NGM": "", "NCM": "", "PCX": "", "NYQ": "",
    "TSX": ".TO", "TOR": ".TO", "TSXV": ".V",
}


def normalize_ticker(raw: str) -> str:
    """Wandelt 'SYMBOL:EXCHANGE' (Twelve Data) in yfinance-Format 'SYMBOL.SUFFIX'.

    - 'AEEM:EPA'  → 'AEEM.PA'
    - 'AAPL:NASDAQ' → 'AAPL'
    - 'IWDA.AS'   → 'IWDA.AS' (bereits yfinance-Format, unverändert)
    - unbekannter Exchange → nur das Symbol (best effort)
    """
    if not raw or ":" not in raw:
        return raw
    symbol, exchange = raw.split(":", 1)
    suffix = EXCHANGE_SUFFIX.get(exchange.strip().upper())
    if suffix is None:
        # Unbekannte Börse: Symbol ohne Suffix versuchen
        return symbol
    return f"{symbol}{suffix}"
