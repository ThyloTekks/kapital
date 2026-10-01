from fastapi import APIRouter, Query
from ..deps import get_df

router = APIRouter()


@router.get("/forecast/defaults")
def get_forecast_defaults():
    """Return current savings stats to pre-populate sliders."""
    df = get_df()
    if df.empty:
        return {"avg_monthly_savings": 0, "avg_monthly_expenses": 0, "current_wealth": 0}

    # Eine Quelle für beide Zahlen. Vorher wurde hier der rohe Zahlungsstrom
    # summiert — ohne die hinterlegten Anfangssalden, also 14.850 € neben dem,
    # was die Übersicht anzeigte. Und `ersparnis` über 12 Monate enthält den
    # Erstattungsterm und jeden Urlaubsmonat; als Basis einer Hochrechnung über
    # Jahrzehnte taugt das nicht.
    from kapital.finance import networth as nw
    cap = nw.savings_capacity(df)
    cur = nw.current(df)

    return {
        "avg_monthly_savings": round(max(cap["monthly_savings"], 0), 2),
        "avg_monthly_expenses": round(max(cap["monthly_expenses"], 0), 2),
        "current_wealth": cur["total"],
        "wealth_breakdown": {
            "liquid": cur["liquid"], "broker_cash": cur["broker_cash"], "depot": cur["depot"],
        },
        "basis": {
            "months": cap["basis_months"],
            "window": cap["window"],
            "excluded_categories": cap["excluded_categories"],
            "excluded_avg": cap["excluded_avg"],
        },
    }


@router.get("/networth")
def get_networth():
    """Aktuelles Vermögen — die Zahl, auf die sich alle Seiten beziehen."""
    from kapital.finance import networth as nw
    return nw.current(get_df())


@router.get("/networth/history")
def get_networth_history(months: int = Query(36, ge=6, le=240)):
    """Vermögensverlauf je Monat, rückwärts vom heutigen kalibrierten Stand."""
    from kapital.finance import networth as nw
    df = get_df()
    h = nw.history(df, months=months)
    cur = nw.current(df)
    h["current"] = cur
    return h


@router.get("/darlehen")
def get_darlehen():
    """Offene Darlehen je Person — Forderungen, nicht Ausgaben."""
    from kapital.finance import networth as nw
    return nw.darlehen(get_df())
