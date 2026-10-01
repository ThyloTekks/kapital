"""Render-Test für die UI-Atome — ohne Browser.

Der Syntaxcheck (jsxcheck.py) findet Tippfehler, aber keine Render-Fehler:
eine undefinierte Variable im JSX fällt erst auf, wenn die Komponente wirklich
gezeichnet wird. Dieses Skript zieht ui.jsx durch Babel und rendert die Atome
serverseitig in einer Duktape-VM.

    /tmp/jsxcheck/bin/python kapital/tools/jsxrender.py

Setup wie bei jsxcheck.py, zusätzlich:
    curl -sSL -o /tmp/react.js \
        https://unpkg.com/react@18.3.1/umd/react.production.min.js
    curl -sSL -o /tmp/react-dom-server-legacy.js \
        https://unpkg.com/react-dom@18.3.1/umd/react-dom-server-legacy.browser.production.min.js
"""
import sys
from pathlib import Path

import dukpy

BABEL = Path("/tmp/babel-standalone.js")
REACT = Path("/tmp/react.js")
REACT_DOM = Path("/tmp/react-dom-server-legacy.js")
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"

# Duktape kennt einige Browser-Globals nicht, die React und die Atome anfassen.
STUBS = """
var self = this, window = this, global = this;
var console = { log: function(){}, warn: function(){}, error: function(){} };
function TextEncoder(){}
TextEncoder.prototype.encode = function(s){ return s; };
var Intl = {
  NumberFormat: function(){ return { format: function(v){ return String(v); } }; },
  DateTimeFormat: function(){ return { format: function(v){ return String(v); } }; }
};
Date.prototype.toLocaleDateString = function(){ return "01.01.2026"; };
Date.prototype.toLocaleString = function(){ return "01.01.2026"; };
var localStorage = { getItem: function(){ return null; }, setItem: function(){} };
var sessionStorage = { getItem: function(){ return null; }, setItem: function(){} };
var document = {
  documentElement: { setAttribute: function(){}, getAttribute: function(){ return "dark"; } },
  addEventListener: function(){}, removeEventListener: function(){}
};
true;
"""

# name -> props (JSON-serialisierbar)
CASES = [
    ("Pill", {"children": "Test"}),
    ("Card", {"children": "Inhalt"}),
    ("Card", {"children": "Inhalt", "level": "primary"}),
    ("Card", {"children": "Inhalt", "level": "quiet"}),
    ("Stat", {"label": "Vermögen", "value": "1.234,00 €"}),
    ("Stat", {"label": "Sparrate", "value": "12 %", "large": True, "tone": "pos"}),
    ("Btn", {"children": "Klick"}),
    ("Spinner", {}),
    ("EmptyState", {"title": "Leer", "desc": "nichts da"}),
    ("WarningStrip", {"warnings": ["Achtung"]}),
    ("Icon", {"name": "bank"}),
]


def main() -> int:
    for f in (BABEL, REACT, REACT_DOM):
        if not f.exists():
            print(f"Fehlt: {f} — siehe Docstring.")
            return 2

    i = dukpy.JSInterpreter()
    i.evaljs(STUBS)
    i.evaljs(REACT.read_text()); i.evaljs("true;")
    i.evaljs(REACT_DOM.read_text()); i.evaljs("true;")
    i.evaljs(BABEL.read_text()); i.evaljs("true;")

    src = (FRONTEND / "ui.jsx").read_text(encoding="utf-8")
    i.evaljs("var __code = Babel.transform(dukpy['src'], {presets:['react']}).code; true;", src=src)
    i.evaljs("eval(__code); true;")

    failed = 0
    for name, props in CASES:
        label = f"{name}({props.get('level') or props.get('tone') or ''})".replace("()", "")
        try:
            html = i.evaljs(
                "var C = eval(dukpy['n']);"
                "ReactDOMServer.renderToStaticMarkup("
                "  React.createElement(C, dukpy['p'], dukpy['p'].children)"
                ");",
                n=name, p=props,
            )
            ok = isinstance(html, str) and len(html) > 0
            print(f"  {'OK    ' if ok else 'LEER  '} {label}")
            if not ok:
                failed += 1
        except Exception as exc:
            failed += 1
            print(f"  FEHLER {label}\n         {str(exc)[:300]}")

    print()
    if failed:
        print(f"{failed} von {len(CASES)} Komponenten fehlerhaft.")
        return 1
    print(f"Alle {len(CASES)} Komponenten rendern.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
