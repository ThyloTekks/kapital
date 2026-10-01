"""
Inter-account transfer detector.

Three types of pairs are detected:

  1. Cross-account transfers  — different account_label, opposite signs,
     matching amount, within WINDOW_DAYS.
     Example: Giro → Trade Republic deposit, Kleingeld Plus between ING accounts.

  2. Same-account refunds — same account_label, same payee (non-empty),
     opposite signs, matching amount, within REFUND_WINDOW_DAYS.
     Example: Patrick Wiedmann (sent and received back).

  3. Manual marks — transactions already flagged is_transfer=True are
     left untouched.

Detected pairs get:
  - is_transfer  = True
  - transfer_id  = shared short UUID
  - category     = "Umbuchung"

Performance: O(n * avg_bucket_size) via groupby on rounded amount instead of O(n²).
"""

from __future__ import annotations

import uuid
import pandas as pd
import numpy as np


WINDOW_DAYS        = 7     # cross-account: max days between legs
# Erstattungen auf demselben Konto: 90 Tage bei blosser Empfängergleichheit
# waren viel zu weit. Im Bestand hat das 33 Paare erzeugt, die nichts
# miteinander zu tun hatten (u. a. −3.000 € und +3.000 € 59 Tage auseinander,
# beide an den eigenen Namen) und damit 25.837 € aus jeder Auswertung entfernt —
# unsichtbar, weil eine entfernte Buchung keine Lücke im Diagramm hinterlässt.
REFUND_WINDOW_DAYS = 14
AMOUNT_TOLERANCE   = 0.02  # relative tolerance (2 %)
# Bei Erstattungen zusätzlich verlangen, dass sich die Buchungstexte ähneln.
# Gleicher Empfänger allein genügt nicht: bei Eigenüberträgen ist der Empfänger
# immer man selbst.
REFUND_DESC_MIN_SIMILARITY = 0.45


def _descriptions_similar(a, b) -> bool:
    """Grobe Ähnlichkeit zweier Buchungstexte (Token-Überlappung)."""
    ta = {w for w in str(a or "").lower().split() if len(w) > 3}
    tb = {w for w in str(b or "").lower().split() if len(w) > 3}
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= REFUND_DESC_MIN_SIMILARITY


def _amounts_match(a: float, b: float) -> bool:
    if a == 0:
        return False
    return abs(abs(a) - abs(b)) / abs(a) <= AMOUNT_TOLERANCE


def _mark_pair(df: pd.DataFrame, idx_a: int, idx_b: int, matched: set) -> None:
    pair_id = str(uuid.uuid4())[:8]
    for idx in (idx_a, idx_b):
        df.at[idx, "is_transfer"] = True
        df.at[idx, "transfer_id"] = pair_id
        df.at[idx, "category"]    = "Umbuchung"
    matched.add(idx_a)
    matched.add(idx_b)


def _match_within_bucket(
    df: pd.DataFrame,
    bucket_indices: list,
    matched: set,
    *,
    cross_account: bool,
    window_days: int,
) -> None:
    """Greedy O(k²) matching within a small amount bucket (k is usually 1–3)."""
    for i, idx_a in enumerate(bucket_indices):
        if idx_a in matched:
            continue
        row_a = df.loc[idx_a]
        payee_a = str(row_a.get("payee", "")).strip().lower()

        for idx_b in bucket_indices[i + 1:]:
            if idx_b in matched:
                continue
            row_b = df.loc[idx_b]

            if cross_account:
                if row_a["account_label"] == row_b["account_label"]:
                    continue
            else:
                # Same-account refund: must share account AND payee
                if row_a["account_label"] != row_b["account_label"]:
                    continue
                if not payee_a:
                    continue
                if payee_a != str(row_b.get("payee", "")).strip().lower():
                    continue
                # Buchungstexte müssen zusammenpassen, sonst ist es keine
                # Erstattung, sondern zufällig derselbe Betrag.
                if not _descriptions_similar(row_a.get("description"), row_b.get("description")):
                    continue

            if np.sign(row_a["amount"]) == np.sign(row_b["amount"]):
                continue

            if not _amounts_match(row_a["amount"], row_b["amount"]):
                continue

            date_diff = abs((row_a["date"] - row_b["date"]).days)
            if date_diff > window_days:
                continue

            _mark_pair(df, idx_a, idx_b, matched)
            break


def detect_transfers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect transfer pairs and annotate them.
    Returns a new DataFrame with updated is_transfer, transfer_id, category.
    """
    df = df.copy()
    df["is_transfer"] = df["is_transfer"].astype(bool)
    df["transfer_id"] = df["transfer_id"].fillna("").astype(str).replace("nan", "")

    unmatched = df[~df["is_transfer"]].copy()
    if unmatched.empty:
        return df

    matched: set[int] = set()

    # Round to cent for bucketing — bank transfers are always exact to the cent.
    # The 2 % tolerance check happens inside the bucket, covering small fee deductions.
    unmatched["_bucket"] = unmatched["amount"].abs().round(2)

    # ── Pass 1: cross-account transfers ──────────────────────────────────────────
    for _, bucket in unmatched.groupby("_bucket"):
        if len(bucket) < 2:
            continue
        _match_within_bucket(
            df, list(bucket.index), matched,
            cross_account=True, window_days=WINDOW_DAYS,
        )

    # ── Pass 2: same-account refunds ─────────────────────────────────────────────
    unmatched2 = df[~df["is_transfer"]].copy()
    if unmatched2.empty:
        return df
    unmatched2["_bucket"] = unmatched2["amount"].abs().round(2)

    for _, bucket in unmatched2.groupby("_bucket"):
        if len(bucket) < 2:
            continue
        _match_within_bucket(
            df, list(bucket.index), matched,
            cross_account=False, window_days=REFUND_WINDOW_DAYS,
        )

    return df


def get_transfer_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a summary DataFrame of transfer pairs:
    One row per pair: transfer_id, date, von_konto, zu_konto, betrag, beschreibung.
    """
    _valid_tid = df["transfer_id"].fillna("").astype(str).replace("nan", "").str.strip()
    transfers = df[df["is_transfer"] & (_valid_tid != "")].copy()
    if transfers.empty:
        return pd.DataFrame()

    pairs = []

    for tid, group in transfers.groupby("transfer_id"):
        if len(group) != 2:
            continue
        a, b = group.iloc[0], group.iloc[1]
        if a["amount"] < 0:
            src, dst = a, b
        else:
            src, dst = b, a
        pairs.append({
            "transfer_id":  tid,
            "date":         src["date"],
            "von_konto":    src["account_label"],
            "zu_konto":     dst["account_label"],
            "betrag":       abs(src["amount"]),
            "beschreibung": src["description"] or src["payee"],
        })

    return pd.DataFrame(pairs) if pairs else pd.DataFrame()
