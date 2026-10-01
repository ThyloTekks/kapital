"""
Persistent user-defined categorization rules.

Rules are stored in  kapital/data/custom_rules.json  as a list of:
  {
    "pattern":  "netflix",          # case-insensitive substring
    "category": "Unterhaltung & Freizeit",
    "field":    "both"              # "payee" | "description" | "both"
  }

Custom rules are checked BEFORE the built-in keyword rules, so they always win.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd

_HERE      = Path(__file__).parent
_DATA_DIR  = _HERE.parent.parent / "data"
RULES_PATH = _DATA_DIR / "custom_rules.json"


# ── Load / Save ───────────────────────────────────────────────────────────────

def load_rules() -> list[dict]:
    """Return list of custom rule dicts, empty list if none saved."""
    if not RULES_PATH.exists():
        return []
    try:
        with open(RULES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_rules(rules: list[dict]) -> None:
    from .storage import write_json_atomic
    write_json_atomic(RULES_PATH, rules)


def add_rule(pattern: str, category: str, field: str = "both") -> list[dict]:
    """Add or update a rule (same pattern+field = overwrite). Returns updated rules."""
    rules = load_rules()
    # Update existing rule with same pattern+field
    for r in rules:
        if r["pattern"].lower() == pattern.lower() and r["field"] == field:
            r["category"] = category
            save_rules(rules)
            return rules
    rules.insert(0, {"pattern": pattern, "category": category, "field": field})
    save_rules(rules)
    return rules


def delete_rule(pattern: str, field: str = "both") -> list[dict]:
    rules = load_rules()
    rules = [r for r in rules if not (r["pattern"].lower() == pattern.lower() and r["field"] == field)]
    save_rules(rules)
    return rules


# ── Apply rules to DataFrame ──────────────────────────────────────────────────

def rule_mask(df: pd.DataFrame, rule: dict) -> pd.Series:
    """Welche Zeilen trifft diese Regel? Eine Quelle für Anwenden und Vorschau."""
    pattern = str(rule.get("pattern", "")).lower()
    field = rule.get("field", "both")
    if not pattern or df.empty:
        return pd.Series(False, index=df.index)

    payee = df["payee"].fillna("").str.lower()
    desc = df["description"].fillna("").str.lower()
    if field == "payee":
        mask = payee.str.contains(pattern, na=False, regex=False)
    elif field == "description":
        mask = desc.str.contains(pattern, na=False, regex=False)
    else:  # both
        mask = (payee.str.contains(pattern, na=False, regex=False)
                | desc.str.contains(pattern, na=False, regex=False))

    # Umbuchungen nie umkategorisieren. Ohne diesen Guard überschreibt jede
    # Regel auch erkannte Überträge — im Bestand waren dadurch 336 Zeilen als
    # is_transfer=True mit fremder Kategorie unterwegs, was die Umbuchungs-
    # Ausschlüsse in allen Auswertungen verschiebt.
    if "is_transfer" in df.columns:
        mask &= ~df["is_transfer"].fillna(False).astype(bool)
    return mask


def rule_impact(df: pd.DataFrame, rule: dict) -> dict:
    """Vorschau: was würde diese Regel verändern?

    Wird vor dem Anlegen einer Regel angezeigt. Eine Regel auf den Empfänger
    'PayPal' trifft 739 Zeilen, von denen 270 bereits richtig zugeordnet sind —
    ohne Vorschau überschreibt ein Klick sie alle, ohne Rückgängig.
    """
    mask = rule_mask(df, rule)
    hit = df[mask]
    already = hit[(hit["category"].fillna("") != "")
                  & (hit["category"] != "Sonstiges")
                  & (hit["category"] != rule.get("category"))]
    return {
        "matches": int(mask.sum()),
        "would_overwrite": int(len(already)),
        "overwritten_categories": already["category"].value_counts().head(6).to_dict(),
    }


def apply_custom_rules(
    df: pd.DataFrame,
    rules: Optional[list[dict]] = None,
    only_uncategorized: bool = False,
) -> pd.DataFrame:
    """
    Apply custom rules to every row. Overwrites the category column.
    Rows already categorised by a previous custom-rule pass are re-evaluated
    (allows rule edits to propagate).

    only_uncategorized=True beschränkt die Anwendung auf Zeilen in 'Sonstiges'
    bzw. ohne Kategorie — damit eine neue Regel bestehende, bereits korrekte
    Zuordnungen nicht überschreibt.
    """
    if rules is None:
        rules = load_rules()
    if not rules or df.empty:
        return df

    df = df.copy()
    if only_uncategorized:
        open_rows = (df["category"].fillna("") == "") | (df["category"] == "Sonstiges")
    for rule in rules:
        mask = rule_mask(df, rule)
        if only_uncategorized:
            mask &= open_rows
        df.loc[mask, "category"] = rule["category"]

    return df


# ── Helpers for the "Sonstiges aufräumen" UI ─────────────────────────────────

def uncategorized_payees(df: pd.DataFrame, min_occurrences: int = 1) -> pd.DataFrame:
    """
    Return a DataFrame of unique payees still in 'Sonstiges', sorted by
    total absolute amount (highest first).  Useful for bulk-assign UI.
    """
    sonstiges = df[df["category"] == "Sonstiges"].copy()
    sonstiges = sonstiges[sonstiges["payee"].str.strip() != ""]

    agg = (
        sonstiges.groupby("payee")
        .agg(
            anzahl   = ("amount", "count"),
            summe    = ("amount", lambda x: x.abs().sum()),
            beispiel = ("description", "first"),
        )
        .reset_index()
        .sort_values("summe", ascending=False)
    )
    return agg[agg["anzahl"] >= min_occurrences].reset_index(drop=True)
