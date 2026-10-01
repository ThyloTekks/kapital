// Vermögen — die Ansicht, die bisher gefehlt hat.
//
// Die App konnte den Kontostand von heute und eine Hochrechnung in die Zukunft,
// aber nicht die Frage "wie hat sich mein Vermögen entwickelt". Für eine
// Finanz-App ist das die zentrale Kurve.
//
// Bewusst ehrlich beschriftet: liquides Vermögen ist exakt (kalibrierter Stand,
// rückwärts gerechnet), eingesetztes Kapital steht zum EINSTAND, nicht zum
// Marktwert. Der Depotauszug ist eine Momentaufnahme ohne Verlauf; einen
// Marktwert-Verlauf zu schätzen hiesse, eine Zahl zu erfinden.

const WealthChart = ({ rows, width = 860, height = 260 }) => {
  const [hover, setHover] = React.useState(null);
  const ref = React.useRef(null);
  if (!rows || rows.length === 0) return null;

  const padL = 74, padR = 18, padT = 18, padB = 30;
  const w = width - padL - padR, h = height - padT - padB;
  const vals = rows.flatMap(r => [r.wealth, r.invested]);
  const rawMax = Math.max(...vals, 1);
  const rawMin = Math.min(...vals, 0);
  const span = rawMax - rawMin || 1;
  const x = (i) => padL + (rows.length > 1 ? (i / (rows.length - 1)) * w : w / 2);
  const y = (v) => padT + h - ((v - rawMin) / span) * h;

  const line = (key) => rows.map((r, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(r[key])}`).join(" ");
  const area = `${line("wealth")} L${x(rows.length - 1)},${y(rawMin)} L${x(0)},${y(rawMin)} Z`;

  const onMove = (e) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    const rel = e.clientX - box.left - padL;
    const i = Math.max(0, Math.min(rows.length - 1, Math.round((rel / w) * (rows.length - 1))));
    setHover({ i, x: e.clientX - box.left, y: e.clientY - box.top });
  };

  const ticks = [0, 0.25, 0.5, 0.75, 1].map(f => rawMin + span * f);

  return (
    <div ref={ref} style={{ position: "relative", overflowX: "auto" }}
         onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <svg width={width} height={height} style={{ display: "block", minWidth: 560 }}>
        <defs>
          <linearGradient id="wealthGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={width - padR} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth="1" />
            <text x={padL - 10} y={y(t) + 4} textAnchor="end" fontSize="10"
                  fill="var(--muted)" fontFamily="var(--mono)">
              {Math.round(t / 1000)}k
            </text>
          </g>
        ))}
        {rows.map((r, i) => (
          (rows.length <= 16 || i % Math.ceil(rows.length / 14) === 0) && (
            <text key={r.month} x={x(i)} y={height - padB + 16} textAnchor="middle"
                  fontSize="9" fill="var(--muted)" fontFamily="var(--mono)">{r.month.slice(2)}</text>
          )
        ))}
        <path d={area} fill="url(#wealthGrad)" />
        <path d={line("invested")} fill="none" stroke="var(--warn)" strokeWidth="1.6"
              strokeDasharray="4 4" opacity="0.75" />
        <path d={line("wealth")} fill="none" stroke="var(--accent)" strokeWidth="2.2"
              strokeLinejoin="round" strokeLinecap="round" />
        {hover && (
          <g>
            <line x1={x(hover.i)} x2={x(hover.i)} y1={padT} y2={padT + h}
                  stroke="var(--muted)" strokeWidth="1" strokeDasharray="3 3" />
            <circle cx={x(hover.i)} cy={y(rows[hover.i].wealth)} r="4"
                    fill="var(--accent)" stroke="var(--bg-1)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hover && (
        <div style={{
          position: "absolute", left: Math.min(hover.x + 14, width - 190), top: 14,
          background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 8,
          padding: "8px 12px", fontSize: 12, fontFamily: "var(--mono)", pointerEvents: "none",
          boxShadow: "0 4px 14px var(--shadow)", whiteSpace: "nowrap",
        }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{rows[hover.i].month}</div>
          <div style={{ color: "var(--accent)" }}>Vermögen {fmtEUR(rows[hover.i].wealth, { decimals: 0 })}</div>
          <div style={{ color: "var(--warn)" }}>eingesetzt {fmtEUR(rows[hover.i].invested, { decimals: 0 })}</div>
        </div>
      )}
    </div>
  );
};

const PageVermoegen = () => {
  const [months, setMonths] = React.useState(36);
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    setLoading(true); setError("");
    fetch(`/api/networth/history?months=${months}`)
      .then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`);
        return j;
      })
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [months]);

  if (loading && !data) return <Spinner />;
  if (error && !data) return (
    <div style={{ padding: "24px 32px" }}>
      <EmptyState icon="info" title="Vermögen konnte nicht geladen werden" desc={error} />
    </div>
  );
  if (!data || !data.series.length) return (
    <div style={{ padding: "24px 32px" }}>
      <EmptyState icon="bank" title="Noch keine Daten"
        desc="Importiere zuerst Kontoauszüge unter Import." />
    </div>
  );

  const c = data.current || {};
  const rows = data.series;
  const first = rows[0], last = rows[rows.length - 1];
  const delta = last.wealth - first.wealth;
  const perMonth = rows.length > 1 ? delta / (rows.length - 1) : 0;

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20 }}>
      <WarningStrip warnings={data.note ? [data.note] : []} />

      {/* Woraus das Vermögen besteht */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        <Card level="primary"><Stat label="Gesamtvermögen" value={fmtEUR(c.total)} large
                    sub={c.depot_as_of ? `Depot per ${fmtDate(c.depot_as_of)}` : "Depot ohne Stichtag"} /></Card>
        <Card><Stat label="Liquide Konten" value={fmtEUR(c.liquid)} sub="Giro, Tagesgeld" /></Card>
        <Card><Stat label="Depot" value={fmtEUR(c.depot)} sub="laut Depotauszug" /></Card>
        <Card><Stat label="Freies Guthaben" value={fmtEUR(c.broker_cash)} sub="beim Broker" /></Card>
      </div>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>Vermögensverlauf</div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3 }}>
              {first.month} bis {last.month} ·{" "}
              <span style={{ color: delta >= 0 ? "var(--pos)" : "var(--neg)" }}>
                {fmtEUR(delta, { decimals: 0, sign: true })}
              </span>{" "}
              gesamt, das sind {fmtEUR(perMonth, { decimals: 0, sign: true })} im Monat
            </div>
          </div>
          <Segmented value={String(months)} onChange={(v) => setMonths(Number(v))}
            options={[{ value: "12", label: "1 J." }, { value: "36", label: "3 J." },
                      { value: "60", label: "5 J." }, { value: "240", label: "Alles" }]} />
        </div>

        <WealthChart rows={rows} />

        <div style={{ display: "flex", gap: 16, fontSize: 11, color: "var(--muted)", marginTop: 10, justifyContent: "flex-end", flexWrap: "wrap" }}>
          <span><span style={{ display: "inline-block", width: 14, height: 2, background: "var(--accent)", marginRight: 5, verticalAlign: "middle" }} />liquides Vermögen</span>
          <span><span style={{ display: "inline-block", width: 14, height: 2, background: "var(--warn)", marginRight: 5, verticalAlign: "middle" }} />eingesetztes Kapital (Einstand)</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.6 }}>
          Der Verlauf ist vom heutigen kalibrierten Stand rückwärts gerechnet — genauer,
          als vorwärts zu kumulieren, weil der Kontostand vor dem ersten Import sonst
          unbekannt bliebe. Das eingesetzte Kapital steht zum Einstand: einen
          Marktwert-Verlauf gibt der Depotauszug nicht her, und ihn zu schätzen wäre geraten.
        </div>
      </Card>

      {/* Konten im Detail */}
      <Card>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Konten</div>
        <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 14 }}>
          Umbenennen unter Übersicht → Konten
        </div>
        {(c.accounts || []).map(a => (
          <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 500 }}>{a.name}</div>
              <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--mono)" }}>
                {a.type}
                {a.calibrated
                  ? <> · Anfangssaldo {fmtEUR(a.opening, { decimals: 0 })}</>
                  : <span style={{ color: "var(--warn)" }}> · kein Kontostand hinterlegt</span>}
              </div>
            </div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 600,
                          color: a.balance < 0 ? "var(--neg)" : "var(--fg)" }}>
              {fmtEUR(a.balance)}
            </div>
          </div>
        ))}
      </Card>
    </div>
  );
};

window.PageVermoegen = PageVermoegen;
