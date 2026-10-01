"""
Budget-Ziele je Kategorie + Ist/Ziel-Vergleich für einen Monat.

Persistiert in  data/budgets.json:

    {
      "avg_months": 6,                     # Referenzfenster für den Durchschnitt
      "exclude_sonderausgaben": false,     # Sonderausgaben aus dem Schnitt nehmen
      "targets": {"Lebensmittel": 400.0}   # manuelle Ziele; schlagen den Schnitt
    }

Eine Kategorie ohne Eintrag in "targets" bekommt als Ziel den Durchschnitt der
letzten `avg_months` vollständigen Monate vor dem betrachteten Monat.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .models import SAVINGS_CATEGORIES, NON_ECONOMIC_CATEGORIES

_HERE = Path(__file__).parent
_DATA_DIR = _HERE.parent.parent / "data"
BUDGETS_PATH = _DATA_DIR / "budgets.json"

DEFAULT_AVG_MONTHS = 6

# Kategorien, die nie im Budget-Vergleich auftauchen (kein Konsum)
_NON_CONSUMPTION = {"Einkommen"} | NON_ECONOMIC_CATEGORIES | SAVINGS_CATEGORIES


# ── Persistenz ────────────────────────────────────────────────────────────────

def load_budgets() -> dict:
    if BUDGETS_PATH.exists():
        try:
            data = json.loads(BUDGETS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("avg_months", DEFAULT_AVG_MONTHS)
                data.setdefault("exclude_sonderausgaben", False)
                data.setdefault("targets", {})
                return data
        except Exception:
            pass
    return {"avg_months": DEFAULT_AVG_MONTHS, "exclude_sonderausgaben": False, "targets": {}}


def save_budgets(data: dict) -> None:
    from .storage import write_json_atomic
    write_json_atomic(BUDGETS_PATH, data)


def set_target(category: str, value: float | None) -> dict:
    """Manuelles Ziel setzen (value=None → zurück auf Durchschnitt)."""
    data = load_budgets()
    targets = data.get("targets", {})
    if value is None:
        targets.pop(category, None)
    else:
        targets[category] = round(float(value), 2)
    data["targets"] = targets
    save_budgets(data)
    return data


# ── Ausgaben je Monat/Kategorie ───────────────────────────────────────────────

def consumption(df: pd.DataFrame, exclude_sonderausgaben: bool = False) -> pd.DataFrame:
    """Konsum-Buchungen: ohne Umbuchungen, Einkommen und Investitionen."""
    if df.empty:
        return df
    r = df[~df["is_transfer"].astype(bool)].copy()
    r = r[~r["category"].isin(_NON_CONSUMPTION)]
    if exclude_sonderausgaben and "is_sonderausgabe" in r.columns:
        r = r[~r["is_sonderausgabe"].astype(bool)]
    return r


def net_spend_matrix(df: pd.DataFrame, exclude_sonderausgaben: bool = False) -> pd.DataFrame:
    """Netto-Ausgaben (Ausgaben − Erstattungen) je Monat × Kategorie.

    Index = 'YYYY-MM' (str), Spalten = Kategorien, Werte ≥ 0.
    """
    r = consumption(df, exclude_sonderausgaben)
    if r.empty:
        return pd.DataFrame()
    r["ym"] = r["date"].dt.to_period("M").astype(str)
    mat = r.pivot_table(index="ym", columns="category", values="amount", aggfunc="sum")
    return (-mat).fillna(0.0).clip(lower=0.0).sort_index()


def data_months(df: pd.DataFrame) -> list[str]:
    """Alle Monate mit mindestens einer Buchung, aufsteigend."""
    if df.empty:
        return []
    return sorted(df["date"].dt.to_period("M").astype(str).unique().tolist())


def last_complete_month(df: pd.DataFrame, today: pd.Timestamp | None = None) -> str | None:
    """Letzter vollständig abgeschlossener Monat, für den Daten existieren."""
    months = data_months(df)
    if not months:
        return None
    today = today or pd.Timestamp.today()
    current = today.to_period("M")
    candidates = [m for m in months if pd.Period(m, "M") < current]
    return candidates[-1] if candidates else None


# ── Monatsübersicht ───────────────────────────────────────────────────────────

def _reference_window(all_months: list[str], ym: str, n: int) -> list[str]:
    """Die letzten n Monate mit Daten *vor* ym."""
    target = pd.Period(ym, "M")
    prior = [m for m in all_months if pd.Period(m, "M") < target]
    return prior[-n:] if n > 0 else prior


def month_overview(df: pd.DataFrame, ym: str) -> dict:
    """Ist/Ziel-Vergleich aller Konsum-Kategorien für den Monat `ym`."""
    cfg = load_budgets()
    avg_months = int(cfg.get("avg_months", DEFAULT_AVG_MONTHS))
    excl_sonder = bool(cfg.get("exclude_sonderausgaben", False))
    targets: dict = cfg.get("targets", {})

    mat = net_spend_matrix(df, exclude_sonderausgaben=excl_sonder)
    if mat.empty:
        return {
            "month": ym, "avg_months": avg_months,
            "exclude_sonderausgaben": excl_sonder,
            "reference_months": [], "categories": [],
            "total_ist": 0.0, "total_ziel": 0.0, "total_delta": 0.0,
        }

    all_months = mat.index.tolist()
    ref_months = _reference_window(all_months, ym, avg_months)
    ref_frame = mat.loc[[m for m in ref_months if m in mat.index]] if ref_months else mat.iloc[0:0]

    ist_row = mat.loc[ym] if ym in mat.index else None

    # Buchungszahl je Kategorie im Monat
    month_rows = consumption(df, excl_sonder)
    counts: dict[str, int] = {}
    if not month_rows.empty:
        month_rows = month_rows[month_rows["date"].dt.to_period("M").astype(str) == ym]
        counts = month_rows.groupby("category").size().to_dict()

    cats = set(mat.columns.tolist()) | set(targets.keys())
    out = []
    for cat in sorted(cats):
        ist = float(ist_row[cat]) if ist_row is not None and cat in ist_row.index else 0.0
        if cat in ref_frame.columns and not ref_frame.empty:
            series = ref_frame[cat]
            avg = float(series.mean())
            n_active = int((series > 0).sum())
        else:
            avg = 0.0
            n_active = 0

        manual = targets.get(cat)
        if manual is not None:
            ziel = float(manual)
            quelle = "manuell"
        else:
            ziel = avg
            quelle = "schnitt"

        # Kategorien ohne jede Aktivität und ohne Ziel überspringen
        if ist == 0 and ziel == 0 and manual is None:
            continue

        delta = ist - ziel
        if ziel > 0:
            pct = ist / ziel
        else:
            pct = 2.0 if ist > 0 else 0.0

        # Abstufung statt Ja/Nein. Vorher galt ab 5 % über Ziel alles als
        # "over" und wurde gleich rot dargestellt — 0,75 € über einem
        # Durchschnittswert sah aus wie 2.500 € über einem gesetzten Budget.
        #
        # Zusätzlich zählt, wie belastbar das Ziel ist: ein selbst gesetztes
        # Budget ist eine Zusage und darf rot werden. Der 6-Monats-Schnitt ist
        # ein statistischer Erwartungswert, den man per Definition in etwa der
        # Hälfte der Monate überschreitet — der wird höchstens gelb.
        reliable = (manual is not None) or (n_active >= 3)
        material = delta > 100.0          # kleine Beträge sind kein Alarm
        if ziel <= 0 and ist <= 0:
            status, severity = "on", "none"
        elif ziel <= 0 and ist > 0:
            # Kategorie ohne Referenz: keine Aussage möglich, kein Alarm.
            status, severity = "over", "unknown"
        elif pct > 1.10:
            status = "over"
            if not reliable:
                severity = "unknown"
            elif pct > 2.0 and material:
                severity = "high" if manual is not None else "medium"
            elif pct > 1.25 and material:
                severity = "medium"
            else:
                severity = "low"
        elif ist < ziel * 0.90:
            status, severity = "under", "none"
        else:
            status, severity = "on", "none"

        out.append({
            "category": cat,
            "ist": round(ist, 2),
            "ziel": round(ziel, 2),
            "durchschnitt": round(avg, 2),
            "quelle": quelle,
            "delta": round(delta, 2),
            "pct": round(pct, 4),
            "status": status,
            "severity": severity,
            "reliable": bool(reliable),
            "count": int(counts.get(cat, 0)),
            "n_ref_months": len(ref_frame),
            "n_active_months": n_active,
        })

    out.sort(key=lambda c: c["delta"], reverse=True)
    total_ist = round(sum(c["ist"] for c in out), 2)
    total_ziel = round(sum(c["ziel"] for c in out), 2)

    return {
        "month": ym,
        "avg_months": avg_months,
        "exclude_sonderausgaben": excl_sonder,
        "reference_months": ref_frame.index.tolist(),
        "categories": out,
        "total_ist": total_ist,
        "total_ziel": total_ziel,
        "total_delta": round(total_ist - total_ziel, 2),
    }


# ── Basis-Ausgaben (wiederkehrende Grundlast) ────────────────────────────────

DEFAULT_BASELINE_EXCLUDED = ["Reisen & Urlaub"]


def baseline(
    df: pd.DataFrame,
    months: int = 6,
    exclude_categories: list[str] | None = None,
    exclude_sonderausgaben: bool = True,
    today: pd.Timestamp | None = None,
) -> dict:
    """Was kostet ein normaler Monat — ohne Einmaliges?

    Die Frage dahinter: wie viel könnte ich monatlich sparen, wenn man die
    Ausreisser wegrechnet. Dafür taugt weder die Gesamtsumme (ein
    Urlaub verschiebt sie um Tausende) noch der Blick auf einen einzelnen
    Monat.

    Drei bewusste Entscheidungen:

    1. Nur ABGESCHLOSSENE Monate. Der laufende Monat ist unvollständig und
       würde den Schnitt systematisch nach unten ziehen.
    2. Ausgeschlossenes wird beziffert, nicht verschwiegen. Ein Durchschnitt,
       der stillschweigend Posten weglässt, ist genau die Sorte Kennzahl, der
       man später nicht mehr traut — deshalb kommt zurück, wie viel pro Monat
       herausgerechnet wurde.
    3. Einnahmen kommen aus derselben Fensterlogik, damit die abgeleitete
       Sparfähigkeit zum Ausgabenschnitt passt.
    """
    excl = list(DEFAULT_BASELINE_EXCLUDED if exclude_categories is None else exclude_categories)
    excl_norm = {c.strip().lower() for c in excl}

    last = last_complete_month(df, today)
    if not last or df.empty:
        return {
            "months": [], "n_months": 0, "avg_spend": 0.0, "avg_income": 0.0,
            "avg_savings": 0.0, "savings_rate": 0.0, "per_month": [],
            "categories": [], "excluded_categories": excl,
            "excluded_avg": 0.0, "sonderausgaben_avg": 0.0,
            "exclude_sonderausgaben": exclude_sonderausgaben,
        }

    all_months = data_months(df)
    window = [m for m in all_months if pd.Period(m, "M") <= pd.Period(last, "M")][-months:]
    if not window:
        window = [last]

    # Voller Schnitt (nichts ausgenommen) — als Vergleichsgrösse.
    mat_full = net_spend_matrix(df, exclude_sonderausgaben=False)
    # Grundlast: ohne Sonderausgaben und ohne die genannten Kategorien.
    mat_base = net_spend_matrix(df, exclude_sonderausgaben=exclude_sonderausgaben)

    def _rows(mat: pd.DataFrame, drop: set[str]) -> pd.DataFrame:
        if mat.empty:
            return pd.DataFrame()
        sub = mat.loc[[m for m in window if m in mat.index]]
        keep = [c for c in sub.columns if str(c).strip().lower() not in drop]
        return sub[keep]

    base_rows = _rows(mat_base, excl_norm)
    full_rows = _rows(mat_full, set())

    n = max(len(base_rows), 1)
    avg_spend = float(base_rows.sum(axis=1).mean()) if not base_rows.empty else 0.0
    avg_full = float(full_rows.sum(axis=1).mean()) if not full_rows.empty else 0.0

    # Einnahmen im selben Fenster, gleiche Definition wie in analytics.
    r = df[~df["is_transfer"].astype(bool) & (df["category"] != "Umbuchung")].copy()
    r["ym"] = r["date"].dt.to_period("M").astype(str)
    inc = r[(r["category"] == "Einkommen") & (r["amount"] > 0) & (r["ym"].isin(window))]
    avg_income = float(inc.groupby("ym")["amount"].sum().reindex(window).fillna(0.0).mean())

    per_month = []
    for m in window:
        spend = float(base_rows.loc[m].sum()) if m in base_rows.index else 0.0
        total = float(full_rows.loc[m].sum()) if m in full_rows.index else 0.0
        income = float(inc[inc["ym"] == m]["amount"].sum())
        per_month.append({
            "month": m,
            "spend": round(spend, 2),
            "total_spend": round(total, 2),
            "excluded": round(max(total - spend, 0.0), 2),
            "income": round(income, 2),
            "savings": round(income - spend, 2),
        })

    cats = []
    if not base_rows.empty:
        for cat, avg in base_rows.mean().sort_values(ascending=False).items():
            if avg > 0.005:
                cats.append({"category": str(cat), "avg": round(float(avg), 2)})

    # Wie viel steckt in dem, was herausgerechnet wurde?
    sonder_avg = 0.0
    if exclude_sonderausgaben and "is_sonderausgabe" in df.columns:
        so = df[df["is_sonderausgabe"].astype(bool) & (df["amount"] < 0)].copy()
        if not so.empty:
            so["ym"] = so["date"].dt.to_period("M").astype(str)
            so = so[so["ym"].isin(window)]
            sonder_avg = float(so["amount"].abs().groupby(so["ym"]).sum().reindex(window).fillna(0.0).mean())

    avg_savings = avg_income - avg_spend
    return {
        "months": window,
        "n_months": len(window),
        "avg_spend": round(avg_spend, 2),
        "avg_spend_incl_all": round(avg_full, 2),
        "avg_income": round(avg_income, 2),
        "avg_savings": round(avg_savings, 2),
        "savings_rate": round(avg_savings / avg_income, 4) if avg_income > 0 else 0.0,
        "excluded_avg": round(max(avg_full - avg_spend, 0.0), 2),
        "sonderausgaben_avg": round(sonder_avg, 2),
        "excluded_categories": excl,
        "exclude_sonderausgaben": exclude_sonderausgaben,
        "per_month": per_month,
        "categories": cats,
    }
