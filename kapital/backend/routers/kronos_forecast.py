"""KI-Kursprognose via Kronos Foundation Model (mini/small/base)."""
import gc
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from ..app_settings import get_twelve_data_key, normalize_ticker

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
KRONOS_DIR = Path(__file__).parent.parent / "kronos_model"

_MODELS = {
    "mini":  {"model": "NeoQuasar/Kronos-mini",  "tokenizer": "NeoQuasar/Kronos-Tokenizer-2k",  "params": "4M"},
    "small": {"model": "NeoQuasar/Kronos-small", "tokenizer": "NeoQuasar/Kronos-Tokenizer-2k",  "params": "25M"},
    "base":  {"model": "NeoQuasar/Kronos-base",  "tokenizer": "NeoQuasar/Kronos-Tokenizer-base", "params": "100M"},
}

# Höchstens so viele Modelle gleichzeitig im RAM halten (Eviction-Limit).
_MAX_CACHED_MODELS = 1
_predictor_cache: dict = {}  # key → KronosPredictor


def _load_predictor(model_key: str = "small"):
    if model_key in _predictor_cache:
        return _predictor_cache[model_key]

    cfg = _MODELS.get(model_key)
    if cfg is None:
        raise ValueError(f"Unknown model key: {model_key}")

    # Eviction: ältestes Modell entladen, bevor ein neues geladen wird.
    while len(_predictor_cache) >= _MAX_CACHED_MODELS:
        old_key = next(iter(_predictor_cache))
        del _predictor_cache[old_key]
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    if str(KRONOS_DIR.parent) not in sys.path:
        sys.path.insert(0, str(KRONOS_DIR.parent))

    from kapital.backend.kronos_model import KronosTokenizer, Kronos, KronosPredictor

    tokenizer = KronosTokenizer.from_pretrained(cfg["tokenizer"])
    model = Kronos.from_pretrained(cfg["model"])
    predictor = KronosPredictor(model, tokenizer, max_context=512)
    _predictor_cache[model_key] = predictor
    return predictor


def _twelve_data_search(isin: str, api_key: str) -> str | None:
    """Search Twelve Data for a ticker and return it in yfinance format."""
    try:
        import urllib.request
        url = f"https://api.twelvedata.com/symbol_search?symbol={isin}&apikey={api_key}"
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        results = data.get("data", [])
        for item in results:
            symbol = item.get("symbol", "")
            exchange = item.get("exchange", "")
            if symbol:
                raw = f"{symbol}:{exchange}" if exchange else symbol
                return normalize_ticker(raw)  # → yfinance-Format (z. B. AEEM.PA)
    except Exception:
        pass
    return None


def _twelve_data_history(ticker: str, api_key: str, lookback: int) -> pd.DataFrame | None:
    """Fetch OHLCV history from Twelve Data. Returns DataFrame indexed by date."""
    try:
        import urllib.request
        # Reines Symbol für Twelve Data extrahieren (yfinance-Suffix entfernen).
        symbol = ticker
        for sep in (":", "."):
            if sep in symbol:
                symbol = symbol.split(sep, 1)[0]
        url = (
            f"https://api.twelvedata.com/time_series?symbol={symbol}"
            f"&interval=1day&outputsize={lookback}&apikey={api_key}"
        )
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        values = data.get("values")
        if not values:
            return None
        rows = []
        for v in reversed(values):  # API returns newest-first
            rows.append({
                "date": pd.Timestamp(v["datetime"]),
                "open": float(v["open"]),
                "high": float(v["high"]),
                "low": float(v["low"]),
                "close": float(v["close"]),
            })
        df = pd.DataFrame(rows).set_index("date")
        return df if len(df) >= 30 else None
    except Exception:
        return None


def _pick_best_quote(quotes: list) -> str | None:
    """Wähle aus yf.Search-Quotes das beste Listing: ETF/EQUITY + .DE bevorzugt."""
    candidates = [q for q in (quotes or []) if q.get("symbol")]
    if not candidates:
        return None

    def score(q: dict) -> int:
        sym = q.get("symbol", "") or ""
        qtype = (q.get("quoteType") or "").upper()
        s = 0
        if qtype == "ETF":
            s += 30
        elif qtype == "EQUITY":
            s += 20
        if sym.endswith(".DE"):
            s += 10
        elif sym.endswith((".AS", ".PA", ".L")):
            s += 5
        elif "." not in sym:
            s += 3  # US-Listing ohne Suffix
        return s

    return max(candidates, key=score).get("symbol")


def _resolve_ticker(isin: str) -> str | None:
    """Resolve ISIN to yfinance ticker.

    Priorität:
    1. Gespeichertes Mapping in isin_tickers.json (alte SYMBOL:EXCHANGE-Einträge
       werden automatisch ins yfinance-Format normalisiert)
    2. yfinance Search (bestes ETF/EQUITY-Listing, .DE bevorzugt)
    3. Twelve Data Symbol Search (yfinance-Format, persistiert)
    4. ISIN direkt als Ticker (optimistisch, ohne Extra-Download)
    """
    # 1. Gespeichertes Mapping
    ticker_file = DATA_DIR / "isin_tickers.json"
    if ticker_file.exists():
        try:
            mapping = json.loads(ticker_file.read_text())
        except Exception:
            mapping = {}
        if mapping.get(isin):
            return normalize_ticker(mapping[isin])

    # 2. yfinance Search
    try:
        import yfinance as yf
        best = _pick_best_quote(yf.Search(isin, max_results=10).quotes)
        if best:
            _persist_ticker(isin, best)
            return best
    except Exception:
        pass

    # 3. Twelve Data Symbol Search
    api_key = get_twelve_data_key()
    if api_key:
        ticker = _twelve_data_search(isin, api_key)
        if ticker:
            _persist_ticker(isin, ticker)
            return ticker

    # 4. ISIN direkt (optimistisch – der eigentliche Download im Forecast validiert).
    #    Kein zusätzlicher Probe-Download, um doppeltes Laden zu vermeiden.
    return isin


def _persist_ticker(isin: str, ticker: str) -> None:
    """Save auto-discovered ISIN→ticker mapping so it survives restarts."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ticker_file = DATA_DIR / "isin_tickers.json"
    mapping: dict = {}
    if ticker_file.exists():
        try:
            mapping = json.loads(ticker_file.read_text())
        except Exception:
            pass
    mapping[isin] = ticker
    ticker_file.write_text(json.dumps(mapping, indent=2, ensure_ascii=False))


@router.get("/kronos/models")
def kronos_models():
    return {"models": [
        {"key": k, "params": v["params"], "hf_model": v["model"]}
        for k, v in _MODELS.items()
    ]}


@router.get("/kronos/forecast")
def kronos_forecast(isin: str, days: int = 30, lookback: int = 120, model: str = "small"):
    """
    Fetch OHLCV history for the given ISIN and return a Kronos price forecast.

    Returns:
        historical: last `lookback` daily candles (date, open, high, low, close)
        forecast:   next `days` predicted candles
        ticker:     resolved yfinance ticker
    """
    if days < 5 or days > 90:
        raise HTTPException(400, "days must be between 5 and 90")
    if lookback < 30 or lookback > 500:
        raise HTTPException(400, "lookback must be between 30 and 500")
    if model not in _MODELS:
        raise HTTPException(400, f"model must be one of: {list(_MODELS.keys())}")

    ticker = _resolve_ticker(isin)
    if ticker is None:
        raise HTTPException(404, f"Kein Ticker für ISIN {isin} gefunden. Bitte in Einstellungen → ISIN/Ticker hinterlegen.")

    raw = None
    data_source = "yfinance"
    yf_error = None
    try:
        import yfinance as yf
        _raw = yf.download(ticker, period="2y", interval="1d", auto_adjust=True, progress=False)
        if _raw is not None and len(_raw) >= 30:
            if isinstance(_raw.columns, pd.MultiIndex):
                _raw.columns = [c[0].lower() for c in _raw.columns]
            else:
                _raw.columns = [c.lower() for c in _raw.columns]
            raw = _raw[["open", "high", "low", "close"]].dropna()
            raw.index = pd.to_datetime(raw.index).tz_localize(None)
        else:
            yf_error = "keine/zu wenige Daten zurückgegeben"
    except Exception as e:
        yf_error = f"{type(e).__name__}: {e}"

    # Fallback: Twelve Data
    api_key = get_twelve_data_key()
    if raw is None or len(raw) < 30:
        if api_key:
            raw = _twelve_data_history(ticker, api_key, lookback + 30)
            data_source = "twelvedata"

    if raw is None or len(raw) < 30:
        reasons = [f"yfinance ({yf_error or 'keine Daten'})"]
        reasons.append("Twelve Data ohne API-Key" if not api_key else "Twelve Data ohne ausreichende Daten")
        raise HTTPException(
            502,
            f"Zu wenig Kursdaten für {ticker}. Quellen: " + ", ".join(reasons) + ".",
        )

    # ── Währung ───────────────────────────────────────────────────────────────
    # yfinance liefert Kurse in Börsenwährung. Ohne diesen Schritt rendert das
    # Frontend einen Dollarkurs mit Euro-Zeichen (AMAT: 468 "€" statt ~390 €).
    from kapital.finance import fx
    native_ccy = fx.detect_currency(ticker) if data_source == "yfinance" else None
    raw, currency, fx_rate = fx.convert_frame(raw, native_ccy or "EUR")
    fx_note = None
    if native_ccy and native_ccy != "EUR" and fx_rate is None:
        fx_note = (
            f"Kein EUR-Kurs für {native_ccy} verfügbar — Werte sind in {native_ccy} "
            f"angegeben, nicht umgerechnet."
        )

    # Use at most `lookback` rows
    hist = raw.tail(lookback).copy()
    x_ts = pd.Series(hist.index)

    # Future business days
    last_date = hist.index[-1]
    y_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=days)
    y_ts = pd.Series(y_dates)

    try:
        predictor = _load_predictor(model)
        pred_df = predictor.predict(
            df=hist,
            x_timestamp=x_ts,
            y_timestamp=y_ts,
            pred_len=days,
            sample_count=3,   # average over 3 samples for stability
            verbose=False,
        )
    except Exception as e:
        raise HTTPException(500, f"Kronos-Inferenz fehlgeschlagen: {e}")

    def _rows(df: pd.DataFrame, cols=("open", "high", "low", "close")) -> list:
        return [
            {"date": str(idx.date()), **{c: round(float(row[c]), 4) for c in cols}}
            for idx, row in df.iterrows()
        ]

    # Return last 60 days for display + forecast
    display_hist = hist.tail(60)
    return {
        "ticker": ticker,
        "isin": isin,
        "model": model,
        "data_source": data_source,
        # currency sagt dem Frontend, wie es formatieren darf. Ohne dieses Feld
        # ist jede Zahl hier eine Behauptung ohne Einheit.
        "currency": currency,
        "native_currency": native_ccy or currency,
        "fx_rate": round(fx_rate, 6) if fx_rate else None,
        "warnings": [fx_note] if fx_note else [],
        "historical": _rows(display_hist),
        "forecast": _rows(pred_df),
    }


@router.get("/kronos/status")
def kronos_status():
    return {"loaded_models": list(_predictor_cache.keys())}
