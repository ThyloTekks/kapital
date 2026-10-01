// Page: Jahresübersicht

const PageJahresuebersicht = () => {
  const [account, setAccount] = React.useState("all");
  const [error, setError] = React.useState("");
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [view, setView] = React.useState("jahre");

  const fetchData = React.useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ account });
    fetch(`/api/jahresuebersicht?${params}`)
      .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`); return j; })
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message || "Unbekannter Fehler"); setLoading(false); });
  }, [account]);

  React.useEffect(() => { fetchData(); }, [fetchData]);

  if (loading && !data) return <Spinner />;
  if (!data || (!data.years?.length && !data.monthly?.length)) return <EmptyState title="Keine Daten" desc="Importiere zuerst Kontodaten." />;

  const { years = [], monthly = [], categories = [], all_accounts = [] } = data;
  const maxCat = Math.max(...categories.map(c => Math.abs(c.total)), 1);

  const rateColor = (r) => r >= 20 ? "var(--pos)" : r >= 10 ? "var(--accent)" : "var(--neg)";

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20 }}>
      <WarningStrip warnings={error ? [error] : []} onDismiss={() => setError("")} />
      {/* Filter bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <Segmented
          options={[{ label: "Jahresübersicht", value: "jahre" }, { label: "Monatsverlauf", value: "monate" }, { label: "Kategorien", value: "kategorien" }]}
          value={view}
          onChange={setView}
        />
        {all_accounts.length > 1 && (
          <select value={account} onChange={e => setAccount(e.target.value)} style={{
            padding: "7px 12px", background: "var(--bg-1)", border: "1px solid var(--line)",
            borderRadius: 10, color: account === "all" ? "var(--muted)" : "var(--fg)",
            fontSize: 12, fontFamily: "inherit", outline: "none", cursor: "pointer",
          }}>
            <option value="all">Alle Konten</option>
            {all_accounts.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        )}
      </div>

      {/* Jahresübersicht */}
      {view === "jahre" && (
        years.length === 0 ? <EmptyState title="Keine Jahresdaten" /> : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
              {years.slice(-1).map(y => (
                <React.Fragment key={y.year}>
                  <Card>
                    <Stat label={`Einnahmen ${y.year}`} value={fmtEUR(y.einnahmen)} large deltaTone="pos" />
                  </Card>
                  <Card>
                    <Stat label={`Ausgaben ${y.year}`} value={fmtEUR(y.ausgaben)} deltaTone="neg" />
                  </Card>
                  <Card>
                    <Stat label={`Investiert ${y.year}`} value={fmtEUR(y.investiert)} deltaTone="accent" />
                  </Card>
                  <Card>
                    <Stat label={`Sparrate ${y.year}`} value={`${y.sparrate?.toFixed(1)} %`}
                      delta={fmtEUR(y.ersparnis) + " gespart"}
                      deltaTone={y.sparrate >= 20 ? "pos" : y.sparrate >= 10 ? "neutral" : "neg"} />
                  </Card>
                </React.Fragment>
              ))}
            </div>

            <Card padding={0}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--line)" }}>
                    <th style={{ textAlign: "left", padding: "11px 20px", fontWeight: 500 }}>Jahr</th>
                    <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Einnahmen</th>
                    <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Ausgaben</th>
                    <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Investiert</th>
                    <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Ersparnis</th>
                    <th style={{ textAlign: "right", padding: "11px 20px", fontWeight: 500 }}>Sparrate</th>
                  </tr>
                </thead>
                <tbody>
                  {[...years].reverse().map(y => (
                    <tr key={y.year} style={{ borderBottom: "1px solid var(--line)" }}>
                      <td style={{ padding: "12px 20px", fontFamily: "var(--mono)", fontWeight: 600 }}>{y.year}</td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "var(--mono)", color: "var(--pos)" }}>
                        +{fmtEUR(y.einnahmen)}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "var(--mono)", color: "var(--neg)" }}>
                        {fmtEUR(y.ausgaben)}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "var(--mono)", color: "var(--accent)" }}>
                        {fmtEUR(y.investiert)}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "var(--mono)", fontWeight: 500 }}>
                        {fmtEUR(y.ersparnis)}
                      </td>
                      <td style={{ padding: "12px 20px", textAlign: "right" }}>
                        <span style={{ fontFamily: "var(--mono)", fontWeight: 600, color: rateColor(y.sparrate) }}>
                          {y.sparrate?.toFixed(1)} %
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </>
        )
      )}

      {/* Monatsverlauf */}
      {view === "monate" && (
        monthly.length === 0 ? <EmptyState title="Keine Monatsdaten" /> : (
          <>
            <Card padding={0}>
              <div style={{ padding: "18px 22px 0" }}>
                <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Cashflow</div>
                <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>Monatlicher Verlauf</div>
              </div>
              <div style={{ padding: "14px 12px 16px" }}>
                <BarChart
                  data={monthly.slice(-24).map(m => ({ label: m.ym.slice(0, 7), in: m.einnahmen, out: m.ausgaben }))}
                  height={240} posKey="in" negKey="out" xKey="label"
                  yFmt={(v) => fmtEUR(v, { decimals: 0 })}
                />
              </div>
            </Card>

            <Card padding={0}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--line)" }}>
                    <th style={{ textAlign: "left", padding: "11px 20px", fontWeight: 500 }}>Monat</th>
                    <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Einnahmen</th>
                    <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Ausgaben</th>
                    <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Ersparnis</th>
                    <th style={{ textAlign: "right", padding: "11px 20px", fontWeight: 500 }}>Sparrate</th>
                  </tr>
                </thead>
                <tbody>
                  {[...monthly].reverse().map((m, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--line)" }}>
                      <td style={{ padding: "11px 20px", fontFamily: "var(--mono)", fontSize: 12, color: "var(--muted)" }}>
                        {m.ym.slice(0, 7)}
                      </td>
                      <td style={{ padding: "11px 14px", textAlign: "right", fontFamily: "var(--mono)", color: "var(--pos)" }}>
                        +{fmtEUR(m.einnahmen)}
                      </td>
                      <td style={{ padding: "11px 14px", textAlign: "right", fontFamily: "var(--mono)", color: "var(--neg)" }}>
                        {fmtEUR(m.ausgaben)}
                      </td>
                      <td style={{ padding: "11px 14px", textAlign: "right", fontFamily: "var(--mono)", fontWeight: 500 }}>
                        {fmtEUR(m.ersparnis)}
                      </td>
                      <td style={{ padding: "11px 20px", textAlign: "right" }}>
                        <span style={{ fontFamily: "var(--mono)", fontWeight: 600, color: rateColor(m.sparrate) }}>
                          {m.sparrate?.toFixed(1)} %
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </>
        )
      )}

      {/* Kategorien */}
      {view === "kategorien" && (
        categories.length === 0 ? <EmptyState title="Keine Kategoriedaten" /> : (
          <Card>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Ausgaben nach Kategorie (gesamt)</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {categories.slice(0, 20).map(c => (
                <div key={c.category}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                    <span style={{ fontSize: 13 }}>{c.category}</span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 500 }}>{fmtEUR(Math.abs(c.total))}</span>
                  </div>
                  <div style={{ height: 4, background: "var(--bg-2)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ width: `${(Math.abs(c.total) / maxCat) * 100}%`, height: "100%", background: "var(--accent)", opacity: 0.7 }} />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )
      )}
    </div>
  );
};

window.PageJahresuebersicht = PageJahresuebersicht;
