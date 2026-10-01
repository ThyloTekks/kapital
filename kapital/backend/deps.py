"""Shared dependencies: data loading, category metadata."""
from __future__ import annotations
import os, sys, math, threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from kapital.finance import storage
from kapital.finance.models import get_categories, _BASE_CATEGORIES

# ── Category metadata (color + icon) ─────────────────────────────────────────

_PALETTE = [
    "#4ade80", "#60a5fa", "#fbbf24", "#f472b6", "#a78bfa",
    "#34d399", "#fb923c", "#38bdf8", "#e879f9", "#6ee7b7",
    "#f87171", "#94a3b8", "#facc15", "#c084fc", "#2dd4bf",
]

_CAT_META: dict[str, dict] = {
    "Einkommen":               {"color": "#4ade80", "icon": "💰"},
    "Lebensmittel":            {"color": "#60a5fa", "icon": "🛒"},
    "Restaurant & Cafe":       {"color": "#fbbf24", "icon": "🍽️"},
    "Wohnen & Nebenkosten":    {"color": "#a78bfa", "icon": "🏠"},
    "Transport & Auto":        {"color": "#f472b6", "icon": "🚌"},
    "Gesundheit":              {"color": "#34d399", "icon": "💊"},
    "Kleidung & Shopping":     {"color": "#fb923c", "icon": "👗"},
    "Unterhaltung & Freizeit": {"color": "#38bdf8", "icon": "🎬"},
    "Reisen & Urlaub":         {"color": "#e879f9", "icon": "✈️"},
    "Versicherungen":          {"color": "#94a3b8", "icon": "🛡️"},
    "Telekommunikation":       {"color": "#6ee7b7", "icon": "📱"},
    "Investment & Sparen":     {"color": "#4ade80", "icon": "📈"},
    "Vermögensaufbau":         {"color": "#22d3ee", "icon": "🏦"},
    "Kaution":                 {"color": "#fbbf24", "icon": "🔑"},
    "Umbuchung":               {"color": "#64748b", "icon": "↔️"},
    "Gebühren & Zinsen":       {"color": "#f87171", "icon": "💳"},
    "Sonstiges":               {"color": "#64748b", "icon": "📋"},
}


def cat_meta(name: str, idx: int = 0) -> dict:
    if name in _CAT_META:
        return _CAT_META[name]
    color = _PALETTE[hash(name) % len(_PALETTE)]
    return {"color": color, "icon": "🏷️"}


def categories_list() -> list[dict]:
    cats = get_categories()
    return [
        {"id": c, "name": c, "is_custom": c not in _BASE_CATEGORIES, **cat_meta(c, i)}
        for i, c in enumerate(cats)
    ]


# ── DataFrame cache ───────────────────────────────────────────────────────────

_cache: pd.DataFrame | None = None

# FastAPI führt `def`-Endpunkte (im Gegensatz zu `async def`) in einem
# Threadpool aus — sie laufen also echt parallel. Jeder schreibende Endpunkt
# macht get_df() → copy → ändern → save() → set_df(); ohne Sperre baut der
# zweite Schreiber auf dem Stand VOR dem ersten auf und dessen Änderung ist
# spurlos weg. Bei der Review-Modal-Zuordnung sind das schnell hunderte Zeilen.
_lock = threading.RLock()


@contextmanager
def transaction():
    """Sperre für jede read-modify-write-Sequenz auf dem Buchungsbestand.

        with deps.transaction():
            df = get_df().copy()
            ...
            storage.save(df); set_df(df)

    RLock, damit verschachtelte Aufrufe (Upload ruft intern erneut) nicht
    blockieren.
    """
    with _lock:
        yield


def get_df() -> pd.DataFrame:
    global _cache
    with _lock:
        if _cache is None:
            _cache = storage.load()
        return _cache


def reload_df() -> pd.DataFrame:
    global _cache
    with _lock:
        _cache = storage.load()
        return _cache


def set_df(df: pd.DataFrame) -> None:
    global _cache
    with _lock:
        _cache = df


def parse_accounts(account: str | None) -> list[str] | None:
    """Kontofilter einlesen — eine Quelle für alle Router.

    Akzeptiert weiterhin den Einzelwert ("Giro") und zusätzlich eine
    Komma-Liste ("Giro,Trade Republic"). "" und "all" bedeuten: kein Filter.
    Rückgabe None = nicht filtern.
    """
    if not account or account == "all":
        return None
    names = [a.strip() for a in str(account).split(",") if a.strip()]
    names = [a for a in names if a != "all"]
    return names or None


def account_options(df) -> list[str]:
    """Die Auswahl des Kontofilters — Anzeigenamen, nicht rohe account_label.

    Ohne diese Auflösung listet der Filter, was beim Import in der Parquet
    landete: dieselbe IBAN mit und ohne Leerzeichen, daneben den Namen. Eine
    Umbenennung unter Einstellungen erreicht die gespeicherten Zeilen nie, also
    zeigte der Filter IBANs, während die Konten-Karte daneben die richtigen
    Namen zeigt.
    """
    from kapital.finance.networth import account_display_groups
    return sorted(account_display_groups(df).keys())


def filter_by_accounts(df, account: str | None):
    """Nach Konto filtern — die Auswahl ist ein Anzeigename.

    Der Anzeigename wird auf alle rohen account_label zurückübersetzt, die
    dasselbe Konto bezeichnen. Ohne das trifft "Giro" nur die Zeilen, die
    wörtlich "Giro" gespeichert haben, und unterschlägt stillschweigend die
    unter der IBAN importierten — beim Bestand hier 1.438 von 5.206 Buchungen.
    """
    names = parse_accounts(account)
    if not names or df is None or df.empty:
        return df
    return df[df["account_label"].isin(account_raw_labels(df, *names))]


def account_raw_labels(df, *names: str) -> list[str]:
    """Anzeigenamen -> alle rohen account_label, die sie bezeichnen.

    Für Router, die eine Maske bauen statt zu filtern. Ein unbekannter Name
    wird unverändert durchgereicht, damit ein Filter auf ein rohes Label
    (alte Lesezeichen, direkte API-Aufrufe) weiter greift.
    """
    from kapital.finance.networth import account_display_groups
    groups = account_display_groups(df)
    raw: list[str] = []
    for n in names:
        raw.extend(groups.get(n, [n]))
    return raw


# ── Zeilen-Referenzen ─────────────────────────────────────────────────────────
# Der tx_hash ist ein Fingerabdruck für Dubletten, kein Primärschlüssel: er ist
# md5(datum|betrag|kontotyp|beschreibung[:60]) auf 12 Zeichen. Vier echte
# Bahnfahrten à 8 € am selben Tag bekommen denselben Wert — im Bestand teilen
# sich 20 Zeilen 9 Hashes.
#
# Jede Oberfläche, die den Hash als Zeilen-ID benutzt, verliert dadurch still
# Daten: das Review-Modal hielt seine Auswahl als {id: kategorie} und liess von
# 20 Zuordnungen 9 übrig, und eine Kategorie-Änderung auf der Buchungsseite traf
# alle Kollisionspartner mit.
#
# Deshalb "<hash>~<n>". Die Tilde ist in einer URL unreserviert (RFC 3986) und
# funktioniert damit auch als Pfadsegment; "#" täte das nicht, es beginnt dort
# das Fragment.
ROW_REF_SEP = "~"


def row_occurrences(df) -> "pd.Series":
    """Laufende Nummer jeder Zeile innerhalb ihrer tx_hash-Gruppe."""
    return df.groupby("tx_hash").cumcount()


def make_row_ref(tx_hash: str, occurrence: int) -> str:
    return f"{tx_hash}{ROW_REF_SEP}{int(occurrence)}"


def resolve_row_ref(df, ref: str):
    """Zeilen-Referenz auflösen -> Index der Treffer, oder None.

    "<hash>~<n>" bezeichnet genau die n-te Zeile mit diesem tx_hash. Ein blosser
    "<hash>" trifft weiterhin alle Zeilen damit, damit ältere Aufrufer und offene
    Browser-Tabs nicht brechen. "#" wird als Trenner mitgelesen, weil eine frühere
    Fassung ihn ausgeliefert hat.
    """
    ref = str(ref or "")
    tx_hash, sep, occ = ref.partition(ROW_REF_SEP)
    if not sep:
        tx_hash, sep, occ = ref.partition("#")
    rows = df.index[df["tx_hash"] == tx_hash]
    if len(rows) == 0:
        return None
    if not sep or not occ:
        return rows
    try:
        n = int(occ)
    except ValueError:
        return rows
    return rows[n:n + 1] if 0 <= n < len(rows) else None


def resolve_row_refs(df, refs):
    """Mehrere Referenzen auflösen -> (Index aller Treffer, Liste der unbekannten)."""
    import pandas as _pd
    found, missing = [], []
    for r in refs:
        idx = resolve_row_ref(df, r)
        if idx is None:
            missing.append(r)
        else:
            found.extend(list(idx))
    return _pd.Index(found).unique(), missing


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _clean(v: Any) -> Any:
    """Convert NaN / Inf / Period to JSON-safe types."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → list of dicts, safe for JSON serialisation."""
    out = []
    for row in df.to_dict(orient="records"):
        cleaned = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):       # datetime / Timestamp
                cleaned[k] = v.isoformat()[:10]
            elif hasattr(v, "year"):          # pandas Period
                cleaned[k] = str(v)
            else:
                cleaned[k] = _clean(v)
        out.append(cleaned)
    return out
