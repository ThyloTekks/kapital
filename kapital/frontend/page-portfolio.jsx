// Page: Portfolio

const PagePortfolio = () => {
  const { data, loading } = useFetch("/api/portfolio");
  const [tab, setTab] = React.useState("positionen");

  if (loading) return <Spinner />;
  if (!data || (!data.positions?.length && !data.sold?.length)) return (
    <EmptyState title="Keine Portfoliodaten" desc="Importiere Trade Republic CSV oder PDF." />
  );

  const { positions = [], sold = [], summary = {}, allocation = {}, dividends = [], trades = [], income = {} } = data;
  const plColor = (v) => v == null ? "var(--muted)" : v >= 0 ? "var(--pos)" : "var(--neg)";
  const fmtXirr = (v) => v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)} %`;

  const tabs = [
    ["positionen", "Positionen"],
    ["analyse", "Analyse"],
    ["trades", "Trades"],
    ["dividenden", "Dividenden"],
    ["ki_prognose", "KI-Prognose"],
  ];
  if (sold.length > 0) tabs.splice(2, 0, ["realisiert", "Realisiert"]);

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
        <Card>
          <Stat label="Depotwert" value={fmtEUR(summary.total_value)} large sub={`${summary.n_positions} Positionen`} />
        </Card>
        <Card>
          <Stat
            label="Unrealisiert"
            value={fmtEUR(summary.total_pl)}
            delta={summary.total_pl_pct != null ? `${summary.total_pl_pct > 0 ? "+" : ""}${summary.total_pl_pct?.toFixed(2)} %` : null}
            deltaTone={summary.total_pl >= 0 ? "pos" : "neg"}
            sub="Buchgewinn/-verlust"
          />
        </Card>
        <Card>
          <Stat
            label="Realisiert"
            value={fmtEUR(summary.total_realized_gain)}
            deltaTone={summary.total_realized_gain >= 0 ? "pos" : "neg"}
            sub={`${summary.n_sold || 0} Positionen verkauft`}
          />
        </Card>
        <Card>
          <Stat label="Freies Guthaben" value={fmtEUR(summary.tr_cash)} sub="TR Konto" />
          {allocation.etf_pct > 0 && (
            <div style={{ display: "flex", gap: 12, fontSize: 11, color: "var(--muted)", marginTop: 10 }}>
              <span>ETFs <strong style={{ color: "var(--fg)" }}>{allocation.etf_pct?.toFixed(0)}%</strong></span>
              <span>Aktien <strong style={{ color: "var(--fg)" }}>{allocation.stock_pct?.toFixed(0)}%</strong></span>
            </div>
          )}
        </Card>
      </div>

      {/* Tabs */}
      <Segmented
        options={tabs.map(([v, l]) => ({ value: v, label: l }))}
        value={tab}
        onChange={setTab}
      />

      {/* Positionen */}
      {tab === "positionen" && (
        positions.length === 0 ? <EmptyState title="Keine offenen Positionen" /> : (
          <Card padding={0}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--line)" }}>
                  <th style={{ textAlign: "left", padding: "11px 20px", fontWeight: 500 }}>Name</th>
                  <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Stück</th>
                  <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Ø Kauf</th>
                  <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Kurs</th>
                  <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Wert</th>
                  <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>G/V</th>
                  <th style={{ textAlign: "right", padding: "11px 20px", fontWeight: 500 }}>XIRR</th>
                </tr>
              </thead>
              <tbody>
                {positions.map(p => (
                  <tr key={p.isin} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ padding: "12px 20px" }}>
                      <div style={{ fontWeight: 500 }}>{p.name}</div>
                      <div style={{ fontSize: 10, color: "var(--muted)", fontFamily: "var(--mono)", marginTop: 2 }}>
                        {p.isin}
                        {p.is_etf && <span style={{ marginLeft: 6, padding: "1px 5px", background: "var(--accent-soft)", color: "var(--accent)", borderRadius: 4, fontSize: 9 }}>ETF</span>}
                      </div>
                    </td>
                    <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "var(--mono)", fontSize: 12 }}>{p.qty}</td>
                    <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "var(--mono)", fontSize: 12 }}>
                      {p.avg_price != null ? fmtEUR(p.avg_price) : <span style={{ color: "var(--muted)" }}>—</span>}
                    </td>
                    <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "var(--mono)", fontSize: 12 }}>
                      {p.current_price != null ? fmtEUR(p.current_price) : <span style={{ color: "var(--muted)" }}>—</span>}
                    </td>
                    <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "var(--mono)", fontWeight: 600 }}>{fmtEUR(p.value)}</td>
                    <td style={{ padding: "12px 14px", textAlign: "right" }}>
                      <div style={{ fontFamily: "var(--mono)", fontWeight: 500, color: plColor(p.pl), fontSize: 13 }}>
                        {p.pl >= 0 ? "+" : ""}{fmtEUR(p.pl)}
                      </div>
                      {p.pl_pct != null && (
                        <div style={{ fontSize: 10, color: plColor(p.pl_pct), fontFamily: "var(--mono)" }}>
                          {p.pl_pct >= 0 ? "+" : ""}{p.pl_pct?.toFixed(2)} %
                        </div>
                      )}
                    </td>
                    <td style={{ padding: "12px 20px", textAlign: "right" }}>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: p.xirr == null ? "var(--muted)" : plColor(p.xirr) }}>
                        {fmtXirr(p.xirr)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )
      )}

      {/* Analyse */}
      {tab === "analyse" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Income breakdown */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
            <Card>
              <Stat label="Zinsen (TR)" value={fmtEUR(income.interest || 0)} deltaTone="pos" sub="Zinseinnahmen" />
            </Card>
            <Card>
              <Stat label="Dividenden" value={fmtEUR(income.dividends || 0)} deltaTone="pos" sub="Ausschüttungen" />
            </Card>
            <Card>
              <Stat label="Cashback / Prämien" value={fmtEUR(income.cashback || 0)} deltaTone="pos" sub="Runden, Prämien" />
            </Card>
            <Card>
              <Stat label="Sonstige Einnahmen" value={fmtEUR(income.other || 0)} deltaTone="neutral" sub="Sonstiges" />
            </Card>
          </div>

          {/* Portfolio health */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <Card>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Allokation</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {[
                  { label: "ETFs", value: allocation.etf_value, pct: allocation.etf_pct, color: "var(--accent)" },
                  { label: "Einzelaktien", value: allocation.stock_value, pct: allocation.stock_pct, color: "var(--neg)" },
                ].map(row => (
                  <div key={row.label}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                      <span style={{ fontSize: 13 }}>{row.label}</span>
                      <div style={{ textAlign: "right" }}>
                        <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 500 }}>{fmtEUR(row.value)}</span>
                        <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)", marginLeft: 8 }}>{row.pct?.toFixed(1)} %</span>
                      </div>
                    </div>
                    <div style={{ height: 6, background: "var(--bg-2)", borderRadius: 3 }}>
                      <div style={{ width: `${row.pct || 0}%`, height: "100%", background: row.color, opacity: 0.8, borderRadius: 3 }} />
                    </div>
                  </div>
                ))}
                <div style={{ paddingTop: 8, borderTop: "1px solid var(--line)", fontSize: 12, color: "var(--muted)" }}>
                  Top-3-Konzentration: <strong style={{ color: "var(--fg)" }}>{allocation.top3_pct || 0} %</strong> des Depots
                  {allocation.top3_pct > 60 && <span style={{ color: "var(--neg)", marginLeft: 6 }}>⚠ Hohe Konzentration</span>}
                </div>
              </div>
            </Card>

            <Card>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Performance (XIRR)</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {positions
                  .filter(p => p.xirr != null)
                  .sort((a, b) => (b.xirr || 0) - (a.xirr || 0))
                  .slice(0, 8)
                  .map(p => (
                    <div key={p.isin} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 12, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "70%" }}>{p.name}</span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, flexShrink: 0, color: plColor(p.xirr) }}>
                        {fmtXirr(p.xirr)}
                      </span>
                    </div>
                  ))}
                {positions.filter(p => p.xirr == null).length > 0 && (
                  <div style={{ fontSize: 11, color: "var(--muted)", paddingTop: 4 }}>
                    {positions.filter(p => p.xirr == null).length} Positionen ohne Preis — XIRR nicht berechenbar
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* Underperformers */}
          {positions.filter(p => p.pl_pct != null && p.pl_pct < -10).length > 0 && (
            <Card>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Unterdurchschnittliche Positionen</div>
              <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 14 }}>Buchverlust &gt; 10 %</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {positions.filter(p => p.pl_pct != null && p.pl_pct < -10).map(p => (
                  <div key={p.isin} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", background: "var(--neg-soft)", borderRadius: 8, border: "1px solid var(--neg-soft)" }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>{p.name}</div>
                      <div style={{ fontSize: 10, color: "var(--muted)", fontFamily: "var(--mono)" }}>{p.isin}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontFamily: "var(--mono)", color: "var(--neg)", fontWeight: 600 }}>{p.pl_pct?.toFixed(2)} %</div>
                      <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--neg)" }}>{fmtEUR(p.pl)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Realisierte Gewinne/Verluste */}
      {tab === "realisiert" && (
        sold.length === 0 ? <EmptyState title="Keine realisierten Positionen" /> : (
          <Card padding={0}>
            <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontWeight: 600 }}>Verkaufte Positionen</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 600, color: plColor(summary.total_realized_gain) }}>
                Gesamt: {summary.total_realized_gain >= 0 ? "+" : ""}{fmtEUR(summary.total_realized_gain)}
              </span>
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--line)" }}>
                  <th style={{ textAlign: "left", padding: "11px 20px", fontWeight: 500 }}>Name</th>
                  <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Investiert</th>
                  <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Erlöse</th>
                  <th style={{ textAlign: "right", padding: "11px 20px", fontWeight: 500 }}>Realisierter G/V</th>
                </tr>
              </thead>
              <tbody>
                {sold.map(p => (
                  <tr key={p.isin} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ padding: "12px 20px" }}>
                      <div style={{ fontWeight: 500 }}>{p.name}</div>
                      <div style={{ fontSize: 10, color: "var(--muted)", fontFamily: "var(--mono)", marginTop: 2 }}>{p.isin}</div>
                    </td>
                    <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "var(--mono)", fontSize: 12 }}>{fmtEUR(p.total_invested)}</td>
                    <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "var(--mono)", fontSize: 12 }}>{fmtEUR(p.total_proceeds)}</td>
                    <td style={{ padding: "12px 20px", textAlign: "right" }}>
                      <span style={{ fontFamily: "var(--mono)", fontWeight: 600, color: plColor(p.realized_gain) }}>
                        {p.realized_gain >= 0 ? "+" : ""}{fmtEUR(p.realized_gain)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )
      )}

      {/* Trades */}
      {tab === "trades" && (
        trades.length === 0 ? <EmptyState title="Keine Trades" /> : (
          <Card padding={0}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--line)" }}>
                  <th style={{ textAlign: "left", padding: "11px 20px", fontWeight: 500 }}>Datum</th>
                  <th style={{ textAlign: "left", padding: "11px 14px", fontWeight: 500 }}>Art</th>
                  <th style={{ textAlign: "left", padding: "11px 14px", fontWeight: 500 }}>ISIN</th>
                  <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Stück</th>
                  <th style={{ textAlign: "right", padding: "11px 14px", fontWeight: 500 }}>Preis</th>
                  <th style={{ textAlign: "right", padding: "11px 20px", fontWeight: 500 }}>Betrag</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ padding: "11px 20px", fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)" }}>{t.date}</td>
                    <td style={{ padding: "11px 14px" }}>
                      <Pill tone={t.action === "BUY" ? "pos" : "neg"} size="sm">{t.action === "BUY" ? "Kauf" : "Verkauf"}</Pill>
                    </td>
                    <td style={{ padding: "11px 14px", fontFamily: "var(--mono)", fontSize: 11 }}>{t.isin}</td>
                    <td style={{ padding: "11px 14px", textAlign: "right", fontFamily: "var(--mono)", fontSize: 12 }}>{t.qty}</td>
                    <td style={{ padding: "11px 14px", textAlign: "right", fontFamily: "var(--mono)", fontSize: 12 }}>{fmtEUR(t.price)}</td>
                    <td style={{ padding: "11px 20px", textAlign: "right", fontFamily: "var(--mono)", fontWeight: 500, color: t.amount > 0 ? "var(--pos)" : "var(--fg)" }}>
                      {fmtEUR(t.amount, { sign: t.amount > 0 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )
      )}

      {/* Dividenden */}
      {tab === "dividenden" && (
        dividends.length === 0 ? <EmptyState title="Keine Dividenden / Ausschüttungen" /> : (
          <Card padding={0}>
            <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontWeight: 600 }}>Dividenden & Ausschüttungen</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 600, color: "var(--pos)" }}>
                +{fmtEUR(income.dividends)}
              </span>
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--line)" }}>
                  <th style={{ textAlign: "left", padding: "11px 20px", fontWeight: 500 }}>Datum</th>
                  <th style={{ textAlign: "left", padding: "11px 14px", fontWeight: 500 }}>ISIN</th>
                  <th style={{ textAlign: "left", padding: "11px 14px", fontWeight: 500 }}>Art</th>
                  <th style={{ textAlign: "right", padding: "11px 20px", fontWeight: 500 }}>Betrag</th>
                </tr>
              </thead>
              <tbody>
                {dividends.map((d, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ padding: "11px 20px", fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)" }}>{d.date}</td>
                    <td style={{ padding: "11px 14px", fontFamily: "var(--mono)", fontSize: 11 }}>{d.isin}</td>
                    <td style={{ padding: "11px 14px", fontSize: 12 }}>{d.type}</td>
                    <td style={{ padding: "11px 20px", textAlign: "right", fontFamily: "var(--mono)", fontWeight: 500, color: "var(--pos)" }}>
                      +{fmtEUR(d.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )
      )}
      {/* KI-Prognose */}
      {tab === "ki_prognose" && (
        <KiPrognoseTab positions={positions} />
      )}
    </div>
  );
};

const KiPrognoseTab = ({ positions }) => {
  const [selectedIsin, setSelectedIsin] = React.useState(positions[0]?.isin || "");
  const [days, setDays] = React.useState(30);
  const [kronosModel, setKronosModel] = React.useState("small");
  const [result, setResult] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [apiKeyInput, setApiKeyInput] = React.useState("");
  const [apiKeyStatus, setApiKeyStatus] = React.useState(null); // {set: bool, preview: str}
  const [savingKey, setSavingKey] = React.useState(false);
  const toast = useToast();

  React.useEffect(() => {
    fetch("/api/settings").then(r => r.json()).then(d => setApiKeyStatus(d)).catch(() => {});
  }, []);

  const saveApiKey = async () => {
    if (!apiKeyInput.trim()) return;
    setSavingKey(true);
    const res = await fetch("/api/settings/twelve_data_key", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKeyInput.trim() }),
    });
    setSavingKey(false);
    if (res.ok) {
      setApiKeyStatus({ twelve_data_api_key_set: true, twelve_data_api_key_preview: `${apiKeyInput.slice(0, 4)}…` });
      setApiKeyInput("");
      toast("Twelve Data API-Key gespeichert");
    }
  };

  const selectedPos = positions.find(p => p.isin === selectedIsin);

  const runForecast = async () => {
    if (!selectedIsin) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`/api/kronos/forecast?isin=${selectedIsin}&days=${days}&model=${kronosModel}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Unbekannter Fehler");
      setResult(json);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Build chart data: historical (type=hist) + forecast (type=fc)
  const chartData = React.useMemo(() => {
    if (!result) return [];
    const hist = result.historical.map(d => ({ date: d.date, hist: d.close, fc: null }));
    // Overlap: last hist point as first forecast anchor
    const lastHist = hist[hist.length - 1];
    const fc = result.forecast.map((d) => ({
      date: d.date,
      hist: null,
      fc: d.close,
    }));
    // Join last hist point to first fc point for visual continuity
    fc[0] = { ...fc[0], histAnchor: lastHist.hist };
    return [...hist, ...fc];
  }, [result]);

  const lastClose = result?.historical?.at(-1)?.close;
  const fcClose = result?.forecast?.at(-1)?.close;
  const fcChange = lastClose && fcClose ? ((fcClose - lastClose) / lastClose) * 100 : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Controls */}
      <Card>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Kronos KI-Kursprognose</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 12, alignItems: "end" }}>
          <div>
            <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Position</div>
            <select
              value={selectedIsin}
              onChange={e => setSelectedIsin(e.target.value)}
              style={{ width: "100%", padding: "9px 14px", background: "var(--bg-2)", border: "1px solid var(--line)", borderRadius: 10, color: "var(--fg)", fontSize: 13, fontFamily: "var(--mono)", outline: "none" }}
            >
              {positions.map(p => (
                <option key={p.isin} value={p.isin}>{p.name} ({p.isin})</option>
              ))}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Modell</div>
            <select
              value={kronosModel}
              onChange={e => { setKronosModel(e.target.value); setResult(null); }}
              style={{ padding: "9px 14px", background: "var(--bg-2)", border: "1px solid var(--line)", borderRadius: 10, color: "var(--fg)", fontSize: 13, fontFamily: "var(--mono)", outline: "none" }}
            >
              <option value="mini">mini · 4M</option>
              <option value="small">small · 25M</option>
              <option value="base">base · 100M</option>
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Tage</div>
            <select
              value={days}
              onChange={e => setDays(parseInt(e.target.value))}
              style={{ padding: "9px 14px", background: "var(--bg-2)", border: "1px solid var(--line)", borderRadius: 10, color: "var(--fg)", fontSize: 13, fontFamily: "var(--mono)", outline: "none" }}
            >
              {[10, 20, 30, 45, 60].map(d => <option key={d} value={d}>{d} Tage</option>)}
            </select>
          </div>
          <Btn variant="primary" onClick={runForecast} disabled={loading || !selectedIsin}>
            {loading ? "Lädt …" : "Prognose starten"}
          </Btn>
        </div>

        {/* First-use hint */}
        {!result && !loading && !error && (
          <div style={{ marginTop: 14, padding: "10px 14px", background: "var(--bg-2)", borderRadius: 8, fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
            <strong style={{ color: "var(--fg)" }}>Kronos</strong> ist ein KI-Foundation-Model (AAAI 2026), trainiert auf Candlestick-Daten von 45+ Börsen.{" "}
            Downloadgröße: <strong style={{ color: "var(--fg)" }}>mini ~20 MB · small ~100 MB · base ~400 MB</strong>. Jedes Modell wird einmalig von HuggingFace geladen und dann gecacht.
          </div>
        )}
      </Card>

      {/* Twelve Data API-Key */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Twelve Data API-Key</div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              Fallback-Datenquelle für ISINs, die yfinance nicht kennt. Kostenlos unter{" "}
              <span style={{ color: "var(--accent)", fontFamily: "var(--mono)" }}>twelvedata.com</span>
            </div>
          </div>
          {apiKeyStatus?.twelve_data_api_key_set && (
            <Pill tone="pos" size="sm">✓ {apiKeyStatus.twelve_data_api_key_preview}</Pill>
          )}
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <input
            type="password"
            value={apiKeyInput}
            onChange={e => setApiKeyInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && saveApiKey()}
            placeholder={apiKeyStatus?.twelve_data_api_key_set ? "Neuen Key eingeben zum Überschreiben …" : "API-Key eingeben …"}
            style={{
              flex: 1, padding: "8px 12px", background: "var(--bg-2)", border: "1px solid var(--line)",
              borderRadius: 8, color: "var(--fg)", fontSize: 12, fontFamily: "var(--mono)", outline: "none",
            }}
          />
          <Btn variant="secondary" onClick={saveApiKey} disabled={savingKey || !apiKeyInput.trim()}>
            {savingKey ? "Speichert …" : "Speichern"}
          </Btn>
        </div>
      </Card>

      {/* Error */}
      {error && (
        <div style={{ padding: "14px 18px", background: "var(--neg-soft)", border: "1px solid var(--neg-soft)", borderRadius: 10, fontSize: 13, color: "var(--neg)" }}>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <Card>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, padding: "32px 0" }}>
            <Spinner />
            <div style={{ fontSize: 13, color: "var(--muted)" }}>Kronos läuft … (erste Anfrage lädt Modell von HuggingFace)</div>
          </div>
        </Card>
      )}

      {/* Results */}
      {result && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
            <Card>
              <Stat label="Letzter Kurs" value={fmtMoney(lastClose, result.currency || "EUR")} sub={result.historical.at(-1)?.date} />
            </Card>
            <Card>
              <Stat
                label={`Prognose in ${days} Tagen`}
                value={fmtMoney(fcClose, result.currency || "EUR")}
                delta={fcChange != null ? `${fcChange >= 0 ? "+" : ""}${fcChange.toFixed(2)} %` : null}
                deltaTone={fcChange >= 0 ? "pos" : "neg"}
                sub={result.forecast.at(-1)?.date}
              />
            </Card>
            <Card>
              <Stat label="Ticker" value={result.ticker} sub={`${result.isin} · Kronos-${result.model}`} />
            </Card>
          </div>

          <Card padding={0}>
            <div style={{ padding: "18px 22px 0" }}>
              <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>KI-Kursprognose · {selectedPos?.name}</div>
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>Verlauf (60 Tage) + Prognose ({days} Tage)</div>
            </div>
            <div style={{ padding: "14px 12px 4px" }}>
              <KronosChart historical={result.historical} forecast={result.forecast} currency={result.currency || "EUR"} />
            </div>
            <div style={{ padding: "8px 22px 16px", display: "flex", gap: 20, fontSize: 11, color: "var(--muted)" }}>
              <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 12, height: 2, background: "var(--muted)", display: "inline-block", borderRadius: 1 }} /> Verlauf
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 12, height: 2, background: "var(--accent)", display: "inline-block", borderRadius: 1 }} /> KI-Prognose
              </span>
            </div>
          </Card>

          {/* Disclaimer */}
          <div style={{ padding: "12px 16px", background: "rgba(250,204,21,0.06)", border: "1px solid rgba(250,204,21,0.2)", borderRadius: 8, fontSize: 11, color: "var(--muted)", lineHeight: 1.7 }}>
            <strong style={{ color: "rgba(250,204,21,0.8)" }}>Hinweis:</strong> Diese Prognose ist eine experimentelle KI-Vorhersage und <strong>keine Anlageempfehlung</strong>. Finanzmärkte sind hochgradig unvorhersehbar. Das Modell basiert auf historischen Kursmustern und berücksichtigt keine Fundamentaldaten, Nachrichten oder makroökonomischen Faktoren.
          </div>
        </>
      )}
    </div>
  );
};

const KronosChart = ({ historical, forecast, currency = "EUR" }) => {
  const [tooltip, setTooltip] = React.useState(null);
  const svgRef = React.useRef(null);

  const width = 800, height = 260;
  const padL = 72, padR = 16, padT = 16, padB = 32;
  const w = width - padL - padR;
  const h = height - padT - padB;

  const allPoints = [...historical, ...forecast];
  const allClose = allPoints.map(d => d.close);
  const { axMin, axMax, ticks: yTicks } = niceAxis(Math.min(...allClose), Math.max(...allClose));

  const n = allPoints.length;
  const xScale = (i) => padL + (i / (n - 1)) * w;
  const yScale = (v) => padT + h - ((v - axMin) / (axMax - axMin)) * h;

  const histPts = historical.map((d, i) => [xScale(i), yScale(d.close)]);
  const fcPts = forecast.map((d, i) => [xScale(historical.length - 1 + i), yScale(d.close)]);
  // Connect forecast to last hist point
  const fcLine = [histPts[histPts.length - 1], ...fcPts];

  const toPath = (pts) => pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const fcAreaPath = `${toPath(fcLine)} L${fcLine[fcLine.length-1][0]},${padT+h} L${fcLine[0][0]},${padT+h} Z`;

  const showTip = (e, d, isFc) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, d, isFc });
  };

  // X-axis labels: show ~8 evenly spaced dates
  const xLabels = allPoints
    .map((d, i) => ({ i, date: d.date }))
    .filter((_, i) => i % Math.ceil(n / 8) === 0 || i === n - 1);

  const splitX = xScale(historical.length - 1);

  return (
    <div style={{ position: "relative" }}>
      <svg ref={svgRef} width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: "block" }} onMouseLeave={() => setTooltip(null)}>
        {/* Grid */}
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={width - padR} y1={yScale(t)} y2={yScale(t)} stroke="var(--line)" strokeWidth="1" strokeDasharray={i === 0 ? "" : "2 4"} />
            <text x={padL - 8} y={yScale(t) + 4} textAnchor="end" fontSize="10" fill="var(--muted)" fontFamily="var(--mono)">{compactNum(t)}</text>
          </g>
        ))}
        {xLabels.map(({ i, date }) => (
          <text key={i} x={xScale(i)} y={height - padB + 16} textAnchor="middle" fontSize="9" fill="var(--muted)" fontFamily="var(--mono)">{date}</text>
        ))}

        {/* Forecast zone background */}
        <rect x={splitX} y={padT} width={width - padR - splitX} height={h} fill="var(--accent)" opacity="0.03" />
        <line x1={splitX} x2={splitX} y1={padT} y2={padT + h} stroke="var(--accent)" strokeWidth="1" strokeDasharray="3 3" opacity="0.4" />

        {/* Forecast area fill */}
        <defs>
          <linearGradient id="grad-fc" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={fcAreaPath} fill="url(#grad-fc)" />

        {/* Historical line */}
        <path d={toPath(histPts)} fill="none" stroke="var(--muted)" strokeWidth="1.5" strokeLinejoin="round" opacity="0.7" />

        {/* Forecast line */}
        <path d={toPath(fcLine)} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />

        {/* Hover overlay per point */}
        {allPoints.map((d, i) => (
          <rect
            key={i}
            x={xScale(i) - w / n / 2}
            y={padT}
            width={w / n}
            height={h}
            fill="transparent"
            onMouseEnter={(e) => showTip(e, d, i >= historical.length)}
            onMouseMove={(e) => showTip(e, d, i >= historical.length)}
          />
        ))}

        {/* Endpoint dot */}
        {fcPts.length > 0 && (
          <circle cx={fcPts[fcPts.length-1][0]} cy={fcPts[fcPts.length-1][1]} r="4" fill="var(--accent)" stroke="var(--bg-1)" strokeWidth="2" />
        )}
      </svg>

      {tooltip && (
        <div style={{
          position: "absolute",
          left: tooltip.x + 14,
          top: tooltip.y - 14,
          background: "var(--bg-1)",
          border: `1px solid ${tooltip.isFc ? "var(--accent)" : "var(--line)"}`,
          borderRadius: 6,
          padding: "7px 12px",
          fontSize: 12,
          fontFamily: "var(--mono)",
          color: "var(--fg)",
          pointerEvents: "none",
          zIndex: 20,
          whiteSpace: "nowrap",
          boxShadow: "0 4px 12px var(--shadow)"
        }}>
          <div style={{ fontWeight: 600, marginBottom: 4, color: tooltip.isFc ? "var(--accent)" : "var(--fg)" }}>
            {tooltip.isFc ? "KI-Prognose" : "Kurs"} · {tooltip.d.date}
          </div>
          <div>O: {fmtMoney(tooltip.d.open, currency)} / H: {fmtMoney(tooltip.d.high, currency)}</div>
          <div>L: {fmtMoney(tooltip.d.low, currency)} / <strong>C: {fmtMoney(tooltip.d.close, currency)}</strong></div>
        </div>
      )}
    </div>
  );
};

window.PagePortfolio = PagePortfolio;
