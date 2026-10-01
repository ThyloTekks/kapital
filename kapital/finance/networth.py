"""Vermögen — die eine Quelle für "wie viel habe ich" und "wie viel kann ich sparen".

Vorher beantworteten drei Seiten dieselbe Frage verschieden: die Übersicht mit
kalibrierten Salden, die Prognose mit dem rohen Zahlungsstrom (14.850 € daneben),
und FIRE gar nicht — die fragte den Nutzer. Genau wie bei den vier
Ausgaben-Definitionen gilt: eine Zahl, eine Funktion, alle Seiten fragen dort.

Was hier NICHT passiert: eine Depotwert-Historie erfinden. Der Depotauszug ist
eine Momentaufnahme ohne Verlauf, und Kurse rückwirkend zu beschaffen wäre
geraten. Die Historie zeigt deshalb liquides Vermögen exakt und eingesetztes
Kapital zum Einstand — beides beschriftet, damit niemand einen Marktwert
hineinliest, der nicht da ist.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from . import storage

log = logging.getLogger(__name__)


def _norm(v) -> str:
    return str(v or "").replace(" ", "").upper()


def account_display_groups(df: pd.DataFrame) -> dict[str, list[str]]:
    """Anzeigename -> alle rohen account_label, die dasselbe Konto bezeichnen.

    Der in der Parquet gespeicherte `account_label` ist der Wert vom
    Importzeitpunkt und friert ein: derselbe Bestand trägt dasselbe Konto als
    "Giro", als IBAN mit Leerzeichen und als IBAN ohne Leerzeichen. Eine
    spätere Umbenennung landet nur in iban_labels.json und erreicht die
    gespeicherten Zeilen nie.

    Deshalb wird der Anzeigename immer hier aufgelöst und nie aus der Parquet
    gelesen — sonst zeigt ein Kontofilter rohe IBANs an und zerlegt ein Konto
    in mehrere Einträge, von denen jeder nur einen Teil der Buchungen trifft.
    """
    if df is None or df.empty or "account_label" not in df.columns:
        return {}
    labels = storage.load_iban_labels() or {}
    label_by_norm = {_norm(k): v for k, v in labels.items()}
    groups: dict[str, list[str]] = {}
    for raw in df["account_label"].dropna().unique():
        display = label_by_norm.get(_norm(raw)) or str(raw)
        groups.setdefault(display, []).append(raw)
    return groups


def account_balances(df: pd.DataFrame) -> list[dict]:
    """Salden je Konto — zusammengeführt und kalibriert.

    Zusammenführung über den ANZEIGENAMEN: dasselbe Konto liegt im Bestand
    unter mehreren Bezeichnungen (IBAN mit und ohne Leerzeichen, bei
    Altimporten auch als blosser Name). Ohne die Auflösung über
    iban_labels.json erscheint ein Konto mehrfach und ein hinterlegter Saldo
    wird doppelt gezählt.

    Der Saldo läuft immer über die GESAMTE Historie, nie über einen
    Datumsfilter — ein Kontostand, der sich beim Umschalten des Zeitraums
    ändert, ist keiner.
    """
    if df is None or df.empty:
        return []

    balances = storage.load_giro_balances() or {}

    cal_by_norm: dict[str, float] = {}
    for k, v in balances.items():
        bal = v.get("balance") if isinstance(v, dict) else v
        if bal is not None:
            cal_by_norm.setdefault(_norm(k), float(bal))

    groups = account_display_groups(df)

    out = []
    for display, raw_labels in groups.items():
        sub = df[df["account_label"].isin(raw_labels)]
        flow = float(sub["amount"].sum())
        bal = cal_by_norm.get(_norm(raw_labels[0]))
        if bal is None:
            bal = cal_by_norm.get(_norm(display))
        out.append({
            "id": raw_labels[0],
            "name": display,
            "raw_labels": raw_labels,
            "type": sub["account"].iloc[0] if len(sub) else "Giro",
            "balance": bal if bal is not None else flow,
            "flow": round(flow, 2),
            "calibrated": bal is not None,
            # Differenz zwischen hinterlegtem Stand und importiertem Fluss:
            # das ist der Anfangssaldo vor dem ersten Import.
            "opening": round(bal - flow, 2) if bal is not None else 0.0,
        })
    out.sort(key=lambda a: abs(a["balance"]), reverse=True)
    return out


def depot_value() -> Optional[float]:
    """Aktueller Depotwert laut Depotauszug. None, wenn keiner importiert ist."""
    snap = storage.load_depot_snapshot()
    if snap is None or snap.empty or "current_value" not in snap.columns:
        return None
    val = pd.to_numeric(snap["current_value"], errors="coerce").sum()
    return round(float(val), 2) if pd.notna(val) else None


def current(df: pd.DataFrame) -> dict:
    """Aktuelles Vermögen: liquide Konten + Depot."""
    accounts = account_balances(df)
    # Trade Republic ist ein Verrechnungskonto, kein Girokonto — sein Saldo ist
    # freies Guthaben und wird separat ausgewiesen, damit er nicht doppelt
    # neben dem Depotwert steht.
    liquid = sum(a["balance"] for a in accounts if a["type"] != "Trade Republic")
    broker_cash = sum(a["balance"] for a in accounts if a["type"] == "Trade Republic")
    depot = depot_value()
    snap_date = storage.load_depot_snapshot_date()

    total = liquid + broker_cash + (depot or 0.0)
    return {
        "liquid": round(liquid, 2),
        "broker_cash": round(broker_cash, 2),
        "depot": depot,
        "depot_as_of": snap_date,
        "total": round(total, 2),
        "accounts": accounts,
        "uncalibrated": [a["name"] for a in accounts if not a["calibrated"]],
    }


def history(df: pd.DataFrame, months: int = 36) -> dict:
    """Vermögensverlauf je Monat.

    Rückwärts gerechnet: der heutige kalibrierte Saldo ist der Anker, davon
    werden die bekannten Bewegungen abgezogen. Das ist genauer als vorwärts zu
    kumulieren, weil der Anfangssaldo vor dem ersten Import unbekannt ist —
    genau daran ist die Prognose bisher gescheitert.

    `invested` ist das eingesetzte Kapital zum EINSTAND, kein Marktwert. Eine
    Marktwert-Historie gibt der Depotauszug nicht her, und sie zu schätzen
    hiesse, eine Zahl zu erfinden.
    """
    if df is None or df.empty:
        return {"months": [], "series": [], "note": ""}

    accounts = account_balances(df)
    anchor = sum(a["balance"] for a in accounts)

    real = df.copy()
    real["ym"] = real["date"].dt.to_period("M")
    all_months = sorted(real["ym"].unique())
    if not all_months:
        return {"months": [], "series": [], "note": ""}
    window = all_months[-months:]

    # Netto-Zufluss je Monat über alle Konten (Umbuchungen heben sich auf).
    per_month = real.groupby("ym")["amount"].sum()

    # Vom heutigen Stand rückwärts: Stand am Ende von Monat m.
    end_balance: dict[pd.Period, float] = {}
    running = anchor
    for m in reversed(all_months):
        end_balance[m] = running
        running -= float(per_month.get(m, 0.0))

    # Eingesetztes Kapital (Einstand) kumuliert.
    from .models import SAVINGS_CATEGORIES
    inv = real[
        real["category"].isin(SAVINGS_CATEGORIES)
        & (real["amount"] < 0)
        & ~real["is_transfer"].fillna(False).astype(bool)
    ]
    inv_cum = inv.groupby("ym")["amount"].sum().abs().cumsum() if not inv.empty else pd.Series(dtype=float)

    rows = []
    for m in window:
        rows.append({
            "month": str(m),
            "wealth": round(float(end_balance.get(m, 0.0)), 2),
            "invested": round(float(inv_cum.reindex(all_months).ffill().get(m, 0.0) or 0.0), 2),
        })

    note = ""
    if any(not a["calibrated"] for a in accounts):
        names = ", ".join(a["name"] for a in accounts if not a["calibrated"])
        note = (f"Für {names} ist kein Kontostand hinterlegt — dort zählt nur der "
                f"importierte Zahlungsstrom, der Verlauf ist um den unbekannten "
                f"Anfangssaldo verschoben.")
    return {"months": [r["month"] for r in rows], "series": rows, "note": note,
            "anchor": round(anchor, 2)}


def savings_capacity(df: pd.DataFrame, months: int = 6) -> dict:
    """Monatliche Sparfähigkeit — die Grundlast-Zahl, nicht der Rohschnitt.

    Prognose und FIRE haben bisher `ersparnis` aus monthly_summary gemittelt.
    Diese Zahl enthält den Erstattungsterm und schwankt mit jedem Urlaubsmonat;
    als Grundlage einer Hochrechnung über Jahrzehnte taugt sie nicht.
    """
    from . import budgets
    b = budgets.baseline(df, months=months)
    return {
        "monthly_savings": b["avg_savings"],
        "monthly_expenses": b["avg_spend"],
        "monthly_income": b["avg_income"],
        "basis_months": b["n_months"],
        "window": b["months"],
        "excluded_categories": b["excluded_categories"],
        "excluded_avg": b["excluded_avg"],
    }


def darlehen(df: pd.DataFrame) -> dict:
    """Offene Darlehen je Person.

    Geliehenes Geld ist eine Forderung und gehört damit zum Vermögen — es ist
    nur gerade nicht auf dem Konto. Deshalb steht das hier und nicht in den
    Ausgaben.

    Vorzeichen: eine Zahlung AN jemanden (negativ) erhöht die Forderung, eine
    Tilgung VON jemandem (positiv) senkt sie. Der Saldo ist das, was noch
    offen ist.
    """
    from .models import LOAN_CATEGORY

    if df is None or df.empty:
        return {"total_offen": 0.0, "personen": [], "n_bookings": 0}

    r = df[(df["category"] == LOAN_CATEGORY)
           & ~df["is_transfer"].fillna(False).astype(bool)].copy()
    if r.empty:
        return {"total_offen": 0.0, "personen": [], "n_bookings": 0}

    personen = []
    for payee, g in r.groupby(r["payee"].fillna("").str.strip()):
        if not payee:
            payee = "ohne Empfänger"
        verliehen = float(abs(g[g["amount"] < 0]["amount"].sum()))
        getilgt = float(g[g["amount"] > 0]["amount"].sum())
        offen = verliehen - getilgt
        letzte = g["date"].max()
        # Tilgt jemand regelmässig, lässt sich abschätzen, wann er durch ist.
        tilgungen = g[g["amount"] > 0].sort_values("date")
        rate = float(tilgungen["amount"].tail(6).median()) if len(tilgungen) >= 3 else 0.0
        monate_rest = int(round(offen / rate)) if rate > 0 and offen > 0 else None
        personen.append({
            "person": str(payee),
            "verliehen": round(verliehen, 2),
            "getilgt": round(getilgt, 2),
            "offen": round(offen, 2),
            "n": int(len(g)),
            "letzte_bewegung": letzte.strftime("%Y-%m-%d") if pd.notna(letzte) else None,
            "tilgungsrate": round(rate, 2) if rate else None,
            "monate_bis_getilgt": monate_rest,
        })
    personen.sort(key=lambda p: abs(p["offen"]), reverse=True)
    return {
        "total_offen": round(sum(p["offen"] for p in personen), 2),
        "personen": personen,
        "n_bookings": int(len(r)),
    }
