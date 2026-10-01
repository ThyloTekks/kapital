"""
KI-Monatsbewertung über die Claude API (Anthropic).

Es werden ausschließlich aggregierte Daten übertragen (Kategorie-Summen,
Top-Empfänger, auffällige Einzelbuchungen, Depot-Trades) — keine IBANs,
keine Kontonummern, keine Roh-Dateien.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from .app_settings import load_settings

MODEL = "claude-opus-5"
MAX_TOKENS = 16000

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
REVIEWS_PATH = _DATA_DIR / "coach_reviews.json"


# ── API-Key ───────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    key = (load_settings().get("anthropic_api_key") or "").strip()
    return key or os.environ.get("ANTHROPIC_API_KEY", "").strip()


# ── Persistenz der Bewertungen ────────────────────────────────────────────────

def _load_reviews() -> dict:
    if REVIEWS_PATH.exists():
        try:
            data = json.loads(REVIEWS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_reviews(data: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    REVIEWS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fingerprint(snapshot: dict) -> str:
    raw = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_cached(ym: str) -> dict | None:
    return _load_reviews().get(ym)


def store(ym: str, snapshot: dict, result: dict, usage: dict) -> dict:
    entry = {
        "month": ym,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "fingerprint": fingerprint(snapshot),
        "model": MODEL,
        "result": result,
        "usage": usage,
    }
    data = _load_reviews()
    data[ym] = entry
    _save_reviews(data)
    return entry


def delete(ym: str) -> bool:
    data = _load_reviews()
    if ym in data:
        del data[ym]
        _save_reviews(data)
        return True
    return False


# ── Prompt + Schema ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Du bist der persönliche Finanz-Coach in der App "Kapital". Du bewertest jeden \
abgeschlossenen Monat eines einzelnen Privatanwenders in Deutschland: seine \
Ausgaben, sein Sparverhalten und seine Depot-Transaktionen.

Deine Haltung: fordernd, aber fair. Du bist kein Cheerleader und kein \
Moralapostel. Wenn etwas gut läuft, sagst du das klar und benennst konkret, \
was der Grund war — echtes Lob, kein Trostpflaster. Wenn etwas schlecht läuft, \
sprichst du es direkt an, mit Zahlen statt Andeutungen, und ohne den Menschen \
abzuwerten.

Regeln:
- Schreibe auf Deutsch, per Du, in ganzen Sätzen. Keine Emojis.
- Belege jede Aussage mit einer Zahl aus den Daten. Erfinde nie eine Zahl.
- Beträge in Euro, mit Tausenderpunkt, z. B. "1.240 €".
- Unterscheide Einmaleffekte (Sonderausgaben, Urlaub, Anschaffungen) von \
strukturellen Mustern. Ein teurer Monat wegen einer Autoreparatur ist kein \
Konsumproblem — sag das dann auch.
- Ein Ziel aus der Quelle "schnitt" ist nur der eigene Durchschnitt der \
Vormonate, kein bewusst gesetztes Ziel. Behandle eine Abweichung davon als \
Beobachtung, nicht als Regelbruch. Ein Ziel aus der Quelle "manuell" hat sich \
der User selbst gesetzt — daran darfst du ihn hart messen.
- Beim Depot bewertest du Verhalten, nicht Kursentwicklung: Klumpenrisiken, \
Aktionismus, Verkäufe ohne erkennbaren Grund, Sparplan-Disziplin, \
Diversifikation. Gib keine Kauf- oder Verkaufsempfehlungen für einzelne \
Wertpapiere und keine Prognosen.
- Wenn die Datenlage für eine Aussage zu dünn ist (wenige Referenzmonate, \
kaum Buchungen), sag das offen, statt zu spekulieren.
- Maßnahmen sind konkret und im nächsten Monat umsetzbar. Keine Allgemeinplätze \
wie "weniger ausgeben".
"""

USER_TEMPLATE = """\
Bewerte den Monat {monat}. Hier sind die aggregierten Daten als JSON:

{payload}

Hinweise zur Struktur:
- "kennzahlen": Einnahmen, Ausgaben, Investitionen und Sparrate des Monats. \
"sparrate" ist ein Anteil (0.25 = 25 %).
- "vormonate": dieselben Kennzahlen der Vormonate zum Vergleich.
- "budget.kategorien": Ist gegen Ziel je Kategorie. "ziel_quelle" ist \
"manuell" (selbst gesetzt) oder "schnitt" (Durchschnitt der Referenzmonate). \
"abweichung" > 0 bedeutet mehr ausgegeben als vorgesehen.
- "depot": Käufe und Verkäufe des Monats. Negative Beträge sind Abflüsse.

Vergib eine Punktzahl von 0 bis 100 für den Monat: 0-39 schwach, 40-59 \
durchwachsen, 60-79 solide, 80-100 stark. Gewichte Sparrate und strukturelle \
Ausgabendisziplin höher als einzelne Ausreißer.

Nenne 1 bis 3 Dinge, die gut liefen ("lob"), und 1 bis 4 Dinge, die du \
kritisierst ("kritik"). Wenn ein Monat wirklich gut war, darf "kritik" auch \
nur einen milden Hinweis enthalten — erfinde keine Probleme. Wenn ein Monat \
wirklich schlecht war, muss "lob" nicht geschönt werden.
"""

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "Ein Satz, der den Monat auf den Punkt bringt. Max. 90 Zeichen.",
        },
        "gesamturteil": {
            "type": "string",
            "enum": ["stark", "solide", "durchwachsen", "schwach"],
        },
        "punktzahl": {"type": "integer", "description": "0 bis 100"},
        "zusammenfassung": {
            "type": "string",
            "description": "2 bis 4 Sätze Gesamteinordnung des Monats mit konkreten Zahlen.",
        },
        "lob": {
            "type": "array",
            "description": "1 bis 3 Punkte, die gut liefen.",
            "items": {
                "type": "object",
                "properties": {
                    "titel": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["titel", "text"],
                "additionalProperties": False,
            },
        },
        "kritik": {
            "type": "array",
            "description": "1 bis 4 Kritikpunkte, schärfster zuerst.",
            "items": {
                "type": "object",
                "properties": {
                    "titel": {"type": "string"},
                    "text": {"type": "string"},
                    "kategorie": {
                        "type": "string",
                        "description": "Betroffene Kategorie, oder leerer String.",
                    },
                    "schaerfe": {"type": "string", "enum": ["hinweis", "warnung", "alarm"]},
                },
                "required": ["titel", "text", "kategorie", "schaerfe"],
                "additionalProperties": False,
            },
        },
        "depot": {
            "type": "object",
            "properties": {
                "urteil": {
                    "type": "string",
                    "enum": ["stark", "solide", "durchwachsen", "schwach", "keine_aktivitaet"],
                },
                "text": {
                    "type": "string",
                    "description": "2 bis 4 Sätze zu Käufen, Verkäufen und Sparverhalten.",
                },
            },
            "required": ["urteil", "text"],
            "additionalProperties": False,
        },
        "massnahmen": {
            "type": "array",
            "description": "1 bis 3 konkrete Maßnahmen für den kommenden Monat.",
            "items": {
                "type": "object",
                "properties": {
                    "titel": {"type": "string"},
                    "text": {"type": "string"},
                    "kategorie": {
                        "type": "string",
                        "description": "Betroffene Kategorie, oder leerer String.",
                    },
                    "zielwert": {
                        "type": "number",
                        "description": "Vorgeschlagenes Monatsziel in Euro; 0 wenn keins sinnvoll ist.",
                    },
                },
                "required": ["titel", "text", "kategorie", "zielwert"],
                "additionalProperties": False,
            },
        },
        "frage": {
            "type": "string",
            "description": "Eine unbequeme Rückfrage an den User zu diesem Monat.",
        },
    },
    "required": [
        "headline", "gesamturteil", "punktzahl", "zusammenfassung",
        "lob", "kritik", "depot", "massnahmen", "frage",
    ],
    "additionalProperties": False,
}


# ── API-Aufruf ────────────────────────────────────────────────────────────────

class CoachError(RuntimeError):
    pass


def evaluate(snapshot: dict, effort: str = "high") -> tuple[dict, dict]:
    """Ruft Claude auf und liefert (result, usage). Wirft CoachError bei Problemen."""
    api_key = get_api_key()
    if not api_key:
        raise CoachError(
            "Kein Anthropic-API-Key hinterlegt. Trag ihn unter Einstellungen ein "
            "oder setze die Umgebungsvariable ANTHROPIC_API_KEY."
        )

    try:
        import anthropic
    except ImportError as e:
        raise CoachError(
            "Das Paket 'anthropic' fehlt im venv. Installieren mit: "
            "uv pip install anthropic"
        ) from e

    client = anthropic.Anthropic(api_key=api_key)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)
    user_text = USER_TEMPLATE.format(monat=snapshot.get("monat", ""), payload=payload)

    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": RESULT_SCHEMA},
            },
            messages=[{"role": "user", "content": user_text}],
        ) as stream:
            message = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise CoachError("Anthropic-API-Key ungültig oder abgelaufen.") from e
    except anthropic.RateLimitError as e:
        raise CoachError("Anthropic-Rate-Limit erreicht. Später erneut versuchen.") from e
    except anthropic.APIStatusError as e:
        raise CoachError(f"Anthropic-API-Fehler ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise CoachError("Keine Verbindung zur Anthropic-API. Internetverbindung prüfen.") from e

    if message.stop_reason == "refusal":
        raise CoachError("Die Anfrage wurde vom Modell abgelehnt.")
    if message.stop_reason == "max_tokens":
        raise CoachError("Antwort wurde abgeschnitten (max_tokens). Bitte erneut versuchen.")

    text = next((b.text for b in message.content if b.type == "text"), "")
    if not text:
        raise CoachError("Leere Antwort vom Modell erhalten.")

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise CoachError(f"Antwort war kein gültiges JSON: {e}") from e

    usage = {
        "input_tokens": getattr(message.usage, "input_tokens", 0),
        "output_tokens": getattr(message.usage, "output_tokens", 0),
    }
    return result, usage
