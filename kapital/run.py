"""Start the Kapital app: FastAPI backend + React frontend.

    python -m kapital.run              starten
    python -m kapital.run --reload     starten, Backend-Änderungen laden automatisch neu
    python -m kapital.run --restart    laufende Instanz beenden, dann starten
    python -m kapital.run --stop       nur beenden

`python kapital/run.py` tut exakt dasselbe — die Datei hat einen
__main__-Block, der in beiden Fällen greift.

Zum Beenden im laufenden Terminal genügt Strg+C. Das Terminalfenster
zuzumachen ist der unzuverlässige Weg: je nach Shell bekommt der Prozess kein
SIGTERM, läuft weiter und hält den Port — der nächste Start scheitert dann mit
"address already in use". Genau dafür gibt es hier --restart.
"""
import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser

# Make finance/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uvicorn

PORT = int(os.environ.get("KAPITAL_PORT", "8502"))
HOST = os.getenv("KAPITAL_HOST", "127.0.0.1")


def _port_pids(port: int) -> list[int]:
    """PIDs, die auf diesem Port lauschen (macOS/Linux via lsof)."""
    try:
        out = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for line in out.split():
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid != os.getpid():
            pids.append(pid)
    return pids


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, port))
            return True
        except OSError:
            return False


def stop_running(port: int, quiet: bool = False) -> int:
    """Laufende Instanz beenden. Erst SIGTERM, dann notfalls SIGKILL."""
    pids = _port_pids(port)
    if not pids:
        if not quiet:
            print(f"Auf Port {port} läuft nichts.", flush=True)
        return 0

    for pid in pids:
        print(f"Beende laufende Instanz (PID {pid}) …", flush=True)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError:
            print(f"  Keine Berechtigung für PID {pid} — fremder Prozess?", flush=True)
            continue

    for _ in range(40):                       # bis zu 4 Sekunden auf sauberes Ende warten
        if not _port_pids(port):
            break
        time.sleep(0.1)

    for pid in _port_pids(port):
        print(f"  PID {pid} reagiert nicht auf SIGTERM — SIGKILL.", flush=True)
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    time.sleep(0.3)
    return len(pids)


def _open_browser():
    # Unter --reload startet uvicorn Kindprozesse neu; ohne diese Sperre ginge
    # bei jedem Reload ein neuer Tab auf.
    if os.environ.get("KAPITAL_BROWSER_OPENED") == "1":
        return
    os.environ["KAPITAL_BROWSER_OPENED"] = "1"
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{PORT}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kapital.run", description="Kapital starten")
    ap.add_argument("--reload", action="store_true",
                    help="Backend-Änderungen automatisch neu laden (Frontend geht ohnehin per Reload)")
    ap.add_argument("--restart", action="store_true", help="laufende Instanz beenden, dann starten")
    ap.add_argument("--stop", action="store_true", help="nur die laufende Instanz beenden")
    ap.add_argument("--no-browser", action="store_true", help="keinen Browser öffnen")
    args = ap.parse_args(argv)

    if args.stop:
        stop_running(PORT)
        return 0

    if args.restart:
        stop_running(PORT, quiet=True)

    if not _port_free(PORT):
        pids = _port_pids(PORT)
        pid_txt = f" (PID {', '.join(map(str, pids))})" if pids else ""
        print(f"\nPort {PORT} ist belegt{pid_txt}.", flush=True)
        print("Vermutlich läuft noch eine ältere Instanz — etwa weil ein Terminalfenster", flush=True)
        print("geschlossen wurde, statt den Prozess mit Strg+C zu beenden.\n", flush=True)
        print("  python -m kapital.run --restart      alte beenden und neu starten", flush=True)
        print("  python -m kapital.run --stop         nur beenden", flush=True)
        print(f"  KAPITAL_PORT=8503 python -m kapital.run   auf anderem Port starten\n", flush=True)
        return 1

    if not args.no_browser:
        threading.Thread(target=_open_browser, daemon=True).start()

    if args.reload:
        print("Auto-Reload aktiv: Änderungen an .py-Dateien starten den Server neu.", flush=True)
        print("Frontend-Dateien (.jsx) brauchen ohnehin nur ein Neuladen im Browser.\n", flush=True)

    uvicorn.run(
        "kapital.backend.main:app",
        # Nur lokal binden. Die App hat keine Authentifizierung: unter 0.0.0.0
        # kann jeder im selben Netz alle Buchungen lesen, ein Konto komplett
        # löschen (DELETE /api/transactions/account/{label}) und den
        # hinterlegten API-Key überschreiben. Die CORS-Regel schützt nur
        # Browser, nicht curl. Für bewussten Fernzugriff: KAPITAL_HOST setzen.
        host=HOST,
        port=PORT,
        reload=args.reload,
        reload_dirs=[os.path.dirname(os.path.abspath(__file__))] if args.reload else None,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
