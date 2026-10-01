import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from ..deps import (get_df, categories_list, cat_meta, df_to_records,
                    account_options, filter_by_accounts)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
from kapital.finance import analytics, storage
from kapital.finance.models import SAVINGS_CATEGORIES
from kapital.finance.storage import load_iban_labels, load_giro_balances

router = APIRouter()


def _parse_date(value: str, field: str):
    """Datum aus der Query lesen — mit klarer 400 statt Traceback.

    Vorher ging der Rohstring direkt in pd.Timestamp; ein ungültiges Datum
    (etwa aus einem alten Lesezeichen) endete in einem 500er, der 800 Zeichen
    Traceback samt Dateipfaden an den Browser zurückgab.
    """
    import pandas as pd
    if not value or not isinstance(value, str):
        return None
    if not _DATE_RE.match(value):
        raise HTTPException(400, f"{field} muss das Format JJJJ-MM-TT haben (bekommen: {value!r})")
    try:
        return pd.Timestamp(value)
    except Exception:
        raise HTTPException(400, f"{field} ist kein gültiges Datum: {value!r}")


# Wie viele Einzelbuchungen unter "Top Ausgaben" stehen. Eine Top-Liste, die
# man scrollen muss, beantwortet die Frage "was war ungewöhnlich" nicht mehr.
TOP_EXPENSES_N = 10


def _apply_filters(df, date_from: str, date_to: str, account: str):
    ts_from, ts_to = _parse_date(date_from, "date_from"), _parse_date(date_to, "date_to")
    if ts_from is not None and ts_to is not None and ts_from > ts_to:
        ts_from, ts_to = ts_to, ts_from   # vertauschte Eingabe still korrigieren
    if ts_from is not None:
        df = df[df["date"] >= ts_from]
    if ts_to is not None:
        df = df[df["date"] <= ts_to]
    # Mehrfachauswahl: "Giro,Trade Republic". "" und "all" heissen: kein Filter.
    return filter_by_accounts(df, account)


@router.get("/dashboard")
def get_dashboard(
    date_from: str = Query(""),
    date_to: str = Query(""),
    account: str = Query("all"),
    exclude_sonderausgaben: bool = Query(False),
):
    full_df = get_df()
    cats = {c["id"]: c for c in categories_list()}

    # All accounts for the filter dropdown (from full dataset)
    all_accounts = account_options(full_df)

    # df_base: nur datums-/kontogefiltert (Basis für Kontosalden).
    # df: zusätzlich sonderausgaben-gefiltert (Basis für Cashflow-Analysen).
    df_base = _apply_filters(full_df, date_from, date_to, account)
    df = df_base
    if exclude_sonderausgaben and "is_sonderausgabe" in df_base.columns:
        df = df_base[~df_base["is_sonderausgabe"].astype(bool)]

    if df_base.empty:
        return {
            "summary": {"total_income": 0, "total_expenses": 0, "total_refunds": 0,
                        "total_invested": 0, "net_cashflow": 0, "savings": 0,
                        "savings_rate": 0, "n_transactions": 0},
            "accounts": [], "top_categories": [], "top_expenses": [],
            "top_expenses_hidden": 0, "top_expenses_excluded": [],
            "recent_transactions": [],
            "weekly_cashflow": [], "monthly_cashflow": [],
            "all_accounts": all_accounts, "warnings": [],
            "empty_reason": "no_rows_in_range",
        }

    # ── Konten ────────────────────────────────────────────────────────────────
    # Drei Korrekturen gegenüber vorher:
    #  1. Der Saldo wird über die GESAMTE Historie gebildet, nie über den
    #     Datumsfilter. Ein Kontostand, der sich beim Umschalten auf "30 Tage"
    #     ändert, ist kein Kontostand.
    #  2. Dieselbe IBAN mit und ohne Leerzeichen ist EIN Konto. Vorher wurden
    #     daraus zwei Zeilen mit geteiltem Saldo.
    #  3. iban_labels.json wurde geladen und weggeworfen. Jetzt liefert es den
    #     Anzeigenamen, und giro_balances.json den kalibrierten Anfangssaldo —
    #     beides war gespeichert und wurde nie gelesen.
    from kapital.finance import networth as nw
    acc_rows = nw.account_balances(full_df)
    warnings: list[str] = []
    for a in acc_rows:
        if len(a["raw_labels"]) > 1:
            warnings.append(
                f"{a['name']} lag unter {len(a['raw_labels'])} verschiedenen "
                f"Kontobezeichnungen im Bestand und wird jetzt als ein Konto gezeigt."
            )
    if any(not a["calibrated"] for a in acc_rows):
        warnings.append(
            "Für Konten ohne hinterlegten Kontostand wird der kumulierte "
            "Zahlungsstrom seit Importbeginn gezeigt — das ist kein echter Saldo."
        )

    # Cashflow-Analysen aus df (sonderausgaben-gefiltert). df kann leer sein,
    # wenn der Filter im gewählten Zeitraum alles entfernt.
    if df.empty:
        import pandas as pd
        summary = {"total_income": 0, "total_expenses": 0, "total_refunds": 0,
                   "total_invested": 0, "net_cashflow": 0, "savings": 0,
                   "savings_rate": 0, "n_transactions": 0}
        monthly = pd.DataFrame(columns=["ym", "einnahmen", "ausgaben", "ersparnis"])
    else:
        summary = analytics.period_summary(df)
        monthly = analytics.monthly_summary(df)

    # Top categories (expenses, no transfers)
    cat_spend: dict[str, float] = {}
    exp = df[(df["amount"] < 0) & ~df["is_transfer"]].copy()
    for _, row in exp.iterrows():
        cat = row["category"]
        if cat != "Umbuchung":
            cat_spend[cat] = cat_spend.get(cat, 0) + abs(float(row["amount"]))
    top_cats = sorted(cat_spend.items(), key=lambda x: x[1], reverse=True)[:8]
    top_categories = [
        {"id": k, "name": k, "value": round(v, 2), **cats.get(k, cat_meta(k))}
        for k, v in top_cats
    ]

    # Top-Ausgaben als EINZELNE Buchungen. Andere Frage als die Kategorie-
    # Summen darüber: nicht "wo geht mein Geld hin", sondern "was war
    # ungewöhnlich". Deshalb sind vorhersehbare Posten ausblendbar — konfiguriert
    # in settings.json statt hart verdrahtet, weil Kategorien umbenennbar sind.
    from kapital.backend.app_settings import load_settings
    _excluded = load_settings().get("top_expenses_excluded_categories") or ["Wohnen & Nebenkosten"]
    _excl_norm = {str(c).strip().lower() for c in _excluded}
    single = exp[
        (exp["category"] != "Umbuchung")
        & (~exp["category"].isin(SAVINGS_CATEGORIES))
        & (exp["category"] != "Einkommen")
    ].copy()
    hidden_by_category = int(single["category"].str.strip().str.lower().isin(_excl_norm).sum())
    single = single[~single["category"].str.strip().str.lower().isin(_excl_norm)]
    single = single.assign(_abs=single["amount"].abs()).nlargest(TOP_EXPENSES_N, "_abs")
    top_expenses = [
        {
            "id": str(r["tx_hash"]),
            "date": r["date"].strftime("%Y-%m-%d"),
            "payee": (str(r.get("payee", "") or "").strip()
                      or str(r.get("description", "") or "")[:50] or "—"),
            "description": str(r.get("description", "") or "")[:120],
            "amount": round(float(r["amount"]), 2),
            "category": str(r.get("category", "Sonstiges")),
            "account": str(r.get("account_label", "")),
            "is_sonderausgabe": bool(r.get("is_sonderausgabe", False)),
            **cats.get(str(r.get("category", "")), cat_meta(str(r.get("category", "")))),
        }
        for _, r in single.iterrows()
    ]

    # Recent transactions (last 10)
    recent_df = df.sort_values("date", ascending=False).head(10)
    recent = []
    for _, row in recent_df.iterrows():
        cat_id = str(row.get("category", "Sonstiges"))
        recent.append({
            "id": str(row["tx_hash"]),
            "date": row["date"].strftime("%Y-%m-%d"),
            "payee": str(row.get("payee", "")),
            "description": str(row.get("description", "")),
            "category": cat_id,
            "amount": round(float(row["amount"]), 2),
            "account": str(row.get("account_label", "")),
            "is_transfer": bool(row.get("is_transfer", False)),
        })

    # Weekly cashflow (last 8 ISO weeks)
    import pandas as pd
    df2 = df.copy()
    _iso = df2["date"].dt.isocalendar()
    df2["week"] = _iso.week
    df2["year"] = _iso.year  # ISO-Jahr, sonst falsche Labels am Jahreswechsel
    df2["yw"] = df2["year"].astype(str) + "-KW" + df2["week"].astype(str).str.zfill(2)
    # Dieselbe Definition wie im Monatschart. Vorher waren es rohe Summen mit
    # Vorzeichen — dort steckten Investitionen und Erstattungen drin, im
    # Monatschart nicht. Beim Umschalten Woche/Monat änderte sich also
    # unsichtbar die Bedeutung des Diagramms.
    _wk = df2[~df2["is_transfer"] & (df2["category"] != "Umbuchung")]
    _excl_out = {"Umbuchung", "Einkommen"} | set(SAVINGS_CATEGORIES)
    _excl_ref = {"Einkommen"} | set(SAVINGS_CATEGORIES)
    weekly = _wk.groupby("yw").apply(
        lambda g: pd.Series({
            "income":  g[(g["category"] == "Einkommen") & (g["amount"] > 0)]["amount"].sum(),
            "expense": abs(g[(g["amount"] < 0) & (~g["category"].isin(_excl_out))]["amount"].sum()),
            "refunds": g[(g["amount"] > 0) & (~g["category"].isin(_excl_ref))]["amount"].sum(),
        }),
        include_groups=False,
    ).reset_index().tail(8)
    weekly_cashflow = [
        {
            "label": r["yw"].split("-")[1],
            "in": round(float(r["income"]), 2),
            "out": round(float(r["expense"]), 2),
            "refunds": round(float(r["refunds"]), 2),
            # Überschuss = Einnahmen − (Ausgaben − Erstattungen). Ohne den
            # Erstattungsterm kann die Sparrate nie zum Diagramm passen.
            "savings": round(float(r["income"] - (r["expense"] - r["refunds"])), 2),
        }
        for _, r in weekly.iterrows()
    ]

    # Monthly cashflow (last 24 months)
    monthly_cf = monthly.tail(24)
    monthly_cashflow = [
        {
            "label": str(r["ym"]),
            "in": round(float(r["einnahmen"]), 2),
            "out": round(float(r["ausgaben"]), 2),
            "refunds": round(float(r.get("erstattungen", 0) or 0), 2),
            "savings": round(float(r["ersparnis"]), 2),
        }
        for _, r in monthly_cf.iterrows()
    ]

    return {
        "warnings": warnings,
        "summary": {k: round(float(v), 2) if isinstance(v, float) else v for k, v in summary.items()},
        "accounts": acc_rows,
        "top_categories": top_categories,
        "top_expenses": top_expenses,
        "top_expenses_hidden": hidden_by_category,
        "top_expenses_excluded": _excluded,
        "recent_transactions": recent,
        "weekly_cashflow": weekly_cashflow,
        "monthly_cashflow": monthly_cashflow,
        "all_accounts": all_accounts,
    }


@router.get("/baseline")
def get_baseline(
    months: int = Query(6, ge=1, le=24),
    exclude_categories: str = Query("", description="Komma-Liste; leer = Voreinstellung"),
    exclude_sonderausgaben: bool = Query(True),
):
    """Grundlast: was ein normaler Monat kostet, ohne Einmaliges.

    Beantwortet 'wie viel könnte ich monatlich sparen', ohne dass ein einzelner
    Urlaub die Antwort um Tausende verschiebt.
    """
    from kapital.finance import budgets
    from kapital.backend.app_settings import load_settings, save_settings

    settings = load_settings()
    if exclude_categories:
        cats = [c.strip() for c in exclude_categories.split(",") if c.strip()]
    else:
        cats = settings.get("baseline_excluded_categories")
        if cats is None:
            cats = list(budgets.DEFAULT_BASELINE_EXCLUDED)

    result = budgets.baseline(
        get_df(),
        months=months,
        exclude_categories=cats,
        exclude_sonderausgaben=exclude_sonderausgaben,
    )
    result["all_categories"] = [c["id"] for c in categories_list()]
    return result


class BaselineConfigBody(BaseModel):
    exclude_categories: list[str] | None = None
    months: int | None = None


@router.put("/baseline/config")
def set_baseline_config(body: BaselineConfigBody):
    """Voreinstellung merken, damit die Auswahl den Seitenwechsel überlebt."""
    from kapital.backend.app_settings import load_settings, save_settings

    s = load_settings()
    if body.exclude_categories is not None:
        s["baseline_excluded_categories"] = [
            str(c).strip() for c in body.exclude_categories if str(c).strip()
        ]
    if body.months is not None:
        s["baseline_months"] = max(1, min(24, int(body.months)))
    save_settings(s)
    return {
        "ok": True,
        "exclude_categories": s.get("baseline_excluded_categories", []),
        "months": s.get("baseline_months", 6),
    }
