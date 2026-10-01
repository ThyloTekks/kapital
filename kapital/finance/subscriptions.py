"""
Subscription / recurring payment detection.

Two independent detection passes:

  Pass 1 – Payee-based
    Groups by normalised payee (case-folded, whitespace-collapsed).
    Catches subscriptions where the bank preserves the merchant name.

  Pass 2 – Description-based
    Groups by the first 50 characters of the description field.
    Catches PayPal charges and any transaction where the payee is a
    generic payment processor but the description repeats reliably.

Both passes apply the same interval-regularity and amount-consistency
filters.  Results are merged and deduplicated so the same subscription
never appears twice.
"""
from __future__ import annotations

import re
from datetime import timedelta

import numpy as np
import pandas as pd


# ── Tuning knobs ──────────────────────────────────────────────────────────────

AMOUNT_CV          = 0.20   # 20 % — tolerates moderate price increases
INTERVAL_STD_SHORT = 12     # days; for avg_interval ≤ 37 days (monthly)
INTERVAL_STD_LONG  = 22     # days; for longer intervals
DESC_PREFIX_LEN    = 50     # chars used as description group key
MIN_DESC_LEN       = 8      # skip descriptions shorter than this

# Minimum occurrences per interval class.
# Semi-annual/annual allow 2 because users may only have 1-2 years of data;
# but those get extra-strict amount consistency (cv ≤ 2 %) to avoid
# coincidental same-merchant payments being promoted.
_MIN_OCC: dict[str, int] = {
    "Wöchentlich":       3,
    "Zweiwöchentlich":   3,
    "Monatlich":         3,
    "Alle 2 Monate":     3,
    "Vierteljährlich":   3,
    "Halbjährlich":      2,
    "Jährlich":          2,
}
_RECENT_WINDOW = 5
_TIGHT_CV_FREQS = {"Halbjährlich", "Jährlich"}   # stricter amount check for low-occ freqs
_TIGHT_CV       = 0.02


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Case-fold + collapse whitespace."""
    return re.sub(r'\s+', ' ', str(s).lower().strip())


def _classify_interval(avg: float) -> tuple[str, int] | None:
    """Return (label, annual_factor) or None when interval is non-standard."""
    if   6  <= avg <=  9:   return "Wöchentlich",       52
    elif 12  <= avg <= 16:  return "Zweiwöchentlich",   26
    elif 25  <= avg <= 37:  return "Monatlich",         12
    elif 55  <= avg <= 70:  return "Alle 2 Monate",      6
    elif 80  <= avg <= 105: return "Vierteljährlich",    4
    elif 160 <= avg <= 210: return "Halbjährlich",       2
    elif 320 <= avg <= 410: return "Jährlich",           1
    return None


def _st_median_safe(vals):
    """Median, robust gegen leere Listen."""
    import statistics as _st
    return _st.median(vals) if vals else 0.0


def _evaluate_group(
    grp: pd.DataFrame,
    display_key: str,
    today: pd.Timestamp,
) -> dict | None:
    """
    Return a result row dict if the group looks like a subscription,
    or None if it fails any filter.
    """
    n = len(grp)

    avg_amt = grp["abs_amount"].mean()
    if avg_amt < 1.0:
        return None

    # Betragskonstanz auf dem AKTUELLEN Niveau prüfen, nicht über die ganze
    # Historie.
    #
    # Der Grund: die Prüfung über alles verwirft genau die Abos, deren Preis
    # sich geändert hat — Netflix (10,99 → 14,65) kommt auf cv 0,35 und fiel
    # deshalb komplett aus der Erkennung. Ausgerechnet die interessanten Fälle
    # waren damit unsichtbar, und zwar WEIL sie teurer geworden sind.
    #
    # Eine Preiserhöhung ist ein Sprung von einem Plateau auf das nächste; eine
    # schwankende Rechnung ist Rauschen. Das Plateau der letzten Zahlungen
    # trennt beides: dort ist ein erhöhtes Abo wieder konstant, eine
    # Stromabrechnung nicht.
    # Robust gegen einen einzelnen Ausreisser: Median statt Mittelwert, und es
    # genügt, wenn die MEISTEN der letzten Zahlungen auf dem Niveau liegen. Ein
    # einzelner Gutschrift- oder Teilmonat darf ein Abo nicht disqualifizieren
    # — bei Netflix kippte genau ein Monat (5,98 € statt 18,98 €) die ganze
    # Erkennung, obwohl der Preis über Jahre eine klare Leiter bildet.
    recent = grp.sort_values("date")["abs_amount"].tail(_RECENT_WINDOW)
    recent_med = float(recent.median()) if len(recent) else 0.0
    if recent_med > 0 and len(recent) >= 3:
        nah = sum(1 for v in recent if abs(float(v) - recent_med) / recent_med <= 0.15)
        cv_recent = 0.0 if nah >= len(recent) - 1 else 1.0
    else:
        recent_mean = float(recent.mean()) if len(recent) else 0.0
        cv_recent = (float(recent.std()) / recent_mean) if recent_mean > 0 and len(recent) > 1 else 0.0
    cv = (grp["abs_amount"].std() / avg_amt) if avg_amt > 0 else 1.0
    if cv_recent > AMOUNT_CV:
        return None
    # Obergrenze NUR auf dem aktuellen Fenster, nicht über die ganze Historie.
    # Über Jahre erzeugt jede Preisleiter plus ein anteilig berechneter Monat
    # ein extremes Verhältnis — bei Netflix 24:1 zwischen 0,79 € und 18,98 €,
    # obwohl es durchgehend dasselbe Abo ist. Falsch gruppierte Zeilen fallen
    # auch im aktuellen Fenster auf; eine acht Jahre alte Teilbuchung nicht.
    if len(recent) and (float(recent.max()) / max(float(recent.min()), 0.01)) > 8:
        return None

    dates = sorted(grp["date"].dt.normalize())
    if len(dates) < 2:
        return None

    intervals   = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    # Median statt Mittelwert: ein ausgefallener Monat erzeugt eine Lücke von
    # ~60 Tagen und zieht den Mittelwert zwischen zwei Frequenzklassen. Netflix
    # kam so auf 37,2 Tage im Schnitt — monatlich, aber nicht mehr als solches
    # erkennbar, nur weil zwei Abbuchungen fehlten. Der Median liegt bei 30.
    avg_int     = float(np.median(intervals))
    # Streuung gegen den Median messen, ebenfalls robust gegen einzelne Lücken.
    dev         = [abs(i - avg_int) for i in intervals]
    std_int     = float(np.median(dev)) * 1.4826 if len(intervals) > 1 else 0.0

    # Interval-std gate
    limit = INTERVAL_STD_SHORT if avg_int <= 37 else INTERVAL_STD_LONG
    if std_int > limit:
        return None

    classified = _classify_interval(avg_int)
    if classified is None:
        return None
    freq, annual_factor = classified

    # Minimum-occurrence check (per-frequency)
    if n < _MIN_OCC.get(freq, 3):
        return None

    # Extra-strict amount consistency for low-occurrence long intervals
    if freq in _TIGHT_CV_FREQS and n < 3 and cv > _TIGHT_CV:
        return None

    last_date     = max(dates)
    next_expected = last_date + timedelta(days=int(avg_int))

    # Recency: skip if last payment is more than 2 intervals overdue
    if today > next_expected + timedelta(days=int(avg_int)):
        return None

    # ── Preisentwicklung ──────────────────────────────────────────────────────
    # Eine Preiserhöhung ist in einer Monatsansicht strukturell unsichtbar:
    # jeder einzelne Monat sieht normal aus, und die Verdreifachung merkt man
    # nach vier Jahren oder gar nicht. Der Durchschnittsbetrag verdeckt sie
    # zusätzlich. Deshalb hier erster gegen letzter Betrag.
    ordered = grp.sort_values("date")
    amounts = ordered["abs_amount"].tolist()
    dates = ordered["date"].tolist()
    n_edge = min(3, max(1, len(amounts) // 3))
    first_amt = float(_st_median_safe(amounts[:max(n_edge, 3)]))
    import statistics as _st
    last_amt = float(_st.median(amounts[-_RECENT_WINDOW:]))
    change_pct = ((last_amt / first_amt) - 1) * 100 if first_amt > 0 else 0.0

    # Wann hat sich der Betrag zuletzt spürbar geändert? Rückwärts suchen,
    # bis ein Sprung von mehr als 3 % gegen den aktuellen Betrag auftaucht.
    changed_at = None
    prev_amount = None
    for i in range(len(amounts) - 1, 0, -1):
        if abs(amounts[i] - amounts[i - 1]) / max(amounts[i - 1], 0.01) > 0.03:
            changed_at = dates[i]
            prev_amount = round(float(amounts[i - 1]), 2)
            break

    return {
        "payee":         display_key,
        "avg_amount":    round(avg_amt, 2),
        "first_amount":  round(first_amt, 2),
        "last_amount":   round(last_amt, 2),
        "change_pct":    round(change_pct, 1),
        "changed_at":    changed_at,
        "amount_before": prev_amount,
        "first_seen":    dates[0] if dates else None,
        "frequency":     freq,
        "interval_days": int(round(avg_int)),
        # Jahres- und Monatskosten aus dem AKTUELLEN Preis, nicht aus dem
        # Schnitt über die ganze Historie. Netflix kam über den Schnitt auf
        # 13,16 € im Monat, obwohl es aktuell 18,98 € kostet — mit so einer
        # Zahl kann man nicht planen, und sie verdeckt genau die Erhöhung, die
        # nebenan ausgewiesen wird.
        "annual_cost":   round(last_amt * annual_factor, 2),
        "monthly_cost":  round(last_amt * annual_factor / 12, 2),
        "avg_cost_hist": round(avg_amt * annual_factor / 12, 2),
        "occurrences":   n,
        "last_date":     last_date,
        "next_expected": next_expected,
        "category":      grp["category"].mode().iloc[0],
    }


# ── Public API ────────────────────────────────────────────────────────────────

def detect_subscriptions(
    df: pd.DataFrame,
    min_occurrences: int = 3,
    amount_cv_threshold: float = AMOUNT_CV,
) -> pd.DataFrame:
    """
    Detect recurring payments via two independent passes (payee + description).
    Returns a DataFrame sorted by annual_cost descending.
    """
    has_payee = df["payee"].fillna("").str.strip() != ""
    has_desc  = df["description"].fillna("").str.strip() != ""
    expenses = df[
        ~df["is_transfer"] &
        (df["category"] != "Umbuchung") &
        (df["amount"] < 0) &
        (has_payee | has_desc)
    ].copy()

    if expenses.empty:
        return pd.DataFrame()

    expenses["abs_amount"] = expenses["amount"].abs()
    today = pd.Timestamp.today().normalize()

    seen_keys: set[str] = set()   # deduplicate across passes
    results: list[dict] = []

    # ── Pass 1: group by normalised payee ─────────────────────────────────────
    # Bei Zahlungsdienstleistern den echten Händler aus dem Buchungstext
    # verwenden. Sonst landen ALLE Zahlungen über PayPal in einer Gruppe —
    # im Bestand 739 Zeilen mit wilder Streuung, in der kein Abo mehr
    # erkennbar ist. Netflix läuft genau so und war deshalb nie ein Abo.
    # Dieselbe Extraktion wie in der Zuordnung; eine Logik, nicht zwei.
    from .review import extract_merchant, is_aggregator

    def _group_key(row) -> str:
        payee = str(row.get("payee") or "")
        if is_aggregator(payee):
            merchant = extract_merchant(payee, str(row.get("description") or ""))
            # Ohne erkennbaren Händler NICHT gruppieren, sonst entsteht der
            # PayPal-Sammeltopf über einen Umweg neu.
            return _norm(merchant) if merchant else ""
        return _norm(payee)

    expenses["_payee_norm"] = expenses.apply(_group_key, axis=1)
    # Anzeigename: bei Dienstleistern der Händler, sonst der Empfänger.
    expenses["_display"] = expenses.apply(
        lambda r: extract_merchant(str(r.get("payee") or ""), str(r.get("description") or ""))
        if is_aggregator(str(r.get("payee") or "")) else str(r.get("payee") or ""),
        axis=1,
    )
    for norm_payee, grp in expenses[expenses["_payee_norm"] != ""].groupby("_payee_norm"):
        if len(grp) < 2:
            continue
        # Use the most common raw payee as the display label
        display = grp["_display"].mode().iloc[0] if "_display" in grp.columns else grp["payee"].mode().iloc[0]
        row = _evaluate_group(grp, display, today)
        if row:
            seen_keys.add(norm_payee)
            results.append(row)

    # ── Pass 2: group by description prefix ───────────────────────────────────
    expenses["_desc_key"] = (
        expenses["description"]
        .fillna("")
        .str.strip()
        .str[:DESC_PREFIX_LEN]
        .map(_norm)
    )
    for desc_key, grp in expenses[
        expenses["_desc_key"].str.len() >= MIN_DESC_LEN
    ].groupby("_desc_key"):
        if len(grp) < 2:
            continue

        # Skip if every row in this group already matched a payee group
        norm_payees_in_grp = set(grp["_payee_norm"].unique())
        if norm_payees_in_grp and norm_payees_in_grp.issubset(seen_keys):
            continue

        display = grp["description"].mode().iloc[0][:DESC_PREFIX_LEN].strip()
        row = _evaluate_group(grp, display, today)
        if row:
            results.append(row)

    if not results:
        return pd.DataFrame()

    out = (
        pd.DataFrame(results)
        .drop_duplicates(subset=["payee", "avg_amount", "frequency"])
        .sort_values("annual_cost", ascending=False)
        .reset_index(drop=True)
    )
    return out


# ── Geteilte Abos ─────────────────────────────────────────────────────────────

def find_offsets(df, merchant: str, since_months: int = 18) -> dict:
    """Wiederkehrende EINGÄNGE, die zu einem Abo gehören.

    Ein Abo kann geteilt sein: bei Netflix steckt ein Zusatzmitglied in
    derselben Abbuchung, und dafür kommt regelmässig Geld zurück. Brutto sind
    das 18,98 €, dein Anteil ist es nicht.

    Erkennung über den Buchungstext: wer dir für Netflix Geld überweist,
    schreibt üblicherweise "Netflix" dazu. Bewusst konservativ — nur
    regelmässige Eingänge mit passendem Text zählen, damit keine einmalige
    Rückzahlung als Dauerrabatt erscheint.
    """
    if df is None or df.empty or not merchant:
        return {"monthly": 0.0, "quellen": []}

    key = merchant.split(".")[0].strip().lower()
    if len(key) < 4:
        return {"monthly": 0.0, "quellen": []}

    cutoff = pd.Timestamp.today() - pd.Timedelta(days=since_months * 31)
    inc = df[
        (df["amount"] > 0)
        & (df["date"] >= cutoff)
        & ~df["is_transfer"].fillna(False).astype(bool)
        & (
            df["description"].fillna("").str.lower().str.contains(key, regex=False)
            | df["payee"].fillna("").str.lower().str.contains(key, regex=False)
        )
    ]
    if inc.empty:
        return {"monthly": 0.0, "quellen": []}

    quellen = []
    gesamt = 0.0
    for payee, g in inc.groupby(inc["payee"].fillna("").str.strip()):
        if len(g) < 3:
            continue          # eine einmalige Rückzahlung ist kein geteiltes Abo
        spanne = (g["date"].max() - g["date"].min()).days / 30.4
        monatlich = float(g["amount"].sum()) / max(spanne, 1.0)
        gesamt += monatlich
        quellen.append({
            "von": str(payee) or "unbekannt",
            "monatlich": round(monatlich, 2),
            "n": int(len(g)),
            "letzte": g["date"].max().strftime("%Y-%m-%d"),
        })
    quellen.sort(key=lambda q: -q["monatlich"])
    return {"monthly": round(gesamt, 2), "quellen": quellen}
