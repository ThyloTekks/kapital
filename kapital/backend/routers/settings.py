"""App settings — persisted in data/settings.json."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..app_settings import load_settings, save_settings

router = APIRouter()


class TwelveDataKeyBody(BaseModel):
    api_key: str


class AnthropicKeyBody(BaseModel):
    api_key: str


def _preview(key: str) -> str:
    if not key:
        return ""
    return f"{key[:8]}…{key[-4:]}" if len(key) > 14 else f"{key[:4]}…"


@router.get("/settings")
def get_settings():
    import os
    s = load_settings()
    key = s.get("twelve_data_api_key", "")
    ant = (s.get("anthropic_api_key") or "").strip()
    ant_env = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    return {
        "twelve_data_api_key_set": bool(key),
        "twelve_data_api_key_preview": f"{key[:4]}…" if len(key) > 4 else ("" if not key else key),
        "anthropic_api_key_set": bool(ant) or ant_env,
        "anthropic_api_key_source": "settings" if ant else ("env" if ant_env else ""),
        "anthropic_api_key_preview": _preview(ant),
    }


@router.put("/settings/anthropic_key")
def set_anthropic_key(body: AnthropicKeyBody):
    """API-Key für die KI-Monatsbewertung. Wird lokal in data/settings.json abgelegt."""
    s = load_settings()
    key = body.api_key.strip()
    if key:
        s["anthropic_api_key"] = key
    else:
        s.pop("anthropic_api_key", None)
    save_settings(s)
    return {"ok": True, "set": bool(key)}


@router.put("/settings/twelve_data_key")
def set_twelve_data_key(body: TwelveDataKeyBody):
    s = load_settings()
    s["twelve_data_api_key"] = body.api_key.strip()
    save_settings(s)
    return {"ok": True}


# ── Kontobezeichnungen ────────────────────────────────────────────────────────
# Bewusst zur Anzeigezeit aufgelöst statt in die Parquet-Datei geschrieben:
# account_label ist Join-Schlüssel für die Umbuchungserkennung, für jeden
# Kontofilter und für das Löschen nach Konto, und es steckt im tx_hash. Ein
# Rename per Datei-Umschreibung wäre eine Migration mit Folgen bis in die
# Duplikaterkennung — ein Label-Mapping ist rückgängig zu machen und kostet nichts.

class AccountLabelBody(BaseModel):
    label: str


def _norm_iban(v: str) -> str:
    return str(v or "").replace(" ", "").upper()


@router.get("/settings/accounts")
def list_accounts():
    """Alle Konten mit roher Bezeichnung, Anzeigename und hinterlegtem Saldo."""
    from ..deps import get_df
    from kapital.finance.storage import load_iban_labels, load_giro_balances

    df = get_df()
    labels = load_iban_labels()
    balances = load_giro_balances()
    by_norm = {_norm_iban(k): v for k, v in (labels or {}).items()}

    out = []
    if not df.empty:
        for raw in sorted(df["account_label"].dropna().unique()):
            display = by_norm.get(_norm_iban(raw)) or str(raw)
            entry = (balances or {}).get(display) or (balances or {}).get(str(raw)) or {}
            out.append({
                "raw_label": str(raw),
                "display_name": display,
                "is_renamed": display != str(raw),
                "n_transactions": int((df["account_label"] == raw).sum()),
                "flow": round(float(df[df["account_label"] == raw]["amount"].sum()), 2),
                "calibrated_balance": entry.get("balance") if isinstance(entry, dict) else None,
            })
    return {"accounts": out}


@router.put("/settings/accounts/{raw_label}/label")
def set_account_label(raw_label: str, body: AccountLabelBody):
    """Konto umbenennen. Schreibt nur data/iban_labels.json."""
    from kapital.finance.storage import load_iban_labels, save_iban_labels

    label = (body.label or "").strip()
    if not label:
        raise HTTPException(400, "Der Name darf nicht leer sein.")
    if len(label) > 60:
        raise HTTPException(400, "Der Name darf höchstens 60 Zeichen haben.")
    if any(ch in label for ch in ("\n", "\r", "\t")):
        raise HTTPException(400, "Der Name darf keine Zeilenumbrüche enthalten.")

    labels = load_iban_labels() or {}
    # Kollision nur verbieten, wenn ein ANDERES Konto den Namen schon trägt.
    # Zwei Bezeichnungen desselben Kontos bewusst auf denselben Namen zu legen
    # ist der Weg, wie Dubletten zusammengeführt werden.
    for k, v in labels.items():
        if v == label and _norm_iban(k) != _norm_iban(raw_label):
            from ..deps import get_df
            df = get_df()
            same = not df.empty and _norm_iban(k)[:10] == _norm_iban(raw_label)[:10]
            if not same:
                raise HTTPException(
                    409, f"Der Name {label!r} wird bereits von einem anderen Konto verwendet."
                )
    labels[raw_label] = label
    save_iban_labels(labels)
    return {"ok": True, "raw_label": raw_label, "display_name": label}


class ExcludedCategoriesBody(BaseModel):
    categories: list[str]


@router.put("/settings/top_expenses_excluded")
def set_top_expenses_excluded(body: ExcludedCategoriesBody):
    """Welche Kategorien in den Top-Ausgaben pauschal ausgeblendet werden.

    Als Liste in settings.json statt fest im Code: Kategorien sind umbenennbar,
    ein hart verdrahteter Name wird am Tag der Umbenennung stillschweigend wirkungslos.
    """
    s = load_settings()
    cats = [str(c).strip() for c in (body.categories or []) if str(c).strip()]
    s["top_expenses_excluded_categories"] = cats
    save_settings(s)
    return {"ok": True, "categories": cats}


# ── Sicherung der Konfiguration ───────────────────────────────────────────────
# Die Buchungen liegen versioniert als Parquet vor. Die HANDARBEIT steckt aber
# in den JSON-Dateien: Regeln, Kontobezeichnungen, Budgets, ISIN-Zuordnungen,
# Abo-Overrides. Genau die waren bisher durch nichts gesichert — und sie sind
# das, was sich nicht aus einem Bankexport wiederherstellen lässt.

_CONFIG_FILES = [
    "custom_rules.json", "custom_categories.json", "iban_labels.json",
    "giro_balances.json", "budgets.json", "abo_overrides.json",
    "isin_tickers.json", "isin_succession.json", "manual_prices.json",
    "depot_snapshot_meta.json",
]
# settings.json enthält API-Schlüssel und wird deshalb nur auf ausdrücklichen
# Wunsch mitgesichert.
_SECRET_FILES = ["settings.json"]


def _data_dir():
    from kapital.finance import storage
    return storage._DATA_DIR


@router.get("/settings/backup")
def download_backup(include_secrets: bool = False):
    """Alle Konfigurationsdateien als eine JSON-Datei."""
    import json as _json
    from datetime import datetime, timezone

    d = _data_dir()
    names = list(_CONFIG_FILES) + (list(_SECRET_FILES) if include_secrets else [])
    payload = {
        "kapital_backup": 1,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "includes_secrets": bool(include_secrets),
        "files": {},
    }
    for name in names:
        f = d / name
        if not f.exists():
            continue
        try:
            payload["files"][name] = _json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            payload.setdefault("skipped", {})[name] = f"{type(exc).__name__}: {exc}"

    body = _json.dumps(payload, indent=2, ensure_ascii=False)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        iter([body]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename=kapital-konfig-{stamp}.json'},
    )


class RestoreBody(BaseModel):
    payload: dict
    dry_run: bool = True


@router.post("/settings/restore")
def restore_backup(body: RestoreBody):
    """Konfiguration zurückspielen. Standardmässig nur ein Bericht.

    Vor dem Schreiben wird der aktuelle Stand daneben gelegt — ein Restore, der
    den bisherigen Zustand vernichtet, ist keine Sicherung, sondern ein zweites
    Risiko.
    """
    import json as _json
    from datetime import datetime
    from kapital.finance.storage import write_json_atomic

    payload = body.payload or {}
    if payload.get("kapital_backup") != 1:
        raise HTTPException(400, "Das sieht nicht nach einer Kapital-Sicherung aus.")
    files = payload.get("files") or {}
    if not isinstance(files, dict) or not files:
        raise HTTPException(400, "Die Sicherung enthält keine Dateien.")

    d = _data_dir()
    allowed = set(_CONFIG_FILES) | set(_SECRET_FILES)
    plan, rejected = [], []
    for name, content in files.items():
        if name not in allowed:
            rejected.append(name)          # keine beliebigen Pfade schreiben
            continue
        cur = d / name
        plan.append({
            "file": name,
            "exists": cur.exists(),
            "entries_new": len(content) if hasattr(content, "__len__") else 1,
        })

    if body.dry_run:
        return {"ok": True, "dry_run": True, "would_write": plan, "rejected": rejected}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = d / f"_restore_backup_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for item in plan:
        name = item["file"]
        cur = d / name
        if cur.exists():
            (backup_dir / name).write_text(cur.read_text(encoding="utf-8"), encoding="utf-8")
        write_json_atomic(cur, files[name])
        written.append(name)

    from ..deps import reload_df
    reload_df()
    return {"ok": True, "dry_run": False, "written": written,
            "rejected": rejected, "previous_state_in": str(backup_dir)}
