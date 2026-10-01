"""Monatsabschluss: Budget-Ziele, Ist/Ziel-Vergleich und KI-Bewertung."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_df, cat_meta
from .. import coach as coach_mod
from kapital.finance import budgets, monatsbericht, review as review_core

router = APIRouter()


class TargetBody(BaseModel):
    value: float | None = None      # None = zurück auf Durchschnitt


class BudgetConfigBody(BaseModel):
    avg_months: int | None = None
    exclude_sonderausgaben: bool | None = None


# ── Monatsauswahl ─────────────────────────────────────────────────────────────

@router.get("/monatsabschluss/months")
def available_months():
    """Alle Monate mit Daten, plus Marker für den letzten vollständigen Monat."""
    df = get_df()
    months = budgets.data_months(df)
    open_counts = review_core.open_counts_by_month(df)
    last = budgets.last_complete_month(df)
    reviews = coach_mod._load_reviews()
    return {
        "months": [
            {
                "month": m,
                "open": int(open_counts.get(m, 0)),
                "has_review": m in reviews,
            }
            for m in reversed(months)
        ],
        "last_complete": last,
    }


# ── Budget-Konfiguration ──────────────────────────────────────────────────────

@router.get("/monatsabschluss/budget")
def get_budget_config():
    cfg = budgets.load_budgets()
    return {
        "avg_months": cfg.get("avg_months", budgets.DEFAULT_AVG_MONTHS),
        "exclude_sonderausgaben": cfg.get("exclude_sonderausgaben", False),
        "targets": cfg.get("targets", {}),
    }


@router.put("/monatsabschluss/budget")
def update_budget_config(body: BudgetConfigBody):
    cfg = budgets.load_budgets()
    if body.avg_months is not None:
        if not 1 <= body.avg_months <= 24:
            raise HTTPException(400, "avg_months muss zwischen 1 und 24 liegen")
        cfg["avg_months"] = int(body.avg_months)
    if body.exclude_sonderausgaben is not None:
        cfg["exclude_sonderausgaben"] = bool(body.exclude_sonderausgaben)
    budgets.save_budgets(cfg)
    return {"ok": True, **cfg}


@router.put("/monatsabschluss/ziel/{category}")
def set_category_target(category: str, body: TargetBody):
    if body.value is not None and body.value < 0:
        raise HTTPException(400, "Ziel darf nicht negativ sein")
    cfg = budgets.set_target(category, body.value)
    return {"ok": True, "category": category, "targets": cfg.get("targets", {})}


# ── Ist/Ziel-Übersicht ────────────────────────────────────────────────────────

@router.get("/monatsabschluss/uebersicht")
def month_overview(month: str = Query("", description="'YYYY-MM'; leer = letzter vollständiger Monat")):
    df = get_df()
    ym = month or budgets.last_complete_month(df)
    if not ym:
        return {"month": None, "empty": True, "categories": [], "open": 0}

    overview = budgets.month_overview(df, ym)
    for c in overview["categories"]:
        c.update(cat_meta(c["category"]))

    kpis = monatsbericht._kpis(df, ym)
    prev = monatsbericht._history(df, ym, 1)

    return {
        **overview,
        "empty": False,
        "kennzahlen": kpis,
        "vormonat": prev[0] if prev else None,
        "open": int(review_core.open_counts_by_month(df).get(ym, 0)),
        "is_complete": ym != str(pd.Timestamp.today().to_period("M")),
    }


# ── KI-Bewertung ──────────────────────────────────────────────────────────────

@router.get("/monatsabschluss/bewertung")
def get_review(month: str = Query("")):
    """Gespeicherte Bewertung abrufen (kein API-Call)."""
    df = get_df()
    ym = month or budgets.last_complete_month(df)
    if not ym:
        raise HTTPException(400, "Kein Monat verfügbar")

    cached = coach_mod.get_cached(ym)
    if not cached:
        return {"month": ym, "exists": False, "api_key_set": bool(coach_mod.get_api_key())}

    snapshot = monatsbericht.build_snapshot(df, ym)
    stale = cached.get("fingerprint") != coach_mod.fingerprint(snapshot)
    return {
        "month": ym,
        "exists": True,
        "stale": stale,
        "created_at": cached.get("created_at"),
        "model": cached.get("model"),
        "usage": cached.get("usage"),
        "result": cached.get("result"),
        "api_key_set": bool(coach_mod.get_api_key()),
    }


@router.post("/monatsabschluss/bewertung")
def create_review(
    month: str = Query(""),
    force: bool = Query(False, description="Auch bewerten, wenn schon eine Bewertung existiert"),
    effort: str = Query("high", description="low | medium | high | xhigh | max"),
):
    """Monat von Claude bewerten lassen. Kostet einen API-Call."""
    df = get_df()
    ym = month or budgets.last_complete_month(df)
    if not ym:
        raise HTTPException(400, "Kein vollständiger Monat vorhanden")

    open_count = int(review_core.open_counts_by_month(df).get(ym, 0))
    if open_count > 0:
        raise HTTPException(
            409,
            f"{open_count} Buchungen in {ym} sind noch nicht zugeordnet. "
            "Ordne sie zu, bevor du bewerten lässt.",
        )

    snapshot = monatsbericht.build_snapshot(df, ym)

    if not force:
        cached = coach_mod.get_cached(ym)
        if cached and cached.get("fingerprint") == coach_mod.fingerprint(snapshot):
            return {"month": ym, "cached": True, **cached}

    if effort not in ("low", "medium", "high", "xhigh", "max"):
        raise HTTPException(400, f"Ungültiges effort-Level: {effort!r}")

    try:
        result, usage = coach_mod.evaluate(snapshot, effort=effort)
    except coach_mod.CoachError as e:
        raise HTTPException(400, str(e))

    entry = coach_mod.store(ym, snapshot, result, usage)
    return {"month": ym, "cached": False, **entry}


@router.delete("/monatsabschluss/bewertung")
def delete_review(month: str = Query(...)):
    return {"ok": coach_mod.delete(month), "month": month}


@router.get("/monatsabschluss/snapshot")
def get_snapshot(month: str = Query("")):
    """Die exakten Daten, die an die KI gehen würden — zur Kontrolle."""
    df = get_df()
    ym = month or budgets.last_complete_month(df)
    if not ym:
        raise HTTPException(400, "Kein Monat verfügbar")
    return monatsbericht.build_snapshot(df, ym)
