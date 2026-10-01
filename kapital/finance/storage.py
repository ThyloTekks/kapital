"""
Persistent storage for transactions.

All transactions are saved to a single Parquet file.
The file lives at  kapital/data/transactions.parquet  relative to this
module's parent directory.

Public API:
  load()                         → DataFrame (empty if no file yet)
  save(df)                       → None
  merge(existing, new_df)        → (merged_df, n_added, n_duplicates)
  delete_range(df, from, to, accounts) → DataFrame
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd

from .models import COLUMNS

log = logging.getLogger(__name__)

# Wie viele Vorgängerversionen der Parquet-Datei aufgehoben werden.
# 6.279 Zeilen sind ~200 KB — die Versionen kosten praktisch nichts und sind
# die einzige Absicherung gegen einen fehlerhaften Schreibvorgang.
_KEEP_VERSIONS = 5


class StorageCorruptError(RuntimeError):
    """Die Datei existiert, ist aber nicht lesbar.

    Bewusst eine eigene Exception: 'Datei fehlt' (leerer Bestand ist korrekt)
    und 'Datei kaputt' (auf keinen Fall weiterarbeiten) sind verschiedene
    Zustände. Sie stillschweigend gleich zu behandeln hat zur Folge, dass die
    App fröhlich mit null Buchungen startet und der nächste Speichervorgang
    genau diese Leere festschreibt.
    """

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE             = Path(__file__).parent          # finance/
_DATA_DIR         = _HERE.parent.parent / "data"          # kapital/data/
STORE_PATH        = _DATA_DIR / "transactions.parquet"
DEPOT_STORE_PATH  = _DATA_DIR / "depot_snapshot.parquet"
IBAN_LABELS_PATH  = _DATA_DIR / "iban_labels.json"
_BALANCE_PATH     = _DATA_DIR / "giro_balances.json"


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Load / Save ───────────────────────────────────────────────────────────────

def load() -> pd.DataFrame:
    """Load persisted transactions. Returns empty DataFrame if none saved yet."""
    if not STORE_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    try:
        df = pd.read_parquet(STORE_PATH)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        # Back-fill columns added in later versions
        for col in COLUMNS:
            if col not in df.columns:
                if col in ("is_transfer", "is_sonderausgabe"):
                    df[col] = False
                elif col in ("units", "price_per_unit"):
                    df[col] = 0.0
                else:
                    df[col] = ""
        df["units"] = pd.to_numeric(df["units"], errors="coerce").fillna(0.0)
        df["price_per_unit"] = pd.to_numeric(df["price_per_unit"], errors="coerce").fillna(0.0)
        return df[COLUMNS].reset_index(drop=True)
    except Exception as exc:
        # NICHT still auf leer zurückfallen: der Bestand ist unersetzlich und
        # ein leeres DataFrame würde beim nächsten save() die Datei überschreiben.
        log.error("transactions.parquet ist nicht lesbar: %s: %s", type(exc).__name__, exc)
        raise StorageCorruptError(
            f"{STORE_PATH} existiert, ist aber nicht lesbar ({type(exc).__name__}: {exc}). "
            f"Es wurde NICHTS überschrieben. Vorgängerversionen liegen unter "
            f"{STORE_PATH.name}.1 … .{_KEEP_VERSIONS}."
        ) from exc


def _rotate_versions(path: Path) -> None:
    """path → path.1, path.1 → path.2, … (älteste fällt raus)."""
    oldest = path.with_suffix(path.suffix + f".{_KEEP_VERSIONS}")
    if oldest.exists():
        oldest.unlink()
    for n in range(_KEEP_VERSIONS - 1, 0, -1):
        src = path.with_suffix(path.suffix + f".{n}")
        if src.exists():
            src.rename(path.with_suffix(path.suffix + f".{n + 1}"))
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".1"))


def save(df: pd.DataFrame) -> None:
    """Persist transactions to Parquet — atomar, mit Versionsrotation.

    Erst in eine temporäre Datei schreiben, dann os.replace: ein abgebrochener
    Schreibvorgang kann die bestehende Datei damit nicht mehr zerstören.
    """
    _ensure_data_dir()
    out = df[COLUMNS].copy()
    # Bool-Spalten robust nach echtem bool casten: gemischte Werte (z. B. "" aus
    # neu geparsten Zeilen + True/False aus Bestand) lassen den Parquet-Write sonst
    # scheitern ("Could not convert '' with type str: tried to convert to boolean").
    for col in ("is_transfer", "is_sonderausgabe"):
        if col in out.columns:
            out[col] = out[col].replace("", False).fillna(False).astype(bool)

    _rotate_versions(STORE_PATH)
    tmp = STORE_PATH.with_suffix(STORE_PATH.suffix + ".tmp")
    try:
        out.to_parquet(tmp, index=False)
        os.replace(tmp, STORE_PATH)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    log.info("transactions.parquet gespeichert (%d Zeilen)", len(out))


def write_json_atomic(path: Path, data) -> None:
    """JSON atomar schreiben — gleiche Begründung wie bei save().

    Alle JSON-Schreiber der App (Regeln, Budgets, Salden, Ticker) machen ein
    read-modify-write ohne Sperre; ohne atomares Ersetzen hinterlässt ein
    Abbruch eine halbe Datei, die beim nächsten Start still verworfen wird.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


SETTINGS_PATH = _DATA_DIR / "settings.json"


def load_settings_raw() -> dict:
    """data/settings.json lesen — ohne Abhängigkeit auf das Backend.

    finance/ darf nichts aus backend/ importieren; budgets.py liest seine
    Konfiguration aus demselben Grund direkt aus data/.
    """
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        log.warning("settings.json ist nicht lesbar")
        return {}


def load_own_payee_names() -> list[str]:
    """Empfängernamen, die den Kontoinhaber selbst bezeichnen.

    Eine Gutschrift, deren Empfänger man selbst ist, ist keine Erstattung,
    sondern ein nicht erkannter Eigenübertrag. Ohne diese Liste wurden solche
    Buchungen von den Ausgaben abgezogen und haben damit Ersparnis erzeugt,
    die es nie gab. Bewusst konfigurierbar statt geraten.
    """
    names = load_settings_raw().get("own_payee_names") or []
    return [str(n).strip().lower() for n in names if str(n).strip()]


# ── IBAN label persistence ────────────────────────────────────────────────────

def load_iban_labels() -> dict[str, str]:
    """Load persisted IBAN → user label mapping."""
    if IBAN_LABELS_PATH.exists():
        try:
            return json.loads(IBAN_LABELS_PATH.read_text())
        except Exception:
            pass
    return {}


def save_iban_labels(mapping: dict[str, str]) -> None:
    """Persist IBAN → user label mapping."""
    write_json_atomic(IBAN_LABELS_PATH, mapping)


def resolve_label(iban: Optional[str], fallback: str, iban_labels: dict[str, str]) -> str:
    """Return user label for IBAN if set, else fallback."""
    if iban and iban in iban_labels:
        return iban_labels[iban]
    return fallback


# ── Depot snapshot persistence ────────────────────────────────────────────────

DEPOT_META_PATH = _DATA_DIR / "depot_snapshot_meta.json"


def save_depot_snapshot(snapshot: pd.DataFrame, as_of: str = "") -> None:
    """Persist a Depotauszug snapshot to disk — mit Stichtag.

    Ohne Datum kann niemand entscheiden, ob der Snapshot oder die Transaktionen
    aktueller sind. Genau daran lag es, dass eine verkaufte Position wieder als
    gehalten auftauchte: der Snapshot galt bedingungslos als Wahrheit.
    """
    _ensure_data_dir()
    tmp = DEPOT_STORE_PATH.with_suffix(DEPOT_STORE_PATH.suffix + ".tmp")
    try:
        snapshot.to_parquet(tmp, index=False)
        os.replace(tmp, DEPOT_STORE_PATH)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    write_json_atomic(DEPOT_META_PATH, {
        "as_of": as_of or pd.Timestamp.today().strftime("%Y-%m-%d"),
        "imported_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "n_positions": int(len(snapshot)),
    })


def load_depot_snapshot_date() -> Optional[str]:
    """Stichtag des gespeicherten Snapshots ('YYYY-MM-DD') oder None."""
    if not DEPOT_META_PATH.exists():
        return None
    try:
        return json.loads(DEPOT_META_PATH.read_text(encoding="utf-8")).get("as_of") or None
    except Exception:
        log.warning("depot_snapshot_meta.json ist nicht lesbar")
        return None


def load_depot_snapshot() -> Optional[pd.DataFrame]:
    """Load persisted Depotauszug snapshot. Returns None if none saved yet."""
    if not DEPOT_STORE_PATH.exists():
        return None
    try:
        df = pd.read_parquet(DEPOT_STORE_PATH)
        return df if not df.empty else None
    except Exception:
        return None


# ── Giro balance persistence ──────────────────────────────────────────────────

def save_giro_balance(label: str, balance: float, balance_date: str = "") -> None:
    """Persist the last-known Giro/savings-account balance extracted from CSV header."""
    _ensure_data_dir()
    data: dict = {}
    if _BALANCE_PATH.exists():
        try:
            data = json.loads(_BALANCE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    data[label] = {"balance": round(balance, 2), "date": balance_date}
    write_json_atomic(_BALANCE_PATH, data)


def load_giro_balances() -> dict[str, dict]:
    """Load stored Giro balances: {account_label: {balance, date}}."""
    if not _BALANCE_PATH.exists():
        return {}
    try:
        return json.loads(_BALANCE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── TR cash balance persistence ───────────────────────────────────────────────

_TR_CASH_PATH = _DATA_DIR / "tr_cash_balance.json"


def load_tr_cash_balance() -> float:
    """Load the persisted Trade Republic cash/Verrechnungskonto balance."""
    if not _TR_CASH_PATH.exists():
        return 0.0
    try:
        return float(json.loads(_TR_CASH_PATH.read_text(encoding="utf-8")).get("balance", 0.0))
    except Exception:
        return 0.0


def save_tr_cash_balance(val: float) -> None:
    """Persist the TR cash balance so it survives app restarts."""
    _ensure_data_dir()
    _TR_CASH_PATH.write_text(
        json.dumps({"balance": round(val, 2)}, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Deduplication helpers ─────────────────────────────────────────────────────

def _content_key(df: pd.DataFrame) -> pd.Series:
    """Fallback dedup key: (date, amount, account-type, description[:60]).

    Used when two imports of the same account used different account_labels,
    which causes tx_hash to differ even for identical transactions.
    """
    return (
        df["date"].dt.strftime("%Y-%m-%d")
        + "|" + df["amount"].map(lambda x: f"{x:.2f}")
        + "|" + df["account"].fillna("")
        + "|" + df["description"].fillna("").str[:60]
    )


def deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove duplicate rows from df by content key, keeping the first occurrence.

    Returns (deduped_df, n_removed).
    """
    key = _content_key(df)
    dupes = key.duplicated(keep="first")
    n_removed = int(dupes.sum())
    return df[~dupes].reset_index(drop=True), n_removed


# ── Merge with deduplication ──────────────────────────────────────────────────

def merge(existing: pd.DataFrame, new_df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """
    Merge new_df into existing, deduplicating by tx_hash first, then by
    content key (date + amount + account-type + description) as fallback.

    The content-key fallback catches cases where the same transaction was
    imported under two different account_labels (e.g. 'Mein Giro' vs
    'GiroKonto_Historie'), which produces different tx_hashes.

    Returns:
      merged_df   – combined, sorted DataFrame
      n_added     – number of genuinely new rows added
      n_dupes     – number of rows skipped as duplicates
    """
    if new_df.empty:
        return existing, 0, 0

    if existing.empty:
        merged = new_df.copy()
        return merged.sort_values("date").reset_index(drop=True), len(merged), 0

    # Pass 1: hash-based dedup (fast)
    existing_hashes = set(existing["tx_hash"].dropna())
    new_mask = ~new_df["tx_hash"].isin(existing_hashes)
    truly_new = new_df[new_mask]
    n_dupes = len(new_df) - len(truly_new)

    # Pass 2: content-key fallback (catches label-rename duplicates)
    if not truly_new.empty:
        existing_keys = set(_content_key(existing))
        new_keys = _content_key(truly_new)
        content_mask = ~new_keys.isin(existing_keys)
        n_dupes += int((~content_mask).sum())
        truly_new = truly_new[content_mask]

    n_added = len(truly_new)

    if truly_new.empty:
        return existing, 0, n_dupes

    merged = (
        pd.concat([existing, truly_new], ignore_index=True)
        .sort_values("date")
        .reset_index(drop=True)
    )
    return merged, n_added, n_dupes


# ── Delete by date range ──────────────────────────────────────────────────────

def delete_range(
    df: pd.DataFrame,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    accounts: Optional[list[str]] = None,
) -> tuple[pd.DataFrame, int]:
    """
    Remove all rows whose date falls within [date_from, date_to].
    If accounts is given, only delete rows for those account_labels.

    Returns (new_df, n_deleted).
    """
    mask_date = (df["date"].dt.date >= date_from) & (df["date"].dt.date <= date_to)

    if accounts:
        mask = mask_date & df["account_label"].isin(accounts)
    else:
        mask = mask_date

    n_deleted = mask.sum()
    new_df = df[~mask].reset_index(drop=True)
    return new_df, int(n_deleted)
