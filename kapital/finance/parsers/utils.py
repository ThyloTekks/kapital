"""Shared helpers for all CSV parsers."""

from __future__ import annotations

import hashlib
import re
import io
import pandas as pd
from typing import Optional


def detect_encoding(raw: bytes) -> str:
    """Best-effort Encoding-Erkennung ohne harte Abhängigkeit von chardet.

    Reihenfolge: chardet → charset-normalizer → UTF-8/Latin-1-Heuristik.
    So crasht der Import nicht, falls chardet im aktiven venv fehlt.
    """
    sample = raw[:10_000]
    # 1. chardet, falls installiert
    try:
        import chardet
        enc = (chardet.detect(sample) or {}).get("encoding")
        if enc:
            return enc if enc.lower() != "ascii" else "utf-8"
    except Exception:
        pass
    # 2. charset-normalizer (häufig via requests/yfinance vorhanden)
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(sample).best()
        if best and best.encoding:
            enc = best.encoding
            return enc if enc.lower() != "ascii" else "utf-8"
    except Exception:
        pass
    # 3. Heuristik: erst UTF-8 versuchen, sonst Latin-1
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def read_bytes(uploaded_file) -> bytes:
    uploaded_file.seek(0)
    return uploaded_file.read()


def decode(raw: bytes) -> str:
    enc = detect_encoding(raw)
    try:
        return raw.decode(enc)
    except Exception:
        return raw.decode("latin-1", errors="replace")


def parse_german_amount(value: str) -> Optional[float]:
    if not isinstance(value, str):
        try:
            return float(value)
        except Exception:
            return None
    # Strip currency symbols, currency codes (EUR, USD…), non-breaking spaces, quotes
    v = re.sub(r'[€$£\xa0"\']', "", value).strip()
    v = re.sub(r"\s*[A-Z]{3}\s*$", "", v).strip()
    v = v.replace("\u202f", "").replace("\u00a0", "")  # narrow no-break space
    if not v or v.lower() in ("nan", "none", "-", "n/a"):
        return None

    # Detect German format: comma is decimal separator, dots are thousands
    # Heuristic: if comma appears after the last dot → German format
    last_comma = v.rfind(",")
    last_dot   = v.rfind(".")

    if last_comma > last_dot:
        # German: "1.234,56" or "1.234,6" or "-100,00"
        v = v.replace(".", "").replace(",", ".")
    elif last_dot > last_comma and last_comma != -1:
        # US: "1,234.56" — remove thousands comma
        v = v.replace(",", "")
    elif last_comma != -1 and last_dot == -1:
        # Only comma, no dot → German decimal comma: "100,00"
        v = v.replace(",", ".")
    # else: only dot or no separator → treat as-is (e.g. "100.00" or "100")

    v = v.replace(" ", "")
    try:
        return float(v)
    except ValueError:
        return None


def parse_german_date(value: str) -> Optional[pd.Timestamp]:
    if not isinstance(value, str):
        return None
    v = value.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return pd.to_datetime(v, format=fmt)
        except Exception:
            continue
    try:
        return pd.to_datetime(v, dayfirst=True)
    except Exception:
        return None


def make_tx_hash(date: pd.Timestamp, amount: float, account_label: str, description: str,
                 account: str = "") -> str:
    """Stable fingerprint used for deduplication.

    Uses the account *type* (e.g. 'Giro', 'TR') rather than the mutable
    account_label so that the same transaction isn't duplicated when the
    user renames an account or imports it from two overlapping CSV exports.
    """
    date_str = pd.Timestamp(date).strftime("%Y-%m-%d") if date is not None else ""
    # Prefer account type; fall back to account_label for backwards compat
    acc_key = account or account_label
    key = f"{date_str}|{amount:.2f}|{acc_key}|{str(description)[:60]}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def empty_df() -> pd.DataFrame:
    from ..models import COLUMNS
    return pd.DataFrame(columns=COLUMNS)


def make_row(
    date: pd.Timestamp,
    amount: float,
    description: str,
    payee: str,
    account: str,
    account_label: str = "",
    notes: str = "",
    isin: str = "",
    units: float = 0.0,
    price_per_unit: float = 0.0,
) -> dict:
    label = account_label or account
    return {
        "date": date,
        "amount": amount,
        "description": description,
        "payee": payee,
        "account": account,
        "account_label": label,
        "category": "Sonstiges",
        "is_transfer": False,
        "transfer_id": "",
        "tx_hash": make_tx_hash(date, amount, label, description, account=account),
        "notes": notes,
        "isin": isin,
        "units": units,
        "price_per_unit": price_per_unit,
    }


_FLOAT_COLS = {"amount", "units", "price_per_unit"}
_BOOL_COLS  = {"is_transfer", "is_sonderausgabe"}

def finalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Enforce schema, types and sort order. Used by all parsers."""
    if df.empty:
        return df
    from ..models import COLUMNS
    for col in COLUMNS:
        if col not in df.columns:
            if col in _BOOL_COLS:
                df[col] = False
            elif col in _FLOAT_COLS:
                df[col] = 0.0
            else:
                df[col] = ""
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["units"] = pd.to_numeric(df["units"], errors="coerce").fillna(0.0)
    df["price_per_unit"] = pd.to_numeric(df["price_per_unit"], errors="coerce").fillna(0.0)
    df = df.dropna(subset=["date", "amount"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[COLUMNS]
