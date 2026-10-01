from fastapi import APIRouter, Query
from ..deps import get_df, df_to_records

router = APIRouter()


@router.get("/jahresuebersicht")
def get_jahresuebersicht(account: str = Query("all")):
    from kapital.finance import analytics
    full_df = get_df()
    from ..deps import account_options, filter_by_accounts
    all_accounts = account_options(full_df)
    df = filter_by_accounts(full_df, account)
    if df.empty:
        return {"years": [], "monthly": [], "all_accounts": all_accounts}

    yearly = analytics.yearly_summary(df)
    monthly = analytics.monthly_summary(df)

    years_data = []
    for _, row in yearly.iterrows():
        years_data.append({
            "year": int(row["year"]),
            "einnahmen": round(float(row.get("einnahmen", 0)), 2),
            "ausgaben":  round(float(row.get("ausgaben", 0)), 2),
            "investiert": round(float(row.get("investiert", 0)), 2),
            "ersparnis":  round(float(row.get("ersparnis", 0)), 2),
            "sparrate":   round(float(row.get("sparrate", 0)) * 100, 1),
        })

    monthly_data = []
    for _, row in monthly.iterrows():
        monthly_data.append({
            "ym": str(row["ym"]),
            "einnahmen": round(float(row.get("einnahmen", 0)), 2),
            "ausgaben":  round(float(row.get("ausgaben", 0)), 2),
            "investiert": round(float(row.get("investiert", 0)), 2),
            "ersparnis":  round(float(row.get("ersparnis", 0)), 2),
            "sparrate":   round(float(row.get("sparrate", 0)) * 100, 1),
        })

    # Category breakdown
    cat_df = analytics.category_breakdown(df)
    cat_data = []
    for _, row in cat_df.iterrows():
        cat_data.append({
            "category": str(row["category"]),
            "total": round(float(row.get("total", 0)), 2),
        })

    return {"years": years_data, "monthly": monthly_data, "categories": cat_data, "all_accounts": all_accounts}
