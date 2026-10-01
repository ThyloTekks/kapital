"""
Unified transaction data model for the finance analyzer.

DataFrame schema:
  date           datetime64[ns]
  amount         float  (negative = Ausgabe, positive = Einnahme)
  description    str    (Verwendungszweck / Buchungstext)
  payee          str    (Auftraggeber / Empfänger)
  account        str    Konto-Typ: "Giro" | "Trade Republic" | "PayPal"
  account_label  str    Benutzer-Label: z.B. "ING Girokonto", "ING Tagesgeld"
  category       str    (see CATEGORIES)
  is_transfer    bool
  transfer_id    str    shared ID for matched transfer pairs
  tx_hash        str    stable fingerprint for deduplication
  notes          str
"""

from __future__ import annotations

import json
from pathlib import Path

ACCOUNT_GIRO = "Giro"
ACCOUNT_TR = "Trade Republic"
ACCOUNT_PAYPAL = "PayPal"

ACCOUNT_TYPES = [ACCOUNT_GIRO, ACCOUNT_TR, ACCOUNT_PAYPAL]

# Built-in categories — never removed
_BASE_CATEGORIES = [
    "Einkommen",
    "Lebensmittel",
    "Restaurant & Cafe",
    "Wohnen & Nebenkosten",
    "Transport & Auto",
    "Gesundheit",
    "Kleidung & Shopping",
    "Unterhaltung & Freizeit",
    "Reisen & Urlaub",
    "Versicherungen",
    "Telekommunikation",
    "Investment & Sparen",
    "Vermögensaufbau",
    "Kaution",
    "Darlehen & Rückzahlung",
    "Umbuchung",
    "Gebühren & Zinsen",
    "Sonstiges",
]

# Categories treated as "savings" in the analytics (not counted as living expenses)
SAVINGS_CATEGORIES = {"Investment & Sparen", "Vermögensaufbau"}

# Geliehenes Geld und seine Tilgung. Wird wie eine Umbuchung behandelt und
# taucht in keiner wirtschaftlichen Auswertung auf.
#
# Der Grund: eine Tilgung ist KEIN Einkommen und KEINE Erstattung — es ist
# eigenes Geld, das zurückkommt. Als Erstattung gezählt senkt sie die Ausgaben
# und erzeugt damit Ersparnis, die es nie gab. Derselbe Denkfehler wie bei den
# nicht erkannten Eigenüberträgen: eine Bilanzbewegung in einer
# Gewinn-und-Verlust-Rechnung.
LOAN_CATEGORY = "Darlehen & Rückzahlung"

# Kategorien, die aus JEDER wirtschaftlichen Betrachtung fallen.
NON_ECONOMIC_CATEGORIES = {"Umbuchung", LOAN_CATEGORY}

_CUSTOM_PATH = Path(__file__).parent.parent.parent / "data" / "custom_categories.json"


def load_custom_categories() -> list[str]:
    if _CUSTOM_PATH.exists():
        try:
            data = json.loads(_CUSTOM_PATH.read_text())
            return [c for c in data if c and c not in _BASE_CATEGORIES]
        except Exception:
            pass
    return []


def save_custom_categories(custom: list[str]) -> None:
    _CUSTOM_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_PATH.write_text(json.dumps(custom, ensure_ascii=False, indent=2))


def get_categories() -> list[str]:
    """Return full category list: built-ins + user-defined."""
    return _BASE_CATEGORIES + load_custom_categories()


# Module-level CATEGORIES kept for backwards compatibility;
# call get_categories() where the live list is needed.
CATEGORIES = get_categories()

COLUMNS = [
    "date", "amount", "description", "payee",
    "account", "account_label",
    "category", "is_transfer", "transfer_id", "tx_hash", "notes",
    "is_sonderausgabe",  # bool – one-time / special expense flag
    # Portfolio fields (only populated for buy/sell/dividend transactions)
    "isin",   # str  – ISIN of the security
    "units",  # float – number of shares/units (positive=buy, negative=sell)
    "price_per_unit",  # float – execution price in EUR
]
