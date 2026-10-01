from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from ..deps import get_df

router = APIRouter()

# Sparer-Pauschbetrag nach Jahr. Vorher stand hier fest 1.000 € — das gilt erst
# seit 2023. Für 2018–2022 waren es 801 €, die Steuerseite rechnete für fünf
# Jahrgänge mit dem falschen Freibetrag. Zusammenveranlagte haben den doppelten
# Betrag; das steht in settings.json ("steuer_zusammenveranlagt").
_SPARER_PAUSCHBETRAG = {
    2009: 801.0,    # 801 € seit der Abgeltungsteuer
    2023: 1000.0,   # Anhebung durch das Jahressteuergesetz 2022
}


def sparer_pauschbetrag(year: int, joint: bool = False) -> float:
    """Freibetrag für Kapitalerträge im jeweiligen Jahr."""
    base = 801.0
    for start in sorted(_SPARER_PAUSCHBETRAG):
        if year >= start:
            base = _SPARER_PAUSCHBETRAG[start]
    return base * (2 if joint else 1)


_TAX_KEYWORDS = [
    "dividend", "dividende", "zinsen", "zins", "saveback",
    "ausschüttung", "interest", "coupon", "distribution",
]


@router.get("/steuer")
def get_steuer(year: int = Query(0)):
    df = get_df()
    if df.empty:
        return {"years": [], "selected_year": year, "capital_income": 0,
                "tax_withheld": 0, "net_income": 0,
                "freibetrag": sparer_pauschbetrag(year or 0),
                "freibetrag_verbraucht": 0.0, "zusammenveranlagt": False,
                "fsa_used_pct": 0,
                "monthly": [], "capital_rows": [], "tax_rows": []}

    available_years = sorted(df["date"].dt.year.unique().tolist(), reverse=True)
    if not year or year not in available_years:
        year = available_years[0] if available_years else 2026

    _TAX_CATEGORIES = {"Einkommen", "Gebühren & Zinsen"}
    kw_pattern = "|".join(_TAX_KEYWORDS)

    cap_mask = (
        (df["amount"] > 0) &
        ~df["is_transfer"] &
        (
            df["description"].str.lower().str.contains(kw_pattern, na=False) |
            (
                df["category"].isin(_TAX_CATEGORIES) &
                ~df["description"].str.lower().str.contains(r"gehalt|lohn|salary|rente", na=False)
            )
        )
    )
    cap_df = df[cap_mask]

    tax_mask = (
        (df["amount"] < 0) &
        df["description"].str.lower().str.contains(
            r"steuer|tax|kapitalertrag|withhold|abgeltung", na=False
        )
    )
    tax_df = df[tax_mask]

    cap_yr = cap_df[cap_df["date"].dt.year == year]
    tax_yr = tax_df[tax_df["date"].dt.year == year]

    total_cap = float(cap_yr["amount"].sum())
    total_tax = float(tax_yr["amount"].abs().sum())
    net_cap = total_cap - total_tax
    from kapital.backend.app_settings import load_settings
    joint = bool(load_settings().get("steuer_zusammenveranlagt", False))
    fsa = sparer_pauschbetrag(year, joint)
    fsa_pct = min(total_cap / fsa, 1.0) * 100 if total_cap > 0 and fsa > 0 else 0

    # Monthly breakdown
    monthly = []
    if not cap_yr.empty:
        m_cap = (
            cap_yr.assign(m=cap_yr["date"].dt.to_period("M").astype(str))
            .groupby("m")["amount"].sum().to_dict()
        )
        m_tax = {}
        if not tax_yr.empty:
            m_tax = (
                tax_yr.assign(m=tax_yr["date"].dt.to_period("M").astype(str))
                .groupby("m")["amount"].apply(lambda s: s.abs().sum()).to_dict()
            )
        all_months = sorted(set(m_cap) | set(m_tax))
        for m in all_months:
            monthly.append({
                "month": m,
                "capital": round(float(m_cap.get(m, 0)), 2),
                "tax": round(float(m_tax.get(m, 0)), 2),
            })

    cap_rows = []
    for _, row in cap_yr.sort_values("date", ascending=False).iterrows():
        cap_rows.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "payee": str(row.get("payee", "")),
            "description": str(row.get("description", "")),
            "category": str(row.get("category", "")),
            "account": str(row.get("account_label", "")),
            "amount": round(float(row["amount"]), 4),
        })

    tax_rows = []
    for _, row in tax_yr.sort_values("date", ascending=False).iterrows():
        tax_rows.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "description": str(row.get("description", "")),
            "account": str(row.get("account_label", "")),
            "amount": round(float(row["amount"]), 4),
        })

    return {
        "years": available_years,
        "selected_year": year,
        "capital_income": round(total_cap, 4),
        "tax_withheld": round(total_tax, 4),
        "net_income": round(net_cap, 4),
        "fsa_used_pct": round(fsa_pct, 1),
        "freibetrag": fsa,
        "freibetrag_verbraucht": round(min(total_cap, fsa), 2),
        "zusammenveranlagt": joint,
        "monthly": monthly,
        "capital_rows": cap_rows,
        "tax_rows": tax_rows,
    }


# ── Nebentätigkeit ────────────────────────────────────────────────────────────

@router.get("/nebentaetigkeit")
def get_nebentaetigkeit(category: str = Query(""), jahr: int = Query(0)):
    """Einnahmen/Ausgaben einer Tätigkeit je Jahr, angelehnt an eine EÜR."""
    from kapital.finance import nebentaetigkeit as nt
    from kapital.backend.app_settings import load_settings

    df = get_df()
    cat = (category if isinstance(category, str) else "") or \
          load_settings().get("nebentaetigkeit_kategorie") or "Producing"
    jahr_i = jahr if isinstance(jahr, int) else 0
    data = nt.jahresuebersicht(df, cat)
    data["buchungen"] = nt.buchungen(df, cat, jahr_i or None)
    data["verfuegbare_kategorien"] = nt.available_categories(df)
    data["gewaehltes_jahr"] = jahr_i or None
    return data


class NebentaetigkeitConfig(BaseModel):
    category: str


@router.put("/nebentaetigkeit/config")
def set_nebentaetigkeit(body: NebentaetigkeitConfig):
    """Welche Kategorie als Nebentätigkeit ausgewertet wird."""
    from kapital.backend.app_settings import load_settings, save_settings
    s = load_settings()
    s["nebentaetigkeit_kategorie"] = body.category.strip()
    save_settings(s)
    return {"ok": True, "category": s["nebentaetigkeit_kategorie"]}


@router.get("/nebentaetigkeit/export")
def export_nebentaetigkeit(category: str = Query(""), jahr: int = Query(0)):
    """Buchungsliste als CSV — die Vorlage für den Steuerberater."""
    import io
    from kapital.finance import nebentaetigkeit as nt
    from kapital.backend.app_settings import load_settings

    cat = category or load_settings().get("nebentaetigkeit_kategorie") or "Producing"
    csv = nt.to_csv(get_df(), cat, jahr or None)
    name = f"{cat.lower().replace(' ', '-')}-{jahr or 'alle'}.csv"
    return StreamingResponse(
        iter([csv]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}"},
    )
