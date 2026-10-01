"""PayPal CSV parser."""

from __future__ import annotations

import io
import pandas as pd

from .utils import decode, read_bytes, parse_german_amount, parse_german_date, empty_df, make_row, finalize_df

_TYPE_HINTS = {
    "allgemeine zahlung": "Sonstiges",
    "zahlung": "Sonstiges",
    "express-kaufzahlung": "Kleidung & Shopping",
    "website-zahlung": "Kleidung & Shopping",
    "bankeinzug": "Umbuchung",
    "bankgutschrift": "Umbuchung",
    "auszahlung": "Umbuchung",
    "geld senden": "Sonstiges",
    "geld anfordern": "Einkommen",
    "rückzahlung": "Sonstiges",
    "stornierung": "Sonstiges",
    "gebühr": "Gebühren & Zinsen",
}

_STATUS_OK = {"abgeschlossen", "completed", "ausstehend", "pending"}


def parse_paypal(uploaded_file, account_label: str = "PayPal") -> pd.DataFrame:
    raw  = read_bytes(uploaded_file)
    text = decode(raw)

    for sep in (",", ";"):
        try:
            df_raw = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, on_bad_lines="skip")
            if len(df_raw.columns) >= 5:
                break
        except Exception:
            continue
    else:
        return empty_df()

    df_raw.columns = [str(c).strip().strip('"').strip() for c in df_raw.columns]
    col_lower = {c: c.lower() for c in df_raw.columns}

    def find(*kw):
        for k in kw:
            for orig, low in col_lower.items():
                if k in low:
                    return orig
        return None

    date_col   = find("datum", "date")
    name_col   = find("name")
    type_col   = find("typ", "type")
    status_col = find("status")
    net_col    = find("netto", "net")
    gross_col  = find("brutto", "gross")

    if not date_col:
        return empty_df()
    amount_col = net_col or gross_col
    if not amount_col:
        return empty_df()

    rows = []
    for _, row in df_raw.iterrows():
        if status_col:
            status = str(row.get(status_col, "")).strip().lower()
            if status not in _STATUS_OK:
                continue

        date_str = str(row.get(date_col, "")).strip()
        date = parse_german_date(date_str)
        if date is None:
            try:
                date = pd.to_datetime(date_str, dayfirst=False)
            except Exception:
                continue

        amount = parse_german_amount(str(row.get(amount_col, "")))
        if amount is None or amount == 0.0:
            continue

        payee   = str(row.get(name_col, "") if name_col else "").strip()
        tx_type = str(row.get(type_col, "") if type_col else "").strip().lower()
        category = _TYPE_HINTS.get(tx_type, "Sonstiges")
        if any(kw in tx_type for kw in ("bankeinzug", "bankgutschrift", "auszahlung", "guthaben")):
            category = "Umbuchung"
        elif amount > 0 and "zahlung" not in tx_type:
            category = "Einkommen"

        r = make_row(date, amount, tx_type or payee, payee, "PayPal", account_label)
        r["category"] = category
        rows.append(r)

    return finalize_df(pd.DataFrame(rows)) if rows else empty_df()
