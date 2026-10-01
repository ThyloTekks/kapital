"""Trade Republic CSV parser."""

from __future__ import annotations

import hashlib
import io
import re

import pandas as pd

from .utils import (
    decode, read_bytes, parse_german_amount, parse_german_date,
    empty_df, make_row, finalize_df,
)

# Old German-style type → category (legacy format)
_TYPE_CATEGORY_MAP = {
    "einzahlung": "Umbuchung",
    "auszahlung": "Umbuchung",
    "kauf": "Investment & Sparen",
    "verkauf": "Investment & Sparen",
    "dividende": "Einkommen",
    "dividenden": "Einkommen",
    "zins": "Einkommen",
    "zinsen": "Einkommen",
    "zinszahlung": "Einkommen",
    "sparplan": "Investment & Sparen",
    "sparplanausführung": "Investment & Sparen",
    "gebühr": "Gebühren & Zinsen",
    "steuer": "Gebühren & Zinsen",
    "steuern": "Gebühren & Zinsen",
    "quellensteuer": "Gebühren & Zinsen",
    "kapitalertragsteuer": "Gebühren & Zinsen",
    "solidaritätszuschlag": "Gebühren & Zinsen",
    "saveback": "Einkommen",
    "bonus": "Einkommen",
    "prämie": "Einkommen",
    "round up": "Investment & Sparen",
    "round-up": "Investment & Sparen",
    "ausschüttung": "Einkommen",
    "rückzahlung": "Umbuchung",
    "erstattung": "Sonstiges",
}

# New English-style type → category (Transaktionsexport.csv format)
_NEW_TYPE_CATEGORY = {
    "buy": "Investment & Sparen",
    "sell": "Investment & Sparen",
    "customer_inbound": "Umbuchung",
    "customer_outbound": "Umbuchung",
    "transfer_inbound": "Umbuchung",
    "transfer_instant_outbound": "Umbuchung",
    "dividend": "Einkommen",
    "distribution": "Einkommen",
    "interest_payment": "Einkommen",
    "referral": "Einkommen",
    "saveback": "Einkommen",
    "round_up": "Investment & Sparen",
    "corporate_action": "Sonstiges",
    "capital_incr_cash": "Sonstiges",
    "rights": "Sonstiges",
    "exchange": "Gebühren & Zinsen",
    "tax_refund": "Einkommen",
    "bonus": "Einkommen",
    "gift": "Einkommen",
    "stockperk": "Einkommen",
    "credit": "Einkommen",
    "card_transaction": "Sonstiges",
    "card_refund": "Sonstiges",
    "savings_plan": "Investment & Sparen",
    "isin_change": "Sonstiges",
    "unbundling": "Sonstiges",
    "merger": "Sonstiges",
    "reverse_split": "Sonstiges",
    "split": "Sonstiges",
    "free_receipt": "Sonstiges",
    "tender_offer": "Sonstiges",
    "warrant_exercise": "Investment & Sparen",
    "tilg": "Sonstiges",
    "offer": "Sonstiges",
    "bonus_issue": "Sonstiges",
    "bonus_issue_cancelled": "Sonstiges",
    "spin_off": "Sonstiges",
    "capital_reduction": "Sonstiges",
}

# Only these types move shares — shares in other rows (e.g. DIVIDEND) indicate
# "shares held" not shares traded, and must NOT affect position reconstruction.
_SHARE_MOVING_TYPES = {"buy", "sell"}

_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$')


def _best_sep(text: str) -> str:
    """Pick the separator that yields the most consistent column count."""
    best_sep, best_score = ";", 0
    for sep in (";", ",", "\t"):
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str,
                             on_bad_lines="skip", nrows=20)
            if len(df.columns) < 2:
                continue
            score = len(df.columns) * len(df)
            if score > best_score:
                best_score = score
                best_sep = sep
        except Exception:
            continue
    return best_sep


def _is_new_tr_export(df_raw: pd.DataFrame) -> bool:
    """Detect the modern Transaktionsexport.csv format (English column names)."""
    cols = {c.strip().strip('"').lower() for c in df_raw.columns}
    return "symbol" in cols and "shares" in cols and "type" in cols


def _parse_new_export(df_raw: pd.DataFrame, account_label: str) -> pd.DataFrame:
    """Parse the modern Trade Republic Transaktionsexport.csv format."""
    df_raw.columns = [c.strip().strip('"').lower() for c in df_raw.columns]

    rows = []
    for _, row in df_raw.iterrows():
        # Date (YYYY-MM-DD)
        date_str = str(row.get("date", "") or "").strip()
        if not date_str or date_str == "nan":
            continue
        date = parse_german_date(date_str[:10])
        if date is None:
            continue

        # Amount – skip rows without a cash amount (e.g. pure corporate actions)
        amt_raw = str(row.get("amount", "") or "").strip()
        if not amt_raw or amt_raw == "nan":
            continue
        amount = parse_german_amount(amt_raw)
        if amount is None:
            continue

        # Include fee + tax in effective amount for accurate cost basis
        fee = parse_german_amount(str(row.get("fee", "") or "").strip()) or 0.0
        tax = parse_german_amount(str(row.get("tax", "") or "").strip()) or 0.0
        amount = amount + fee + tax

        # Transaction type
        tx_type = str(row.get("type", "") or "").strip().upper()
        tx_type_key = tx_type.lower()

        # Security name
        name_raw = str(row.get("name", "") or "").strip()
        if name_raw.lower() in ("nan", "none", ""):
            name_raw = ""
        description = f"{tx_type}: {name_raw}" if name_raw else tx_type

        # ISIN from symbol column
        isin_raw = str(row.get("symbol", "") or "").strip()
        isin = isin_raw if _ISIN_RE.match(isin_raw) else ""

        # Units/shares — only BUY and SELL actually change share position.
        # DIVIDEND/DISTRIBUTION store "shares held" not "shares traded"; zeroing
        # them prevents position reconstruction from counting dividends as buys.
        units = 0.0
        if tx_type_key in _SHARE_MOVING_TYPES:
            shares_raw = str(row.get("shares", "") or "").strip()
            if shares_raw and shares_raw not in ("nan", ""):
                try:
                    units = float(shares_raw)
                except (ValueError, TypeError):
                    units = 0.0

        # Price per unit (execution price, without fees)
        price_raw = str(row.get("price", "") or "").strip()
        price_per_unit = 0.0
        if price_raw and price_raw not in ("nan", ""):
            try:
                price_per_unit = float(price_raw)
            except (ValueError, TypeError):
                price_per_unit = 0.0

        category = _NEW_TYPE_CATEGORY.get(tx_type_key, "Sonstiges")

        r = make_row(
            date, amount, description, "Trade Republic", "Trade Republic",
            account_label, isin=isin, units=units, price_per_unit=price_per_unit,
        )
        r["category"] = category

        # Use transaction_id as stable hash to prevent re-import duplicates
        tx_id = str(row.get("transaction_id", "") or "").strip()
        if tx_id and tx_id != "nan":
            r["tx_hash"] = hashlib.md5(f"TR:{tx_id}".encode()).hexdigest()[:12]

        rows.append(r)

    return finalize_df(pd.DataFrame(rows)) if rows else empty_df()


def _parse_old_format(df_raw: pd.DataFrame, account_label: str) -> pd.DataFrame:
    """Parse legacy German-column Trade Republic CSV exports."""
    col_lower = {c: c.lower().strip() for c in df_raw.columns}

    def find(*keywords) -> str | None:
        for kw in keywords:
            for orig, low in col_lower.items():
                if kw in low:
                    return orig
        return None

    date_col   = find("datum", "date", "buchungsdatum", "wertstellungsdatum")
    amount_col = find("gesamtbetrag", "betrag", "gesamt", "netto", "brutto", "amount", "total")
    type_col   = find("typ", "type", "transaktion", "geschäftsart", "art", "buchungstext")
    name_col   = find("bezeichnung", "beschreibung", "description",
                      "titel", "name", "wertpapier", "security")

    if not date_col:
        return empty_df()

    if not amount_col:
        for col in df_raw.columns:
            if col in (date_col, type_col, name_col):
                continue
            parsed = df_raw[col].dropna().apply(
                lambda v: parse_german_amount(str(v))
            ).dropna()
            if len(parsed) > len(df_raw) * 0.5:
                amount_col = col
                break

    if not amount_col:
        return empty_df()

    rows = []
    for _, row in df_raw.iterrows():
        date_str = str(row.get(date_col, "")).strip().strip('"')
        if not date_str or date_str.lower() in ("nan", ""):
            continue
        date = parse_german_date(date_str)
        if date is None:
            continue

        amount_str = str(row.get(amount_col, "")).strip().strip('"')
        amount = parse_german_amount(amount_str)
        if amount is None:
            continue

        tx_type_raw = str(row.get(type_col, "") if type_col else "").strip().strip('"')
        name_raw    = str(row.get(name_col,  "") if name_col else "").strip().strip('"')
        tx_type_low = tx_type_raw.lower()

        if tx_type_raw and name_raw and tx_type_low != name_raw.lower():
            description = f"{tx_type_raw}: {name_raw}"
        elif tx_type_raw:
            description = tx_type_raw
        else:
            description = name_raw

        category = _TYPE_CATEGORY_MAP.get(tx_type_low, "Investment & Sparen")

        r = make_row(date, amount, description, "Trade Republic", "Trade Republic", account_label)
        r["category"] = category
        rows.append(r)

    return finalize_df(pd.DataFrame(rows)) if rows else empty_df()


def parse_trade_republic(uploaded_file, account_label: str = "Trade Republic") -> pd.DataFrame:
    raw  = read_bytes(uploaded_file)
    text = decode(raw)
    text = text.lstrip("\ufeff").lstrip("\u00ef\u00bb\u00bf")

    sep = _best_sep(text)
    try:
        df_raw = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, on_bad_lines="skip")
    except Exception:
        return empty_df()

    if df_raw.empty or len(df_raw.columns) < 2:
        return empty_df()

    df_raw.columns = [str(c).strip().strip('"').strip() for c in df_raw.columns]

    if _is_new_tr_export(df_raw):
        return _parse_new_export(df_raw, account_label)
    return _parse_old_format(df_raw, account_label)
