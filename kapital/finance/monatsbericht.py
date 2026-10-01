"""
Aggregierter Monats-Snapshot als Input für die KI-Bewertung.

Bewusst aggregiert: keine IBANs, keine Kontonummern, keine Roh-CSV — nur
Kategorie-Summen, Top-Empfänger, auffällige Einzelbuchungen und Depot-Trades.
"""

from __future__ import annotations

import pandas as pd

from . import analytics, budgets, storage
from .models import SAVINGS_CATEGORIES


def _month_slice(df: pd.DataFrame, ym: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df[df["date"].dt.to_period("M").astype(str) == ym].copy()


def _kpis(df: pd.DataFrame, ym: str) -> dict:
    s = analytics.period_summary(_month_slice(df, ym))
    return {
        "einnahmen": round(float(s["total_income"]), 2),
        "ausgaben": round(float(s["total_expenses"]), 2),
        "erstattungen": round(float(s["total_refunds"]), 2),
        "investiert": round(float(s["total_invested"]), 2),
        "ersparnis": round(float(s["savings"]), 2),
        "sparrate": round(float(s["savings_rate"]), 4),
        "n_buchungen": int(s["n_transactions"]),
    }


def _history(df: pd.DataFrame, ym: str, n: int = 6) -> list[dict]:
    """KPIs der n Monate vor `ym` — Kontext für die Einordnung."""
    months = budgets.data_months(df)
    target = pd.Period(ym, "M")
    prior = [m for m in months if pd.Period(m, "M") < target][-n:]
    return [{"monat": m, **_kpis(df, m)} for m in prior]


def _top_payees(month_df: pd.DataFrame, n: int = 12) -> list[dict]:
    exp = month_df[
        (month_df["amount"] < 0)
        & (~month_df["is_transfer"].astype(bool))
        & (~month_df["category"].isin({"Umbuchung"} | SAVINGS_CATEGORIES))
    ].copy()
    if exp.empty:
        return []
    exp["_key"] = exp["payee"].fillna("").str.strip()
    exp.loc[exp["_key"] == "", "_key"] = exp["description"].fillna("").str.strip().str[:40]
    grp = (
        exp.groupby(["_key", "category"])["amount"]
        .agg(betrag=lambda x: round(float(x.abs().sum()), 2), anzahl="count")
        .reset_index()
        .sort_values("betrag", ascending=False)
        .head(n)
    )
    return [
        {"empfaenger": r["_key"][:60], "kategorie": r["category"],
         "betrag": r["betrag"], "anzahl": int(r["anzahl"])}
        for _, r in grp.iterrows()
    ]


def _big_singles(month_df: pd.DataFrame, n: int = 8, min_amount: float = 100.0) -> list[dict]:
    exp = month_df[
        (month_df["amount"] <= -min_amount)
        & (~month_df["is_transfer"].astype(bool))
        & (month_df["category"] != "Umbuchung")
    ].copy()
    if exp.empty:
        return []
    exp = exp.reindex(exp["amount"].abs().sort_values(ascending=False).index).head(n)
    return [
        {
            "datum": r["date"].strftime("%Y-%m-%d"),
            "empfaenger": (str(r.get("payee", "") or "").strip() or str(r.get("description", ""))[:40])[:60],
            "betrag": round(float(r["amount"]), 2),
            "kategorie": str(r.get("category", "")),
            "sonderausgabe": bool(r.get("is_sonderausgabe", False)),
        }
        for _, r in exp.iterrows()
    ]


def _depot(month_df: pd.DataFrame) -> dict:
    if month_df.empty or "units" not in month_df.columns:
        return {"kaeufe": [], "verkaeufe": [], "netto_investiert": 0.0}

    trades = month_df[
        month_df["isin"].fillna("").astype(str).str.strip().ne("")
        & month_df["units"].fillna(0).ne(0)
    ]

    def _fmt(rows: pd.DataFrame) -> list[dict]:
        out = []
        for _, r in rows.iterrows():
            name = str(r.get("description", ""))
            for prefix in ("BUY: ", "SELL: "):
                if name.startswith(prefix):
                    name = name[len(prefix):]
            out.append({
                "datum": r["date"].strftime("%Y-%m-%d"),
                "wertpapier": name[:60],
                "isin": str(r.get("isin", "")),
                "stueck": round(float(r.get("units", 0)), 4),
                "kurs": round(float(r.get("price_per_unit", 0)), 4),
                "betrag": round(float(r["amount"]), 2),
            })
        return out

    kaeufe = _fmt(trades[trades["units"] > 0])
    verkaeufe = _fmt(trades[trades["units"] < 0])
    netto = round(sum(-k["betrag"] for k in kaeufe) - sum(v["betrag"] for v in verkaeufe), 2)

    # Sparpläne / Investitionen ohne ISIN (z. B. Überweisung an Broker)
    sparen = month_df[
        month_df["category"].isin(SAVINGS_CATEGORIES) & (month_df["amount"] < 0)
    ]
    return {
        "kaeufe": kaeufe,
        "verkaeufe": verkaeufe,
        "netto_investiert": netto,
        "sparen_ohne_wertpapier": round(float(-sparen["amount"].sum()), 2) if not sparen.empty else 0.0,
    }


def _holdings(top: int = 12) -> list[dict]:
    snap = storage.load_depot_snapshot()
    if snap is None or snap.empty:
        return []
    s = snap.sort_values("current_value", ascending=False).head(top)
    return [
        {"wertpapier": str(r["name"])[:60], "wert": round(float(r["current_value"]), 2)}
        for _, r in s.iterrows()
        if float(r.get("current_value", 0) or 0) > 0
    ]


def build_snapshot(df: pd.DataFrame, ym: str) -> dict:
    """Kompletter, aggregierter Monats-Snapshot für die Bewertung."""
    month_df = _month_slice(df, ym)
    overview = budgets.month_overview(df, ym)

    return {
        "monat": ym,
        "kennzahlen": _kpis(df, ym),
        "vormonate": _history(df, ym, 6),
        "budget": {
            "referenz_monate": overview["reference_months"],
            "gesamt_ist": overview["total_ist"],
            "gesamt_ziel": overview["total_ziel"],
            "kategorien": [
                {
                    "kategorie": c["category"],
                    "ist": c["ist"],
                    "ziel": c["ziel"],
                    "ziel_quelle": c["quelle"],
                    "abweichung": c["delta"],
                    "status": c["status"],
                    "anzahl": c["count"],
                }
                for c in overview["categories"]
            ],
        },
        "top_empfaenger": _top_payees(month_df),
        "grosse_einzelbuchungen": _big_singles(month_df),
        "depot": _depot(month_df),
        "depot_groesste_positionen": _holdings(),
    }
