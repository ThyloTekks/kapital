from fastapi import APIRouter, Query
from ..deps import get_df

router = APIRouter()


@router.get("/fire/defaults")
def get_fire_defaults():
    df = get_df()
    if df.empty:
        return {"avg_monthly_expenses": 2000, "avg_monthly_savings": 500, "current_wealth": 0}

    # Dieselbe Quelle wie Übersicht und Prognose. current_wealth war hier
    # hartkodiert 0 — die App kennt die Zahl, hat sie aber den Nutzer tippen
    # lassen.
    from kapital.finance import networth as nw
    cap = nw.savings_capacity(df)
    cur = nw.current(df)

    return {
        "avg_monthly_expenses": round(max(cap["monthly_expenses"], 0), 2),
        "avg_monthly_savings": round(max(cap["monthly_savings"], 0), 2),
        "current_wealth": cur["total"],
        "wealth_breakdown": {
            "liquid": cur["liquid"], "broker_cash": cur["broker_cash"], "depot": cur["depot"],
        },
        "basis": {"months": cap["basis_months"], "window": cap["window"]},
    }


@router.get("/fire/compute")
def compute_fire(
    monthly_expenses: float = Query(2000),
    monthly_savings: float = Query(500),
    current_wealth: float = Query(0),
    annual_return: float = Query(7),
    inflation: float = Query(2),
    swr: float = Query(4),
):
    fire_number = (monthly_expenses * 12) / (swr / 100) if swr > 0 else 0
    real_return = (1 + annual_return / 100) / (1 + inflation / 100) - 1
    monthly_real = (1 + real_return) ** (1 / 12) - 1

    # Months to FIRE
    def months_to_fire(pv, pmt, r, target):
        if r <= 0:
            return int((target - pv) / pmt) if pmt > 0 else 99999
        if pv >= target:
            return 0
        n = 0
        current = pv
        while current < target and n < 1200:
            current = current * (1 + r) + pmt
            n += 1
        return n if current >= target else 99999

    months = months_to_fire(current_wealth, monthly_savings, monthly_real, fire_number)
    years = round(months / 12, 1) if months < 99999 else None

    # Wealth projection (annual, 40 years)
    projection = []
    wealth = current_wealth
    for y in range(41):
        projection.append({"year": y, "value": round(wealth, 2)})
        wealth = wealth * (1 + annual_return / 100) + monthly_savings * 12

    return {
        "fire_number": round(fire_number, 2),
        "months_to_fire": months if months < 99999 else None,
        "years_to_fire": years,
        "gap": round(max(0, fire_number - current_wealth), 2),
        "annual_expenses": round(monthly_expenses * 12, 2),
        "passive_income_at_fire": round(fire_number * swr / 100, 2),
        "projection": projection,
    }
