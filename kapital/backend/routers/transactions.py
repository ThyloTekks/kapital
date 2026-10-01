from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
import io

from ..deps import (get_df, reload_df, set_df, categories_list, cat_meta, transaction,
                    row_occurrences, make_row_ref, resolve_row_ref, resolve_row_refs)
from kapital.finance import storage
from kapital.finance import abo_overrides
from kapital.finance.custom_rules import apply_custom_rules, load_rules

router = APIRouter()


class CategoryUpdate(BaseModel):
    category: str


class SonderausgabeUpdate(BaseModel):
    is_sonderausgabe: bool


class AboUpdate(BaseModel):
    is_abo: bool


class BulkDeleteBody(BaseModel):
    tx_hashes: List[str]


@router.get("/transactions")
def list_transactions(
    search: str = Query("", description="Search in payee/description"),
    category: str = Query("all"),
    account: str = Query("all"),
    sonderausgabe: str = Query("all", description="all | true | false"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    sort: str = Query("date_desc"),
):
    df = get_df()
    if df.empty:
        return {"items": [], "total": 0, "categories": [], "accounts": []}

    mask = [True] * len(df)
    import pandas as pd
    mask = pd.Series([True] * len(df), index=df.index)

    if search:
        sl = search.lower()
        mask &= (
            df["payee"].str.lower().str.contains(sl, na=False) |
            df["description"].str.lower().str.contains(sl, na=False)
        )
    if category != "all":
        mask &= df["category"] == category
    if account != "all":
        # Anzeigename -> alle rohen account_label desselben Kontos, siehe deps.
        from ..deps import account_raw_labels
        mask &= df["account_label"].isin(account_raw_labels(df, account))
    if sonderausgabe in ("true", "false") and "is_sonderausgabe" in df.columns:
        flag = df["is_sonderausgabe"].astype(bool)
        mask &= flag if sonderausgabe == "true" else ~flag

    filtered = df[mask].copy()

    if sort == "date_asc":
        filtered = filtered.sort_values("date", ascending=True)
    elif sort == "amount_asc":
        filtered = filtered.sort_values("amount", ascending=True)
    elif sort == "amount_desc":
        filtered = filtered.sort_values("amount", ascending=False)
    elif sort in ("amount_abs_desc", "amount_abs_asc"):
        # Nach Betragshöhe, Vorzeichen egal. Zum Durchsehen ist das die
        # nützlichste Reihenfolge: die grössten Bewegungen zuerst, egal ob
        # Ein- oder Ausgang. Die vorzeichenbehaftete Sortierung stellt sonst
        # die grössten Gutschriften an den Anfang und die grössten Ausgaben
        # ans Ende.
        filtered = filtered.assign(_abs=filtered["amount"].abs()).sort_values(
            "_abs", ascending=(sort == "amount_abs_asc")
        ).drop(columns=["_abs"])
    else:
        filtered = filtered.sort_values("date", ascending=False)

    total = len(filtered)
    page_df = filtered.iloc[offset: offset + limit]

    cats = {c["id"]: c for c in categories_list()}
    forced = abo_overrides.forced_keys()
    # Zeilen-Referenz statt blossem tx_hash — siehe deps.ROW_REF_SEP. Die
    # laufende Nummer zählt über den ungefilterten Bestand, damit dieselbe Zeile
    # unter jedem Filter dieselbe Referenz trägt.
    occurrence = row_occurrences(df)
    items = []
    for _, row in page_df.iterrows():
        cat_id = str(row.get("category", "Sonstiges"))
        payee = str(row.get("payee", ""))
        desc = str(row.get("description", ""))
        is_abo = (
            abo_overrides.norm_key(payee) in forced
            or abo_overrides.norm_key(desc[:50]) in forced
        )
        items.append({
            "id": make_row_ref(str(row["tx_hash"]), occurrence.loc[row.name]),
            "tx_hash": str(row["tx_hash"]),
            "date": row["date"].strftime("%Y-%m-%d"),
            "payee": payee,
            "description": desc,
            "category": cat_id,
            "amount": round(float(row["amount"]), 2),
            "account": str(row.get("account_label", "")),
            "is_transfer": bool(row.get("is_transfer", False)),
            "is_sonderausgabe": bool(row.get("is_sonderausgabe", False)),
            "is_abo": bool(is_abo),
            "confidence": float(row.get("confidence", 1.0)) if "confidence" in row.index else 1.0,
        })

    # Available filter options
    cat_options = sorted(df["category"].dropna().unique().tolist())
    from ..deps import account_options
    acc_options = account_options(df)

    return {
        "items": items,
        "total": total,
        "categories": cat_options,
        "accounts": acc_options,
    }


@router.put("/transactions/{tx_hash}/category")
def update_category(tx_hash: str, body: CategoryUpdate):
    df = get_df()
    idx = resolve_row_ref(df, tx_hash)
    if idx is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Transaction not found")
    df = df.copy()
    df.loc[idx, "category"] = body.category
    storage.save(df)
    set_df(df)
    return {"ok": True, "tx_hash": tx_hash, "category": body.category}


@router.put("/transactions/{tx_hash}/sonderausgabe")
def update_sonderausgabe(tx_hash: str, body: SonderausgabeUpdate):
    df = get_df()
    idx = resolve_row_ref(df, tx_hash)
    if idx is None:
        raise HTTPException(404, "Transaction not found")
    df = df.copy()
    df.loc[idx, "is_sonderausgabe"] = body.is_sonderausgabe
    storage.save(df)
    set_df(df)
    return {"ok": True, "tx_hash": tx_hash, "is_sonderausgabe": body.is_sonderausgabe}


@router.put("/transactions/{tx_hash}/abo")
def update_abo(tx_hash: str, body: AboUpdate):
    """Mark/unmark a booking's payee as a subscription.

    Flags the payee (or description prefix when the payee is empty) so that
    this and all future bookings with the same payee show up in the Abo tab.
    """
    df = get_df()
    idx = resolve_row_ref(df, tx_hash)
    if idx is None:
        raise HTTPException(404, "Transaction not found")
    row = df.loc[idx[0]]
    payee = str(row.get("payee", "")).strip()
    desc = str(row.get("description", "")).strip()[:50]
    label = payee or desc
    if not label:
        raise HTTPException(400, "Buchung hat keinen Empfänger/Verwendungszweck")
    if body.is_abo:
        abo_overrides.force_abo(label)
    else:
        abo_overrides.unforce_abo(abo_overrides.norm_key(label))
    return {"ok": True, "tx_hash": tx_hash, "is_abo": body.is_abo, "label": label}


@router.delete("/transactions/all")
def delete_all_transactions():
    """Delete every transaction and wipe the parquet file."""
    import pandas as pd
    from kapital.finance.models import COLUMNS
    df = get_df()
    n = len(df)
    empty = pd.DataFrame(columns=COLUMNS)
    storage.save(empty)
    set_df(empty)
    return {"ok": True, "deleted": n}


@router.delete("/transactions/bulk")
def delete_bulk(body: BulkDeleteBody):
    """Ausgewählte Buchungen löschen.

    Über die Zeilen-Referenz, nicht über den blossen tx_hash: bei kollidierendem
    Hash hätte das Löschen EINER Fahrkarte alle vier gleichen mitgenommen —
    unwiederbringlich, ohne Hinweis in der Oberfläche.
    """
    df = get_df()
    before = len(df)
    idx, missing = resolve_row_refs(df, body.tx_hashes)
    if len(idx) == 0:
        raise HTTPException(404, "Keine der Buchungen gefunden")
    df = df.drop(index=idx).reset_index(drop=True)
    n_deleted = before - len(df)
    storage.save(df)
    set_df(df)
    return {"ok": True, "deleted": n_deleted, "skipped": len(missing)}


@router.delete("/transactions/account/{account_label}")
def delete_by_account(account_label: str):
    """Delete all transactions for a specific account_label."""
    df = get_df()
    before = len(df)
    df = df[df["account_label"] != account_label].reset_index(drop=True)
    n_deleted = before - len(df)
    storage.save(df)
    set_df(df)
    return {"ok": True, "deleted": n_deleted, "account": account_label}


@router.get("/transactions/export")
def export_csv():
    df = get_df()
    if df.empty:
        return {"error": "no data"}
    export_df = df[["date", "amount", "payee", "description", "category", "account_label", "is_transfer"]].copy()
    export_df["date"] = export_df["date"].dt.strftime("%Y-%m-%d")
    buf = io.StringIO()
    export_df.to_csv(buf, index=False, sep=";")
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transaktionen.csv"},
    )


# ── Wartung: Umbuchungserkennung neu laufen lassen ───────────────────────────

class TransferFlagBody(BaseModel):
    is_transfer: bool


@router.put("/transactions/{tx_hash}/transfer")
def set_transfer_flag(tx_hash: str, body: TransferFlagBody):
    """Eine Buchung manuell als Umbuchung markieren oder die Markierung lösen.

    Bisher gab es keinen Weg, eine falsch erkannte Umbuchung zurückzunehmen —
    eine fälschlich markierte Buchung verschwand dauerhaft aus jeder Auswertung,
    ohne Spur in der Oberfläche.
    """
    with transaction():
        df = get_df().copy()
        idx = resolve_row_ref(df, tx_hash)
        if idx is None:
            raise HTTPException(404, "Buchung nicht gefunden")
        df.loc[idx, "is_transfer"] = bool(body.is_transfer)
        if not body.is_transfer:
            df.loc[idx, "transfer_id"] = ""
            umb = [i for i in idx if df.at[i, "category"] == "Umbuchung"]
            df.loc[umb, "category"] = "Sonstiges"
        storage.save(df)
        set_df(df)
    return {"ok": True, "tx_hash": tx_hash, "is_transfer": bool(body.is_transfer)}


@router.post("/transactions/redetect-transfers")
def redetect_transfers(dry_run: bool = True):
    """Umbuchungserkennung auf dem gesamten Bestand neu ausführen.

    Nötig, weil die Erkennung nur beim Import läuft: eine Korrektur an den
    Regeln erreicht bereits importierte Buchungen sonst nie. Standardmässig
    dry_run=True — es wird nur berichtet, was sich ändern würde.
    """
    from kapital.finance.transfer_detector import detect_transfers

    with transaction():
        df = get_df().copy()
        if df.empty:
            return {"ok": True, "changed": 0, "dry_run": dry_run}

        before = df["is_transfer"].fillna(False).astype(bool).copy()
        reset = df.copy()
        reset["is_transfer"] = False
        reset["transfer_id"] = ""
        after_df = detect_transfers(reset)
        after = after_df["is_transfer"].fillna(False).astype(bool)

        newly_freed = df[before & ~after]
        newly_marked = df[~before & after]
        result = {
            "ok": True,
            "dry_run": dry_run,
            "was_transfer_now_not": int(len(newly_freed)),
            "was_not_now_transfer": int(len(newly_marked)),
            "volume_freed": round(float(newly_freed[newly_freed["amount"] > 0]["amount"].sum()), 2),
            "changed": int(len(newly_freed) + len(newly_marked)),
        }
        if dry_run:
            return result

        # Kategorie der wieder freigegebenen Zeilen zurücksetzen, damit sie in
        # der Zuordnung auftauchen statt als "Umbuchung" stehen zu bleiben.
        after_df.loc[(~after) & (after_df["category"] == "Umbuchung"), "category"] = "Sonstiges"
        storage.save(after_df)
        set_df(after_df)
        return result


class BulkFlagBody(BaseModel):
    tx_hashes: List[str]
    is_sonderausgabe: bool | None = None
    category: str | None = None


@router.put("/transactions/bulk")
def bulk_update(body: BulkFlagBody):
    """Mehrere Buchungen auf einmal markieren oder umkategorisieren.

    Sonderausgaben liessen sich bisher nur einzeln setzen. Genau dieses Flag
    steuert aber die Grundlast-Berechnung — bei tausenden Zeilen ist
    Einzelklicken der falsche Weg.
    """
    if not body.tx_hashes:
        return {"ok": True, "updated": 0}
    if body.is_sonderausgabe is None and body.category is None:
        raise HTTPException(400, "Nichts zu ändern: is_sonderausgabe oder category angeben.")

    with transaction():
        df = get_df().copy()
        idx, missing = resolve_row_refs(df, body.tx_hashes)
        if len(idx) == 0:
            raise HTTPException(404, "Keine der Buchungen gefunden")

        if body.category is not None:
            valid = {c["id"] for c in categories_list()}
            if body.category not in valid:
                raise HTTPException(400, f"Unbekannte Kategorie: {body.category!r}")
            # Umbuchungen nicht umkategorisieren — gleiche Regel wie bei den
            # Regeln, sonst verschieben sich die Ausschlüsse in allen Auswertungen.
            keep = ~df.loc[idx, "is_transfer"].fillna(False).astype(bool)
            df.loc[idx[keep], "category"] = body.category
        if body.is_sonderausgabe is not None:
            df.loc[idx, "is_sonderausgabe"] = bool(body.is_sonderausgabe)

        storage.save(df)
        set_df(df)
    # Übersprungene ausdrücklich melden statt still weglassen.
    return {"ok": True, "updated": int(len(idx)), "skipped": len(missing)}
