"""
Offene Zuordnungen: Buchungen, die der User noch kategorisieren muss.

Als "offen" gilt eine Buchung, wenn sie kein interner Übertrag ist und
entweder in 'Sonstiges' liegt oder keinen erkannten Empfänger hat.
"""

from __future__ import annotations

import re

import pandas as pd

OPEN_CATEGORY = "Sonstiges"

# Zahlungsdienstleister: bei ihnen ist der Empfänger für jede Buchung derselbe,
# der echte Händler steht im Buchungstext. Wer hier auf den Empfänger gruppiert,
# wirft alle Zahlungen über diesen Dienst in einen Topf — im Bestand sind das
# 739 PayPal-Buchungen mit 538 verschiedenen Buchungstexten.
_AGGREGATOR_PAYEES = (
    "paypal", "klarna", "amazon payments", "stripe", "sumup",
    "adyen", "mollie", "shopify", "ratepay",
)

# "PP.4657.PP . SPOTIFY, Ihr Einkauf bei SPOTIFY" → SPOTIFY
_PP_MERCHANT_RE = re.compile(r"PP\.\d+\.PP\s*\.\s*([^,]+)", re.IGNORECASE)
# Generischer Fallback für andere Dienstleister.
_EINKAUF_RE = re.compile(r"Ihr Einkauf bei\s+(.+?)\s*$", re.IGNORECASE)


def is_aggregator(payee: str) -> bool:
    """Ist dieser Empfänger ein Zahlungsdienstleister und kein echter Händler?"""
    p = (payee or "").lower()
    return any(a in p for a in _AGGREGATOR_PAYEES)


def extract_merchant(payee: str, description: str) -> str:
    """Den echten Händler bestimmen.

    Für normale Buchungen ist das der Empfänger. Für Zahlungsdienstleister wird
    er aus dem Buchungstext gezogen; gelingt das nicht (etwa beim
    AWV-Meldepflicht-Boilerplate), bleibt das Ergebnis leer — dann darf auch
    NICHT gruppiert werden, statt auf den Dienstleister zurückzufallen.
    """
    payee = (payee or "").strip()
    desc = (description or "").strip()
    if not is_aggregator(payee):
        return payee

    for rx in (_PP_MERCHANT_RE, _EINKAUF_RE):
        m = rx.search(desc)
        if m:
            merchant = m.group(1).strip(" .,-")
            if merchant and merchant.lower() not in ("privat", "unbekannt"):
                return merchant
    return ""


def group_key(payee: str, description: str) -> str:
    """Schlüssel für „gleiche Buchung, gleiche Kategorie".

    Leerer Schlüssel heisst ausdrücklich: diese Buchung mit keiner anderen
    zusammenfassen.
    """
    merchant = extract_merchant(payee, description)
    return merchant.strip().lower()


def open_mask(df: pd.DataFrame) -> pd.Series:
    """Boolean-Maske aller Buchungen, die noch zugeordnet werden müssen."""
    if df.empty:
        return pd.Series([], dtype=bool)
    not_transfer = ~df["is_transfer"].astype(bool) & (df["category"] != "Umbuchung")
    is_sonstiges = df["category"].fillna("") == OPEN_CATEGORY
    no_payee = df["payee"].fillna("").str.strip() == ""
    return not_transfer & (is_sonstiges | no_payee)


def open_items(df: pd.DataFrame, months: list[str] | None = None) -> pd.DataFrame:
    """Offene Buchungen, optional auf bestimmte Monate ('YYYY-MM') begrenzt."""
    if df.empty:
        return df
    sub = df[open_mask(df)]
    if months:
        ym = sub["date"].dt.to_period("M").astype(str)
        sub = sub[ym.isin(months)]
    return sub.sort_values("date", ascending=False)


def open_counts_by_month(df: pd.DataFrame) -> dict[str, int]:
    """Anzahl offener Buchungen je Monat."""
    if df.empty:
        return {}
    sub = df[open_mask(df)]
    if sub.empty:
        return {}
    return sub.groupby(sub["date"].dt.to_period("M").astype(str)).size().astype(int).to_dict()


def month_is_clean(df: pd.DataFrame, ym: str) -> bool:
    return open_counts_by_month(df).get(ym, 0) == 0


def suggest_category(df: pd.DataFrame, payee: str, description: str) -> tuple[str, int]:
    """Vorschlag aus der eigenen Historie: häufigste Kategorie desselben Empfängers.

    Returns (kategorie, n_treffer); ("", 0) wenn nichts Passendes gefunden wurde.
    """
    key = group_key(payee, description)
    if not key or df.empty:
        return "", 0

    categorised = df[
        (df["category"] != OPEN_CATEGORY)
        & (df["category"] != "Umbuchung")
        & (~df["is_transfer"].fillna(False).astype(bool))
    ]
    if categorised.empty:
        return "", 0

    if is_aggregator(payee):
        # Beim Zahlungsdienstleister zählt der Händler aus dem Buchungstext.
        # Der `description`-Parameter war bisher da und wurde nie benutzt —
        # deshalb schlug die Funktion für alle 739 PayPal-Zeilen dieselbe
        # Kategorie mit dreistelliger Trefferzahl vor.
        cand = categorised[categorised["payee"].fillna("").str.lower().str.contains(
            "|".join(_AGGREGATOR_PAYEES), na=False, regex=True)]
        if cand.empty:
            return "", 0
        keys = cand.apply(
            lambda r: group_key(str(r.get("payee", "")), str(r.get("description", ""))),
            axis=1,
        )
        hits = cand[keys == key]
    else:
        hits = categorised[categorised["payee"].fillna("").str.strip().str.lower() == key]

    if hits.empty:
        return "", 0
    counts = hits["category"].value_counts()
    return str(counts.index[0]), int(counts.iloc[0])
