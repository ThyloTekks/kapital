"""
Portfolio analysis module.

Reconstructs current holdings from all buy/sell transactions that have
ISIN + units data (populated by the PDF parser).

Workflow:
  positions = reconstruct_positions(df)   # current holdings
  prices    = fetch_prices(isins)         # optional: current market prices
  summary   = enrich_with_prices(positions, prices)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from .models import SAVINGS_CATEGORIES


# ── XIRR (pure Python, no scipy dependency) ───────────────────────────────────

def _xirr(cash_flows: list[tuple], guess: float = 0.1) -> Optional[float]:
    """
    Compute XIRR given a list of (date, amount) tuples.
    Negative = outflows (buys), Positive = inflows (sells, dividends, current value).
    Returns annualised rate or None if no convergence.
    """
    if not cash_flows or len(cash_flows) < 2:
        return None

    dates   = [cf[0] for cf in cash_flows]
    amounts = [cf[1] for cf in cash_flows]

    if all(a <= 0 for a in amounts) or all(a >= 0 for a in amounts):
        return None

    min_date = min(dates)
    years = [(d - min_date).days / 365.25 for d in dates]

    def _npv(rate: float) -> float:
        if rate <= -1:
            return float("inf")
        return sum(a / (1.0 + rate) ** t for a, t in zip(amounts, years))

    def _npv_d(rate: float) -> float:
        if rate <= -1:
            return float("inf")
        return sum(-t * a / (1.0 + rate) ** (t + 1) for a, t in zip(amounts, years))

    rate = guess
    for _ in range(200):
        f      = _npv(rate)
        f_d    = _npv_d(rate)
        if abs(f_d) < 1e-14:
            break
        rate_n = rate - f / f_d
        if abs(rate_n - rate) < 1e-9:
            rate = rate_n
            break
        rate = rate_n
        if rate <= -1:
            return None

    # Accept only if converged
    if abs(_npv(rate)) > 1.0 or not (-1 < rate < 100):
        return None
    return rate


def compute_position_xirr(
    df: pd.DataFrame,
    isin: str,
    current_value: Optional[float] = None,
) -> Optional[float]:
    """
    XIRR for a single position.
    Buys are outflows (negative amount in df → positive cost), sells are inflows.
    If position is still open, add current_value as a terminal inflow today.
    """
    pos = df[
        (df["account"] == "Trade Republic") &
        (df["isin"] == isin) &
        (df["units"].fillna(0) != 0)
    ].copy()

    if pos.empty:
        return None

    cash_flows = []
    for _, row in pos.iterrows():
        d = row["date"]
        if hasattr(d, "date"):
            d = d.date()
        # amount is already in NPV sign convention: negative=outflow (buy), positive=inflow (sell)
        cash_flows.append((d, float(row["amount"])))

    if current_value and current_value > 0:
        import datetime
        cash_flows.append((datetime.date.today(), float(current_value)))

    return _xirr(cash_flows)

_DATA_DIR    = Path(__file__).parent.parent.parent / "data"
_TICKER_PATH = _DATA_DIR / "isin_tickers.json"   # user-saved ISIN→ticker map

# ── Common ISIN → yfinance ticker map (pre-seeded for popular ETFs) ────────────
_KNOWN_TICKERS: dict[str, str] = {
    # World / Global ETFs
    "IE00B4L5Y983": "IWDA.AS",      # iShares Core MSCI World
    "IE00B3RBWM25": "VWRL.AS",      # Vanguard FTSE All-World
    "IE00B0M62Q58": "IWRD.L",       # iShares MSCI World (older)
    "LU0274208692": "XDWD.DE",      # Xtrackers MSCI World
    "LU0392494562": "DBXW.DE",      # Xtrackers MSCI World Swap
    "IE00BK5BQT80": "VWCE.DE",      # Vanguard FTSE All-World Acc
    "IE00BD4TXV59": "VHVE.AS",      # Vanguard FTSE Developed World
    # Emerging Markets
    "IE00B4L5YC18": "EIMI.AS",      # iShares Core MSCI EM IMI
    "LU0635178014": "XMME.DE",      # Xtrackers MSCI Emerging Markets
    # S&P 500
    "IE00B5BMR087": "SXR8.DE",      # iShares Core S&P 500
    "IE00B3XXRP09": "XSPX.DE",      # Xtrackers S&P 500
    "LU1681048804": "CSP1.L",       # iShares Core S&P 500 (LU)
    # Europe
    "LU0908500753": "XESC.DE",      # Xtrackers Euro Stoxx 50
    "IE00B53HP851": "IMAE.AS",      # iShares MSCI Europe
    # Bonds
    "IE00B4WXJJ64": "IGLO.AS",      # iShares Global Govt Bond
    "LU0290358497": "DBZB.DE",      # Xtrackers Euro Govt Bond
    # Germany
    "DE0005140008": "DBK.DE",       # Deutsche Bank
    "DE000BASF111": "BAS.DE",       # BASF
    "DE0007236101": "SIE.DE",       # Siemens
    "DE0008404005": "ALV.DE",       # Allianz
    "DE0005151005": "BMW.DE",       # BMW
    # US Tech
    "US0231351067": "AMZN",         # Amazon
    "US5949181045": "MSFT",         # Microsoft
    "US02079K3059": "GOOGL",        # Alphabet
    "US0378331005": "AAPL",         # Apple
    "US67066G1040": "NVDA",         # Nvidia
}


def load_ticker_map() -> dict[str, str]:
    m = dict(_KNOWN_TICKERS)
    if _TICKER_PATH.exists():
        try:
            m.update(json.loads(_TICKER_PATH.read_text()))
        except Exception:
            pass
    return m


def save_ticker_map(mapping: dict[str, str]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _TICKER_PATH.write_text(json.dumps(mapping, indent=2, ensure_ascii=False))


# ── ETF detection ─────────────────────────────────────────────────────────────

_ETF_NAME_KEYWORDS = [
    "etf", "ucits", "index fund", "tracker fund",
    "ishares", "i shares", "vanguard", "xtrackers", "amundi", "lyxor",
    "spdr", "invesco", "wisdomtree", "vaneck", "dws invest", "hsbc etf",
    "msci world", "msci em", "msci emerging", "msci europe", "msci usa",
    "ftse all", "ftse 100", "ftse 250", "s&p 500", "s&p500",
    "stoxx", "euro stoxx", "nasdaq 100", "nasdaq100", "russell 2000",
    "global aggregate", "govt bond", "corporate bond",
]

_ETF_ISIN_PREFIXES = ("IE", "LU")  # Ireland & Luxembourg → almost exclusively UCITS ETFs


def _is_etf(isin: str, name: str) -> bool:
    """Heuristic: True if the position is likely an ETF rather than a stock."""
    n = (name or "").lower()
    for kw in _ETF_NAME_KEYWORDS:
        if kw in n:
            return True
    # IE/LU-domiciled AND has any fund-like term in the name
    if isin and isin[:2] in _ETF_ISIN_PREFIXES:
        for kw in ("etf", "ucits", "index", "msci", "ftse", "stoxx", "s&p",
                   "nasdaq", "ishares", "vanguard", "xtrackers", "amundi",
                   "lyxor", "spdr", "invesco", "fund", "tracker"):
            if kw in n:
                return True
    return False


import re as _re_mod
# Beschreibungen, die eine Kapitalmaßnahme kennzeichnen (Stückzahl == 0).
_CORP_ACTION_RE = _re_mod.compile(
    r"EXCHANGE|CORPORATE[_ ]?ACTION|DELIST|MERGER|SPLIT", _re_mod.IGNORECASE
)

_SUCCESSION_PATH = _DATA_DIR / "isin_succession.json"


def load_isin_succession() -> dict[str, str]:
    """Alte ISIN → neue ISIN bei Kapitalmaßnahmen.

    Ein Reverse Split oder eine Umfirmierung vergibt eine neue ISIN. Ohne diese
    Zuordnung ist dieselbe Position für die Auswertung zwei Positionen: der Kauf
    steht unter der alten ISIN (und gilt ewig als gehalten), der Verkauf oder
    der Depotauszug unter der neuen.
    """
    if not _SUCCESSION_PATH.exists():
        return {}
    try:
        raw = json.loads(_SUCCESSION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {k: v for k, v in raw.items() if not str(k).startswith("_") and isinstance(v, str)}


def resolve_isin(isin: str, succession: Optional[dict] = None) -> str:
    """ISIN auf ihren aktuellen Nachfolger auflösen (transitiv, zyklensicher)."""
    if succession is None:
        succession = load_isin_succession()
    seen = set()
    cur = str(isin or "")
    while cur in succession and cur not in seen:
        seen.add(cur)
        cur = succession[cur]
    return cur

# ── Reconstruct holdings ──────────────────────────────────────────────────────

def reconstruct_positions(df: pd.DataFrame) -> pd.DataFrame:
    """
    From all transactions with ISIN + units data, compute current holdings.

    Returns (active, sold) tuple of DataFrames:
      isin, name, units_held, total_invested, avg_buy_price,
      total_sold, n_buys, n_sells, realized_gain
    """
    # Kapitalmaßnahmen (Übernahme, Delisting, Umtausch) haben units == 0, weil
    # keine Stückzahl gehandelt wird — nur Geld fließt. Sie hier mit
    # `units != 0` wegzufiltern hiess: die Position bleibt für immer "gehalten",
    # der realisierte Gewinn wird nie gebucht und der Einstand steckt weiter im
    # investierten Kapital. Genau so überlebten Alteryx und TUI im Depot.
    tr_all = df[
        (df["account"] == "Trade Republic") &
        (df["isin"].fillna("") != "")
    ].copy()

    if tr_all.empty:
        return pd.DataFrame(), pd.DataFrame()

    _desc_all = tr_all["description"].fillna("")
    _is_corp = _desc_all.str.contains(
        r"EXCHANGE|CORPORATE[_ ]?ACTION|DELIST|MERGER|SPLIT", case=False, na=False, regex=True
    )
    tr = tr_all[(tr_all["units"].fillna(0) != 0) | _is_corp].copy()

    if tr.empty:
        return pd.DataFrame(), pd.DataFrame()

    # ISIN-Nachfolge auflösen, BEVOR gruppiert wird: sonst zählt ein Reverse
    # Split als zwei getrennte Positionen (Kauf unter alter ISIN, Verkauf unter
    # neuer) und die alte bleibt für immer als Geisterbestand stehen.
    _succ = load_isin_succession()
    if _succ:
        tr["isin"] = tr["isin"].map(lambda i: resolve_isin(str(i), _succ))

    tr["units"]         = pd.to_numeric(tr["units"],         errors="coerce").fillna(0)
    tr["price_per_unit"] = pd.to_numeric(tr["price_per_unit"], errors="coerce").fillna(0)
    tr["amount"]        = pd.to_numeric(tr["amount"],         errors="coerce").fillna(0)

    positions = []
    for isin, grp in tr.groupby("isin"):
        grp = grp.sort_values("date")
        buys  = grp[grp["units"] > 0]
        sells = grp[grp["units"] < 0]

        total_invested = buys["amount"].abs().sum()
        total_proceeds = sells["amount"].abs().sum()

        # Laufender Cost-Basis-Pool (gleitendes Mittel): liefert korrekten
        # realisierten Gewinn auch bei Nachkäufen nach einem Verkauf, statt
        # rückwirkend den Durchschnitt aller Käufe zu verwenden.
        pool_units = 0.0
        pool_cost  = 0.0
        realized_gain = 0.0
        closed_by_corp_action = False
        last_sell = pd.NaT
        for _, r in grp.iterrows():
            u   = float(r["units"])
            amt = abs(float(r["amount"]))
            desc = str(r.get("description", "") or "")
            is_corp = bool(_CORP_ACTION_RE.search(desc))

            if u > 0:        # Kauf
                pool_units += u
                pool_cost  += amt
            elif u < 0:      # Verkauf
                sold = -u
                avg = pool_cost / pool_units if pool_units > 1e-9 else 0.0
                cost_of_sale = avg * min(sold, pool_units)
                realized_gain += amt - cost_of_sale
                pool_units = max(pool_units - sold, 0.0)
                pool_cost  = max(pool_cost - cost_of_sale, 0.0)
                last_sell = r["date"]
            elif is_corp and pool_units > 1e-9:
                # Kapitalmaßnahme ohne Stückzahl: schliesst die Restposition.
                # Der Erlös ist der Betrag (bei Übernahmen positiv, bei einer
                # wertlosen Ausbuchung 0) — der verbleibende Einstand wird
                # dagegen realisiert.
                proceeds = float(r["amount"]) if float(r["amount"]) > 0 else 0.0
                realized_gain += proceeds - pool_cost
                pool_units = 0.0
                pool_cost  = 0.0
                closed_by_corp_action = True
                last_sell = r["date"]

        # Der Restbestand ist das, was der Pool nach allen Ereignissen sagt —
        # nicht die blosse Summe der Stückzahlen. Nur so schliesst eine
        # Kapitalmassnahme die Position auch wirklich.
        units_held = pool_units if closed_by_corp_action else grp["units"].sum()

        # Einstandspreis der aktuell gehaltenen Stücke (Rest-Pool)
        avg_buy = pool_cost / pool_units if pool_units > 1e-9 else 0.0
        # Einstand NUR der noch gehaltenen Stücke. total_invested ist die
        # Brutto-Kaufsumme über die gesamte Historie; sie als "cost" einer
        # teilverkauften Position zu verwenden verdoppelt den Einstand und
        # verfälscht Gewinn und Rendite.
        cost_basis = pool_cost

        # Best name: prefer BUY transaction descriptions, strip type prefixes
        _buy_descs = grp[grp["units"] > 0]["description"].dropna()
        _buy_descs = _buy_descs[_buy_descs.str.strip() != ""]
        _all_descs = grp["description"].dropna()
        _all_descs = _all_descs[_all_descs.str.strip() != ""]
        name = _buy_descs.iloc[-1] if not _buy_descs.empty else (
            _all_descs.iloc[-1] if not _all_descs.empty else isin
        )
        # Strip CSV-style type prefixes like "BUY: ", "DIVIDEND: " etc.
        import re as _re
        name = _re.sub(
            r'^(BUY|SELL|DIVIDEND|DISTRIBUTION|SAVEBACK|INTEREST_PAYMENT|'
            r'ROUND_UP|SAVINGS_PLAN|CORPORATE_ACTION|REFERRAL):\s*',
            "", name, flags=_re.IGNORECASE,
        ).strip() or isin

        positions.append({
            "isin":               isin,
            "name":               name,
            "is_etf":             _is_etf(isin, name),
            "units_held":         round(units_held, 6),
            "avg_buy_price":      round(avg_buy, 4),
            "cost_basis":         round(cost_basis, 2),
            "closed_by_corp_action": bool(closed_by_corp_action and pool_units <= 1e-9),
            "total_invested":     round(total_invested, 2),
            "total_sold":         round(total_proceeds, 2),
            "realized_gain":      round(realized_gain, 2),
            "n_buys":             len(buys),
            "n_sells":            len(sells),
            "first_buy":          buys["date"].min() if len(buys) else pd.NaT,
            "last_buy":           buys["date"].max() if len(buys) else pd.NaT,
            "last_sell":          last_sell,
        })

    result = pd.DataFrame(positions)
    # Only positions with units still held
    active = result[result["units_held"] > 0.001].copy()
    sold   = result[result["units_held"] <= 0.001].copy()
    active = active.sort_values("total_invested", ascending=False).reset_index(drop=True)
    # Nach Verkaufsdatum, neueste zuerst; Zeilen ohne Datum ans Ende.
    sold   = sold.sort_values("last_sell", ascending=False, na_position="last").reset_index(drop=True)
    return active, sold


# ── Current prices via yfinance ───────────────────────────────────────────────

def fetch_prices(isins: list[str]) -> dict[str, Optional[float]]:
    """
    Attempt to fetch current prices for a list of ISINs.
    Returns {isin: price_eur_or_None}.
    Tries: known ticker map, then direct ISIN lookup.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {isin: None for isin in isins}

    ticker_map = load_ticker_map()
    prices = {}

    for isin in isins:
        ticker_symbol = ticker_map.get(isin)
        price = None

        if ticker_symbol:
            try:
                t = yf.Ticker(ticker_symbol)
                info = t.fast_info
                price = float(info.last_price or 0) or None
                # Convert to EUR using the correct per-currency FX pair
                currency = (getattr(info, 'currency', None) or 'EUR').upper()
                if currency != 'EUR' and price:
                    try:
                        fx_ticker = f"EUR{currency}=X"
                        fx = yf.Ticker(fx_ticker).fast_info.last_price
                        if fx:
                            price = price / fx
                        else:
                            price = None  # unknown FX → don't show wrong value
                    except Exception:
                        price = None
            except Exception:
                price = None

        if price is None:
            # Try ISIN directly (works for some exchanges)
            try:
                t = yf.Ticker(isin)
                info = t.fast_info
                price = float(info.last_price or 0) or None
                currency = (getattr(info, 'currency', None) or 'EUR').upper()
                if currency != 'EUR' and price:
                    try:
                        fx_ticker = f"EUR{currency}=X"
                        fx = yf.Ticker(fx_ticker).fast_info.last_price
                        price = (price / fx) if fx else None
                    except Exception:
                        price = None
            except Exception:
                price = None

        prices[isin] = price

    return prices


# ── Enrich positions with current prices ─────────────────────────────────────

def enrich_with_prices(
    positions: pd.DataFrame,
    prices: dict[str, Optional[float]],
) -> pd.DataFrame:
    """Add current_price, current_value, unrealized_gain, gain_pct columns."""
    if positions.empty:
        return positions

    df = positions.copy()
    df["current_price"]    = df["isin"].map(prices)
    df["current_value"]    = df["current_price"] * df["units_held"]
    df["unrealized_gain"]  = df["current_value"] - (df["avg_buy_price"] * df["units_held"])
    df["gain_pct"]         = (
        df["unrealized_gain"] / (df["avg_buy_price"] * df["units_held"])
    ).replace([float("inf"), float("-inf")], None) * 100
    return df


def snapshot_staleness_warnings(
    tr_df: pd.DataFrame,
    snapshot: Optional[pd.DataFrame],
    snapshot_date: Optional[str],
) -> list[str]:
    """Wo widersprechen sich Snapshot und Buchungen?

    Meldet Abweichungen, statt sie stillschweigend zugunsten des Snapshots zu
    entscheiden. Ein lokales Tool hat keinen Operator ausser dem Nutzer — wenn
    die Daten uneins sind, muss die Oberfläche das sagen.
    """
    out: list[str] = []
    if snapshot is None or snapshot.empty or not snapshot_date:
        return out
    try:
        snap_ts = pd.Timestamp(snapshot_date)
    except Exception:
        return out

    later = tr_df[
        (tr_df["date"] > snap_ts)
        & (tr_df["isin"].fillna("") != "")
        & (tr_df["units"].fillna(0) < 0)
    ]
    stale_isins = sorted(set(later["isin"]) & set(snapshot["isin"].dropna()))
    if stale_isins:
        out.append(
            f"Der Depot-Snapshot ist vom {snap_ts.date()}, aber danach wurde in "
            f"{len(stale_isins)} Position(en) noch verkauft. Für diese gelten die "
            f"Buchungen, nicht der Snapshot."
        )
    return out


def isins_closed_after(tr_df: pd.DataFrame, snapshot_date: Optional[str]) -> set[str]:
    """ISINs, die laut Buchungen NACH dem Snapshot-Stichtag geschlossen wurden.

    Getrennt von merge_with_snapshot, damit die Merge-Funktion keine
    Transaktionsdaten braucht und einzeln testbar bleibt.
    """
    if tr_df is None or tr_df.empty:
        return set()

    succ = load_isin_succession()
    rel = tr_df[tr_df["isin"].fillna("") != ""].copy()
    if rel.empty:
        return set()
    rel["isin"] = rel["isin"].map(lambda i: resolve_isin(str(i), succ))

    snap_ts = None
    if snapshot_date:
        try:
            snap_ts = pd.Timestamp(snapshot_date)
        except Exception:
            snap_ts = None

    out: set[str] = set()
    for isin, grp in rel.groupby("isin"):
        units = grp["units"].fillna(0)
        has_buy = bool((units > 0).any())
        closed = float(units.sum()) <= 0.001
        corp = bool(_CORP_ACTION_RE.search(" ".join(grp["description"].fillna("").tolist())))

        if snap_ts is not None:
            # Mit Stichtag: nur Ereignisse NACH dem Snapshot schlagen ihn.
            after = grp[grp["date"] > snap_ts]
            if not after.empty and (closed or _CORP_ACTION_RE.search(
                    " ".join(after["description"].fillna("").tolist()))):
                out.add(str(isin))
        elif has_buy and (closed or corp):
            # Ohne Stichtag lässt sich nicht nach Aktualität entscheiden. Dann
            # gilt: eine LÜCKENLOSE Historie (Kauf UND Schliessung liegen vor)
            # ist belastbarer als ein Depotauszug ohne Datum. Ohne diese Regel
            # blendet ein alter Auszug verkaufte Positionen dauerhaft wieder ein.
            out.add(str(isin))
    return out


def merge_with_snapshot(
    positions: pd.DataFrame,
    snapshot: pd.DataFrame,
    closed_after_snapshot: Optional[set] = None,
) -> pd.DataFrame:
    """
    Merge reconstructed positions with a Depotauszug snapshot.

    The snapshot is the ground truth for current holdings and values.
    For positions only in the snapshot (bought before Kontoauszug period),
    we show them with current_value but without avg_buy_price.
    For positions in both, snapshot current_value takes precedence.
    """
    if snapshot is None or snapshot.empty:
        return positions

    snap = snapshot.copy()
    snap = snap.rename(columns={"units": "units_held", "current_value": "snap_value"})
    snap["units_held"] = pd.to_numeric(snap["units_held"], errors="coerce").fillna(0)
    snap["snap_value"] = pd.to_numeric(snap["snap_value"], errors="coerce")

    if positions.empty:
        # No transaction data — use snapshot entirely
        result = snap[["isin", "name", "units_held", "snap_value"]].copy()
        result["is_etf"]          = result.apply(lambda r: _is_etf(r["isin"], r["name"]), axis=1)
        result["avg_buy_price"]   = None
        result["total_invested"]  = None
        result["total_sold"]      = 0.0
        result["realized_gain"]   = 0.0
        result["n_buys"]          = 0
        result["n_sells"]         = 0
        result["first_buy"]       = pd.NaT
        result["last_buy"]        = pd.NaT
        result["current_value"]   = result["snap_value"]
        result["current_price"]   = result["snap_value"] / result["units_held"].replace(0, pd.NA)
        result["unrealized_gain"] = None
        result["gain_pct"]        = None
        return result[result["units_held"] > 0].reset_index(drop=True)

    # Merge on ISIN (outer: Positionen aus Transaktionen, die NICHT im Snapshot
    # stehen, dürfen nicht verschwinden).
    merged = snap.merge(positions, on="isin", how="outer", suffixes=("_snap", "_tx"))

    # Prefer snapshot name if we have it, else transaction name
    merged["name"] = merged["name_snap"].where(
        merged["name_snap"].notna() & (merged["name_snap"] != ""),
        merged["name_tx"]
    )
    # Der Snapshot gilt — aber nicht bedingungslos. Wenn die Transaktionen
    # sagen, dass eine Position nach dem Snapshot-Stichtag geschlossen wurde,
    # gewinnen die Transaktionen. Ohne diese Regel blendet ein alter Snapshot
    # verkaufte Positionen dauerhaft wieder ein.
    merged["units_held"] = merged["units_held_snap"].fillna(merged["units_held_tx"])
    if closed_after_snapshot:
        closed = merged["isin"].isin(set(closed_after_snapshot))
        merged.loc[closed, "units_held"] = 0.0

    # Current value from snapshot (für tx-only Positionen liegt kein Snapshot-Wert vor)
    merged["current_value"] = merged["snap_value"]
    merged["current_price"]  = (merged["snap_value"] / merged["units_held"].replace(0, pd.NA)).where(
        merged["units_held"] > 0
    )

    # Unrealized gain only if we have avg_buy_price
    if "avg_buy_price" not in merged.columns:
        merged["avg_buy_price"] = np.nan
    # units_held > 0 gehört zwingend in die Maske: eine geschlossene Position
    # hat keinen Buchgewinn, und der Nenner (Einstand × Stückzahl) wäre 0.
    mask = (
        merged["avg_buy_price"].notna()
        & (merged["avg_buy_price"] > 0)
        & merged["units_held"].notna()
        & (merged["units_held"] > 0)
    )
    merged["unrealized_gain"] = None
    merged.loc[mask, "unrealized_gain"] = (
        merged.loc[mask, "current_value"] - merged.loc[mask, "avg_buy_price"] * merged.loc[mask, "units_held"]
    )
    merged["gain_pct"] = None
    merged.loc[mask, "gain_pct"] = (
        merged.loc[mask, "unrealized_gain"] / (merged.loc[mask, "avg_buy_price"] * merged.loc[mask, "units_held"])
    ).replace([float("inf"), float("-inf")], None) * 100

    # Fill missing transaction columns
    for col in ["total_invested", "total_sold", "realized_gain", "n_buys", "n_sells"]:
        if col not in merged.columns:
            merged[col] = 0
        merged[col] = merged[col].fillna(0)
    for col in ["first_buy", "last_buy"]:
        if col not in merged.columns:
            merged[col] = pd.NaT

    # is_etf: tx-Wert bevorzugen, sonst aus ISIN+Name neu berechnen
    # (robust gegen fehlende Werte UND gegen Suffix-Kollision is_etf_snap/_tx).
    if "is_etf_tx" in merged.columns:
        tx_etf = merged["is_etf_tx"]
    elif "is_etf" in merged.columns:
        tx_etf = merged["is_etf"]
    else:
        tx_etf = pd.Series([pd.NA] * len(merged), index=merged.index)
    recomputed = merged.apply(
        lambda r: _is_etf(str(r.get("isin", "")), str(r.get("name", ""))), axis=1
    )
    merged["is_etf"] = tx_etf.where(tx_etf.notna(), recomputed).astype(bool)

    cols = [
        "isin", "name", "is_etf", "units_held", "avg_buy_price", "total_invested",
        "total_sold", "realized_gain", "n_buys", "n_sells", "first_buy", "last_buy",
        "current_price", "current_value", "unrealized_gain", "gain_pct",
    ]
    for c in cols:
        if c not in merged.columns:
            merged[c] = None
    return merged[cols][merged["units_held"] > 0].reset_index(drop=True)


# ── Timeline: invested capital over time ──────────────────────────────────────

def investment_timeline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Monthly cumulative invested capital in TR (buy outflows only).
    Returns DataFrame: ym (Period str), invested_cumulative
    """
    tr_buys = df[
        (df["account"] == "Trade Republic") &
        (df["amount"] < 0) &
        (df["category"].isin(SAVINGS_CATEGORIES))
    ].copy()

    if tr_buys.empty:
        return pd.DataFrame()

    tr_buys["ym"] = tr_buys["date"].dt.to_period("M")
    monthly = tr_buys.groupby("ym")["amount"].sum().abs().reset_index()
    monthly["invested_cumulative"] = monthly["amount"].cumsum()
    monthly["ym"] = monthly["ym"].astype(str)
    return monthly


# ── Income type classification ────────────────────────────────────────────────

def _classify_income(description: str) -> str:
    """Classify TR income into Dividende / Zinsen / Saveback / Bonus / Sonstiges."""
    desc = (description or "").lower()
    if any(k in desc for k in ("saveback", "save back", "save-back")):
        return "Saveback"
    if any(k in desc for k in ("dividende", "dividend", "ausschüttung", "distribution")):
        return "Dividende"
    if any(k in desc for k in ("zinsen", "zins", "interest", "zinserträge",
                                "interest_payment")):
        return "Zinsen"
    if any(k in desc for k in ("referral", "bonus", "empfehlung", "stockperk",
                                "gift", "prämie")):
        return "Bonus"
    return "Sonstiges"


# ── Dividend / interest income ────────────────────────────────────────────────

def dividend_history(df: pd.DataFrame) -> pd.DataFrame:
    """
    Dividend and interest payments from TR, grouped by month and ISIN.
    Adds income_type column: Dividende / Zinsen / Saveback / Sonstiges.
    """
    inc = df[
        (df["account"] == "Trade Republic") &
        (df["amount"] > 0) &
        (df["category"] == "Einkommen")
    ].copy()

    if inc.empty:
        return pd.DataFrame()

    inc["ym"]          = inc["date"].dt.to_period("M").astype(str)
    inc["income_type"] = inc["description"].apply(_classify_income)
    return (
        inc.groupby(["ym", "isin", "description", "income_type"])["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "betrag"})
        .sort_values(["ym", "betrag"], ascending=[True, False])
    )


# ── Benchmark comparison ──────────────────────────────────────────────────────

def fetch_benchmark_history(ticker: str = "IWDA.AS", start: str = "2019-01-01") -> pd.DataFrame:
    """
    Fetch benchmark price history via yfinance.
    Returns DataFrame: date, close, normalised (rebased to 100 at start).
    """
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()

    try:
        hist = yf.Ticker(ticker).history(start=start, auto_adjust=True)
        if hist.empty:
            return pd.DataFrame()
        hist = hist[["Close"]].reset_index()
        hist.columns = ["date", "close"]
        hist["date"] = pd.to_datetime(hist["date"]).dt.tz_localize(None)
        first_close  = hist["close"].iloc[0]
        hist["normalised"] = hist["close"] / first_close * 100 if first_close else 100
        return hist
    except Exception:
        return pd.DataFrame()


def portfolio_value_history(df: pd.DataFrame, positions: pd.DataFrame) -> pd.DataFrame:
    """
    Approximate portfolio value over time using cost-basis cumulated monthly.
    Returns DataFrame: date, portfolio_value (cumulative invested, normalised to 100).
    Used for benchmark comparison when live prices aren't available per date.
    """
    timeline = investment_timeline(df)
    if timeline.empty:
        return pd.DataFrame()

    timeline["date"] = pd.to_datetime(timeline["ym"])
    first_val = timeline["invested_cumulative"].iloc[0]
    timeline["normalised"] = (
        timeline["invested_cumulative"] / first_val * 100
        if first_val else 100
    )
    return timeline[["date", "invested_cumulative", "normalised"]]
