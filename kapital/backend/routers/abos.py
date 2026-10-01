from fastapi import APIRouter
from pydantic import BaseModel

from ..deps import get_df, cat_meta
from kapital.finance import abo_overrides

router = APIRouter()

_FREQ_MAP = {
    "Wöchentlich":     "weekly",
    "Zweiwöchentlich": "biweekly",
    "Monatlich":       "monthly",
    "Alle 2 Monate":   "bimonthly",
    "Vierteljährlich": "quarterly",
    "Halbjährlich":    "halfyearly",
    "Jährlich":        "yearly",
}
_INTERVAL_TO_FREQ_DE = {v: k for k, v in _FREQ_MAP.items()}

# Payments per year for each interval — used to derive monthly cost for manual abos.
_ANNUAL_FACTOR = {
    "weekly":     52,
    "biweekly":   26,
    "monthly":    12,
    "bimonthly":   6,
    "quarterly":   4,
    "halfyearly":  2,
    "yearly":      1,
}


def _forced_item(df, key: str, label: str) -> dict | None:
    """Build an abo item for a user-forced payee, computed from its transactions.

    Recomputed on every request, so newly imported bookings for the same payee
    are automatically reflected.
    """
    import pandas as pd
    from kapital.finance.subscriptions import _classify_interval

    exp = df[(df["amount"] < 0) & (~df["is_transfer"].fillna(False))].copy()
    if exp.empty:
        return None

    pk = exp["payee"].fillna("").map(abo_overrides.norm_key)
    dk = exp["description"].fillna("").str[:50].map(abo_overrides.norm_key)
    grp = exp[(pk == key) | (dk == key)]
    if grp.empty:
        return None

    amount = float(grp["amount"].abs().mean())
    dates  = sorted(pd.to_datetime(grp["date"]).dt.normalize())

    freq_de = "Monatlich"
    if len(dates) >= 2:
        gaps    = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        avg_gap = sum(gaps) / len(gaps)
        cls     = _classify_interval(avg_gap)
        if cls:
            freq_de = cls[0]

    interval = _FREQ_MAP.get(freq_de, "monthly")
    factor   = _ANNUAL_FACTOR.get(interval, 12)
    monthly  = amount * factor / 12
    cat_mode = grp["category"].mode()
    category = str(cat_mode.iloc[0]) if not cat_mode.empty else "Sonstiges"
    last     = max(dates)

    return {
        "id":            key,
        "payee":         label,
        "category":      category,
        "avg_amount":    round(amount, 2),
        "monthly_cost":  round(monthly, 2),
        "annual_cost":   round(amount * factor, 2),
        "interval":      interval,
        "frequency":     freq_de,
        "count":         int(len(grp)),
        "last_date":     last.strftime("%Y-%m-%d"),
        "next_expected": "",
        "manual":        False,
        "forced":        True,
        "key":           key,
    }


def _offsets_for(df, merchant: str) -> dict:
    """Gegenzahlungen zu einem Abo — ein Abo kann geteilt sein."""
    try:
        from kapital.finance.subscriptions import find_offsets
        return find_offsets(df, merchant)
    except Exception:
        return {"monthly": 0.0, "quellen": []}


def _f(v):
    """Zahl oder None — die Erkennung liefert für kurze Reihen leere Felder."""
    try:
        import math
        f = float(v)
        return None if math.isnan(f) else round(f, 2)
    except (TypeError, ValueError):
        return None


def _d(v):
    """Datum als YYYY-MM-DD oder None."""
    try:
        return v.strftime("%Y-%m-%d") if v is not None and hasattr(v, "strftime") else None
    except Exception:
        return None


def _manual_item(m: dict) -> dict:
    """Turn a stored manual override into an API item (same shape as detected)."""
    interval = m.get("interval", "monthly")
    factor   = _ANNUAL_FACTOR.get(interval, 12)
    amount   = abs(float(m.get("avg_amount", 0)))
    monthly  = amount * factor / 12
    payee    = str(m.get("payee", ""))
    return {
        "id":            m.get("id", ""),
        "payee":         payee,
        "category":      str(m.get("category", "Sonstiges")),
        "avg_amount":    round(amount, 2),
        "monthly_cost":  round(monthly, 2),
        "annual_cost":   round(amount * factor, 2),
        "interval":      interval,
        "frequency":     _INTERVAL_TO_FREQ_DE.get(interval, "Monatlich"),
        "count":         None,
        "last_date":     "",
        "next_expected": "",
        "manual":        True,
        "key":           abo_overrides.norm_key(payee),
    }


@router.get("/abos")
def get_abos():
    from kapital.finance.subscriptions import detect_subscriptions

    overrides = abo_overrides.load_overrides()
    hidden    = abo_overrides.hidden_keys()

    df = get_df()

    items: list[dict] = []
    detected_keys: set[str] = set()
    if not df.empty:
        try:
            subs_df = detect_subscriptions(df)
        except Exception:
            subs_df = None

        if subs_df is not None and not subs_df.empty:
            for _, row in subs_df.iterrows():
                payee = str(row.get("payee", ""))
                key   = abo_overrides.norm_key(payee)
                if key in hidden:
                    continue  # user marked this as "not a subscription"
                detected_keys.add(key)

                monthly_cost = abs(float(row.get("monthly_cost", 0)))
                freq_de      = str(row.get("frequency", "Monatlich"))
                interval     = _FREQ_MAP.get(freq_de, "monthly")

                items.append({
                    "id":            payee,
                    "payee":         payee,
                    "category":      str(row.get("category", "Sonstiges")),
                    "avg_amount":    round(abs(float(row.get("avg_amount", 0))), 2),
                    # Preisentwicklung: in einer Monatsansicht ist eine
                    # Erhöhung strukturell unsichtbar — jeder Monat sieht
                    # normal aus, und die Verdreifachung merkt man nach Jahren
                    # oder gar nicht.
                    "first_amount":  _f(row.get("first_amount")),
                    "last_amount":   _f(row.get("last_amount")),
                    "change_pct":    _f(row.get("change_pct")),
                    "amount_before": _f(row.get("amount_before")),
                    "changed_at":    _d(row.get("changed_at")),
                    "first_seen":    _d(row.get("first_seen")),
                    # Geteiltes Abo: was regelmässig zurückkommt.
                    "offset":        _offsets_for(df, str(row.get("payee", ""))),
                    "monthly_cost":  round(monthly_cost, 2),
                    "annual_cost":   round(abs(float(row.get("annual_cost", monthly_cost * 12))), 2),
                    "interval":      interval,
                    "frequency":     freq_de,
                    "count":         int(row.get("occurrences", 0)),
                    "last_date":     row["last_date"].strftime("%Y-%m-%d") if hasattr(row.get("last_date"), "strftime") else str(row.get("last_date", ""))[:10],
                    "next_expected": row["next_expected"].strftime("%Y-%m-%d") if hasattr(row.get("next_expected"), "strftime") else str(row.get("next_expected", ""))[:10],
                    "manual":        False,
                    "key":           key,
                })

    # Append payees the user marked as abo in the Buchungen tab
    # (skip if auto-detection already covers them or they're hidden).
    if not df.empty:
        for f in overrides.get("forced", []):
            fkey = f.get("key", "")
            if not fkey or fkey in detected_keys or fkey in hidden:
                continue
            forced = _forced_item(df, fkey, str(f.get("label", fkey)))
            if forced:
                items.append(forced)

    # Append hand-defined subscriptions.
    for m in overrides.get("manual", []):
        items.append(_manual_item(m))

    items.sort(key=lambda x: x["monthly_cost"], reverse=True)
    total_monthly = round(sum(x["monthly_cost"] for x in items), 2)

    return {
        "subscriptions": items,
        "total_monthly": total_monthly,
        "hidden": overrides.get("hidden", []),
    }


# ── Mutations ─────────────────────────────────────────────────────────────────

class HideBody(BaseModel):
    label: str


class UnhideBody(BaseModel):
    key: str


class ManualBody(BaseModel):
    payee: str
    avg_amount: float
    interval: str = "monthly"
    category: str = "Sonstiges"


@router.post("/abos/hide")
def hide_abo(body: HideBody):
    abo_overrides.hide_abo(body.label)
    return {"ok": True}


@router.post("/abos/unhide")
def unhide_abo(body: UnhideBody):
    abo_overrides.unhide_abo(body.key)
    return {"ok": True}


class ForceBody(BaseModel):
    label: str


@router.post("/abos/force")
def force_abo(body: ForceBody):
    abo_overrides.force_abo(body.label)
    return {"ok": True}


@router.post("/abos/unforce")
def unforce_abo(body: UnhideBody):
    abo_overrides.unforce_abo(body.key)
    return {"ok": True}


@router.post("/abos/manual")
def add_manual_abo(body: ManualBody):
    item = abo_overrides.add_manual(body.payee, body.avg_amount, body.interval, body.category)
    return {"ok": True, "item": item}


@router.delete("/abos/manual/{item_id}")
def delete_manual_abo(item_id: str):
    abo_overrides.delete_manual(item_id)
    return {"ok": True}
