"""
Analytics module: savings rate, income/expense summaries, monthly/yearly trends.

All functions accept a normalized transactions DataFrame and return
DataFrames or scalars suitable for display in Streamlit.

Income definition: only transactions categorised as "Einkommen" (salary,
dividends, interest, state benefits).  Refunds / cashbacks are positive
non-Einkommen amounts and are treated as expense reductions, not income.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from .models import SAVINGS_CATEGORIES, NON_ECONOMIC_CATEGORIES


# ── Helpers ───────────────────────────────────────────────────────────────────

def _real_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Exclude inter-account transfers from economic analysis.
    Removes both is_transfer=True rows AND category='Umbuchung' rows so that
    undetected transfers (is_transfer still False) don't distort summaries.
    """
    return df[~df["is_transfer"] & ~df["category"].isin(NON_ECONOMIC_CATEGORIES)].copy()


def _income(df: pd.DataFrame) -> pd.DataFrame:
    """
    Real income only: positive transactions with category 'Einkommen'.
    Negative Einkommen entries (e.g. a custom rule applied to an outgoing
    payment) are not real income and must be excluded here — they are either
    misclassified expenses or undetected self-transfers.
    """
    r = _real_transactions(df)
    return r[(r["category"] == "Einkommen") & (r["amount"] > 0)]


def _own_names() -> set[str]:
    """Eigene Empfängernamen aus der Konfiguration (klein geschrieben)."""
    try:
        from .storage import load_own_payee_names
        return set(load_own_payee_names())
    except Exception:
        return set()


def _refunds(df: pd.DataFrame) -> pd.DataFrame:
    """
    Positive consumption refunds: insurance payouts, shop returns, cashbacks.
    Excludes Einkommen and SAVINGS_CATEGORIES so that investment proceeds
    (e.g. stock sale receipts) don't distort the living-cost calculation.
    """
    r = _real_transactions(df)
    excluded = {"Einkommen"} | SAVINGS_CATEGORIES
    out = r[(r["amount"] > 0) & ~r["category"].isin(excluded)]

    # Gutschriften an den Kontoinhaber selbst sind Eigenüberträge, die die
    # Umbuchungserkennung nicht gepaart hat — keine Erstattungen. Sie hier
    # mitzuzählen zieht sie von den Ausgaben ab und erzeugt Ersparnis aus dem
    # Nichts. Die Namen stehen in data/settings.json ("own_payee_names").
    own = _own_names()
    if own and not out.empty:
        payee = out["payee"].fillna("").str.strip().str.lower()
        out = out[~payee.isin(own)]
    return out


def _expenses(df: pd.DataFrame) -> pd.DataFrame:
    """Consumption outflows only — excludes transfers, income, and savings/investment categories.

    SAVINGS_CATEGORIES (Investment & Sparen, Vermögensaufbau) are tracked
    separately via _investments() so they don't inflate the 'Ausgaben' metric
    and don't need to be subtracted again in the lebenshaltung formula.
    """
    r = _real_transactions(df)
    excluded = NON_ECONOMIC_CATEGORIES | {"Einkommen"} | SAVINGS_CATEGORIES
    return r[(r["amount"] < 0) & ~r["category"].isin(excluded)]


def _investments(df: pd.DataFrame) -> pd.DataFrame:
    r = _real_transactions(df)
    return r[r["category"].isin(SAVINGS_CATEGORIES)]


# ── Summary for a given period ────────────────────────────────────────────────

def period_summary(df: pd.DataFrame) -> dict:
    """
    Returns a dict with:
      total_income        – Einkommen category only (salary, dividends, etc.)
      total_expenses      – pure consumption outflows (excludes investments)
      total_refunds       – positive non-Einkommen flows (refunds, cashbacks)
      total_invested      – investment outflows (absolute)
      net_cashflow        – income + refunds – expenses – investments
      savings             – income – net_spending, where net_spending = expenses – refunds
      savings_rate        – savings / income
      n_transactions
    """
    inc     = _income(df)["amount"].sum()
    refunds = _refunds(df)["amount"].sum()
    exp     = abs(_expenses(df)["amount"].sum())
    inv     = abs(_investments(df)[_investments(df)["amount"] < 0]["amount"].sum())

    # net_spending can be negative when refunds exceed consumption (e.g. big insurance payout)
    net_spending = exp - refunds
    savings      = inc - net_spending
    savings_rate = max(-1.0, savings / inc) if inc > 0 else 0.0

    return {
        "total_income":    inc,
        "total_expenses":  exp,
        "total_refunds":   refunds,
        "total_invested":  inv,
        "net_cashflow":    inc + refunds - exp - inv,
        "savings":         savings,
        "savings_rate":    savings_rate,
        "n_transactions":  len(df),
    }


# ── Monthly breakdown ─────────────────────────────────────────────────────────

def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by year-month with columns:
      einnahmen, erstattungen, ausgaben, investiert,
      lebenshaltung, ersparnis, sparrate
    """
    r = _real_transactions(df).copy()
    r["ym"] = r["date"].dt.to_period("M")

    income_m = (
        r[(r["category"] == "Einkommen") & (r["amount"] > 0)]
        .groupby("ym")["amount"].sum()
        .rename("einnahmen")
    )
    _excl_ref_m = {"Einkommen"} | SAVINGS_CATEGORIES
    # Dieselbe Ausnahme wie in _refunds(): sonst rechnet das Diagramm mit einem
    # anderen Erstattungsbegriff als die Kennzahl darüber — genau der
    # Widerspruch, der die Sparrate unerklärlich gemacht hat.
    _own = _own_names()
    _ref_rows = r[(r["amount"] > 0) & ~r["category"].isin(_excl_ref_m)]
    if _own and not _ref_rows.empty:
        _ref_rows = _ref_rows[~_ref_rows["payee"].fillna("").str.strip().str.lower().isin(_own)]
    refunds_m = (
        _ref_rows.groupby("ym")["amount"].sum().rename("erstattungen")
    )
    _excl_m = NON_ECONOMIC_CATEGORIES | {"Einkommen"} | SAVINGS_CATEGORIES
    expense_m = (
        r[(r["amount"] < 0) & ~r["category"].isin(_excl_m)]
        .groupby("ym")["amount"].sum()
        .abs()
        .rename("ausgaben")
    )
    invest_m = (
        r[r["category"].isin(SAVINGS_CATEGORIES) & (r["amount"] < 0)]
        .groupby("ym")["amount"].sum()
        .abs()
        .rename("investiert")
    )

    summary = pd.concat([income_m, refunds_m, expense_m, invest_m], axis=1).fillna(0)
    # net_spending can go negative when refunds exceed consumption
    _net_spending_m = summary["ausgaben"] - summary["erstattungen"]
    summary["lebenshaltung"] = _net_spending_m.clip(lower=0)
    summary["ersparnis"] = summary["einnahmen"] - _net_spending_m
    summary["sparrate"]  = (
        summary["ersparnis"] / summary["einnahmen"].replace(0, np.nan)
    ).fillna(0).clip(lower=-1)

    return summary.reset_index()


# ── Yearly breakdown ──────────────────────────────────────────────────────────

def yearly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Same as monthly but grouped by year."""
    r = _real_transactions(df).copy()
    r["year"] = r["date"].dt.year

    income_y = (
        r[(r["category"] == "Einkommen") & (r["amount"] > 0)]
        .groupby("year")["amount"].sum()
        .rename("einnahmen")
    )
    _excl_ref_y = {"Einkommen"} | SAVINGS_CATEGORIES
    refunds_y = (
        r[(r["amount"] > 0) & ~r["category"].isin(_excl_ref_y)]
        .groupby("year")["amount"].sum()
        .rename("erstattungen")
    )
    _excl_y = {"Umbuchung", "Einkommen"} | SAVINGS_CATEGORIES
    expense_y = (
        r[(r["amount"] < 0) & ~r["category"].isin(_excl_y)]
        .groupby("year")["amount"].sum()
        .abs()
        .rename("ausgaben")
    )
    invest_y = (
        r[r["category"].isin(SAVINGS_CATEGORIES) & (r["amount"] < 0)]
        .groupby("year")["amount"].sum()
        .abs()
        .rename("investiert")
    )

    summary = pd.concat([income_y, refunds_y, expense_y, invest_y], axis=1).fillna(0)
    _net_spending_y = summary["ausgaben"] - summary["erstattungen"]
    summary["lebenshaltung"] = _net_spending_y.clip(lower=0)
    summary["ersparnis"] = summary["einnahmen"] - _net_spending_y
    summary["sparrate"]  = (
        summary["ersparnis"] / summary["einnahmen"].replace(0, np.nan)
    ).fillna(0).clip(lower=-1)

    return summary.reset_index()


# ── Category breakdown ────────────────────────────────────────────────────────

def category_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Total expenses by category (absolute values, sorted descending)."""
    r = _expenses(df)
    result = (
        r.groupby("category")["amount"].sum().abs()
        .reset_index()
        .rename(columns={"amount": "betrag"})
        .sort_values("betrag", ascending=False)
    )
    return result


def top_payees(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Top N payees by total spending."""
    r = _expenses(df)
    r = r[r["payee"].str.strip() != ""]
    result = (
        r.groupby("payee")["amount"].sum().abs()
        .reset_index()
        .rename(columns={"amount": "betrag"})
        .sort_values("betrag", ascending=False)
        .head(n)
    )
    return result


# ── Savings projection ────────────────────────────────────────────────────────

def savings_projection(yearly: pd.DataFrame, years_ahead: int = 5) -> pd.DataFrame:
    """
    Simple linear projection of savings based on the average yearly savings.
    Returns a DataFrame with year and projected_cumulative_savings.
    """
    if yearly.empty:
        return pd.DataFrame()

    avg_annual_savings = yearly["ersparnis"].mean()
    last_year = int(yearly["year"].max())
    current_cumulative = yearly["ersparnis"].sum()

    rows = []
    for i in range(1, years_ahead + 1):
        rows.append({
            "jahr": last_year + i,
            "prognostiziertes_jahresersparnis": avg_annual_savings,
            "kumuliertes_ersparnis": current_cumulative + avg_annual_savings * i,
        })
    return pd.DataFrame(rows)
