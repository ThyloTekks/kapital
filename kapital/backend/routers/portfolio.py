import logging
import math
from fastapi import APIRouter
from ..deps import get_df

log = logging.getLogger(__name__)

router = APIRouter()


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except Exception:
        return None


@router.get("/portfolio")
def get_portfolio():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    import pandas as pd
    from kapital.finance import portfolio as pf
    from kapital.finance import storage
    from kapital.finance.storage import load_depot_snapshot

    df = get_df()
    tr_df = df[df["account"] == "Trade Republic"].copy() if not df.empty else df

    if tr_df.empty:
        return {"positions": [], "sold": [], "summary": {}, "allocation": {}, "dividends": [], "trades": [], "income": {}}

    snapshot = load_depot_snapshot()

    # ── Reconstruct positions ──────────────────────────────────────────────────
    active_df = pd.DataFrame()
    sold_df = pd.DataFrame()
    warnings: list[str] = []
    try:
        active_df, sold_df = pf.reconstruct_positions(tr_df)
    except (KeyError, ValueError, TypeError) as exc:
        # Früher: except Exception: pass. Dann lieferte der Endpunkt ein leeres
        # Depot mit HTTP 200 und man konnte "du besitzt nichts" nicht von "der
        # Code ist geflogen" unterscheiden.
        log.exception("reconstruct_positions ist gescheitert")
        warnings.append(
            f"Positionen konnten nicht aus den Buchungen rekonstruiert werden "
            f"({type(exc).__name__}). Die Liste unten ist unvollständig."
        )
    snap_date_early = storage.load_depot_snapshot_date()
    if snapshot is not None and not snapshot.empty and not active_df.empty:
        try:
            active_df = pf.merge_with_snapshot(
                active_df, snapshot,
                closed_after_snapshot=pf.isins_closed_after(tr_df, snap_date_early),
            )
        except (KeyError, ValueError, TypeError) as exc:
            log.exception("merge_with_snapshot ist gescheitert")
            warnings.append(
                f"Depot-Snapshot konnte nicht verrechnet werden ({type(exc).__name__}); "
                f"es werden nur die aus Buchungen rekonstruierten Positionen gezeigt."
            )
    snap_date = snap_date_early
    if snap_date:
        warnings.extend(pf.snapshot_staleness_warnings(tr_df, snapshot, snap_date))
    elif snapshot is not None and not snapshot.empty:
        warnings.append(
            "Der Depot-Snapshot hat kein Datum (vor dieser Version importiert). "
            "Solange das so ist, kann er verkaufte Positionen wieder einblenden — "
            "einmal neu importieren behebt das."
        )

    # ── Build positions list ───────────────────────────────────────────────────
    positions = []
    total_value = 0.0
    total_cost = 0.0

    if not active_df.empty:
        for _, row in active_df.iterrows():
            qty = _f(row.get("units_held", 0)) or 0
            cur_price = _f(row.get("current_price"))
            avg_price = _f(row.get("avg_buy_price")) or 0
            cur_value = _f(row.get("current_value")) or (qty * cur_price if cur_price else 0)
            # Einstand der NOCH gehaltenen Stücke. total_invested ist die
            # Brutto-Kaufsumme über die ganze Historie — bei einer teilweise
            # verkauften Position ist sie zu hoch und verfälscht pl/pl_pct.
            cost = _f(row.get("cost_basis"))
            if cost is None:
                cost = (qty * avg_price) if avg_price else (_f(row.get("total_invested")) or 0)
            unreal = _f(row.get("unrealized_gain"))
            unreal_pct = _f(row.get("gain_pct"))

            if cur_value is None:
                cur_value = 0.0
            total_value += cur_value
            total_cost += cost

            # XIRR per position
            xirr = None
            try:
                raw = pf.compute_position_xirr(tr_df, str(row["isin"]), cur_value or None)
                if raw is not None:
                    xirr = round(raw * 100, 1)
            except (ValueError, TypeError, ZeroDivisionError):
                log.debug("XIRR nicht berechenbar für %s", row.get("isin"))

            positions.append({
                "isin":          str(row.get("isin", "")),
                "name":          str(row.get("name", row.get("isin", ""))),
                "qty":           round(qty, 6),
                "avg_price":     _f(avg_price),
                "current_price": cur_price,
                "value":         round(cur_value, 2),
                "cost":          round(cost, 2),
                "pl":            round(unreal, 2) if unreal is not None else round(cur_value - cost, 2),
                "pl_pct":        round(unreal_pct, 2) if unreal_pct is not None else None,
                "xirr":          xirr,
                "n_buys":        int(row.get("n_buys", 0) or 0),
                "n_sells":       int(row.get("n_sells", 0) or 0),
                "realized_gain": round(float(row.get("realized_gain", 0) or 0), 2),
                "is_etf":        bool(row.get("is_etf", False)),
            })

        positions.sort(key=lambda x: x["value"], reverse=True)

    # ── Realized / sold positions ──────────────────────────────────────────────
    realized = []
    total_realized_gain = 0.0
    if not sold_df.empty:
        for _, row in sold_df.iterrows():
            rg = round(float(row.get("realized_gain", 0) or 0), 2)
            total_realized_gain += rg
            _ls = row.get("last_sell")
            realized.append({
                "isin":          str(row.get("isin", "")),
                "name":          str(row.get("name", row.get("isin", ""))),
                "date":          _ls.strftime("%Y-%m-%d") if _ls is not None and pd.notna(_ls) else None,
                "closed_by_corp_action": bool(row.get("closed_by_corp_action", False)),
                "total_invested": round(float(row.get("total_invested", 0) or 0), 2),
                "total_proceeds": round(float(row.get("total_sold", 0) or 0), 2),
                "realized_gain": rg,
                "n_buys":        int(row.get("n_buys", 0) or 0),
                "n_sells":       int(row.get("n_sells", 0) or 0),
            })
        # Nach Verkaufsdatum, neueste zuerst. Zeilen ohne Datum (Verkäufe ohne
        # zugehörigen Kauf in der importierten Historie) ans Ende.
        realized.sort(key=lambda x: (x["date"] is not None, x["date"] or ""), reverse=True)

    total_pl = total_value - total_cost

    # ── TR uninvested cash (cash flows not tied to a trade) ────────────────────
    non_trade = tr_df[tr_df["units"].fillna(0) == 0]
    tr_cash = round(float(non_trade["amount"].sum()), 2)

    # ── TR income breakdown (exclude deposits and transfers) ──────────────────
    _deposit_prefixes = ("CUSTOMER_INBOUND", "TRANSFER_INBOUND", "TRANSFER_OUTBOUND")
    income_rows = non_trade[
        (non_trade["amount"] > 0) &
        (~non_trade["is_transfer"]) &
        (non_trade["category"] != "Umbuchung") &
        (~non_trade["description"].str.upper().str.startswith(_deposit_prefixes, na=False))
    ]
    interest_total = 0.0
    cashback_total = 0.0
    other_income = 0.0
    for _, row in income_rows.iterrows():
        amt = float(row["amount"])
        desc = str(row.get("description", "")).upper()
        cat = str(row.get("category", ""))
        if "INTEREST" in desc or cat in ("Zinsen", "Zinsen & Sparen"):
            interest_total += amt
        elif any(k in desc for k in ("ROUND_UP", "SAVEBACK", "REFERRAL", "CASHBACK")):
            cashback_total += amt
        else:
            other_income += amt

    # ── Dividends (TR transactions with DIVIDEND/DISTRIBUTION in description) ──
    dividends = []
    try:
        div_mask = (
            (tr_df["amount"] > 0) &
            (tr_df["units"].fillna(0) == 0) &
            (tr_df["description"].str.upper().str.contains("DIVIDEND|DISTRIBUTION|AUSSCHÜTTUNG", na=False))
        )
        for _, row in tr_df[div_mask].sort_values("date", ascending=False).iterrows():
            desc = str(row.get("description", ""))
            # Strip prefix like "DIVIDEND: Name" → "Name"
            import re as _re
            label = _re.sub(r'^(DIVIDEND|DISTRIBUTION|AUSSCHÜTTUNG)[:\s]*', "", desc, flags=_re.IGNORECASE).strip() or desc
            dividends.append({
                "date":   row["date"].strftime("%Y-%m-%d"),
                "isin":   str(row.get("isin", "") or ""),
                "amount": round(float(row["amount"]), 4),
                "type":   label or "Dividende",
            })
    except (KeyError, AttributeError, ValueError) as exc:
        log.exception("Dividenden konnten nicht ermittelt werden")
        warnings.append(f"Dividenden konnten nicht gelesen werden ({type(exc).__name__}).")

    # ── Trades ────────────────────────────────────────────────────────────────
    trades = []
    try:
        # ISIN → Name aus den bereits rekonstruierten Positionen und dem
        # Snapshot. Die Namen existieren schon; die Trades-Tabelle hat sie nur
        # nie mitgeliefert.
        name_by_isin: dict[str, str] = {}
        for frame in (active_df, sold_df):
            if frame is not None and not frame.empty and "name" in frame.columns:
                for _i, _r in frame.iterrows():
                    _n = str(_r.get("name", "") or "").strip()
                    if _n:
                        name_by_isin.setdefault(str(_r.get("isin", "")), _n)
        if snapshot is not None and not snapshot.empty and "name" in snapshot.columns:
            for _i, _r in snapshot.iterrows():
                _n = str(_r.get("name", "") or "").strip()
                if _n:
                    name_by_isin.setdefault(str(_r.get("isin", "")), _n)

        trades_df = tr_df[tr_df["units"].notna() & (tr_df["units"] != 0)].copy()
        for _, row in trades_df.iterrows():
            units = float(row.get("units", 0))
            _isin = str(row.get("isin", ""))
            trades.append({
                "date":   row["date"].strftime("%Y-%m-%d"),
                "action": "BUY" if units > 0 else "SELL",
                "isin":   _isin,
                "name":   name_by_isin.get(_isin, "") or _isin,
                "qty":    abs(round(units, 6)),
                "price":  _f(row.get("price_per_unit")) or 0,
                "amount": round(float(row["amount"]), 2),
            })
        trades.sort(key=lambda x: x["date"], reverse=True)
    except (KeyError, AttributeError, ValueError) as exc:
        log.exception("Trades konnten nicht aufbereitet werden")
        warnings.append(f"Trades konnten nicht gelesen werden ({type(exc).__name__}).")

    # ── Allocation ────────────────────────────────────────────────────────────
    etf_val   = sum(p["value"] for p in positions if p.get("is_etf"))
    stock_val = sum(p["value"] for p in positions if not p.get("is_etf"))
    top3_val  = sum(p["value"] for p in positions[:3]) if positions else 0
    top3_pct  = round(top3_val / total_value * 100, 1) if total_value else 0

    return {
        "warnings":  warnings,
        "positions": positions,
        "sold":      realized,
        "summary": {
            "total_value":         round(total_value, 2),
            "total_cost":          round(total_cost, 2),
            "total_pl":            round(total_pl, 2),
            "total_pl_pct":        round(total_pl / total_cost * 100, 2) if total_cost else 0,
            "total_realized_gain": round(total_realized_gain, 2),
            "tr_cash":             tr_cash,
            "n_positions":         len(positions),
            "n_sold":              len(realized),
        },
        "income": {
            "interest":  round(interest_total, 2),
            "cashback":  round(cashback_total, 2),
            "other":     round(other_income, 2),
            "dividends": round(sum(d["amount"] for d in dividends), 2) if dividends else 0.0,
        },
        "allocation": {
            "etf_value":   round(etf_val, 2),
            "stock_value": round(stock_val, 2),
            "etf_pct":     round(etf_val / total_value * 100, 1) if total_value else 0,
            "stock_pct":   round(stock_val / total_value * 100, 1) if total_value else 0,
            "top3_pct":    top3_pct,
            "n_positions": len(positions),
        },
        "dividends": dividends,
        "trades":    trades,
    }
