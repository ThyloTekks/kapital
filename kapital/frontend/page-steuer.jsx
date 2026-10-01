// Page: Steuervorbereitung


// ── Nebentätigkeit ───────────────────────────────────────────────────────────
// "Producing" war bisher eine Kategorie unter zwanzig. Tatsächlich ist es eine
// durchgehende Tätigkeit mit eigenen Einnahmen über neun Jahre — steuerlich
// wird sie für sich betrachtet. Die Daten lagen längst getrennt vor, es fehlte
// nur die Sicht darauf.
//
// Bewusst KEINE Steuerberatung: die Auswertung rechnet nichts weg, sondern
// stellt Zufluss gegen Abfluss je Jahr und benennt die zwei Stellen, an denen
// die einfache Rechnung an ihre Grenze kommt.
const Nebentaetigkeit = () => {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState("");
  const [jahr, setJahr] = React.useState(0);
  const [showBuchungen, setShowBuchungen] = React.useState(false);

  const load = React.useCallback((cat) => {
    setLoading(true); setErr("");
    const params = new URLSearchParams();
    if (cat) params.set("category", cat);
    if (jahr) params.set("jahr", String(jahr));
    fetch(`/api/nebentaetigkeit?${params}`)
      .then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`);
        return j;
      })
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setErr(e.message); setLoading(false); });
  }, [jahr]);

  React.useEffect(() => { load(); }, [load]);

  const changeCategory = (cat) => {
    fetch("/api/nebentaetigkeit/config", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: cat }),
    }).then(() => load(cat)).catch(() => load(cat));
  };

  if (loading && !data) return <Card><Spinner /></Card>;
  if (err && !data) return <Card><EmptyState icon="info" title="Nicht ladbar" desc={err} /></Card>;
  if (!data || !data.years.length) return null;

  const maxAbs = Math.max(...data.years.map(y => Math.max(y.einnahmen, y.ausgaben)), 1);

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap", marginBottom: 4 }}>
        <div>
          <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Nebentätigkeit
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>{data.category}</div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3 }}>
            {data.n_bookings} Buchungen · {data.first_year}–{data.last_year}
            {data.active ? " · laufend" : " · ruht"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select value={data.category} onChange={(e) => changeCategory(e.target.value)} style={{
            padding: "7px 11px", background: "var(--bg-2)", border: "1px solid var(--line)",
            borderRadius: "var(--r-sm)", color: "var(--fg)", fontSize: 12, fontFamily: "inherit",
          }}>
            {(data.verfuegbare_kategorien || []).map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <Btn variant="secondary" size="sm" icon="download"
               onClick={() => window.open(`/api/nebentaetigkeit/export?category=${encodeURIComponent(data.category)}${jahr ? `&jahr=${jahr}` : ""}`)}>
            CSV
          </Btn>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, margin: "18px 0" }}>
        <Stat label="Einnahmen gesamt"
              value={fmtEUR(data.years.reduce((s, y) => s + y.einnahmen, 0))} />
        <Stat label="Ausgaben gesamt"
              value={fmtEUR(data.years.reduce((s, y) => s + y.ausgaben, 0))} />
        <Stat label="Ergebnis kumuliert" value={fmtEUR(data.total)} large
              tone={data.total >= 0 ? "pos" : "neg"}
              sub={`über ${data.years.length} Jahre`} />
      </div>

      {/* Jahre */}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, minWidth: 520 }}>
          <thead>
            <tr style={{ color: "var(--muted)", fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.07em" }}>
              <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 500 }}>Jahr</th>
              <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>Einnahmen</th>
              <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>Ausgaben</th>
              <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>Ergebnis</th>
              <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>kumuliert</th>
              <th style={{ width: 120, padding: "6px 8px" }} />
            </tr>
          </thead>
          <tbody>
            {data.years.map(y => (
              <tr key={y.jahr}
                  onClick={() => { setJahr(jahr === y.jahr ? 0 : y.jahr); setShowBuchungen(true); }}
                  style={{ borderTop: "1px solid var(--line)", cursor: "pointer",
                           background: jahr === y.jahr ? "var(--accent-soft)" : "transparent" }}>
                <td style={{ padding: "8px", fontFamily: "var(--mono)" }}>{y.jahr}</td>
                <td style={{ padding: "8px", textAlign: "right", fontFamily: "var(--mono)" }}>{fmtEUR(y.einnahmen, { decimals: 0 })}</td>
                <td style={{ padding: "8px", textAlign: "right", fontFamily: "var(--mono)" }}>{fmtEUR(y.ausgaben, { decimals: 0 })}</td>
                <td style={{ padding: "8px", textAlign: "right", fontFamily: "var(--mono)", fontWeight: 600,
                             color: moneyTone(y.ergebnis) }}>
                  {fmtEUR(y.ergebnis, { decimals: 0, sign: true })}
                </td>
                <td style={{ padding: "8px", textAlign: "right", fontFamily: "var(--mono)", color: "var(--muted)" }}>
                  {fmtEUR(y.kumuliert, { decimals: 0, sign: true })}
                </td>
                <td style={{ padding: "8px" }}>
                  {/* Balken: Einnahmen nach rechts, Ausgaben nach links */}
                  <div style={{ display: "flex", alignItems: "center", height: 8 }}>
                    <div style={{ width: "50%", display: "flex", justifyContent: "flex-end" }}>
                      <div style={{ width: `${(y.ausgaben / maxAbs) * 100}%`, height: 8,
                                    background: "var(--neg-dim)", borderRadius: "2px 0 0 2px" }} />
                    </div>
                    <div style={{ width: "50%" }}>
                      <div style={{ width: `${(y.einnahmen / maxAbs) * 100}%`, height: 8,
                                    background: "var(--pos-dim)", borderRadius: "0 2px 2px 0" }} />
                    </div>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(data.hinweise || []).length > 0 && (
        <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
          {data.hinweise.map((h, i) => (
            <div key={i} style={{
              display: "flex", gap: 9, padding: "10px 12px", fontSize: 12, lineHeight: 1.55,
              background: "var(--warn-soft)", border: "1px solid var(--line)", borderRadius: "var(--r-sm)",
            }}>
              <span style={{ color: "var(--warn)" }}>i</span>
              <span>{h.text}</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 14 }}>
        <button onClick={() => setShowBuchungen(v => !v)} style={{
          background: "none", border: "none", padding: 0, cursor: "pointer",
          color: "var(--accent)", fontSize: 12, fontFamily: "inherit",
        }}>
          {showBuchungen ? "Buchungen ausblenden" : `Buchungen anzeigen${jahr ? ` (${jahr})` : ""}`}
        </button>
        {jahr > 0 && (
          <button onClick={() => setJahr(0)} style={{
            background: "none", border: "none", marginLeft: 12, cursor: "pointer",
            color: "var(--muted)", fontSize: 12, fontFamily: "inherit",
          }}>alle Jahre</button>
        )}
      </div>

      {showBuchungen && (
        <div style={{ marginTop: 12, maxHeight: 340, overflowY: "auto" }}>
          {(data.buchungen || []).map(b => (
            <div key={b.id} style={{ display: "flex", gap: 10, alignItems: "baseline",
                                     padding: "7px 0", borderTop: "1px solid var(--line)", fontSize: 12 }}>
              <span style={{ fontFamily: "var(--mono)", color: "var(--muted)", width: 78, flexShrink: 0 }}>{b.datum}</span>
              <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    title={b.zweck}>{b.wer}</span>
              <span style={{ fontFamily: "var(--mono)", fontWeight: 600, color: moneyTone(b.betrag), flexShrink: 0 }}>
                {fmtEUR(b.betrag, { sign: true })}
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 14, lineHeight: 1.6 }}>
        Zufluss gegen Abfluss je Kalenderjahr, angelehnt an eine
        Einnahmenüberschussrechnung. Keine Steuerberatung: Abschreibungen,
        Vorsteuer und die Abgrenzung von Privatanteilen sind hier nicht
        abgebildet. Der CSV-Export ist als Vorlage für deinen Steuerberater gedacht.
      </div>
    </Card>
  );
};

const PageSteuer = () => {
  const [year, setYear] = React.useState(0);
  const [error, setError] = React.useState("");
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  const fetchData = React.useCallback((y = 0) => {
    setLoading(true);
    fetch(`/api/steuer?year=${y}`).then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`); return j; }).then(d => {
      setData(d);
      setYear(d.selected_year);
      setLoading(false);
    }).catch(e => { setError(e.message || "Unbekannter Fehler"); setLoading(false); });
  }, []);

  React.useEffect(() => { fetchData(year); }, []);

  if (loading && !data) return <Spinner />;
  if (!data) return <EmptyState title="Keine Daten" desc="Importiere zuerst Kontodaten." />;

  const { years = [], selected_year, capital_income, tax_withheld, net_income, fsa_used_pct, monthly = [], capital_rows = [], tax_rows = [] } = data;

  const FSA_LIMIT = 1000;
  const fsaUsed = Math.min(capital_income, FSA_LIMIT);
  const fsaPct = Math.min(fsa_used_pct, 100);

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20 }}>
      <WarningStrip warnings={error ? [error] : []} onDismiss={() => setError("")} />
      {/* Year selector */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 13, color: "var(--muted)" }}>Steuerjahr</span>
        <div style={{ display: "flex", gap: 4 }}>
          {years.map(y => (
            <button key={y} onClick={() => fetchData(y)} style={{
              padding: "6px 14px", borderRadius: 8, border: "none", fontFamily: "var(--mono)",
              fontSize: 13, fontWeight: 600, cursor: "pointer",
              background: y === selected_year ? "var(--accent)" : "var(--bg-1)",
              color: y === selected_year ? "var(--on-accent)" : "var(--fg)",
              border: `1px solid ${y === selected_year ? "var(--accent)" : "var(--line)"}`,
            }}>{y}</button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
        <Card>
          <Stat label="Kapitalerträge" value={fmtEUR(capital_income)} large
            deltaTone={capital_income > FSA_LIMIT ? "neg" : "pos"}
            delta={capital_income > FSA_LIMIT ? "Über Sparerpauschbetrag" : "Im Rahmen des FSB"}
            sub={String(selected_year)} />
        </Card>
        <Card>
          <Stat label="Abgeführte Steuer" value={fmtEUR(tax_withheld)} deltaTone="neg" sub="Kapitalertragsteuer" />
        </Card>
        <Card>
          <Stat label="Nettoertrag" value={fmtEUR(net_income)} deltaTone={net_income >= 0 ? "pos" : "neg"} sub="nach Steuer" />
        </Card>
        <Card>
          <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Sparerpauschbetrag</div>
          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--mono)", marginBottom: 8 }}>
            {fmtPct(fsaPct, { sign: false })}
          </div>
          <div style={{ marginBottom: 6 }}>
            <div style={{ height: 5, background: "var(--bg-2)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{
                width: `${fsaPct}%`, height: "100%", borderRadius: 3,
                background: fsaPct >= 100 ? "var(--neg)" : fsaPct >= 75 ? "var(--accent)" : "var(--pos)",
              }} />
            </div>
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)" }}>{fmtEUR(fsaUsed)} von {fmtEUR(FSA_LIMIT)} genutzt</div>
        </Card>
      </div>

      {/* Monthly chart */}
      {monthly.length > 0 && (
        <Card padding={0}>
          <div style={{ padding: "18px 22px 0" }}>
            <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Monatliche Verteilung</div>
            <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>Kapitalerträge {selected_year}</div>
          </div>
          <div style={{ padding: "14px 12px 16px" }}>
            <BarChart
              data={monthly.map(m => ({ label: m.month.slice(5, 7), in: m.capital, out: m.tax }))}
              height={180} posKey="in" negKey="out" xKey="label"
              yFmt={(v) => fmtEUR(v, { decimals: 0 })}
            />
          </div>
        </Card>
      )}

      {/* Capital income transactions */}
      {capital_rows.length > 0 && (
        <Card padding={0}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontWeight: 600, fontSize: 15 }}>Kapitalerträge</div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>{capital_rows.length} Buchungen · {fmtEUR(capital_income)} gesamt</div>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--line)" }}>
                <th style={{ textAlign: "left", padding: "10px 20px", fontWeight: 500 }}>Datum</th>
                <th style={{ textAlign: "left", padding: "10px 14px", fontWeight: 500 }}>Buchungstext</th>
                <th style={{ textAlign: "left", padding: "10px 14px", fontWeight: 500 }}>Konto</th>
                <th style={{ textAlign: "right", padding: "10px 20px", fontWeight: 500 }}>Betrag</th>
              </tr>
            </thead>
            <tbody>
              {capital_rows.map((r, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td style={{ padding: "10px 20px", fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)" }}>{r.date}</td>
                  <td style={{ padding: "10px 14px" }}>
                    <div style={{ fontWeight: 500 }}>{r.payee || r.description}</div>
                    {r.payee && r.description && <div style={{ fontSize: 10, color: "var(--muted)" }}>{r.description}</div>}
                  </td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "var(--muted)" }}>{r.account}</td>
                  <td style={{ padding: "10px 20px", textAlign: "right", fontFamily: "var(--mono)", fontWeight: 600, color: "var(--pos)" }}>
                    +{fmtEUR(r.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Tax rows */}
      {tax_rows.length > 0 && (
        <Card padding={0}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontWeight: 600, fontSize: 15 }}>Steuerabzüge</div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>{tax_rows.length} Buchungen · {fmtEUR(tax_withheld)} gesamt</div>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--line)" }}>
                <th style={{ textAlign: "left", padding: "10px 20px", fontWeight: 500 }}>Datum</th>
                <th style={{ textAlign: "left", padding: "10px 14px", fontWeight: 500 }}>Beschreibung</th>
                <th style={{ textAlign: "left", padding: "10px 14px", fontWeight: 500 }}>Konto</th>
                <th style={{ textAlign: "right", padding: "10px 20px", fontWeight: 500 }}>Betrag</th>
              </tr>
            </thead>
            <tbody>
              {tax_rows.map((r, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td style={{ padding: "10px 20px", fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)" }}>{r.date}</td>
                  <td style={{ padding: "10px 14px" }}>{r.description}</td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "var(--muted)" }}>{r.account}</td>
                  <td style={{ padding: "10px 20px", textAlign: "right", fontFamily: "var(--mono)", fontWeight: 600, color: "var(--neg)" }}>
                    {fmtEUR(r.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {capital_rows.length === 0 && tax_rows.length === 0 && (
        <EmptyState title={`Keine Kapitalerträge in ${selected_year}`} desc="Die automatische Erkennung basiert auf Schlüsselwörtern in Buchungstexten." />
      )}
      <Nebentaetigkeit />
    </div>
  );
};

window.PageSteuer = PageSteuer;
window.Nebentaetigkeit = Nebentaetigkeit;
