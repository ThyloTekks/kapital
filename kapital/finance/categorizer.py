"""
Keyword-based transaction categorizer.

Assigns a category from finance.models.CATEGORIES to each transaction
based on payee name and description.  Rules are checked in priority order;
the first matching rule wins.  Users can override categories in the UI.
"""

from __future__ import annotations

import re
import pandas as pd


# ── Rule table ────────────────────────────────────────────────────────────────
# Each entry: (category, [keywords])  – checked against payee + description (lowercased)
# More specific rules first.

RULES: list[tuple[str, list[str]]] = [
    # ── Income ──────────────────────────────────────────────────────────────
    ("Einkommen", [
        "gehalt", "lohn", "salary", "wages", "gutschrift arbeitgeber",
        "steuererstattung", "kindergeld", "elterngeld", "bafög",
        "rente", "pension", "dividende", "zinsen", "saveback",
    ]),

    # ── Security deposit ────────────────────────────────────────────────────
    ("Kaution", [
        "kaution", "mietkaution", "sicherheitsleistung", "depot kaution",
    ]),

    # ── Investment / Savings ─────────────────────────────────────────────────
    ("Investment & Sparen", [
        "trade republic", "sparplan", "etf", "aktien", "depot",
        "wertpapier", "fonds", "scalable", "dkb broker", "comdirect depot",
        "festgeld", "tagesgeld", "roundup", "round up", "round-up",
    ]),

    # ── Housing ──────────────────────────────────────────────────────────────
    ("Wohnen & Nebenkosten", [
        "miete", "nebenkosten", "hausverwaltung", "stadtwerke", "stromanbieter",
        "gasanbieter", "eon ", "e.on", "vattenfall", "enercity", "swm",
        "wasserwerk", "wasserversorgung", "rundfunkbeitrag", "gez",
        "internet", "dsl", "glasfaser", "telekom", "vodafone", "o2 ",
        "1&1", "unitymedia", "cable", "kabel",
        "heizung", "müll", "abfall", "entsorgung", "grundsteuer",
    ]),

    # ── Groceries ────────────────────────────────────────────────────────────
    ("Lebensmittel", [
        "rewe", "edeka", "aldi", "lidl", "penny", "netto", "kaufland",
        "norma", "real ", "tegut", "billa", "spar ", "dm ", "rossmann",
        "müller ", "aldi süd", "aldi nord", "lebensmittel", "supermarkt",
        "backhaus", "bäckerei", "metzgerei", "fleischerei", "obst",
        "getränke", "biomarkt", "bio company",
    ]),

    # ── Restaurant / Cafe ─────────────────────────────────────────────────────
    ("Restaurant & Cafe", [
        "mcdonalds", "mc donalds", "burger king", "subway", "kfc",
        "pizza", "kebab", "restaurant", "gaststätte", "bistro",
        "cafe ", "kaffee", "starbucks", "backwerk", "nordsee",
        "lieferando", "uber eats", "deliveroo", "wolt", "just eat",
        "domino", "vapiano", "dean david",
    ]),

    # ── Transport ────────────────────────────────────────────────────────────
    ("Transport & Auto", [
        "tankstelle", "aral", "shell", "esso", "bp ", "total ", "jet ",
        "agip", "avgas", "kraftstoff", "benzin", "diesel",
        "db bahn", "deutsche bahn", "s-bahn", "u-bahn", "bvg ", "mvg ",
        "hvv ", "vhh", "rnv ", "kvb ", "bus ", "flixbus", "eurolines",
        "deutschebahn", "db navigator", "bahn.de",
        "uber", "taxi", "free now", "moia", "sixt", "hertz", "europcar",
        "reifen", "kfz", "werkstatt", "autowerkstatt", "tüv", "dekra",
        "parken", "parkhaus", "parkgebühr",
        "flug", "lufthansa", "ryanair", "easyjet", "eurowings",
    ]),

    # ── Health ───────────────────────────────────────────────────────────────
    ("Gesundheit", [
        "apotheke", "pharmacy", "arzt", "zahnarzt", "krankenhaus",
        "krankenkasse", "aok ", "tkk", "barmer", "dak ", "kkh",
        "techniker krankenkasse", "versandapotheke",
        "docmorris", "shop apotheke", "medikament",
        "optiker", "fielmann", "pro optik",
        "fitness", "fitnessstudio", "mcfit", "clever fit", "kieser",
        "sportstudio", "yoga", "wellbeing",
    ]),

    # ── Clothing / Shopping ───────────────────────────────────────────────────
    ("Kleidung & Shopping", [
        "zalando", "amazon", "zara", "h&m ", "hm ", "c&a ", "uniqlo",
        "primark", "about you", "otto ", "otto.de",
        "hugo boss", "adidas", "nike ", "puma ", "deichmann",
        "saturn", "mediamarkt", "media markt", "expert ",
        "ikea", "möbel", "obi ", "baumarkt", "hornbach", "toom",
        "ebay", "ebay-käufer", "aliexpress", "shein",
    ]),

    # ── Entertainment / Leisure ───────────────────────────────────────────────
    ("Unterhaltung & Freizeit", [
        "netflix", "spotify", "apple music", "deezer", "tidal",
        "amazon prime", "disney+", "disney plus", "sky ", "dazn",
        "twitch", "youtube", "patreon",
        "kino", "theater", "konzert", "ticket", "eventim", "ticketmaster",
        "steam", "playstation", "xbox", "nintendo", "gaming",
        "bücher", "thalia", "weltbild", "kindle",
        "verein", "mitgliedsbeitrag", "club ",
    ]),

    # ── Travel ───────────────────────────────────────────────────────────────
    ("Reisen & Urlaub", [
        "booking.com", "airbnb", "hotel", "hostel",
        "holidaycheck", "expedia", "check24 reisen",
        "tui ", "thomas cook", "alltours",
        "mietwagen", "car rental",
    ]),

    # ── Insurance ────────────────────────────────────────────────────────────
    ("Versicherungen", [
        "versicherung", "insurance", "allianz", "generali", "ergo ",
        "huk ", "huk-coburg", "axa ", "zurich", "signal iduna",
        "debeka", "barmenia", "gothaer", "württembergische",
        "haftpflicht", "rechtsschutz", "hausrat", "kfz-versicherung",
    ]),

    # ── Telecommunications ────────────────────────────────────────────────────
    ("Telekommunikation", [
        "telekom", "vodafone", "o2 ", "1&1", "congstar",
        "blau ", "klarmobil", "simyo", "freenet", "mobilfunk",
    ]),

    # ── Fees ─────────────────────────────────────────────────────────────────
    ("Gebühren & Zinsen", [
        "kontoführungsgebühr", "jahresgebühr", "bankgebühr",
        "dispositionskredit", "dispo", "überziehung",
        "mahngebühr", "mahnung", "inkasso",
        "steuer ", "finanzamt",
    ]),
]


def _match(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(kw in t for kw in keywords)


def categorize_row(payee: str, description: str, current_category: str = "Sonstiges") -> str:
    """Return the best-matching category for a single transaction."""
    # Don't override manually-set non-default categories if you want idempotency;
    # here we always re-categorize (caller decides whether to respect existing value).
    combined = f"{payee} {description}"
    for category, keywords in RULES:
        if _match(combined, keywords):
            return category
    return "Sonstiges"


def categorize_df(df: pd.DataFrame, overwrite_manual: bool = False) -> pd.DataFrame:
    """
    Apply categorization pipeline:
      1. Built-in keyword rules  (only on rows still 'Sonstiges' unless overwrite_manual)
      2. Custom user rules        (always applied — user rules win over everything)
    Returns a new DataFrame.
    """
    from .custom_rules import apply_custom_rules, load_rules

    df = df.copy()
    mask = (df["category"] == "Sonstiges") | overwrite_manual
    if mask.any():
        df.loc[mask, "category"] = df.loc[mask].apply(
            lambda r: categorize_row(str(r["payee"]), str(r["description"])), axis=1
        )

    # Custom rules always override (they are more specific than built-ins)
    custom = load_rules()
    if custom:
        df = apply_custom_rules(df, custom)

    return df
