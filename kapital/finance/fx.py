"""Währungsumrechnung — die einzige Quelle dafür in der App.

Vorher gab es zwei Kurspfade: `portfolio.fetch_prices` rechnete korrekt über
`EUR{WÄHRUNG}=X` um, `kronos_forecast` gar nicht. Das Frontend rendert beide mit
`fmtEUR`. Ergebnis: ein Applied-Materials-Kurs von 468 USD wurde als „468,00 €"
angezeigt, während der echte Kurs bei ~390 € lag — kein Spread, sondern eine
fehlende Dimension.

Grundregel hier: **lieber die Fremdwährung ehrlich anzeigen als einen falschen
Euro-Betrag.** Ein Kurs mit falschem Währungszeichen ist schlimmer als kein Kurs,
weil er plausibel aussieht.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

# Kurse ändern sich für unsere Zwecke langsam; ein Cache pro Prozess reicht und
# verhindert, dass ein Portfolio-Aufruf mit 24 Positionen 24 FX-Abfragen macht.
_TTL_SECONDS = 15 * 60
_cache: dict[str, tuple[float, float]] = {}  # währung → (kurs, timestamp)


class FxUnavailable(RuntimeError):
    """Kein Umrechnungskurs verfügbar — Betrag bleibt in Fremdwährung."""


def _now() -> float:
    return time.monotonic()


def clear_cache() -> None:
    _cache.clear()


def get_rate(currency: str) -> float | None:
    """Wie viele Einheiten `currency` kostet 1 EUR? None, wenn unbekannt.

    EUR selbst ist immer 1.0. Für alles andere wird `EUR{currency}=X` abgefragt.
    """
    cur = (currency or "").strip().upper()
    if not cur or cur == "EUR":
        return 1.0

    hit = _cache.get(cur)
    if hit and (_now() - hit[1]) < _TTL_SECONDS:
        return hit[0]

    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance nicht installiert — keine Währungsumrechnung möglich")
        return None

    try:
        rate = yf.Ticker(f"EUR{cur}=X").fast_info.last_price
        rate = float(rate) if rate else None
    except Exception as exc:
        log.warning("FX-Kurs EUR%s=X nicht abrufbar: %s: %s", cur, type(exc).__name__, exc)
        return None

    if not rate or rate <= 0:
        log.warning("FX-Kurs EUR%s=X lieferte keinen brauchbaren Wert (%r)", cur, rate)
        return None

    _cache[cur] = (rate, _now())
    return rate


def get_rates(currencies) -> dict[str, float | None]:
    """Mehrere Währungen auf einmal — eine Abfrage je *distinkter* Währung.

    Das ist der Grund, warum diese Funktion existiert: ein Depot mit 24
    Positionen hat typischerweise zwei bis drei Währungen, nicht 24.
    """
    return {c: get_rate(c) for c in {(c or "EUR").strip().upper() for c in currencies}}


def to_eur(value: float | None, currency: str, rate: float | None = None) -> float | None:
    """Betrag nach EUR umrechnen. None, wenn das nicht seriös möglich ist."""
    if value is None:
        return None
    cur = (currency or "EUR").strip().upper()
    if cur == "EUR":
        return float(value)
    if rate is None:
        rate = get_rate(cur)
    if not rate:
        return None
    return float(value) / rate


def convert_frame(df, currency: str, columns=("open", "high", "low", "close")):
    """OHLC-Kursreihe nach EUR umrechnen.

    Rückgabe: (frame, verwendete_währung, kurs_oder_None).
    Schlägt die Umrechnung fehl, kommt der Frame **unverändert** zurück und die
    Währung ist die Originalwährung — der Aufrufer muss sie dann auch so
    beschriften, statt ein Euro-Zeichen davorzusetzen.
    """
    cur = (currency or "EUR").strip().upper()
    if cur == "EUR":
        return df, "EUR", 1.0

    rate = get_rate(cur)
    if not rate:
        log.warning("Kurse bleiben in %s — kein EUR-Kurs verfügbar", cur)
        return df, cur, None

    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = out[col] / rate
    return out, "EUR", rate


def detect_currency(ticker: str) -> str | None:
    """Börsenwährung eines Tickers laut yfinance. None, wenn unbekannt."""
    if not ticker:
        return None
    try:
        import yfinance as yf
        cur = getattr(yf.Ticker(ticker).fast_info, "currency", None)
        return str(cur).upper() if cur else None
    except Exception as exc:
        log.warning("Währung für %s nicht ermittelbar: %s: %s", ticker, type(exc).__name__, exc)
        return None
