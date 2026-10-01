"""
Trade Republic PDF parser — uses pypdfium2 (no native crypto dependency).

Handles:
  1. Wertpapierabrechnung Kauf / Verkauf
  2. Sparplanausführung
  3. Dividendenabrechnung / Zinsgutschrift / Saveback
  4. Kontoauszug (account statement, multi-transaction)
  5. Depotübersicht / Portfolioübersicht snapshot

pypdfium2 is used for text extraction; all parsing is regex-based on the
raw text so it works across different TR PDF layouts.
"""

from __future__ import annotations

import io
import re
from typing import Optional

import pandas as pd

try:
    import pypdfium2 as pdfium
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

from .utils import make_row, finalize_df, empty_df, parse_german_amount, parse_german_date


# ── Regex helpers ─────────────────────────────────────────────────────────────

_RE_ISIN    = re.compile(r'\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b')
_RE_DATE    = re.compile(r'\b(\d{2}\.\d{2}\.\d{4})\b')
_RE_AMOUNT  = re.compile(r'([+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2})[\s\xa0]*(?:EUR|€)')
_RE_UNITS   = re.compile(
    r'(\d{1,6}(?:[.,]\d+)?)\s*(?:Anteile?|Stück|Aktien|stk\.?)',
    re.IGNORECASE,
)
_RE_PRICE   = re.compile(
    r'(?:Kurs|Preis|à|je\s+Anteil)[:\s]+(\d{1,6}(?:\.\d{3})*,\d{2,4})\s*(?:EUR|€)',
    re.IGNORECASE,
)
_RE_TOTAL   = re.compile(
    r'(?:Gesamtbetrag|Kurswert|Nettobetrag|Betrag|Gesamt)[:\s]+'
    r'([+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:EUR|€)',
    re.IGNORECASE,
)

# German month-name date: "01 Sept. 2025", "01\nSept.\n2025", "01 Okt. 2025"
_MONTHS_DE = {
    'jan': 1, 'feb': 2, 'mär': 3, 'mar': 3, 'apr': 4, 'mai': 5,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dez': 12,
}
_RE_DATE_LONG = re.compile(
    r'(\d{1,2})\s*\.?\s*'
    r'(Jan|Feb|M[äa]r(?:z)?|Apr|Mai|Jun(?:i)?|Jul(?:i)?|Aug|Sept?|Okt|Nov|Dez)\.?\s*'
    r'(\d{4})',
    re.IGNORECASE,
)

# Amount without EUR/€ suffix (used in Depotauszug)
_RE_AMOUNT_PLAIN = re.compile(r'^\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*$')
_RE_STK = re.compile(r'^([\d.,]+)\s*Stk\.\s*(.*)')


def _parse_long_date(m: re.Match) -> Optional[pd.Timestamp]:
    month = _MONTHS_DE.get(m.group(2).lower()[:3])
    if not month:
        return None
    try:
        return pd.Timestamp(year=int(m.group(3)), month=month, day=int(m.group(1)))
    except Exception:
        return None


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_text(uploaded_file) -> str:
    """Extract all text from a PDF using pypdfium2."""
    if not _PDF_AVAILABLE:
        raise ImportError("pypdfium2 ist nicht installiert. Bitte: pip install pypdfium2")
    uploaded_file.seek(0)
    raw = uploaded_file.read()
    doc = pdfium.PdfDocument(raw)
    pages_text = []
    for i in range(len(doc)):
        page = doc[i]
        tp   = page.get_textpage()
        pages_text.append(tp.get_text_range())
    # Normalise non-breaking spaces to regular spaces so amount regexes work
    return "\n".join(pages_text).replace("\xa0", " ")


# ── Document type detection ───────────────────────────────────────────────────

def _detect_type(text: str) -> str:
    t = text[:2000].lower()
    if 'wertpapierabrechnung' in t and 'verkauf' in t:
        return 'verkauf'
    if 'wertpapierabrechnung' in t and 'kauf' in t:
        return 'kauf'
    if 'sparplan' in t and ('ausführung' in t or 'kauf' in t):
        return 'sparplan'
    if 'dividendenabrechnung' in t or 'dividende' in t:
        return 'dividende'
    if 'zinsgutschrift' in t:
        return 'zinsen'
    if 'saveback' in t:
        return 'saveback'
    if 'round up' in t or 'roundup' in t:
        return 'roundup'
    if 'depotauszug' in t or 'depotübersicht' in t or 'portfolioübersicht' in t or 'depotbestand' in t:
        return 'depot'
    if 'kontoauszug' in t or 'kontoübersicht' in t or 'umsatzübersicht' in t or 'umsätze' in t:
        return 'kontoauszug'
    return 'unknown'


# ── Single-transaction parser (Kauf, Verkauf, Sparplan, Dividende …) ──────────

def _parse_single(text: str, doc_type: str, account_label: str) -> pd.DataFrame:
    """Parse a one-trade PDF into a single-row DataFrame."""

    # --- Date ---
    date_m = re.search(
        r'(?:Ausführungstag|Handelstag|Datum|Valutatag|Buchungsdatum)[:\s]+(\d{2}\.\d{2}\.\d{4})',
        text, re.IGNORECASE,
    )
    if not date_m:
        date_m = _RE_DATE.search(text)
    date = parse_german_date(date_m.group(1)) if date_m else None
    if date is None:
        return empty_df()

    # --- ISIN ---
    isin_m = re.search(r'ISIN[:\s]+([A-Z]{2}[A-Z0-9]{9}[0-9])', text, re.IGNORECASE)
    if not isin_m:
        isin_m = _RE_ISIN.search(text)
    isin = isin_m.group(1) if isin_m else ""

    # --- Security name ---
    name = ""
    for pattern in [
        r'(?:Titel|Wertpapier|Produkt|Instrument)[:\s]*\n?\s*(.+?)(?:\n|ISIN|WKN)',
        r'(?:ISIN\s+' + re.escape(isin) + r'\s*)(.+?)(?:\n)',
    ]:
        nm = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if nm:
            name = nm.group(1).strip().split('\n')[0].strip()
            break
    if not name and isin:
        # Grab the line immediately before the ISIN in the text
        pos = text.find(isin)
        if pos > 0:
            before_lines = text[:pos].strip().splitlines()
            candidates = [l.strip() for l in before_lines if l.strip() and not _RE_DATE.match(l.strip())]
            if candidates:
                name = candidates[-1]

    # --- Units ---
    units = 0.0
    um = _RE_UNITS.search(text)
    if um:
        units = parse_german_amount(um.group(1)) or 0.0

    # --- Price per unit ---
    price_per_unit = 0.0
    pm = _RE_PRICE.search(text)
    if pm:
        price_per_unit = parse_german_amount(pm.group(1)) or 0.0

    # --- Total amount ---
    amount = None
    tm = _RE_TOTAL.search(text)
    if tm:
        amount = parse_german_amount(tm.group(1))
    if amount is None:
        all_amounts = [parse_german_amount(m.group(1)) for m in _RE_AMOUNT.finditer(text)]
        all_amounts = [a for a in all_amounts if a is not None]
        if all_amounts:
            amount = max(all_amounts, key=abs)
    if amount is None:
        return empty_df()

    # --- Sign & category ---
    if doc_type in ('kauf', 'sparplan', 'roundup'):
        amount        = -abs(amount)
        units         = abs(units)
        category      = "Investment & Sparen"
    elif doc_type == 'verkauf':
        amount        = abs(amount)
        units         = -abs(units)
        category      = "Investment & Sparen"
    else:  # dividende, zinsen, saveback
        amount        = abs(amount)
        units         = 0.0
        category      = "Einkommen"

    desc = name or doc_type.capitalize()
    row  = make_row(
        date=date, amount=amount, description=desc,
        payee="Trade Republic", account="Trade Republic",
        account_label=account_label,
        isin=isin, units=units, price_per_unit=price_per_unit,
    )
    row["category"] = category
    return finalize_df(pd.DataFrame([row]))


# ── Kontoauszug (multi-transaction statement) parser ─────────────────────────

_TX_TYPE_MAP = {
    'einzahlung':     ('Umbuchung',          +1),
    'auszahlung':     ('Umbuchung',          -1),
    'kauf':           ('Investment & Sparen', -1),
    'verkauf':        ('Investment & Sparen', +1),
    'sparplan':       ('Investment & Sparen', -1),
    'dividende':      ('Einkommen',           +1),
    'zinsen':         ('Einkommen',           +1),
    'zinsgutschrift': ('Einkommen',           +1),
    'saveback':       ('Einkommen',           +1),
    'round up':       ('Investment & Sparen', -1),
    'gebühr':         ('Gebühren & Zinsen',   -1),
    'steuer':         ('Gebühren & Zinsen',   -1),
    'prämie':         ('Einkommen',           +1),
}


def _category_from_desc(desc: str) -> str:
    d = desc.lower()
    for kw, (cat, _) in _TX_TYPE_MAP.items():
        if kw in d:
            return cat
    return "Investment & Sparen"


def _parse_kontoauszug(text: str, account_label: str) -> pd.DataFrame:
    """
    Extract multiple transactions from a TR account statement (Kontoauszug).
    Handles German month-name dates like '01 Sept. 2025' (potentially split over lines).
    """
    rows = []

    # Find all date positions using German month format
    date_matches = list(_RE_DATE_LONG.finditer(text))

    # Fallback to DD.MM.YYYY if no long-format dates found
    if not date_matches:
        date_matches = list(_RE_DATE.finditer(text))
        use_long = False
    else:
        use_long = True

    for idx, dm in enumerate(date_matches):
        if use_long:
            date = _parse_long_date(dm)
        else:
            date = parse_german_date(dm.group(1))
        if date is None:
            continue

        # Text chunk from end of this date to start of next
        start = dm.end()
        end   = date_matches[idx + 1].start() if idx + 1 < len(date_matches) else len(text)
        chunk = text[start:end]

        # Flatten whitespace for easier matching
        chunk_flat = re.sub(r'[ \t\n]+', ' ', chunk).strip()

        # Skip header/footer lines that are not transactions
        skip_keywords = ('datum', 'beschreibung', 'zahlungseingang', 'zahlungsausgang',
                         'saldo', 'kontoübersicht', 'umsatzübersicht', 'barmittelübersicht',
                         'transaktionsübersicht', 'hinweise', 'erstellt am', 'seite',
                         'anfangssaldo', 'endsaldo', 'produkt', 'treuhandkonten',
                         'geldmarktfonds', 'stück', 'kurs pro stück')
        cf = chunk_flat.lower()
        if any(kw in cf[:60] for kw in skip_keywords):
            continue
        if not chunk_flat:
            continue

        # Find all EUR amounts in this chunk
        eur_amounts = list(_RE_AMOUNT.finditer(chunk))
        if not eur_amounts:
            continue

        # First EUR amount = transaction amount; last = running saldo (skip it)
        tx_amount = parse_german_amount(eur_amounts[0].group(1))
        if tx_amount is None:
            continue

        # Extract ISIN (from description like "Cash Dividend for ISIN US78409V1044"
        # or "Buy trade US0378331005 APPLE INC.")
        isin  = ""
        isin_m = re.search(r'ISIN\s+([A-Z]{2}[A-Z0-9]{9}[0-9])', chunk_flat)
        if not isin_m:
            isin_m = _RE_ISIN.search(chunk_flat)
        if isin_m:
            isin = isin_m.group(1)

        # Extract quantity from "quantity: X.XXXX"
        units = 0.0
        qty_m = re.search(r'quantity:\s*([\d.,]+)', chunk_flat, re.IGNORECASE)
        if qty_m:
            units = parse_german_amount(qty_m.group(1)) or 0.0

        # Determine sign and category from transaction type.
        # TR Kontoauszug uses German: "Direktkauf Kauf" / "Direktverkauf Verkauf"
        _buy_kws  = ('buy trade', 'sparplan', 'direktkauf', 'ausführung handel direktkauf')
        _sell_kws = ('sell trade', 'direktverkauf', 'ausführung handel direktverkauf')
        _inc_kws  = ('zinsen', 'interest payment', 'ertrag', 'dividend', 'ausschüttung',
                     'saveback', 'empfehlung', 'referral', 'rückerstattung')
        _in_kws   = ('einzahlung', 'überweisung accepted payin', 'einzahlung akzeptiert',
                     'accepted payin')
        if any(kw in cf for kw in _buy_kws):
            amount   = -abs(tx_amount)
            category = "Investment & Sparen"
        elif any(kw in cf for kw in _sell_kws):
            amount   = abs(tx_amount)
            category = "Investment & Sparen"
            units    = -units
        elif any(kw in cf[:80] for kw in _inc_kws):
            amount   = abs(tx_amount)
            category = "Einkommen"
        elif any(kw in cf for kw in _in_kws):
            amount   = abs(tx_amount)
            category = "Umbuchung"
        elif any(kw in cf[:60] for kw in ('auszahlung', 'ausgang')):
            amount   = -abs(tx_amount)
            category = "Umbuchung"
        else:
            amount   = tx_amount
            category = _category_from_desc(chunk_flat)

        # Build a clean description (remove amounts and trailing saldo text)
        desc_text = _RE_AMOUNT.sub('', chunk_flat).strip()
        # Remove leading type keywords (Zinsen, Ertrag, Handel, …)
        desc_text = re.sub(
            r'^(Zinsen|Ertrag|Handel|Empfehlung|Einzahlung|Auszahlung)\s*',
            '', desc_text, flags=re.IGNORECASE,
        ).strip()
        desc = desc_text[:100] if desc_text else "Trade Republic"

        r = make_row(
            date=date, amount=amount, description=desc,
            payee="Trade Republic", account="Trade Republic",
            account_label=account_label, isin=isin, units=units,
        )
        r["category"] = category
        rows.append(r)

    return finalize_df(pd.DataFrame(rows)) if rows else empty_df()


# ── Depot snapshot (Depotübersicht) ──────────────────────────────────────────

def parse_depot_snapshot(uploaded_file) -> pd.DataFrame:
    """
    Parse a TR Depotauszug / portfolio overview PDF.
    Returns a DataFrame of current holdings: isin, name, units, current_value.
    Not imported as transactions — used for display only.
    """
    if not _PDF_AVAILABLE:
        return pd.DataFrame()
    try:
        text = _extract_text(uploaded_file)
    except Exception:
        return pd.DataFrame()

    lines    = [l.strip() for l in text.splitlines() if l.strip()]
    holdings = []
    seen_isins: set = set()

    _RE_ISIN_LABELED = re.compile(r'ISIN:\s*([A-Z]{2}[A-Z0-9]{9}[0-9])', re.IGNORECASE)

    for i, line in enumerate(lines):
        # Try "ISIN: XXXX" format first, then bare ISIN
        im = _RE_ISIN_LABELED.search(line)
        if not im:
            im = _RE_ISIN.search(line)
        if not im:
            continue
        isin = im.group(1)
        if isin in seen_isins:
            continue
        seen_isins.add(isin)

        # Search backwards for the "X,XX Stk. Name" line
        name  = ""
        units = None
        for back in range(1, 8):
            if i - back < 0:
                break
            prev = lines[i - back]
            sm = _RE_STK.match(prev)
            if sm:
                units = parse_german_amount(sm.group(1))
                name  = sm.group(2).strip()
                # Append intermediate lines between Stk-line and ISIN-line as part of name
                for fwd in range(1, back):
                    mid = lines[i - back + fwd]
                    if _RE_ISIN_LABELED.search(mid) or mid.lower().startswith('lagerland') or mid.lower().startswith('isin'):
                        break
                    name = (name + " " + mid).strip()
                break

        # Fallback: line before ISIN
        if not name and i > 0:
            prev = lines[i - 1]
            if not _RE_DATE.match(prev) and not _RE_AMOUNT.search(prev) and not prev.lower().startswith('lagerland'):
                name = prev

        # Find current_value by scanning forward for plain numeric amounts
        # Format after ISIN line: [Lagerland: …]  price  DD.MM.YYYY  value
        plain_amounts = []
        for fwd in range(1, 10):
            if i + fwd >= len(lines):
                break
            fwd_line = lines[i + fwd]
            # Stop at next position's Stk. line or ISIN line
            if _RE_STK.match(fwd_line) or _RE_ISIN_LABELED.search(fwd_line):
                break
            am = _RE_AMOUNT_PLAIN.match(fwd_line)
            if am:
                v = parse_german_amount(am.group(1))
                if v is not None:
                    plain_amounts.append(v)

        # plain_amounts: [price_per_share, current_value]  (value is the last one)
        current_value = plain_amounts[-1] if plain_amounts else None

        holdings.append({
            "isin":          isin,
            "name":          name,
            "units":         units,
            "current_value": current_value,
        })

    return pd.DataFrame(holdings) if holdings else pd.DataFrame()


# ── Public entry point ────────────────────────────────────────────────────────

def parse_tr_pdf(uploaded_file, account_label: str = "Trade Republic") -> pd.DataFrame:
    """
    Auto-detect PDF type and parse into a normalized transactions DataFrame.
    Returns empty DataFrame on failure (never raises).
    """
    if not _PDF_AVAILABLE:
        raise ImportError(
            "pypdfium2 ist nicht installiert.\n"
            "Bitte ausführen: pip install pypdfium2"
        )
    try:
        text = _extract_text(uploaded_file)
    except Exception as e:
        return empty_df()

    if not text.strip():
        return empty_df()

    doc_type = _detect_type(text)

    if doc_type in ('kauf', 'verkauf', 'sparplan', 'dividende', 'zinsen', 'saveback', 'roundup'):
        return _parse_single(text, doc_type, account_label)
    elif doc_type == 'kontoauszug':
        return _parse_kontoauszug(text, account_label)
    elif doc_type == 'depot':
        return empty_df()  # handled by parse_depot_snapshot
    else:
        # Unknown — try single-transaction first, then statement fallback
        df = _parse_single(text, 'unknown', account_label)
        if not df.empty:
            return df
        return _parse_kontoauszug(text, account_label)
