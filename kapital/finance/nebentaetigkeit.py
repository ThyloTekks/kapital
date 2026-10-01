"""Nebentätigkeit — Einnahmen und Ausgaben einer Tätigkeit je Jahr.

Eine Kategorie wie "Producing" ist in dieser App bisher eine Kategorie unter
zwanzig. Tatsächlich ist sie etwas anderes: eine durchgehende Tätigkeit mit
eigenen Einnahmen, über Jahre, die steuerlich für sich betrachtet wird. Die
Daten dafür liegen längst sauber getrennt vor — es fehlte nur die Sicht darauf.

Diese Auswertung ist an die Einnahmenüberschussrechnung angelehnt: Zufluss
gegen Abfluss, je Kalenderjahr, ohne Bestandsbewertung. Sie ist bewusst KEINE
Steuerberatung und rechnet nichts weg — sie stellt zusammen, was da ist, und
weist auf zwei Punkte hin, bei denen die einfache Zuflussrechnung an ihre
Grenze kommt:

  * Grössere Anschaffungen werden üblicherweise nicht im Jahr des Kaufs voll
    abgezogen, sondern über die Nutzungsdauer verteilt. Ob und wie, entscheidet
    nicht diese App.
  * Über mehrere Jahre anhaltende Verluste wirft das Finanzamt irgendwann die
    Frage auf, ob überhaupt eine Gewinnerzielungsabsicht vorliegt. Deshalb
    steht das kumulierte Ergebnis prominent dabei.
"""
from __future__ import annotations

import logging

import pandas as pd

from . import storage

log = logging.getLogger(__name__)

# Ab welchem Betrag eine Ausgabe als Anschaffung auffällt, die man nicht
# einfach im Jahr des Kaufs voll ansetzt. Bewusst konservativ und als HINWEIS
# gedacht, nicht als Regel — die Grenze hat sich mehrfach geändert und hängt
# an Netto/Brutto und Vorsteuerabzug.
ANSCHAFFUNG_HINWEIS_AB = 800.0


def _rows(df: pd.DataFrame, category: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    r = df[
        (df["category"] == category)
        & ~df["is_transfer"].fillna(False).astype(bool)
    ].copy()
    return r


def jahresuebersicht(df: pd.DataFrame, category: str = "Producing") -> dict:
    """Einnahmen, Ausgaben und Ergebnis je Kalenderjahr."""
    r = _rows(df, category)
    if r.empty:
        return {"category": category, "years": [], "total": 0.0, "n_bookings": 0,
                "hinweise": [], "active": False}

    r["jahr"] = r["date"].dt.year
    years = []
    for jahr, g in r.groupby("jahr"):
        ein = float(g[g["amount"] > 0]["amount"].sum())
        # abs() statt Vorzeichenumkehr: sonst steht bei Jahren ohne Ausgaben
        # ein "-0,00 €" in der Tabelle.
        aus = float(abs(g[g["amount"] < 0]["amount"].sum()))
        years.append({
            "jahr": int(jahr),
            "einnahmen": round(ein, 2),
            "ausgaben": round(aus, 2),
            "ergebnis": round(ein - aus, 2),
            "n": int(len(g)),
        })
    years.sort(key=lambda y: y["jahr"])

    laufend = 0.0
    for y in years:
        laufend += y["ergebnis"]
        y["kumuliert"] = round(laufend, 2)

    hinweise = []

    # Grössere Anschaffungen benennen — sie verzerren das Jahresergebnis der
    # reinen Zuflussrechnung am stärksten.
    gross = r[(r["amount"] < 0) & (r["amount"].abs() >= ANSCHAFFUNG_HINWEIS_AB)]
    for _, row in gross.sort_values("amount").iterrows():
        hinweise.append({
            "art": "anschaffung",
            "jahr": int(row["date"].year),
            "datum": row["date"].strftime("%Y-%m-%d"),
            "betrag": round(float(abs(row["amount"])), 2),
            "wer": str(row.get("payee") or row.get("description") or "")[:60],
            "text": (f"Anschaffung über {abs(float(row['amount'])):,.2f} € — "
                     f"solche Beträge werden meist über die Nutzungsdauer verteilt "
                     f"statt im Kaufjahr voll angesetzt. Das entscheidet dein "
                     f"Steuerberater, nicht diese Auswertung."),
        })

    verlustjahre = [y["jahr"] for y in years if y["ergebnis"] < 0]
    if laufend < 0 and len(years) >= 3:
        hinweise.append({
            "art": "kumuliert",
            "text": (f"Über {len(years)} Jahre steht ein kumuliertes Ergebnis von "
                     f"{laufend:,.2f} € (Verlustjahre: {', '.join(map(str, verlustjahre))}). "
                     f"Bei dauerhaft negativem Ergebnis stellt das Finanzamt die Frage "
                     f"nach der Gewinnerzielungsabsicht."),
        })

    letztes = years[-1]["jahr"] if years else None
    aktuell = pd.Timestamp.today().year
    return {
        "category": category,
        "years": years,
        "total": round(laufend, 2),
        "n_bookings": int(len(r)),
        "first_year": years[0]["jahr"],
        "last_year": letztes,
        "active": bool(letztes is not None and letztes >= aktuell - 1),
        "hinweise": hinweise,
    }


def buchungen(df: pd.DataFrame, category: str = "Producing", jahr: int | None = None) -> list[dict]:
    """Alle Buchungen der Tätigkeit, optional auf ein Jahr begrenzt."""
    r = _rows(df, category)
    if r.empty:
        return []
    if jahr:
        r = r[r["date"].dt.year == int(jahr)]
    out = []
    for _, row in r.sort_values("date", ascending=False).iterrows():
        amt = float(row["amount"])
        out.append({
            "id": str(row["tx_hash"]),
            "datum": row["date"].strftime("%Y-%m-%d"),
            "art": "Einnahme" if amt > 0 else "Ausgabe",
            "wer": str(row.get("payee") or "").strip() or str(row.get("description") or "")[:60],
            "zweck": str(row.get("description") or "")[:120],
            "betrag": round(amt, 2),
            "konto": str(row.get("account_label") or ""),
        })
    return out


def available_categories(df: pd.DataFrame) -> list[str]:
    """Kategorien, die überhaupt Einnahmen UND Ausgaben haben.

    Nur solche taugen als Tätigkeit — eine reine Ausgabenkategorie wie
    'Lebensmittel' ist keine.
    """
    if df is None or df.empty:
        return []
    r = df[~df["is_transfer"].fillna(False).astype(bool)]
    out = []
    for cat, g in r.groupby("category"):
        if cat in ("Umbuchung", "Einkommen"):
            continue
        if (g["amount"] > 0).any() and (g["amount"] < 0).any():
            out.append(str(cat))
    return sorted(out)


def to_csv(df: pd.DataFrame, category: str = "Producing", jahr: int | None = None) -> str:
    """Buchungsliste als CSV — die Vorlage für den Steuerberater."""
    rows = buchungen(df, category, jahr)
    lines = ["Datum;Art;Empfaenger/Zahler;Verwendungszweck;Betrag;Konto"]
    for r in rows:
        zweck = str(r["zweck"]).replace(";", ",").replace("\n", " ")
        wer = str(r["wer"]).replace(";", ",").replace("\n", " ")
        lines.append(
            f'{r["datum"]};{r["art"]};{wer};{zweck};'
            f'{str(r["betrag"]).replace(".", ",")};{r["konto"]}'
        )
    return "\n".join(lines)
