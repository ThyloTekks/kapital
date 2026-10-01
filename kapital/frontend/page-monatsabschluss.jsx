// Page: Monatsabschluss — Budget-Vergleich (animiert) + KI-Bewertung

// ── Animations-Helfer ─────────────────────────────────────────────────────────

const useCountUp = (value, { duration = 950, active = true, delay = 0 } = {}) => {
  const [v, setV] = React.useState(0);
  React.useEffect(() => {
    if (!active) { setV(0); return; }
    let raf, t0 = null;
    const step = (t) => {
      if (t0 === null) t0 = t;
      const elapsed = t - t0 - delay;
      if (elapsed < 0) { raf = requestAnimationFrame(step); return; }
      const p = Math.min(1, elapsed / duration);
      setV(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, active, duration, delay]);
  return v;
};

const URTEIL_TONE = {
  stark:        { color: "var(--accent)", label: "Stark" },
  solide:       { color: "#38bdf8",       label: "Solide" },
  durchwachsen: { color: "var(--warn)",       label: "Durchwachsen" },
  schwach:      { color: "var(--neg)",    label: "Schwach" },
  keine_aktivitaet: { color: "var(--muted)", label: "Keine Aktivität" },
};

const SCHAERFE_TONE = { hinweis: "neutral", warnung: "warn", alarm: "neg" };

// ── Eine Kategorie-Zeile mit animiertem Balken ───────────────────────────────

const BudgetBar = ({ row, index, active, onEditTarget }) => {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(String(Math.round(row.ziel)));

  const over = row.status === "over";
  // Farbe nach Dringlichkeit, nicht nach Ja/Nein. Rot ist der materiellen
  // Überschreitung eines SELBST GESETZTEN Ziels vorbehalten — ein Schnitt aus
  // sechs Monaten wird per Definition in etwa der Hälfte der Monate
  // überschritten, das ist kein Alarm. Wenn alles rot ist, sagt Rot nichts.
  const sev = row.severity || (over ? "medium" : "none");
  const sevColor = { high: "var(--neg)", medium: "var(--over)", low: "var(--warn)",
                     unknown: "var(--muted)", none: "var(--accent)" }[sev] || "var(--accent)";
  const sevLabel = { high: "deutlich über Budget", medium: "über dem Schnitt",
                     low: "leicht über dem Schnitt", unknown: "zu wenig Referenz" }[sev] || "";
  const scale = Math.max(row.ist, row.ziel, 1);
  const istPct = (row.ist / scale) * 100;
  const zielPct = (row.ziel / scale) * 100;
  const delay = index * 65;

  const animIst = useCountUp(row.ist, { active, delay });
  const barColor = over ? sevColor : row.status === "under" ? "var(--accent)" : "#38bdf8";

  const submit = () => {
    const val = parseFloat(draft.replace(",", "."));
    onEditTarget(row.category, isNaN(val) ? null : val);
    setEditing(false);
  };

  return (
    <div style={{
      padding: "13px 18px", borderBottom: "1px solid var(--line)",
      opacity: active ? 1 : 0,
      transform: active ? "none" : "translateY(8px)",
      transition: `opacity 0.4s ease ${delay}ms, transform 0.4s cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 9 }}>
        <span style={{ fontSize: 15, width: 20, textAlign: "center" }}>{row.icon}</span>
        <span style={{ fontSize: 13, fontWeight: 500, flex: 1 }}>{row.category}</span>

        {!editing ? (
          <>
            <span style={{ fontSize: 11, color: "var(--muted)" }}>
              Ziel{" "}
              <button
                onClick={() => { setDraft(String(Math.round(row.ziel))); setEditing(true); }}
                title={row.quelle === "manuell" ? "Manuelles Ziel — klicken zum Ändern" : `Ø der letzten ${row.n_ref_months} Monate — klicken für eigenes Ziel`}
                style={{
                  background: "transparent", border: "none", padding: "0 2px",
                  color: row.quelle === "manuell" ? "var(--fg)" : "var(--muted)",
                  fontFamily: "var(--mono)", fontSize: 11, cursor: "pointer",
                  borderBottom: "1px dashed var(--line)",
                }}
              >
                {fmtEUR(row.ziel, { decimals: 0 })}
              </button>
              {row.quelle === "manuell" && <span style={{ color: "var(--accent)" }}> ·fix</span>}
            </span>
            <span style={{
              fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600, minWidth: 92,
              textAlign: "right", color: over ? sevColor : "var(--fg)",
            }}>
              {fmtEUR(animIst, { decimals: 0 })}
            </span>
            <span style={{
              fontFamily: "var(--mono)", fontSize: 11, minWidth: 74, textAlign: "right",
              color: over ? sevColor : "var(--pos)",
            }}>
              {row.delta >= 0 ? "+" : "−"}{fmtEUR(Math.abs(row.delta), { decimals: 0 }).replace("€", "").trim()} €
            </span>
          </>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, color: "var(--muted)" }}>Eigenes Ziel</span>
            <input
              autoFocus value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); if (e.key === "Escape") setEditing(false); }}
              style={{
                width: 78, background: "var(--bg-2)", border: "1px solid var(--accent)",
                borderRadius: 6, padding: "4px 8px", color: "var(--fg)",
                fontFamily: "var(--mono)", fontSize: 12,
              }}
            />
            <Btn size="sm" variant="primary" onClick={submit}>OK</Btn>
            <Btn size="sm" onClick={() => { onEditTarget(row.category, null); setEditing(false); }}>Ø</Btn>
            <Btn size="sm" variant="ghost" onClick={() => setEditing(false)}>×</Btn>
          </div>
        )}
      </div>

      {/* Balken */}
      <div style={{ position: "relative", height: 8, background: "var(--bg-2)", borderRadius: 4, overflow: "visible" }}>
        <div style={{
          height: "100%", borderRadius: 4, background: barColor,
          width: active ? `${istPct}%` : "0%",
          transition: `width 0.75s cubic-bezier(0.16,1,0.3,1) ${delay + 90}ms`,
          boxShadow: sev === "high" ? "0 1px 10px var(--neg-soft)" : "none",
        }} />
        {row.ziel > 0 && (
          <div style={{
            position: "absolute", top: -3, bottom: -3, left: `${zielPct}%`,
            width: 2, background: "var(--fg)", opacity: active ? 0.55 : 0,
            transition: `opacity 0.4s ease ${delay + 500}ms`, borderRadius: 1,
          }} />
        )}
      </div>

      <div style={{ display: "flex", gap: 10, marginTop: 6, fontSize: 10, color: "var(--muted)" }}>
        <span>{row.count} Buchungen</span>
        {row.quelle === "schnitt" && row.n_ref_months > 0 && (
          <span>Ø aus {row.n_ref_months} Monaten{row.n_active_months < row.n_ref_months ? ` (${row.n_active_months} davon mit Ausgaben)` : ""}</span>
        )}
        {over && row.ziel > 0 && (
          <span style={{ color: sevColor, display: "inline-flex", alignItems: "center", gap: 5 }}>
            {/* Nicht nur Farbe: mit Zeichen und Text bleibt die Aussage auch
                ohne Farbunterscheidung lesbar. */}
            <span aria-hidden="true">{sev === "high" ? "▲▲" : sev === "medium" ? "▲" : "△"}</span>
            {Math.round(row.pct * 100)} % des Ziels
            {sevLabel && <span style={{ color: "var(--muted)" }}>· {sevLabel}</span>}
          </span>
        )}
      </div>
    </div>
  );
};

// ── KI-Bewertung ──────────────────────────────────────────────────────────────

const CoachPanel = ({ month, open, onNeedsReview, apiKeySet, onKeySaved }) => {
  const [state, setState] = React.useState({ loading: true });
  const [running, setRunning] = React.useState(false);
  const [elapsed, setElapsed] = React.useState(0);
  const [error, setError] = React.useState(null);
  const [keyInput, setKeyInput] = React.useState("");
  const toast = useToast();

  const fetchExisting = React.useCallback(() => {
    if (!month) return;
    setState({ loading: true });
    fetch(`/api/monatsabschluss/bewertung?month=${month}`)
      .then((r) => r.json())
      .then((d) => setState({ loading: false, ...d }))
      .catch((e) => { setError(e.message); setState({ loading: false }); });
  }, [month]);

  React.useEffect(() => { fetchExisting(); }, [fetchExisting]);

  React.useEffect(() => {
    if (!running) { setElapsed(0); return; }
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  const run = async (force) => {
    setRunning(true); setError(null);
    try {
      const res = await fetch(`/api/monatsabschluss/bewertung?month=${month}&force=${force ? "true" : "false"}`, { method: "POST" });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Bewertung fehlgeschlagen");
      setState({ loading: false, exists: true, stale: false, ...d, api_key_set: true });
      toast("Bewertung erstellt");
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const saveKey = async () => {
    const res = await fetch("/api/settings/anthropic_key", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: keyInput.trim() }),
    });
    if (res.ok) { toast("API-Key gespeichert"); setKeyInput(""); onKeySaved && onKeySaved(); fetchExisting(); }
    else toast("Speichern fehlgeschlagen", "neg");
  };

  // ── Gate: offene Buchungen ──
  if (open > 0) {
    return (
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ fontSize: 26 }}>🔒</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>Bewertung gesperrt</div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3 }}>
              {open} Buchungen in {month} sind noch nicht zugeordnet. Ohne saubere Kategorien
              wäre jede Bewertung Raten.
            </div>
          </div>
          <Btn variant="primary" icon="tag" onClick={onNeedsReview}>Jetzt zuordnen</Btn>
        </div>
      </Card>
    );
  }

  // ── Gate: kein API-Key ──
  if (!apiKeySet && !state.api_key_set) {
    return (
      <Card>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>KI-Bewertung einrichten</div>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6, marginBottom: 14 }}>
          Für die inhaltliche Monatsbewertung braucht Kapital einen Anthropic-API-Key
          (<span style={{ fontFamily: "var(--mono)" }}>console.anthropic.com</span>). Der Key
          bleibt lokal in <span style={{ fontFamily: "var(--mono)" }}>data/settings.json</span>.
          <br />
          Übertragen werden nur aggregierte Daten: Kategorie-Summen, Top-Empfänger, auffällige
          Einzelbuchungen und Depot-Trades — keine IBANs, keine Kontonummern, keine Dateien.
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="password" value={keyInput} onChange={(e) => setKeyInput(e.target.value)}
            placeholder="sk-ant-…"
            style={{
              flex: 1, background: "var(--bg-2)", border: "1px solid var(--line)",
              borderRadius: 8, padding: "8px 12px", color: "var(--fg)",
              fontSize: 12, fontFamily: "var(--mono)",
            }}
          />
          <Btn variant="primary" onClick={saveKey} disabled={!keyInput.trim()}>Speichern</Btn>
        </div>
      </Card>
    );
  }

  // ── Laufende Bewertung ──
  if (running) {
    return (
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "8px 0" }}>
          <div style={{
            width: 34, height: 34, border: "2px solid var(--line)", borderTopColor: "var(--accent)",
            borderRadius: "50%", animation: "spin 0.8s linear infinite", flexShrink: 0,
          }} />
          <div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Claude analysiert {month} …</div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3 }}>
              Kategorien, Vormonatsvergleich und Depot-Trades werden bewertet · {elapsed}s
            </div>
          </div>
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </Card>
    );
  }

  if (state.loading) return <Card><Spinner /></Card>;

  // ── Noch keine Bewertung ──
  if (!state.exists) {
    return (
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>Monat bewerten lassen</div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4, lineHeight: 1.6 }}>
              Claude schaut sich {month} an: Ausgaben gegen deine Ziele, Sparrate im
              Vormonatsvergleich, und was du im Depot gekauft und verkauft hast.
            </div>
            {error && <div style={{ fontSize: 11, color: "var(--neg)", marginTop: 8 }}>{error}</div>}
          </div>
          <Btn variant="primary" icon="sparkles" onClick={() => run(false)}>Bewerten</Btn>
        </div>
      </Card>
    );
  }

  return <CoachResult state={state} error={error} onRerun={() => run(true)} />;
};

// Reine Darstellung der fertigen Bewertung (ohne Laden/Fetch)
const CoachResult = ({ state, error, onRerun }) => {
  const r = (state && state.result) || {};
  const tone = URTEIL_TONE[r.gesamturteil] || URTEIL_TONE.solide;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Urteil */}
      <Card style={{ borderColor: tone.color === "var(--muted)" ? "var(--line)" : `${tone.color}44` }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 20 }}>
          <div style={{ textAlign: "center", flexShrink: 0 }}>
            <ProgressRing
              value={r.punktzahl || 0} max={100} size={74} thickness={6}
              color={tone.color} label={String(r.punktzahl ?? "—")}
            />
            <div style={{ fontSize: 11, color: tone.color, marginTop: 7, fontWeight: 600 }}>{tone.label}</div>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: "-0.01em", lineHeight: 1.35 }}>
              {r.headline}
            </div>
            <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 8, lineHeight: 1.65 }}>
              {r.zusammenfassung}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
              <span style={{ fontSize: 10, color: "var(--muted)", fontFamily: "var(--mono)" }}>
                {state.model} · {state.created_at ? state.created_at.replace("T", " ").slice(0, 16) : ""}
                {state.usage ? ` · ${state.usage.input_tokens}/${state.usage.output_tokens} Tokens` : ""}
              </span>
              {state.stale && <Pill tone="warn">Daten haben sich seither geändert</Pill>}
              <Btn size="sm" icon="refresh" onClick={onRerun}>Neu bewerten</Btn>
            </div>
            {error && <div style={{ fontSize: 11, color: "var(--neg)", marginTop: 8 }}>{error}</div>}
          </div>
        </div>
      </Card>

      {/* Lob & Kritik */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <Card>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--pos)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>
            Das lief gut
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
            {(r.lob || []).map((l, i) => (
              <div key={i} style={{ borderLeft: "2px solid var(--pos)", paddingLeft: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{l.titel}</div>
                <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3, lineHeight: 1.6 }}>{l.text}</div>
              </div>
            ))}
            {!(r.lob || []).length && <div style={{ fontSize: 12, color: "var(--muted)" }}>Nichts hervorzuheben.</div>}
          </div>
        </Card>

        <Card>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--neg)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>
            Das musst du dir ansehen
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
            {(r.kritik || []).map((k, i) => (
              <div key={i} style={{
                borderLeft: `2px solid ${k.schaerfe === "alarm" ? "var(--neg)" : k.schaerfe === "warnung" ? "var(--warn)" : "var(--line)"}`,
                paddingLeft: 12,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{k.titel}</span>
                  <Pill tone={SCHAERFE_TONE[k.schaerfe] || "neutral"}>{k.schaerfe}</Pill>
                  {k.kategorie && <Pill tone="neutral">{k.kategorie}</Pill>}
                </div>
                <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3, lineHeight: 1.6 }}>{k.text}</div>
              </div>
            ))}
            {!(r.kritik || []).length && <div style={{ fontSize: 12, color: "var(--muted)" }}>Keine Kritikpunkte.</div>}
          </div>
        </Card>
      </div>

      {/* Depot */}
      {r.depot && (
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
            <Icon name="portfolio" size={15} stroke="var(--muted)" />
            <span style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)" }}>
              Depot
            </span>
            <Pill tone="neutral">{(URTEIL_TONE[r.depot.urteil] || {}).label || r.depot.urteil}</Pill>
          </div>
          <div style={{ fontSize: 13, color: "var(--fg)", lineHeight: 1.7 }}>{r.depot.text}</div>
        </Card>
      )}

      {/* Maßnahmen */}
      <Card>
        <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", marginBottom: 12 }}>
          Für nächsten Monat
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {(r.massnahmen || []).map((m, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "flex-start", gap: 12,
              padding: "11px 14px", background: "var(--bg-2)", borderRadius: 10,
              border: "1px solid var(--line)",
            }}>
              <div style={{
                width: 20, height: 20, borderRadius: 5, background: "var(--accent)", color: "var(--on-accent)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, fontWeight: 700, flexShrink: 0, marginTop: 1,
              }}>{i + 1}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{m.titel}</div>
                <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3, lineHeight: 1.6 }}>{m.text}</div>
              </div>
              {m.zielwert > 0 && m.kategorie && (
                <Pill tone="accent">{m.kategorie} → {fmtEUR(m.zielwert, { decimals: 0 })}</Pill>
              )}
            </div>
          ))}
        </div>
        {r.frage && (
          <div style={{
            marginTop: 14, padding: "12px 14px", borderRadius: 10,
            background: "var(--warn-soft)", border: "1px solid var(--warn-soft)",
          }}>
            <div style={{ fontSize: 10, color: "var(--warn)", textTransform: "uppercase", letterSpacing: "0.09em", fontWeight: 600 }}>
              Frage an dich
            </div>
            <div style={{ fontSize: 13, marginTop: 5, lineHeight: 1.6 }}>{r.frage}</div>
          </div>
        )}
      </Card>
    </div>
  );
};

// ── Seite ─────────────────────────────────────────────────────────────────────

const PageMonatsabschluss = () => {
  const [months, setMonths] = React.useState([]);
  const [month, setMonth] = React.useState("");
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [animate, setAnimate] = React.useState(false);
  // Standardmässig ALLE Kategorien. Vorher zeigte die Seite nur die über dem
  // Ziel — dadurch bestand die Ansicht per Konstruktion zu 100 % aus
  // Warnfarben, und die Kategorien, in denen man unter dem Schnitt lag, kamen
  // gar nicht vor. Ein Monatsabschluss, der nur Negatives zeigt, ist kein
  // Abschluss, sondern eine Mahnung.
  const [showAll, setShowAll] = React.useState(true);
  const [apiKeySet, setApiKeySet] = React.useState(false);
  const toast = useToast();

  const loadMonths = React.useCallback(() => {
    fetch("/api/monatsabschluss/months")
      .then((r) => r.json())
      .then((d) => {
        setMonths(d.months || []);
        setMonth((cur) => cur || d.last_complete || (d.months[0] || {}).month || "");
      })
      .catch(() => {});
  }, []);

  const loadKey = React.useCallback(() => {
    fetch("/api/settings").then((r) => r.json())
      .then((d) => setApiKeySet(!!d.anthropic_api_key_set)).catch(() => {});
  }, []);

  const loadOverview = React.useCallback(() => {
    if (!month) return;
    setLoading(true); setAnimate(false);
    fetch(`/api/monatsabschluss/uebersicht?month=${month}`)
      .then((r) => r.json())
      .then((d) => {
        setData(d);
        setLoading(false);
        requestAnimationFrame(() => setTimeout(() => setAnimate(true), 40));
      })
      .catch(() => setLoading(false));
  }, [month]);

  React.useEffect(() => { loadMonths(); loadKey(); }, [loadMonths, loadKey]);
  React.useEffect(() => { loadOverview(); }, [loadOverview]);

  const setTarget = async (category, value) => {
    const res = await fetch(`/api/monatsabschluss/ziel/${encodeURIComponent(category)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    });
    if (res.ok) {
      toast(value === null ? `${category}: zurück auf Durchschnitt` : `${category}: Ziel ${fmtEUR(value, { decimals: 0 })}`);
      loadOverview();
    } else toast("Ziel konnte nicht gesetzt werden", "neg");
  };

  const openReview = () => {
    window.dispatchEvent(new CustomEvent("kapital:review", { detail: { months: [month] } }));
  };

  if (loading && !data) return <Spinner />;
  if (!data || data.empty) {
    return <EmptyState icon="calendar" title="Keine Daten" desc="Importiere zuerst Kontoauszüge." />;
  }

  const cats = data.categories || [];
  const over = cats.filter((c) => c.status === "over");
  const rest = cats.filter((c) => c.status !== "over");
  const shown = showAll ? cats : over;
  const totalOver = over.reduce((s, c) => s + c.delta, 0);
  const k = data.kennzahlen || {};
  const prev = data.vormonat;

  return (
    <div style={{ padding: "24px 32px 60px", display: "flex", flexDirection: "column", gap: 18, maxWidth: 1080 }}>
      {/* Monatswahl */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <select
            value={month} onChange={(e) => setMonth(e.target.value)}
            style={{
              background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 8,
              padding: "8px 12px", color: "var(--fg)", fontSize: 13, fontFamily: "var(--mono)",
              cursor: "pointer",
            }}
          >
            {months.map((m) => (
              <option key={m.month} value={m.month}>
                {m.month}{m.open ? `  ·  ${m.open} offen` : ""}{m.has_review ? "  ·  bewertet" : ""}
              </option>
            ))}
          </select>
          {data.open > 0 && (
            <button onClick={openReview} style={{
              display: "inline-flex", alignItems: "center", gap: 7,
              background: "var(--warn-soft)", border: "1px solid var(--warn-soft)",
              color: "var(--warn)", padding: "7px 12px", borderRadius: 8,
              fontSize: 12, cursor: "pointer", fontFamily: "inherit", fontWeight: 500,
            }}>
              <Icon name="bell" size={13} /> {data.open} Buchungen offen — zuordnen
            </button>
          )}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)" }}>
          Ziele: Ø der letzten {data.avg_months} Monate, sofern nicht manuell gesetzt
        </div>
      </div>

      {/* KPI-Kopf */}
      <Card>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 20 }}>
          <Stat label="Einnahmen" value={fmtEUR(k.einnahmen, { decimals: 0 })} />
          <Stat label="Ausgaben" value={fmtEUR(k.ausgaben, { decimals: 0 })}
            delta={prev ? fmtPct(((k.ausgaben - prev.ausgaben) / (prev.ausgaben || 1)) * 100) : null}
            deltaTone={prev && k.ausgaben > prev.ausgaben ? "neg" : "pos"}
            sub="vs. Vormonat" />
          <Stat label="Investiert" value={fmtEUR(k.investiert, { decimals: 0 })} />
          <Stat label="Sparrate" value={fmtPct(k.sparrate * 100, { sign: false })}
            delta={prev ? fmtPct((k.sparrate - prev.sparrate) * 100) : null}
            deltaTone={prev && k.sparrate >= prev.sparrate ? "pos" : "neg"}
            sub="vs. Vormonat" />
        </div>
      </Card>

      {/* Über Ziel */}
      <Card padding={0}>
        <div style={{
          padding: "16px 20px", borderBottom: "1px solid var(--line)",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap",
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>
              {over.length === 0
                ? "Kein Budget gerissen"
                : `${over.length} ${over.length === 1 ? "Kategorie" : "Kategorien"} über Ziel`}
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3 }}>
              {over.length === 0
                ? `Alle Kategorien liegen auf oder unter ihrem Ziel.`
                : <>Zusammen <span style={{ color: "var(--neg)", fontFamily: "var(--mono)", fontWeight: 600 }}>
                    {fmtEUR(totalOver, { decimals: 0 })}
                  </span> mehr als vorgenommen.</>}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Ist / Ziel gesamt</div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 600, marginTop: 2 }}>
                {fmtEUR(data.total_ist, { decimals: 0 })}
                <span style={{ color: "var(--muted)" }}> / {fmtEUR(data.total_ziel, { decimals: 0 })}</span>
              </div>
            </div>
            <Segmented
              size="sm"
              value={showAll ? "alle" : "over"}
              onChange={(v) => setShowAll(v === "alle")}
              options={[{ value: "over", label: `Über Ziel (${over.length})` }, { value: "alle", label: `Alle (${cats.length})` }]}
            />
          </div>
        </div>

        {shown.length === 0 ? (
          <div style={{ padding: "36px 20px", textAlign: "center" }}>
            <div style={{ fontSize: 30, marginBottom: 8 }}>✓</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>Sauberer Monat</div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
              Schalte auf „Alle“, um jede Kategorie zu sehen.
            </div>
          </div>
        ) : (
          shown.map((row, i) => (
            <BudgetBar key={row.category} row={row} index={i} active={animate} onEditTarget={setTarget} />
          ))
        )}

        {!showAll && rest.length > 0 && (
          <div style={{ padding: "11px 20px", fontSize: 11, color: "var(--muted)" }}>
            {rest.length} weitere Kategorien auf oder unter Ziel.
          </div>
        )}
      </Card>

      {/* KI-Bewertung */}
      <CoachPanel
        month={month} open={data.open} apiKeySet={apiKeySet}
        onNeedsReview={openReview} onKeySaved={loadKey}
      />
    </div>
  );
};

window.PageMonatsabschluss = PageMonatsabschluss;
