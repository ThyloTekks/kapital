"""Zwangs-Zuordnung offener Buchungen nach einem Import."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import pandas as pd

from ..deps import (get_df, set_df, categories_list, cat_meta, transaction,
                    row_occurrences, make_row_ref, resolve_row_ref)
from kapital.finance import storage, review as review_core
from kapital.finance.custom_rules import add_rule, apply_custom_rules, load_rules

router = APIRouter()


class RuleSpec(BaseModel):
    pattern: str
    field: str = "payee"          # payee | description | both


class Assignment(BaseModel):
    tx_hash: str
    category: str
    rule: RuleSpec | None = None  # optional: Regel für künftige Buchungen anlegen


class AssignBody(BaseModel):
    items: list[Assignment]


def _parse_months(months: str) -> list[str]:
    return [m.strip() for m in months.split(",") if m.strip()]


@router.get("/review/status")
def review_status(months: str = Query("", description="Komma-Liste 'YYYY-MM'; leer = alle")):
    """Wie viele Buchungen sind offen — gesamt und je Monat."""
    df = get_df()
    per_month = review_core.open_counts_by_month(df)
    wanted = _parse_months(months)
    if wanted:
        scoped = {m: per_month.get(m, 0) for m in wanted}
    else:
        scoped = per_month
    return {
        "open_total": int(sum(per_month.values())),
        "open_scoped": int(sum(scoped.values())),
        "months": [
            {"month": m, "open": int(n)}
            for m, n in sorted(scoped.items(), reverse=True)
        ],
        "all_months": [
            {"month": m, "open": int(n)}
            for m, n in sorted(per_month.items(), reverse=True)
        ],
    }


@router.get("/review/open")
def review_open(
    months: str = Query("", description="Komma-Liste 'YYYY-MM'; leer = alle"),
    limit: int = Query(500, le=2000),
):
    """Offene Buchungen inkl. Kategorie-Vorschlag aus der eigenen Historie."""
    df = get_df()
    wanted = _parse_months(months)
    items_df = review_core.open_items(df, wanted or None)

    if items_df.empty:
        return {"items": [], "total": 0, "categories": categories_list(), "months": wanted}

    total = len(items_df)
    page = items_df.head(limit)

    # Eindeutige Zeilen-ID statt des kollidierenden tx_hash — Begründung in
    # deps.ROW_REF_SEP. Die laufende Nummer zählt über den VOLLEN Bestand, nicht
    # über die Seite, damit sie unabhängig von Filter und Sortierung dieselbe
    # Zeile bezeichnet.
    occurrence = row_occurrences(df)

    # Vorschläge einmal je Empfänger berechnen (nicht je Zeile)
    suggestion_cache: dict[str, tuple[str, int]] = {}
    items = []
    for _, row in page.iterrows():
        payee = str(row.get("payee", "") or "").strip()
        desc = str(row.get("description", "") or "")
        # Cache-Schlüssel ist der Händler, nicht der Empfänger — sonst teilen
        # sich alle PayPal-Buchungen einen Vorschlag.
        gkey = review_core.group_key(payee, desc)
        ckey = gkey or f"__row__{row['tx_hash']}"
        if ckey not in suggestion_cache:
            suggestion_cache[ckey] = review_core.suggest_category(df, payee, desc)
        sug_cat, sug_n = suggestion_cache[ckey]
        items.append({
            "merchant": review_core.extract_merchant(payee, desc),
            "group_key": gkey,
            "is_aggregator": review_core.is_aggregator(payee),
            "id": make_row_ref(str(row["tx_hash"]), occurrence.loc[row.name]),
            "tx_hash": str(row["tx_hash"]),
            "date": row["date"].strftime("%Y-%m-%d"),
            "month": row["date"].strftime("%Y-%m"),
            "payee": payee,
            "description": desc,
            "amount": round(float(row["amount"]), 2),
            "account": str(row.get("account_label", "")),
            "category": str(row.get("category", "Sonstiges")),
            "suggestion": sug_cat,
            "suggestion_hits": sug_n,
        })

    return {
        "items": items,
        "total": int(total),
        "categories": categories_list(),
        "months": wanted,
    }


@router.post("/review/assign")
def review_assign(body: AssignBody):
    """Mehrere Buchungen auf einmal zuordnen, optional mit neuer Regel."""
    if not body.items:
        return {"ok": True, "updated": 0, "skipped": 0, "rules_added": 0, "open_total": 0}
    with transaction():
        return _assign_locked(body)


def _assign_locked(body: AssignBody):

    df = get_df()
    if df.empty:
        raise HTTPException(400, "Keine Buchungen vorhanden")

    valid = {c["id"] for c in categories_list()}
    df = df.copy()
    updated = 0
    rules_added = 0
    rules_dirty = False

    skipped: list[str] = []
    for item in body.items:
        if item.category not in valid:
            raise HTTPException(400, f"Unbekannte Kategorie: {item.category!r}")
        idx = resolve_row_ref(df, item.tx_hash)
        if idx is None:
            # Nicht mehr auffindbar (Bestand hat sich zwischen Laden und
            # Speichern geändert). Früher ein stilles `continue` — der Nutzer
            # sah einen Erfolgs-Toast und die Buchung war trotzdem offen.
            skipped.append(item.tx_hash)
            continue
        df.loc[idx, "category"] = item.category
        updated += len(idx)

        if item.rule and item.rule.pattern.strip():
            add_rule(item.rule.pattern.strip(), item.category, item.rule.field)
            rules_added += 1
            rules_dirty = True

    # Neue Regeln auf den gesamten Bestand anwenden, damit sie sofort greifen
    if rules_dirty:
        # only_uncategorized: eine neue Regel darf bestehende, bereits korrekte
        # Zuordnungen nicht überschreiben. Vorher wurde jede Regel auf den
        # gesamten Bestand angewandt — eine Regel auf "PayPal" hätte damit alle
        # 739 PayPal-Zeilen überschrieben, auch die 270 bereits richtigen.
        df = apply_custom_rules(df, load_rules(), only_uncategorized=True)

    storage.save(df)
    set_df(df)

    per_month = review_core.open_counts_by_month(df)
    return {
        "ok": True,
        "updated": updated,
        "skipped": len(skipped),
        "rules_added": rules_added,
        "open_total": int(sum(per_month.values())),
        "months": [{"month": m, "open": int(n)} for m, n in sorted(per_month.items(), reverse=True)],
    }
