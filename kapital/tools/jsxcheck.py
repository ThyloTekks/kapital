"""Syntaxprüfung für die .jsx-Dateien — ohne Browser, ohne Build-Schritt.

Die Frontend-Dateien werden nie kompiliert; ein Syntaxfehler zeigt sich sonst
erst in der Browser-Konsole. Dieses Skript schickt jede Datei durch dasselbe
Babel, das auch die App lädt, in einer Duktape-VM.

    /tmp/jsxcheck/bin/python kapital/tools/jsxcheck.py [dateien...]

Setup (einmalig, siehe CLAUDE.md):
    uv venv /tmp/jsxcheck && VIRTUAL_ENV=/tmp/jsxcheck uv pip install dukpy
    curl -sSL -o /tmp/babel-standalone.js \
        https://unpkg.com/@babel/standalone@7.29.0/babel.min.js
"""
import json
import sys
from pathlib import Path

import dukpy

BABEL = Path("/tmp/babel-standalone.js")
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def main(argv: list[str]) -> int:
    if not BABEL.exists():
        print(f"Babel fehlt unter {BABEL} — siehe Docstring für das Setup.")
        return 2

    files = [Path(a) for a in argv] if argv else sorted(FRONTEND.glob("*.jsx"))
    if not files:
        print("Keine .jsx-Dateien gefunden.")
        return 2

    interp = dukpy.JSInterpreter()
    # Duktape kennt einige Browser-Globals nicht, die Babel beim Laden anfasst.
    interp.evaljs("var self = this; var window = this; var global = this;")
    interp.evaljs(BABEL.read_text());  # noqa: E702 - Ergebnis bewusst verworfen
    interp.evaljs("true;")

    failed = 0
    for f in files:
        src = f.read_text(encoding="utf-8")
        try:
            interp.evaljs(
                "Babel.transform(dukpy['src'], {presets:['react']}).code.length;",
                src=src,
            )
            print(f"  OK        {f.name}")
        except Exception as exc:
            failed += 1
            msg = str(exc).replace("\\n", "\n")
            print(f"  FEHLER    {f.name}\n            {msg[:400]}")

    print()
    if failed:
        print(f"{failed} von {len(files)} Dateien mit Syntaxfehler.")
        return 1
    print(f"Alle {len(files)} Dateien sind syntaktisch in Ordnung.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
