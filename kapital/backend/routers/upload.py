import io
import traceback
from fastapi import APIRouter, UploadFile, File, HTTPException

from ..deps import set_df

router = APIRouter()

_FORMAT_NAMES = {
    "giro":           "Girokonto CSV",
    "trade_republic": "Trade Republic CSV",
    "paypal":         "PayPal CSV",
    "tr_pdf":         "Trade Republic PDF",
    "depot_snapshot": "Depot-Snapshot PDF",
}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

    from kapital.finance.parsers.giro import parse_giro
    from kapital.finance.parsers.trade_republic import parse_trade_republic
    from kapital.finance.parsers.paypal import parse_paypal
    from kapital.finance.parsers.trade_republic_pdf import parse_tr_pdf, parse_depot_snapshot
    from kapital.finance.categorizer import categorize_df
    from kapital.finance.transfer_detector import detect_transfers
    from kapital.finance.custom_rules import apply_custom_rules, load_rules
    from kapital.finance import storage
    from kapital.finance.storage import save_depot_snapshot

    raw = await file.read()
    filename = (file.filename or "").lower()

    # Wrap raw bytes in BytesIO so parsers can call .seek() / .read()
    def make_file():
        f = io.BytesIO(raw)
        f.name = filename
        return f

    try:
        parsed_df = None
        parse_type = "unknown"
        parser_errors: list[str] = []

        # ── PDF ──────────────────────────────────────────────────────────────
        if filename.endswith(".pdf"):
            # Try depot snapshot first
            try:
                snap = parse_depot_snapshot(make_file())
                if snap is not None and not snap.empty:
                    # Stichtag mitgeben, sonst kann später niemand entscheiden,
                    # ob Snapshot oder Buchungen aktueller sind.
                    _as_of = ""
                    if "as_of" in snap.columns and len(snap):
                        _as_of = str(snap["as_of"].iloc[0] or "")
                    save_depot_snapshot(snap, as_of=_as_of)
                    return {
                        "ok": True,
                        "type": "depot_snapshot",
                        "format_name": _FORMAT_NAMES["depot_snapshot"],
                        "n_new": 0,
                        "n_parsed": len(snap),
                        "n_duplicates": 0,
                        "n_total": 0,
                        "message": f"{len(snap)} Positionen importiert (Depot-Snapshot)",
                    }
            except Exception as e:
                parser_errors.append(f"Depot-Snapshot: {e}")

            # Try TR PDF transactions
            try:
                parsed_df = parse_tr_pdf(make_file())
                if parsed_df is not None and not parsed_df.empty:
                    parse_type = "tr_pdf"
                else:
                    parser_errors.append("TR-PDF: Keine Transaktionen gefunden")
                    parsed_df = None
            except Exception as e:
                parser_errors.append(f"TR-PDF: {e}")

            if parsed_df is None or parsed_df.empty:
                detail = "PDF konnte nicht geparst werden."
                if parser_errors:
                    detail += " Fehler: " + " | ".join(parser_errors)
                raise HTTPException(400, detail)

        # ── CSV ──────────────────────────────────────────────────────────────
        elif filename.endswith(".csv"):
            for parser_fn, ptype in [
                (parse_trade_republic, "trade_republic"),
                (parse_giro,           "giro"),
                (parse_paypal,         "paypal"),
            ]:
                try:
                    result = parser_fn(make_file())
                    if result is not None and not result.empty:
                        parsed_df = result
                        parse_type = ptype
                        break
                    else:
                        parser_errors.append(f"{ptype}: leer")
                except Exception as e:
                    parser_errors.append(f"{ptype}: {e}")

            if parsed_df is None or parsed_df.empty:
                detail = "CSV-Format nicht erkannt."
                if parser_errors:
                    detail += " Versucht: " + " | ".join(parser_errors)
                raise HTTPException(400, detail)

        else:
            raise HTTPException(400, f"Nicht unterstütztes Dateiformat: {filename!r}. Nur .csv und .pdf erlaubt.")

        # ── Nothing parsed ───────────────────────────────────────────────────
        if parsed_df is None or parsed_df.empty:
            return {
                "ok": True,
                "type": parse_type,
                "format_name": _FORMAT_NAMES.get(parse_type, parse_type),
                "n_new": 0, "n_parsed": 0, "n_duplicates": 0, "n_total": 0,
                "message": "Keine Buchungen in der Datei gefunden.",
            }

        n_parsed = len(parsed_df)

        # ── Categorize + rules ───────────────────────────────────────────────
        parsed_df = categorize_df(parsed_df)
        rules = load_rules()
        if rules:
            parsed_df = apply_custom_rules(parsed_df, rules)

        # ── Merge + deduplicate ──────────────────────────────────────────────
        existing = storage.load()
        existing_hashes = set(existing["tx_hash"].dropna()) if not existing.empty else set()
        merged_df, n_added, n_dupes = storage.merge(existing, parsed_df)

        # ── Transfer detection ───────────────────────────────────────────────
        merged_df = detect_transfers(merged_df)

        storage.save(merged_df)
        set_df(merged_df)

        # ── Betroffene Monate + offene Zuordnungen (für das Review-Gate) ──────
        from kapital.finance import review as review_core

        new_rows = merged_df[~merged_df["tx_hash"].isin(existing_hashes)]
        affected_months = sorted(
            new_rows["date"].dt.to_period("M").astype(str).unique().tolist(), reverse=True
        ) if not new_rows.empty else []

        open_counts = review_core.open_counts_by_month(merged_df)
        n_open_affected = int(sum(open_counts.get(m, 0) for m in affected_months))

        format_name = _FORMAT_NAMES.get(parse_type, parse_type)
        parts = [f"{n_added} neue Buchungen"]
        if n_dupes:
            parts.append(f"{n_dupes} Duplikate übersprungen")
        message = f"{format_name} · " + ", ".join(parts)

        return {
            "ok": True,
            "type": parse_type,
            "format_name": format_name,
            "n_parsed": n_parsed,
            "n_new": n_added,
            "n_duplicates": n_dupes,
            "n_total": len(merged_df),
            "message": message,
            "affected_months": affected_months,
            "n_open_affected": n_open_affected,
        }

    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        # surrogate-/nicht-UTF-8-sicher machen, sonst kann die JSON-Antwort selbst
        # fehlschlagen → Starlette liefert dann Plaintext "Internal Server Error".
        detail = f"Import-Fehler: {e}\n{tb[:600]}".encode("utf-8", "replace").decode("utf-8")
        raise HTTPException(500, detail)
