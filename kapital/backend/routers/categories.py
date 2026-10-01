from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..deps import (get_df, categories_list, cat_meta,
                    account_options, filter_by_accounts)

router = APIRouter()


class CategoryCreate(BaseModel):
    name: str


@router.get("/categories")
def get_categories_with_stats(
    date_from: str = "",
    date_to: str = "",
    account: str = "all",
):
    import pandas as pd
    from kapital.finance.models import get_categories, load_custom_categories, _BASE_CATEGORIES
    full_df = get_df()
    all_accounts = account_options(full_df)
    cats = categories_list()

    df = full_df.copy()
    if date_from:
        df = df[df["date"] >= pd.Timestamp(date_from)]
    if date_to:
        df = df[df["date"] <= pd.Timestamp(date_to)]
    df = filter_by_accounts(df, account)

    # Netto-Ausgaben je Kategorie — dieselbe Definition wie in budgets.py und
    # im Dashboard. Vorher wurde hier abs(amount) über BEIDE Vorzeichen summiert
    # und Umbuchungen nicht ausgeschlossen: eine Erstattung erhöhte damit die
    # angezeigten Ausgaben, und dieselbe Kategorie zeigte auf zwei Seiten zwei
    # verschiedene Summen.
    spend: dict[str, float] = {}
    if not df.empty:
        real = df[~df["is_transfer"].fillna(False).astype(bool) & (df["category"] != "Umbuchung")]
        for cat, grp in real.groupby("category"):
            net = -float(grp["amount"].sum())
            spend[str(cat)] = round(max(net, 0.0), 2)

    # Transaction count per category
    counts: dict[str, int] = {}
    if not df.empty:
        for cat, grp in df.groupby("category"):
            counts[str(cat)] = int(len(grp))

    result = []
    for c in cats:
        result.append({
            **c,
            "spend": spend.get(c["id"], 0),
            "count": counts.get(c["id"], 0),
        })
    return {"categories": result, "all_accounts": all_accounts}


@router.post("/categories")
def create_category(body: CategoryCreate):
    from kapital.finance.models import (
        load_custom_categories, save_custom_categories, get_categories, _BASE_CATEGORIES
    )
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name darf nicht leer sein")
    all_cats = get_categories()
    if name in all_cats:
        raise HTTPException(409, f"Kategorie '{name}' existiert bereits")
    custom = load_custom_categories()
    custom.append(name)
    save_custom_categories(custom)
    return {"ok": True, "name": name, **cat_meta(name)}


@router.get("/categories/{name}/detail")
def get_category_detail(name: str, date_from: str = "", date_to: str = "", account: str = "all"):
    import pandas as pd
    full_df = get_df()
    if full_df.empty:
        return {"monthly": [], "top_payees": [], "avg_monthly": 0, "total": 0, "count": 0}

    df = full_df.copy()
    if date_from:
        df = df[df["date"] >= pd.Timestamp(date_from)]
    if date_to:
        df = df[df["date"] <= pd.Timestamp(date_to)]
    df = filter_by_accounts(df, account)

    cat_df = df[df["category"] == name].copy()
    if cat_df.empty:
        return {"monthly": [], "top_payees": [], "avg_monthly": 0, "total": 0, "count": 0}

    # Monthly trend
    cat_df["ym"] = cat_df["date"].dt.to_period("M")
    monthly = []
    for ym, grp in cat_df.groupby("ym"):
        monthly.append({
            "month": str(ym),
            "amount": round(max(-float(grp["amount"].sum()), 0.0), 2),
            "count": int(len(grp)),
        })
    monthly.sort(key=lambda x: x["month"])

    # Top payees (combine payee + description fallback)
    cat_df["_key"] = cat_df["payee"].fillna("").str.strip()
    cat_df.loc[cat_df["_key"] == "", "_key"] = cat_df["description"].fillna("").str.strip().str[:50]
    payee_stats = (
        cat_df[cat_df["_key"] != ""]
        .groupby("_key")
        .agg(total=("amount", lambda x: round(float(x.abs().sum()), 2)), count=("amount", "count"))
        .reset_index()
        .rename(columns={"_key": "payee"})
        .sort_values("total", ascending=False)
        .head(10)
    )
    top_payees = payee_stats.to_dict("records")

    total = round(float(cat_df["amount"].abs().sum()), 2)
    n_months = len(monthly)
    avg_monthly = round(total / n_months, 2) if n_months > 0 else 0

    return {
        "monthly": monthly,
        "top_payees": top_payees,
        "avg_monthly": avg_monthly,
        "total": total,
        "count": int(len(cat_df)),
    }


@router.delete("/categories/{name}")
def delete_category(name: str):
    from kapital.finance.models import (
        load_custom_categories, save_custom_categories, _BASE_CATEGORIES
    )
    if name in _BASE_CATEGORIES:
        raise HTTPException(400, "Eingebaut Kategorien können nicht gelöscht werden")
    custom = load_custom_categories()
    if name not in custom:
        raise HTTPException(404, "Kategorie nicht gefunden")
    custom = [c for c in custom if c != name]
    save_custom_categories(custom)
    return {"ok": True}


@router.get("/categories/timeseries")
def category_timeseries(
    cats: str = "",
    date_from: str = "",
    date_to: str = "",
    account: str = "all",
    avg_months: int = 6,
):
    """Monatsverlauf mehrerer Kategorien auf EINEM gemeinsamen Monatsraster.

    Warum ein eigener Endpunkt statt N Aufrufe von /detail: dort entstehen die
    Monate über groupby, Monate ohne Buchung fehlen also einfach. Die Charts
    ordnen die x-Achse nach Array-Index — überlagert man zwei Kategorien mit
    unterschiedlichen Lücken, steht der Januar der einen über dem April der
    anderen. Das Ergebnis sieht völlig plausibel aus und ist falsch.

    Zusätzlich kommt je Kategorie ein Referenzwert (Ø der letzten `avg_months`
    Monate) mit — die Frage lautet ja nicht "was war", sondern "ist das für mich
    normal".
    """
    import pandas as pd
    from kapital.finance import budgets

    wanted = [c.strip() for c in cats.split(",") if c.strip()]
    if not wanted:
        return {"months": [], "series": []}
    if len(wanted) > 8:
        raise HTTPException(400, "Höchstens 8 Kategorien gleichzeitig.")

    df = get_df()
    if df.empty:
        return {"months": [], "series": []}

    if date_from:
        df = df[df["date"] >= pd.Timestamp(date_from)]
    if date_to:
        df = df[df["date"] <= pd.Timestamp(date_to)]
    df = filter_by_accounts(df, account)
    if df.empty:
        return {"months": [], "series": []}

    mat = budgets.net_spend_matrix(df)
    if mat.empty:
        return {"months": [], "series": []}

    # Gemeinsames, lückenloses Monatsraster über den gesamten Zeitraum.
    months = pd.period_range(
        df["date"].min().to_period("M"), df["date"].max().to_period("M"), freq="M"
    ).astype(str).tolist()

    series = []
    for cat in wanted:
        col = mat[cat] if cat in mat.columns else pd.Series(dtype=float)
        values = [round(float(col.get(m, 0.0)), 2) for m in months]
        ref = [v for v in values[-avg_months:] if v > 0]
        series.append({
            "id": cat,
            "name": cat,
            "values": values,
            "reference": round(sum(ref) / len(ref), 2) if ref else 0.0,
            "total": round(sum(values), 2),
            **cat_meta(cat),
        })

    return {"months": months, "series": series, "avg_months": avg_months}
