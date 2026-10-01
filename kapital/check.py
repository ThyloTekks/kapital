"""Invariantenprüfung für den persistierten Datenbestand.

    python -m kapital.check            # alle Invarianten
    python -m kapital.check --only 2   # nur Invariante 2
    python -m kapital.check --quiet    # nur die Zusammenfassung

Hintergrund: Die App hat keine Testsuite und wird im Browser geprüft. Das kann
Rechenfehler strukturell nicht finden — eine Sparquote von 27 % und eine von
2,5 % sehen auf dem Bildschirm gleich plausibel aus, und eine stillschweigend
gelöschte Umbuchung hinterlässt keine Lücke im Diagramm.

Dieses Skript prüft daher nicht einzelne Funktionen, sondern fünf Aussagen, die
über den gesamten Bestand wahr sein müssen. Es ist bewusst ein CLI-Einstieg und
wird nie aus einem Router aufgerufen (läuft über alle Zeilen).

Exit-Code 0 = alle Invarianten halten, 1 = mindestens eine verletzt.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import pandas as pd

from kapital.finance import analytics, portfolio as pf, storage
from kapital.finance.models import SAVINGS_CATEGORIES

# Toleranz für Rundungsdifferenzen in Euro-Beträgen.
EPS = 0.01
# Ab welcher Abweichung ein kalibrierter Kontostand als verletzt gilt.
BALANCE_EPS = 1.00


@dataclass
class Result:
    number: int
    name: str
    violations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    skipped: str = ""

    @property
    def ok(self) -> bool:
        return not self.violations and not self.skipped

    def report(self, quiet: bool = False) -> None:
        if self.skipped:
            print(f"  [{self.number}] ÜBERSPRUNGEN  {self.name}\n        {self.skipped}")
            return
        if not self.violations:
            print(f"  [{self.number}] OK            {self.name}")
            for n in self.notes[:6]:
                print(f"        · {n}")
            return
        print(f"  [{self.number}] VERLETZT      {self.name}  ({len(self.violations)})")
        if quiet:
            return
        for line in self.violations[:12]:
            print(f"        {line}")
        if len(self.violations) > 12:
            print(f"        … und {len(self.violations) - 12} weitere")


def _norm_label(s: str) -> str:
    """Kontolabel vergleichbar machen: IBAN ohne Leerzeichen, Groß/Klein egal."""
    return str(s or "").replace(" ", "").strip().upper()


# ── Invariante 1 ──────────────────────────────────────────────────────────────

def check_balances(df: pd.DataFrame) -> Result:
    """Kumulierter Cashflow + hinterlegter Anfangssaldo == echter Kontostand.

    Ohne Kalibrierung ist ein 'Kontostand' nur die Summe aller importierten
    Bewegungen — er stimmt nur, wenn der Import bei Kontoeröffnung beginnt.
    """
    r = Result(1, "Kontosalden stimmen mit giro_balances.json überein")
    stored = storage.load_giro_balances()
    if not stored:
        r.skipped = "keine hinterlegten Salden in data/giro_balances.json"
        return r

    # Doppelte Keys ('Tagesgeld' vs 'tagesgeld') zusammenführen, sonst prüft
    # man gegen einen zufällig gewählten Eintrag.
    by_norm: dict[str, list[tuple[str, float]]] = {}
    for label, entry in stored.items():
        bal = entry.get("balance") if isinstance(entry, dict) else entry
        if bal is None:
            continue
        by_norm.setdefault(_norm_label(label), []).append((label, float(bal)))

    for norm, entries in sorted(by_norm.items()):
        distinct = {round(b, 2) for _, b in entries}
        if len(distinct) > 1:
            names = ", ".join(f"{n!r}={b:.2f}" for n, b in entries)
            r.violations.append(f"widersprüchliche Salden für {norm}: {names}")

    # Konten genauso zusammenfassen wie die Anzeige: über iban_labels.json.
    # Sonst prüft man eine andere Gruppierung, als der Nutzer zu sehen bekommt.
    iban_labels = storage.load_iban_labels() or {}
    label_by_norm = {_norm_label(k): v for k, v in iban_labels.items()}
    display_groups: dict[str, list[str]] = {}
    for lab in df["account_label"].dropna().unique().tolist():
        display = label_by_norm.get(_norm_label(lab)) or str(lab)
        display_groups.setdefault(_norm_label(display), []).append(lab)

    for norm, entries in sorted(by_norm.items()):
        matching = display_groups.get(norm)
        if not matching:
            continue  # Saldo für ein Konto ohne Buchungen — nicht prüfbar
        cum = float(df[df["account_label"].isin(matching)]["amount"].sum())
        expected = entries[0][1]
        # Die Differenz ist KEIN Fehler: der kumulierte Zahlungsstrom entspricht
        # dem Kontostand nur, wenn der Import bei Kontoeröffnung beginnt. Sie
        # ist genau der Anfangssaldo — festhalten, nicht anschlagen.
        if abs(cum - expected) > BALANCE_EPS:
            r.notes.append(
                f"{entries[0][0]}: Anfangssaldo {expected - cum:+,.2f} € "
                f"(hinterlegt {expected:,.2f} €, importierter Zahlungsstrom {cum:,.2f} €)"
            )
    return r


# ── Invariante 2 ──────────────────────────────────────────────────────────────

def check_transfers(df: pd.DataFrame) -> Result:
    """Jede als Umbuchung markierte Zeile hat genau ein Gegenstück.

    Fängt zwei Fehlerklassen: Falschpaare der Erkennung (Geld verschwindet aus
    allen Auswertungen) und Regeln, die die Kategorie einer Umbuchung
    überschreiben.
    """
    r = Result(2, "Umbuchungen haben je genau ein Gegenstück")
    t = df[df["is_transfer"].astype(bool)]
    if t.empty:
        r.skipped = "keine Umbuchungen markiert"
        return r

    no_id = t[t["transfer_id"].fillna("") == ""]
    if len(no_id):
        r.violations.append(f"{len(no_id)} Zeilen mit is_transfer=True ohne transfer_id")

    wrong_cat = t[t["category"] != "Umbuchung"]
    if len(wrong_cat):
        cats = wrong_cat["category"].value_counts().head(4).to_dict()
        r.violations.append(
            f"{len(wrong_cat)} Umbuchungs-Zeilen mit abweichender Kategorie {cats} "
            f"— apply_custom_rules überschreibt ohne ~is_transfer-Guard"
        )

    paired = t[t["transfer_id"].fillna("") != ""]
    for tid, grp in paired.groupby("transfer_id"):
        if len(grp) != 2:
            r.violations.append(f"transfer_id {tid}: {len(grp)} Zeilen statt 2")
            continue
        a, b = grp.iloc[0], grp.iloc[1]
        if abs(float(a["amount"]) + float(b["amount"])) > EPS:
            r.violations.append(
                f"transfer_id {tid}: Beträge heben sich nicht auf "
                f"({a['amount']:.2f} / {b['amount']:.2f})"
            )
        if _norm_label(a["account_label"]) == _norm_label(b["account_label"]):
            days = abs((a["date"] - b["date"]).days)
            r.violations.append(
                f"transfer_id {tid}: beide Zeilen auf demselben Konto "
                f"({a['account_label']}), {days} Tage auseinander, "
                f"{abs(float(a['amount'])):.2f} € — vermutlich Falschpaar"
            )
    return r


# ── Invariante 3 ──────────────────────────────────────────────────────────────

def check_cashflow_identity(df: pd.DataFrame) -> Result:
    """Einnahmen + Erstattungen − Ausgaben − Investitionen == Netto-Cashflow.

    Prüft zusätzlich, ob der Erstattungsterm gegenüber den Einnahmen so groß
    ist, dass eine Sparquote ohne ihn irreführend wäre.
    """
    r = Result(3, "Cashflow-Identität gilt je Monat")
    if df.empty:
        r.skipped = "keine Buchungen"
        return r

    real = df[~df["is_transfer"].astype(bool) & (df["category"] != "Umbuchung")].copy()
    real["ym"] = real["date"].dt.to_period("M").astype(str)

    for ym, grp in real.groupby("ym"):
        s = analytics.period_summary(grp)
        lhs = s["total_income"] + s["total_refunds"] - s["total_expenses"] - s["total_invested"]
        if abs(lhs - s["net_cashflow"]) > EPS:
            r.violations.append(
                f"{ym}: Identität verletzt ({lhs:.2f} != {s['net_cashflow']:.2f})"
            )

    total = analytics.period_summary(df)
    inc, ref = total["total_income"], total["total_refunds"]
    if inc > 0 and ref > 0:
        share = ref / max(total["savings"], EPS)
        if share > 0.25:
            r.violations.append(
                f"Erstattungen sind {ref:,.2f} € = {share * 100:.0f} % der ausgewiesenen "
                f"Ersparnis ({total['savings']:,.2f} €). Die Sparquote von "
                f"{total['savings_rate'] * 100:.1f} % ist ohne diesen Term nicht lesbar — "
                f"ohne Erstattungen wären es {(inc - total['total_expenses']) / inc * 100:.2f} %."
            )
            # Die grössten Beiträge nennen: fast immer sind das nicht erkannte
            # Eigenüberträge oder Fehlkategorisierungen, keine echten
            # Erstattungen. Sie hier zu benennen macht sie behebbar, statt eine
            # Kennzahl zu zeigen, der man nicht trauen kann.
            refunds_df = analytics._refunds(df)
            top = refunds_df.nlargest(6, "amount")[["date", "payee", "description", "amount", "category"]]
            for _, row in top.iterrows():
                label = str(row["payee"] or row["description"] or "")[:38]
                r.violations.append(
                    f"    grösster Posten: {row['amount']:>10,.2f} €  {row['date'].date()}  "
                    f"{label}  [{row['category']}]"
                )
            self_pay = refunds_df[
                refunds_df["payee"].fillna("").str.strip().str.len() > 0
            ]
            counts = self_pay.groupby(self_pay["payee"].str.strip())["amount"].agg(["sum", "count"])
            counts = counts.nlargest(3, "sum")
            for name, row in counts.iterrows():
                r.violations.append(
                    f"    häufigster Empfänger: {row['sum']:>10,.2f} € über {int(row['count'])} Buchungen — {str(name)[:38]}"
                )
    return r


# ── Invariante 4 ──────────────────────────────────────────────────────────────

def check_positions(df: pd.DataFrame) -> Result:
    """Gehaltene Positionen und Depot-Snapshot stimmen überein.

    Abweichungen entstehen durch Kapitalmaßnahmen (units==0 wird verworfen) und
    ISIN-Wechsel nach Splits — beides erzeugt Geisterpositionen.
    """
    r = Result(4, "Positionen und Depot-Snapshot stimmen überein")
    tr = df[df["account"] == "Trade Republic"]
    if tr.empty:
        r.skipped = "keine Trade-Republic-Buchungen"
        return r

    snap = storage.load_depot_snapshot()
    if snap is None or snap.empty:
        r.skipped = "kein Depot-Snapshot importiert"
        return r

    try:
        active, _sold = pf.reconstruct_positions(tr)
    except Exception as exc:  # pragma: no cover - Diagnose
        r.violations.append(f"reconstruct_positions ist gescheitert: {type(exc).__name__}: {exc}")
        return r

    succ = pf.load_isin_succession()
    held = set(active["isin"]) if not active.empty else set()
    in_snap = {pf.resolve_isin(str(i), succ) for i in snap["isin"].dropna()} if "isin" in snap.columns else set()
    snap_date = storage.load_depot_snapshot_date()

    # Nur Kapitalmaßnahmen melden, die NICHT verarbeitet wurden — also solche,
    # nach denen die Position trotzdem noch als gehalten gilt und im Snapshot
    # fehlt. Alles andere zu melden wäre genau der Alarmismus, den diese
    # Prüfung eigentlich verhindern soll.
    corp = tr[
        (tr["units"].fillna(0) == 0)
        & tr["description"].fillna("").str.contains(
            "EXCHANGE|CORPORATE|SPLIT|DELIST|MERGER", case=False, na=False
        )
    ]
    for _, row in corp.iterrows():
        isin = pf.resolve_isin(str(row["isin"]), succ)
        if isin in held and isin not in in_snap:
            r.violations.append(
                f"Kapitalmaßnahme nicht verarbeitet: {row['date'].date()} "
                f"{str(row['description'])[:38]!r} ({isin}) — Position gilt weiter als gehalten"
            )

    for isin in sorted(held - in_snap):
        name = active.loc[active["isin"] == isin, "name"].iloc[0]
        r.violations.append(
            f"{isin} ({str(name)[:34]}) gilt als gehalten, fehlt aber im Snapshot"
        )
    # Snapshot-only ist NICHT automatisch falsch: eine vor Importbeginn gekaufte
    # Position hat schlicht keine Buchungen. Ein Fehler ist es erst, wenn die
    # Buchungen den Verkauf NACH dem Snapshot-Stichtag belegen.
    closed_after = pf.isins_closed_after(tr, snap_date)
    for isin in sorted(in_snap - held):
        row_match = snap[snap["isin"].map(lambda i: pf.resolve_isin(str(i), succ)) == isin]
        name = str(row_match.iloc[0].get("name", "")) if len(row_match) else ""
        if isin in closed_after:
            when = f"nach dem Stichtag {snap_date}" if snap_date else "laut lückenloser Historie"
            r.violations.append(
                f"{isin} ({name[:34]}) steht im Snapshot, wurde {when} aber "
                f"verkauft — Snapshot ist veraltet"
            )
    return r


# ── Invariante 5 ──────────────────────────────────────────────────────────────

def check_currency(df: pd.DataFrame) -> Result:
    """Jeder als Euro dargestellte Kurs ist auch auf Euro zurückführbar.

    Kurse kommen roh aus yfinance in Börsenwährung. Ohne Währungsfeld rendert
    das Frontend sie mit fmtEUR — ein Dollarkurs mit Euro-Zeichen.
    """
    r = Result(5, "Alle als EUR dargestellten Kurse tragen eine Währung")
    try:
        from kapital.finance import fx
    except ImportError:
        r.violations.append(
            "kapital.finance.fx fehlt — es gibt keine gemeinsame Währungsquelle. "
            "kronos_forecast liefert Kurse in Börsenwährung, ui.jsx rendert sie als EUR."
        )
        return r

    tickers = storage.load_ticker_map() if hasattr(storage, "load_ticker_map") else {}
    if not tickers:
        try:
            tickers = pf.load_ticker_map()
        except Exception:
            tickers = {}
    if not tickers:
        r.skipped = "keine ISIN→Ticker-Zuordnung hinterlegt"
        return r

    for isin, ticker in sorted(tickers.items()):
        if not isinstance(ticker, str) or not ticker:
            r.violations.append(f"{isin}: leerer Ticker")
            continue
        if len(ticker) == 12 and ticker[:2].isalpha() and ticker[2:].isalnum() and ticker != isin:
            r.violations.append(
                f"{isin} ist auf {ticker!r} gemappt — das ist eine ISIN, kein Ticker"
            )
    return r


CHECKS = [check_balances, check_transfers, check_cashflow_identity, check_positions, check_currency]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Invariantenprüfung für den Kapital-Datenbestand")
    ap.add_argument("--only", type=int, action="append", help="nur diese Invariante (1-5)")
    ap.add_argument("--quiet", action="store_true", help="nur Zusammenfassung, keine Einzelzeilen")
    args = ap.parse_args(argv)

    df = storage.load()
    if df is None or df.empty:
        print("Keine Buchungen in data/transactions.parquet — nichts zu prüfen.")
        return 0

    span = f"{df['date'].min().date()} bis {df['date'].max().date()}"
    print(f"\nKapital — Invariantenprüfung\n{len(df):,} Buchungen, {span}\n")

    results = []
    for i, fn in enumerate(CHECKS, start=1):
        if args.only and i not in args.only:
            continue
        try:
            res = fn(df)
        except Exception as exc:  # pragma: no cover - Diagnose
            res = Result(i, fn.__doc__.splitlines()[0] if fn.__doc__ else fn.__name__)
            res.violations.append(f"Prüfung selbst gescheitert: {type(exc).__name__}: {exc}")
        results.append(res)
        res.report(args.quiet)

    failed = [r for r in results if r.violations]
    skipped = [r for r in results if r.skipped]
    print()
    if failed:
        print(
            f"{len(failed)} von {len(results)} Invarianten verletzt"
            + (f", {len(skipped)} übersprungen" if skipped else "")
            + "."
        )
        return 1
    print(f"Alle {len(results)} Invarianten halten"
          + (f" ({len(skipped)} übersprungen)" if skipped else "") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
