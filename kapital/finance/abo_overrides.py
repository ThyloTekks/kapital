"""
Persistent user overrides for the Abo (subscriptions) tab.

Stored in  kapital/data/abo_overrides.json:
  {
    "hidden": [ {"key": "<norm>", "label": "<display>"} ],
    "forced": [ {"key": "<norm>", "label": "<display>"} ],
    "manual": [ {"id": "<uuid>", "payee": ..., "avg_amount": ...,
                 "interval": ..., "category": ...} ]
  }

- hidden: auto-detected subscriptions the user marked as "not a subscription".
  Matched against the normalised payee/description display key, so the entry
  stays hidden even when the average amount drifts as new data is imported.
- forced: payees the user flagged as a subscription from the Buchungen tab.
  The abo is (re)computed from all matching transactions, so future bookings
  with the same payee are automatically included.
- manual: subscriptions the user added by hand (not auto-detected).
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

_HERE          = Path(__file__).parent
_DATA_DIR      = _HERE.parent.parent / "data"
OVERRIDES_PATH = _DATA_DIR / "abo_overrides.json"

VALID_INTERVALS = {
    "weekly", "biweekly", "monthly", "bimonthly",
    "quarterly", "halfyearly", "yearly",
}


def norm_key(s: str) -> str:
    """Case-fold + collapse whitespace — matches subscriptions._norm."""
    return re.sub(r"\s+", " ", str(s).lower().strip())


# ── Load / Save ───────────────────────────────────────────────────────────────

def load_overrides() -> dict:
    """Return {"hidden": [...], "manual": [...]}; robust to missing/corrupt file."""
    if not OVERRIDES_PATH.exists():
        return {"hidden": [], "forced": [], "manual": []}
    try:
        with open(OVERRIDES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"hidden": [], "forced": [], "manual": []}
        data.setdefault("hidden", [])
        data.setdefault("forced", [])
        data.setdefault("manual", [])
        return data
    except Exception:
        return {"hidden": [], "forced": [], "manual": []}


def save_overrides(data: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OVERRIDES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Hidden (false positives) ──────────────────────────────────────────────────

def hidden_keys() -> set[str]:
    return {
        h["key"] for h in load_overrides().get("hidden", [])
        if isinstance(h, dict) and "key" in h
    }


def hide_abo(label: str) -> dict:
    """Mark a detected subscription (by its display label) as 'not a subscription'."""
    key = norm_key(label)
    data = load_overrides()
    # Hiding and force-marking are contradictory — drop any forced entry.
    data["forced"] = [f for f in data["forced"] if f.get("key") != key]
    if not any(h.get("key") == key for h in data["hidden"]):
        data["hidden"].append({"key": key, "label": str(label)})
    save_overrides(data)
    return data


def unhide_abo(key: str) -> dict:
    """Restore a previously hidden subscription."""
    key = norm_key(key)
    data = load_overrides()
    data["hidden"] = [h for h in data["hidden"] if h.get("key") != key]
    save_overrides(data)
    return data


# ── Forced (marked as abo from the Buchungen tab) ─────────────────────────────

def forced_keys() -> set[str]:
    return {
        f["key"] for f in load_overrides().get("forced", [])
        if isinstance(f, dict) and "key" in f
    }


def force_abo(label: str) -> dict:
    """Flag a payee (by display label) as a subscription."""
    key = norm_key(label)
    data = load_overrides()
    # Forcing overrides a previous 'not a subscription' decision.
    data["hidden"] = [h for h in data["hidden"] if h.get("key") != key]
    if not any(f.get("key") == key for f in data["forced"]):
        data["forced"].append({"key": key, "label": str(label)})
    save_overrides(data)
    return data


def unforce_abo(key: str) -> dict:
    """Remove a payee's forced-subscription flag."""
    key = norm_key(key)
    data = load_overrides()
    data["forced"] = [f for f in data["forced"] if f.get("key") != key]
    save_overrides(data)
    return data


# ── Manual subscriptions ──────────────────────────────────────────────────────

def add_manual(payee: str, avg_amount: float, interval: str, category: str) -> dict:
    """Add a hand-defined subscription. Returns the stored item."""
    if interval not in VALID_INTERVALS:
        interval = "monthly"
    item = {
        "id":         uuid.uuid4().hex[:12],
        "payee":      str(payee).strip(),
        "avg_amount": round(abs(float(avg_amount)), 2),
        "interval":   interval,
        "category":   str(category).strip() or "Sonstiges",
    }
    data = load_overrides()
    data["manual"].append(item)
    save_overrides(data)
    return item


def delete_manual(item_id: str) -> dict:
    data = load_overrides()
    data["manual"] = [m for m in data["manual"] if m.get("id") != item_id]
    save_overrides(data)
    return data
