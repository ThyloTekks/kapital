"""
Giro account CSV parser.

Supported formats (auto-detected):
  - DKB (Deutsche Kreditbank)
  - ING Girokonto / Tagesgeld / Extrakonto
  - Sparkasse (CAMT-style CSV)
  - Comdirect
  - Generic fallback

The parser tries to extract the IBAN from the CSV header so the
account_label can default to the IBAN if the user doesn't specify one.
Each parser receives an explicit account_label so multiple ING accounts
(e.g. Girokonto + Tagesgeld + Extrakonto) stay separate.
"""

from __future__ import annotations

import io
import re
import pandas as pd
from typing import Optional

from .utils import (
    decode, read_bytes, parse_german_amount, parse_german_date,
    empty_df, make_row, finalize_df,
)


# ── IBAN extraction ───────────────────────────────────────────────────────────

def extract_iban(text: str) -> Optional[str]:
    """Try to pull an IBAN from the first ~30 lines of the file."""
    for line in text.splitlines()[:30]:
        m = re.search(r"\b(DE\d{2}[\s\d]{15,30})\b", line)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


# ── Separator detection ───────────────────────────────────────────────────────

def _detect_sep(text: str) -> str:
    """Pick ; or , based on which appears more in the first 5 lines."""
    sample = "\n".join(text.splitlines()[:5])
    return ";" if sample.count(";") >= sample.count(",") else ","


# ── Format detectors ──────────────────────────────────────────────────────────

def _is_dkb(h: str) -> bool:
    # Old format: Kontonummer + Buchungstag/Belegdatum
    old = "Kontonummer" in h and ("Buchungstag" in h or "Belegdatum" in h)
    # New format (2023+): Buchungsdatum + Zahlungsempfänger
    new = "Buchungsdatum" in h and ("Zahlungsempf" in h or "Zahlungspflichtige" in h)
    return old or new

def _is_ing(h: str) -> bool:
    # Old: Auftraggeber/Empfänger (with slash)
    # New: Auftraggeber / Empfänger (with spaces), or just Auftraggeber
    old = ("Buchung" in h and "Auftraggeber" in h) or "ING-DiBa" in h or "ING Bank" in h
    new = "Umsätze" in h and "DIN EN ISO" in h  # ING new header line
    return old or new

def _is_sparkasse(h: str) -> bool:
    return "Auftragskonto" in h and "Buchungstag" in h

def _is_comdirect(h: str) -> bool:
    return "Umsatz in EUR" in h and "Vorgang" in h


# ── DKB ───────────────────────────────────────────────────────────────────────

def _parse_dkb(text: str, label: str) -> pd.DataFrame:
    lines = text.splitlines()
    # Find the data header row — supports old ("Buchungstag") and new ("Buchungsdatum") format
    header_idx = next(
        (i for i, l in enumerate(lines)
         if "Buchungstag" in l or "Belegdatum" in l or "Buchungsdatum" in l),
        None,
    )
    if header_idx is None:
        return empty_df()

    csv_text = "\n".join(lines[header_idx:])
    sep = _detect_sep(csv_text)
    try:
        df_raw = pd.read_csv(io.StringIO(csv_text), sep=sep, dtype=str, on_bad_lines="skip")
    except Exception:
        return empty_df()
    df_raw.columns = [c.strip().strip('"') for c in df_raw.columns]

    def fc(*kw):
        return next((c for c in df_raw.columns if any(k in c for k in kw)), None)

    date_col    = fc("Buchungstag", "Belegdatum", "Buchungsdatum")
    # New DKB format has separate sender/receiver columns — use both as fallback
    payee_col   = fc("Zahlungsempf", "Auftraggeber", "Beguenstigter")
    payer_col   = fc("Zahlungspflichtige")
    desc_col    = fc("Verwendungszweck")
    amount_col  = fc("Betrag")

    if not date_col or not amount_col:
        return empty_df()

    rows = []
    for _, row in df_raw.iterrows():
        date = parse_german_date(str(row.get(date_col, "")))
        if date is None:
            continue
        amount = parse_german_amount(str(row.get(amount_col, "")))
        if amount is None:
            continue
        def _clean(v) -> str:
            s = str(v).strip().strip('"')
            return "" if s.lower() in ("nan", "none", "") else s
        payee = _clean(row.get(payee_col) if payee_col else "")
        # New DKB: if payee is empty, use payer column (incoming transfer)
        if not payee and payer_col:
            payee = _clean(row.get(payer_col, ""))
        desc  = str(row.get(desc_col, "")  if desc_col  else "").strip().strip('"')
        rows.append(make_row(date, amount, desc, payee, "Giro", label))

    return pd.DataFrame(rows) if rows else empty_df()


# ── ING ───────────────────────────────────────────────────────────────────────

def _parse_ing(text: str, label: str) -> pd.DataFrame:
    lines = text.splitlines()
    # Find header row: line starting with "Buchung" or containing date+amount column names
    header_idx = next(
        (i for i, l in enumerate(lines)
         if (l.startswith("Buchung") and ("Auftraggeber" in l or "Betrag" in l))
         or ("Buchung" in l and "Betrag" in l)),
        None,
    )
    if header_idx is None:
        return empty_df()

    csv_text = "\n".join(lines[header_idx:])
    sep = _detect_sep(csv_text)
    try:
        df_raw = pd.read_csv(io.StringIO(csv_text), sep=sep, dtype=str, on_bad_lines="skip")
    except Exception:
        return empty_df()
    df_raw.columns = [c.strip().strip('"') for c in df_raw.columns]

    def fc(*kw):
        return next((c for c in df_raw.columns if any(k in c for k in kw)), None)

    date_col   = fc("Buchung", "Buchungsdatum")
    payee_col  = fc("Auftraggeber", "Empfänger")
    desc_col   = fc("Verwendungszweck")
    btext_col  = fc("Buchungstext")
    amount_col = fc("Betrag")

    if not date_col or not amount_col:
        return empty_df()

    rows = []
    for _, row in df_raw.iterrows():
        date = parse_german_date(str(row.get(date_col, "")))
        if date is None:
            continue
        amount = parse_german_amount(str(row.get(amount_col, "")))
        if amount is None:
            continue
        payee = str(row.get(payee_col, "") if payee_col else "").strip()
        desc  = str(row.get(desc_col,  "") if desc_col  else "").strip()
        if not desc and btext_col:
            desc = str(row.get(btext_col, "")).strip()
        rows.append(make_row(date, amount, desc, payee, "Giro", label))

    return pd.DataFrame(rows) if rows else empty_df()


# ── Sparkasse ─────────────────────────────────────────────────────────────────

def _parse_sparkasse(text: str, label: str) -> pd.DataFrame:
    sep = _detect_sep(text)
    try:
        df_raw = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, on_bad_lines="skip")
    except Exception:
        return empty_df()
    df_raw.columns = [c.strip().strip('"') for c in df_raw.columns]

    def fc(*kw):
        return next((c for c in df_raw.columns if any(k in c for k in kw)), None)

    date_col   = fc("Buchungstag")
    payee_col  = fc("Auftraggeber", "Beguenstigter")
    desc_col   = fc("Verwendungszweck")
    amount_col = fc("Betrag")

    if not date_col or not amount_col:
        return empty_df()

    rows = []
    for _, row in df_raw.iterrows():
        date = parse_german_date(str(row.get(date_col, "")))
        if date is None:
            continue
        amount = parse_german_amount(str(row.get(amount_col, "")))
        if amount is None:
            continue
        payee = str(row.get(payee_col, "") if payee_col else "").strip().strip('"')
        desc  = str(row.get(desc_col,  "") if desc_col  else "").strip().strip('"')
        rows.append(make_row(date, amount, desc, payee, "Giro", label))

    return pd.DataFrame(rows) if rows else empty_df()


# ── Comdirect ─────────────────────────────────────────────────────────────────

def _parse_comdirect(text: str, label: str) -> pd.DataFrame:
    lines = text.splitlines()
    header_idx = next(
        (i for i, l in enumerate(lines) if "Buchungstag" in l and "Umsatz" in l), None
    )
    if header_idx is None:
        return empty_df()

    csv_text = "\n".join(lines[header_idx:])
    sep = _detect_sep(csv_text)
    try:
        df_raw = pd.read_csv(io.StringIO(csv_text), sep=sep, dtype=str, on_bad_lines="skip")
    except Exception:
        return empty_df()
    df_raw.columns = [c.strip().strip('"') for c in df_raw.columns]

    def fc(*kw):
        return next((c for c in df_raw.columns if any(k in c for k in kw)), None)

    date_col   = fc("Buchungstag")
    amount_col = fc("Umsatz")
    desc_col   = fc("Buchungstext")

    if not date_col or not amount_col:
        return empty_df()

    rows = []
    for _, row in df_raw.iterrows():
        date = parse_german_date(str(row.get(date_col, "")))
        if date is None:
            continue
        amount = parse_german_amount(str(row.get(amount_col, "")))
        if amount is None:
            continue
        desc = str(row.get(desc_col, "") if desc_col else "").strip().strip('"')
        payee = ""
        m = re.search(r"(?:Auftraggeber|Empfänger|Zahlungspflichtiger)[:\s]+(.+?)(?:\s{2,}|$)", desc, re.I)
        if m:
            payee = m.group(1).strip()
        rows.append(make_row(date, amount, desc, payee, "Giro", label))

    return pd.DataFrame(rows) if rows else empty_df()


# ── Generic fallback ──────────────────────────────────────────────────────────

_DATE_KW   = ["datum", "date", "buchung", "valuta", "tag", "wertstellung"]
_AMOUNT_KW = ["betrag", "amount", "umsatz", "summe", "wert"]
_DESC_KW   = ["verwendungszweck", "beschreibung", "purpose", "text", "buchungstext", "memo", "notizen"]
_PAYEE_KW  = ["auftraggeber", "empfänger", "zahlungsempf", "zahlungspflichtige", "name", "payee", "beguenstigter"]


def _find_header_row(lines: list[str], sep: str) -> int:
    """
    Find the line index of the actual column header row.
    Looks for the first row that has at least one date-like and one amount-like keyword,
    or has many semicolons (likely a data header).
    Falls back to 0.
    """
    for i, line in enumerate(lines[:30]):
        low = line.lower()
        has_date   = any(kw in low for kw in _DATE_KW)
        has_amount = any(kw in low for kw in _AMOUNT_KW)
        if has_date and has_amount:
            return i
    return 0


def _parse_generic(text: str, label: str) -> pd.DataFrame:
    lines = text.splitlines()
    first = "\n".join(lines[:5])
    sep = ";" if first.count(";") > first.count(",") else ","

    # Skip metadata preamble — find the real header row
    header_idx = _find_header_row(lines, sep)
    csv_text = "\n".join(lines[header_idx:])

    try:
        df_raw = pd.read_csv(io.StringIO(csv_text), sep=sep, dtype=str, on_bad_lines="skip")
    except Exception:
        return empty_df()
    df_raw.columns = [str(c).strip().strip('"') for c in df_raw.columns]

    def find(keywords):
        for kw in keywords:
            for col in df_raw.columns:
                if kw in col.lower():
                    return col
        return None

    date_col   = find(_DATE_KW)
    amount_col = find(_AMOUNT_KW)
    desc_col   = find(_DESC_KW)
    payee_col  = find(_PAYEE_KW)

    if not date_col or not amount_col:
        return empty_df()

    rows = []
    for _, row in df_raw.iterrows():
        date   = parse_german_date(str(row.get(date_col, "")))
        if date is None:
            continue
        amount = parse_german_amount(str(row.get(amount_col, "")))
        if amount is None:
            continue
        desc  = str(row.get(desc_col,  "") if desc_col  else "").strip()
        payee = str(row.get(payee_col, "") if payee_col else "").strip()
        rows.append(make_row(date, amount, desc, payee, "Giro", label))

    return pd.DataFrame(rows) if rows else empty_df()


# ── Balance extraction ────────────────────────────────────────────────────────

def _parse_balance_line(line: str, next_line: str = "") -> Optional[tuple[float, str]]:
    """
    Given a line (and optionally the one after it), try to extract
    (amount_eur, date_str).  Handles:
      - Amount + EUR on same line: "Kontostand vom 31.03.2024: 1.234,56 EUR"
      - Amount in next semicolon field: "Kontostand vom 31.03.2024:;"1.234,56 EUR";"
      - Amount without EUR suffix (Sparkasse Schlusssaldo row): "...;1.234,56;"
    """
    clean = line.replace('"', '').replace(';', ' ').strip()
    m_date = re.search(r'(\d{2}\.\d{2}\.\d{4})', clean)
    date_str = m_date.group(1) if m_date else ""

    # 1) Amount with EUR on the same line
    m = re.search(r'(-?\d[\d.,]+)\s*EUR', clean, re.I)
    if m:
        amt = parse_german_amount(m.group(1))
        if amt is not None:
            return (amt, date_str)

    # 2) Amount in the next semicolon-delimited field on the same raw line
    fields = [f.strip().strip('"') for f in line.split(';')]
    for fld in fields[1:]:
        m = re.search(r'^(-?\d[\d.,]+)\s*(?:EUR)?$', fld.strip(), re.I)
        if m:
            amt = parse_german_amount(m.group(1))
            if amt is not None:
                return (amt, date_str)

    # 3) Amount on the next line (DKB / ING two-row layout)
    if next_line:
        nc = next_line.replace('"', '').replace(';', ' ').strip()
        m = re.search(r'(-?\d[\d.,]+)\s*EUR', nc, re.I)
        if m:
            amt = parse_german_amount(m.group(1))
            if amt is not None:
                return (amt, date_str)
        # Also check semicolon-separated fields of next line
        nf = [f.strip().strip('"') for f in next_line.split(';')]
        for fld in nf:
            m = re.search(r'^(-?\d[\d.,]+)\s*(?:EUR)?$', fld.strip(), re.I)
            if m:
                amt = parse_german_amount(m.group(1))
                if amt is not None:
                    return (amt, date_str)

    return None


def extract_balance(text: str) -> Optional[tuple[float, str]]:
    """
    Extract (balance_eur, date_str) from a bank CSV.

    Scans in three passes:
    1. First 50 lines — ING / DKB header balance ("Kontostand …")
    2. Last 50 lines — Comdirect footer balance ("Neuer Kontostand")
    3. Whole file  — Sparkasse Schlusssaldo / Anfangssaldo transaction rows

    Returns None if nothing is found.
    """
    lines = text.splitlines()

    # Keywords that mark a balance line (ordered by preference)
    _HEADER_KW  = re.compile(r'kontostand|neuer\s+kontostand|endkontostand', re.I)
    _SALDO_KW   = re.compile(r'schlusssaldo|anfangssaldo|saldo', re.I)

    # Pass 1 — header (first 50 lines)
    head = lines[:50]
    for i, line in enumerate(head):
        clean = line.replace('"', '').strip()
        if not _HEADER_KW.search(clean):
            continue
        result = _parse_balance_line(line, head[i + 1] if i + 1 < len(head) else "")
        if result:
            return result

    # Pass 2 — footer (last 50 lines, e.g. Comdirect "Neuer Kontostand")
    tail = lines[-50:]
    for i, line in enumerate(tail):
        clean = line.replace('"', '').strip()
        if not _HEADER_KW.search(clean):
            continue
        result = _parse_balance_line(line, tail[i + 1] if i + 1 < len(tail) else "")
        if result:
            return result

    # Pass 3 — Sparkasse Schlusssaldo rows anywhere in the file
    # Prefer Schlusssaldo (end balance) over Anfangssaldo (start balance)
    for keyword in ('schlusssaldo', 'anfangssaldo', 'saldo'):
        for i, line in enumerate(lines):
            clean = line.replace('"', '').strip()
            if not re.search(keyword, clean, re.I):
                continue
            result = _parse_balance_line(line, lines[i + 1] if i + 1 < len(lines) else "")
            if result:
                return result

    return None


# ── Public entry point ────────────────────────────────────────────────────────

def parse_giro(uploaded_file, account_label: str = "") -> pd.DataFrame:
    """
    Auto-detect bank format and parse into normalized DataFrame.
    account_label lets callers distinguish multiple accounts of the same type
    (e.g. 'ING Girokonto' vs 'ING Tagesgeld').
    """
    raw  = read_bytes(uploaded_file)
    text = decode(raw)
    h    = text[:600]

    # Default label: try IBAN from header, else generic name
    if not account_label:
        iban = extract_iban(text)
        # Also try to extract IBAN from filename (e.g. Zinskonto_DE54..._2024.csv)
        if not iban and hasattr(uploaded_file, "name"):
            m = re.search(r'(DE\d{2}[\s\d]{15,30})', str(uploaded_file.name).upper())
            if m:
                iban = re.sub(r'\s+', ' ', m.group(1)).strip()
        account_label = iban if iban else "Giro"

    if _is_dkb(h):
        df = _parse_dkb(text, account_label)
    elif _is_ing(h):
        df = _parse_ing(text, account_label)
    elif _is_sparkasse(h):
        df = _parse_sparkasse(text, account_label)
    elif _is_comdirect(h):
        df = _parse_comdirect(text, account_label)
    else:
        df = _parse_generic(text, account_label)

    df = finalize_df(df)

    # Ensure description (Verwendungszweck) is never empty
    _empty = df["description"].fillna("").str.strip() == ""
    if _empty.any():
        _fallback = df.loc[_empty, "payee"].fillna("").str.strip()
        df.loc[_empty, "description"] = _fallback.where(_fallback != "", "Buchung")

    return df
