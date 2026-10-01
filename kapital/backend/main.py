"""Kapital FastAPI application."""
import re
import time
import traceback
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from .routers import (
    dashboard, transactions, categories, portfolio,
    forecast, upload, jahresuebersicht, abos, fire, steuer, regeln,
    kronos_forecast, settings, review, monatsabschluss,
)

app = FastAPI(title="Kapital", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in [
    dashboard.router, transactions.router, categories.router,
    portfolio.router, forecast.router, upload.router,
    jahresuebersicht.router, abos.router, fire.router,
    steuer.router, regeln.router, kronos_forecast.router, settings.router,
    review.router, monatsabschluss.router,
]:
    app.include_router(router, prefix="/api")

FRONTEND = Path(__file__).parent.parent / "frontend"


def _json_safe(text: str) -> str:
    """Strip surrogates / non-UTF-8 so the JSON response itself can't fail to render."""
    return text.encode("utf-8", "replace").decode("utf-8")


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    """Garantiert JSON statt Starlettes Plaintext 'Internal Server Error',
    damit das Frontend res.json() nie auf nicht-JSON läuft."""
    tb = traceback.format_exc()
    detail = _json_safe(f"{type(exc).__name__}: {exc}\n{tb[:800]}")
    return JSONResponse(status_code=500, content={"ok": False, "detail": detail})


@app.get("/api/health")
async def health():
    return {"status": "ok"}


_BUILD_TS = str(int(time.time()))

_JSX_SRC_RE = re.compile(r'src="([^"]+\.jsx)"')


def _inject_cache_bust(html: str) -> str:
    """Cache-Buster je Datei aus deren Änderungszeit.

    Vorher stand hier ein einziger Zeitstempel, der beim Import gesetzt wurde.
    Solange der Server lief, änderte sich die URL also nie — eine bearbeitete
    .jsx kam im Browser schlicht nicht an, egal wie oft man neu lädt, weil die
    URL identisch blieb. Nur ein Serverneustart half, und das ist bei einer App
    ohne Build-Schritt genau die falsche Voraussetzung.

    Mit der mtime je Datei ändert sich die URL exakt dann, wenn sich die Datei
    ändert. Neuladen genügt.
    """
    def sub(m):
        name = m.group(1)
        try:
            ts = int((FRONTEND / name).stat().st_mtime)
        except OSError:
            ts = _BUILD_TS
        return f'src="{name}?v={ts}"'

    return _JSX_SRC_RE.sub(sub, html)


def _safe_static(full_path: str) -> Path | None:
    """Resolve a request path inside FRONTEND, or None if it escapes the dir."""
    try:
        resolved = (FRONTEND / full_path).resolve()
        resolved.relative_to(FRONTEND.resolve())  # raises ValueError on traversal
    except (ValueError, OSError):
        return None
    return resolved


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    target = _safe_static(full_path)
    if target is not None and target.is_file() and full_path != "index.html":
        return FileResponse(target)
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(_inject_cache_bust(html))


@app.get("/")
async def root():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(_inject_cache_bust(html))
