from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..deps import get_df, set_df
from kapital.finance.custom_rules import load_rules, save_rules, add_rule, delete_rule, apply_custom_rules
from kapital.finance import storage

router = APIRouter()


class RuleCreate(BaseModel):
    pattern: str
    category: str
    field: str = "both"


@router.get("/regeln")
def get_rules():
    rules = load_rules()
    df = get_df()
    # Count matches per rule
    for r in rules:
        if not df.empty:
            pattern = r["pattern"].lower()
            field = r.get("field", "both")
            if field == "payee":
                mask = df["payee"].str.lower().str.contains(pattern, na=False, regex=False)
            elif field == "description":
                mask = df["description"].str.lower().str.contains(pattern, na=False, regex=False)
            else:
                mask = (
                    df["payee"].str.lower().str.contains(pattern, na=False, regex=False) |
                    df["description"].str.lower().str.contains(pattern, na=False, regex=False)
                )
            r["count"] = int(mask.sum())
        else:
            r["count"] = 0
    return rules


@router.post("/regeln")
def create_rule(body: RuleCreate):
    if not body.pattern.strip():
        raise HTTPException(400, "Stichwort darf nicht leer sein")
    updated = add_rule(body.pattern.strip(), body.category, body.field)
    # Apply to all transactions
    df = get_df()
    if not df.empty:
        df = apply_custom_rules(df, updated)
        storage.save(df)
        set_df(df)
    return {"ok": True, "rules": updated}


@router.delete("/regeln/{pattern}")
def remove_rule(pattern: str, field: str = "both"):
    rules = load_rules()
    found = any(r["pattern"].lower() == pattern.lower() and r.get("field", "both") == field for r in rules)
    if not found:
        raise HTTPException(404, "Regel nicht gefunden")
    updated = delete_rule(pattern, field)
    return {"ok": True, "rules": updated}


@router.post("/regeln/apply")
def apply_rules():
    """Re-apply all custom rules to every transaction."""
    rules = load_rules()
    df = get_df()
    if df.empty:
        return {"ok": True, "affected": 0}
    df = apply_custom_rules(df, rules)
    storage.save(df)
    set_df(df)
    return {"ok": True, "affected": len(df)}
