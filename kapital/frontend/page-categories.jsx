// Page: Kategorien & Budgets

const CategoryDetail = ({ cat, preset, account, range, onClose }) => {
  const [detail, setDetail] = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    setLoading(true);
    const { date_from, date_to } = presetToDates(preset) || range || { date_from: "", date_to: "" };
    const params = new URLSearchParams({ account });
    if (date_from) params.set("date_from", date_from);
    if (date_to) params.set("date_to", date_to);
    fetch(`/api/categories/${encodeURIComponent(cat.id)}/detail?${params}`)
      .then(r => r.json())
      .then(d => { setDetail(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [cat.id, preset, account]);

  const maxMonthly = detail ? Math.max(...detail.monthly.map(m => m.amount), 1) : 1;
  const maxPayee   = detail ? Math.max(...detail.top_payees.map(p => p.total), 1) : 1;

  return (
    <div style={{
      margin: "0 0 6px 0", background: "var(--bg-0)", border: "1px solid var(--line)",
      borderRadius: 12, overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 20px", borderBottom: "1px solid var(--line)",
        background: "var(--bg-1)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>{cat.icon || "•"}</span>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{cat.name}</div>
            {!loading && detail && (
              <div style={{ fontSize: 11, color: "var(--muted)" }}>
                {detail.count} Buchungen · Ø {fmtEUR(detail.avg_monthly)}/Monat · {fmtEUR(detail.total)} gesamt
              </div>
            )}
          </div>
        </div>
        <button onClick={onClose} style={{
          background: "transparent", border: "none", cursor: "pointer",
          color: "var(--muted)", fontSize: 18, lineHeight: 1, padding: "4px 8px",
        }}>✕</button>
      </div>

      {loading ? (
        <div style={{ padding: 24, textAlign: "center", color: "var(--muted)", fontSize: 13 }}>Lade …</div>
      ) : !detail || detail.count === 0 ? (
        <div style={{ padding: 24, textAlign: "center", color: "var(--muted)", fontSize: 13 }}>Keine Buchungen im gewählten Zeitraum</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 0 }}>
          {/* Monthly bars */}
          <div style={{ padding: "16px 20px", borderRight: "1px solid var(--line)" }}>
            <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>Monatsverlauf</div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 80 }}>
              {detail.monthly.slice(-24).map((m, i) => (
                <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                  <div title={`${m.month}: ${fmtEUR(m.amount)}`} style={{
                    width: "100%", minHeight: 2,
                    height: `${Math.max(2, (m.amount / maxMonthly) * 76)}px`,
                    background: cat.color || "var(--accent)", opacity: 0.8,
                    borderRadius: "2px 2px 0 0", cursor: "default",
                  }} />
                </div>
              ))}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
              {detail.monthly.length > 0 && (
                <>
                  <span style={{ fontSize: 10, color: "var(--muted)" }}>{detail.monthly[0]?.month}</span>
                  <span style={{ fontSize: 10, color: "var(--muted)" }}>{detail.monthly[detail.monthly.length - 1]?.month}</span>
                </>
              )}
            </div>
          </div>

          {/* Top payees */}
          <div style={{ padding: "16px 20px" }}>
            <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>Top Empfänger</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {detail.top_payees.slice(0, 6).map((p, i) => (
                <div key={i}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                    <span style={{ fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "60%" }}>{p.payee}</span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 500, flexShrink: 0 }}>{fmtEUR(p.total)}</span>
                  </div>
                  <div style={{ height: 2, background: "var(--bg-2)", borderRadius: 1 }}>
                    <div style={{ width: `${(p.total / maxPayee) * 100}%`, height: "100%", background: cat.color || "var(--accent)", opacity: 0.7 }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Kategoriezeile ───────────────────────────────────────────────────────────
// Auf Modulebene, NICHT im Render von PageCategories. Eine dort deklarierte
// Komponente ist bei jedem Durchlauf ein neuer Typ — React hängt dann die
// gesamte Liste samt geöffnetem Detail neu ein. Mit Mehrfachauswahl würde
// jedes Anhaken alle anderen Details neu laden.
const CatRow = ({ c, isSelected, compared, onToggleDetail, onToggleCompare,
                  onDelete, maxSpend, preset, account, range, compareDisabled }) => (
  <div>
    <div style={{
      display: "flex", alignItems: "center", gap: 12, padding: "12px 0",
      borderBottom: isSelected ? "none" : "1px solid var(--line)",
      borderRadius: isSelected ? "8px 8px 0 0" : 0,
    }}>
      <input
        type="checkbox"
        checked={compared}
        disabled={!compared && compareDisabled}
        onChange={(e) => { e.stopPropagation(); onToggleCompare(c); }}
        onClick={(e) => e.stopPropagation()}
        title={!compared && compareDisabled ? "Höchstens 5 Kategorien vergleichen" : "Zum Vergleich hinzufügen"}
        aria-label={`${c.name} vergleichen`}
        style={{ flexShrink: 0, cursor: "pointer" }}
      />
      <div
        onClick={() => onToggleDetail(c)}
        style={{ display: "flex", alignItems: "center", gap: 12, flex: 1, cursor: "pointer", minWidth: 0 }}
      >
        <div style={{ width: 10, height: 10, borderRadius: 3, background: c.color || "var(--muted)", flexShrink: 0 }} />
        <div style={{ fontSize: 18, width: 24, textAlign: "center", flexShrink: 0 }}>{c.icon || "•"}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 500, fontSize: 13 }}>{c.name}</div>
          <div style={{ marginTop: 5, height: 3, background: "var(--bg-2)", borderRadius: 2, overflow: "hidden" }}>
            <div style={{ width: `${(c.spend / maxSpend) * 100}%`, height: "100%", background: c.color || "var(--accent)", opacity: 0.75 }} />
          </div>
        </div>
        <div style={{ textAlign: "right", minWidth: 90 }}>
          <div style={{ fontFamily: "var(--mono)", fontWeight: 600, fontSize: 13 }}>{fmtEUR(c.spend)}</div>
          <div style={{ fontSize: 10, color: "var(--muted)" }}>{c.count} Buchungen</div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        {c.is_custom && (
          <button onClick={(e) => { e.stopPropagation(); onDelete(c.name); }} style={{
            background: "transparent", border: "none", cursor: "pointer",
            color: "var(--muted)", fontSize: 14, padding: "4px 6px", borderRadius: 6, lineHeight: 1,
          }} title="Löschen">✕</button>
        )}
        <span style={{ color: "var(--muted)", fontSize: 12, display: "inline-block",
                       transform: isSelected ? "rotate(180deg)" : "rotate(0deg)" }}>▾</span>
      </div>
    </div>
    {isSelected && (
      <CategoryDetail cat={c} preset={preset} account={account} range={range} onClose={() => onToggleDetail(c)} />
    )}
  </div>
);

// ── Kategorie-Vergleich ──────────────────────────────────────────────────────
// Das Referenzband hinter der Linie ist der Punkt: die Frage ist nicht "was war",
// sondern "ist das für mich normal". Genau diesen Vergleich zieht der
// Monatsabschluss ohnehin schon — hier wird er nur sichtbar.
const CategoryCompare = ({ cats, preset, account, range, onRemove }) => {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (!cats.length) { setData(null); return; }
    setLoading(true); setError("");
    const { date_from, date_to } = presetToDates(preset) || range || { date_from: "", date_to: "" };
    const params = new URLSearchParams({ cats: cats.join(","), account });
    if (date_from) params.set("date_from", date_from);
    if (date_to) params.set("date_to", date_to);
    // EIN Aufruf für alle Kategorien — nicht einer pro Kategorie, sonst wird
    // bei jedem Anhaken der gesamte Bestand erneut durchgerechnet.
    fetch(`/api/categories/timeseries?${params}`)
      .then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`);
        return j;
      })
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [cats.join(","), preset, account]);

  if (!cats.length) return null;

  const months = (data && data.months) || [];
  const series = (data && data.series) || [];
  const W = 760, H = 240, padL = 60, padR = 16, padT = 16, padB = 30;
  const w = W - padL - padR, h = H - padT - padB;
  const maxV = Math.max(1, ...series.flatMap(sr => sr.values), ...series.map(sr => sr.reference));
  const x = (i) => padL + (months.length > 1 ? (i / (months.length - 1)) * w : w / 2);
  const y = (v) => padT + h - (v / maxV) * h;

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, gap: 10, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600 }}>Zeitverlauf</div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
            {cats.length} von max. 5 Kategorien · gestrichelt = Ø der letzten {(data && data.avg_months) || 6} Monate
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {series.map((sr, i) => (
            <button key={sr.id} onClick={() => onRemove(sr.id)} title="Aus dem Vergleich nehmen"
              style={{
                display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 9px",
                borderRadius: 999, border: "1px solid var(--line)", background: "var(--bg-2)",
                color: "var(--fg)", fontSize: 11, cursor: "pointer", fontFamily: "inherit",
              }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: CHART_SERIES[i % CHART_SERIES.length], display: "inline-block" }} />
              {sr.name}
              <span style={{ color: "var(--muted)" }}>✕</span>
            </button>
          ))}
        </div>
      </div>

      {loading && !data ? <Spinner /> : error ? (
        <div style={{ padding: "20px 0", fontSize: 13, color: "var(--neg)" }}>
          Verlauf konnte nicht geladen werden: {error}
        </div>
      ) : months.length === 0 ? (
        <EmptyState icon="chart" title="Keine Daten im Zeitraum"
          desc="Für die gewählten Kategorien gibt es hier keine Buchungen." />
      ) : (
        <div style={{ overflowX: "auto" }}>
          <svg width={W} height={H} style={{ display: "block", minWidth: 520 }}>
            {[0, 0.25, 0.5, 0.75, 1].map(f => (
              <g key={f}>
                <line x1={padL} x2={W - padR} y1={y(maxV * f)} y2={y(maxV * f)} stroke="var(--line)" strokeWidth="1" />
                <text x={padL - 8} y={y(maxV * f) + 4} textAnchor="end" fontSize="10"
                      fill="var(--muted)" fontFamily="var(--mono)">
                  {Math.round(maxV * f)}
                </text>
              </g>
            ))}
            {months.map((m, i) => (
              (months.length <= 14 || i % Math.ceil(months.length / 12) === 0) && (
                <text key={m} x={x(i)} y={H - padB + 16} textAnchor="middle" fontSize="9"
                      fill="var(--muted)" fontFamily="var(--mono)">{m.slice(2)}</text>
              )
            ))}
            {series.map((sr, i) => (
              <g key={sr.id}>
                {sr.reference > 0 && (
                  <line x1={padL} x2={W - padR} y1={y(sr.reference)} y2={y(sr.reference)}
                        stroke={CHART_SERIES[i % CHART_SERIES.length]} strokeWidth="1" strokeDasharray="4 4" opacity="0.5" />
                )}
                <path
                  d={sr.values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(v)}`).join(" ")}
                  fill="none" stroke={CHART_SERIES[i % CHART_SERIES.length]} strokeWidth="2" strokeLinejoin="round" />
                {sr.values.map((v, i) => (
                  <circle key={i} cx={x(i)} cy={y(v)} r="2.2" fill={CHART_SERIES[i % CHART_SERIES.length]} />
                ))}
              </g>
            ))}
          </svg>
        </div>
      )}
    </Card>
  );
};

const PageCategories = () => {
  const { preset, account, range: customRange, setPreset, setAccount, setRange } = useSharedFilter();
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [newName, setNewName] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const [selectedCat, setSelectedCat] = React.useState(null);
  // Höchstens 5 gleichzeitig: darüber sind Linien auf dunklem Grund nicht mehr
  // unterscheidbar, und die Kategoriefarben wurden für Punkte und Balken
  // gewählt, nicht für nebeneinanderliegende 2px-Linien.
  const [compare, setCompare] = React.useState([]);
  const toggleCompare = React.useCallback((c) => {
    setCompare(prev => prev.includes(c.name)
      ? prev.filter(n => n !== c.name)
      : (prev.length >= 5 ? prev : [...prev, c.name]));
  }, []);
  const toast = useToast();

  const fetchData = React.useCallback(() => {
    setLoading(true);
    const { date_from, date_to } = presetToDates(preset) || range || { date_from: "", date_to: "" };
    const params = new URLSearchParams({ account });
    if (date_from) params.set("date_from", date_from);
    if (date_to) params.set("date_to", date_to);
    fetch(`/api/categories?${params}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [preset, account]);

  React.useEffect(() => { fetchData(); }, [fetchData]);

  const createCategory = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    const res = await fetch("/api/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName.trim() }),
    });
    setCreating(false);
    if (res.ok) {
      setNewName("");
      fetchData();
      toast(`Kategorie "${newName.trim()}" erstellt`, "pos");
    } else {
      const d = await res.json().catch(() => ({}));
      toast(d.detail || "Fehler beim Erstellen", "neg");
    }
  };

  const deleteCategory = async (name) => {
    const res = await fetch(`/api/categories/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (res.ok) {
      if (selectedCat?.id === name) setSelectedCat(null);
      fetchData();
      toast(`Kategorie "${name}" gelöscht`);
    } else {
      const d = await res.json().catch(() => ({}));
      toast(d.detail || "Löschen fehlgeschlagen", "neg");
    }
  };

  if (loading && !data) return <Spinner />;

  const cats = data?.categories || [];
  const allAccounts = data?.all_accounts || [];
  const maxSpend = Math.max(...cats.map(c => c.spend || 0), 1);
  const builtIn = cats.filter(c => !c.is_custom);
  const custom = cats.filter(c => c.is_custom);

  const toggleDetail = (cat) => {
    setSelectedCat(prev => prev?.id === cat.id ? null : cat);
  };

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20, maxWidth: 980 }}>
      {/* Filter bar */}
      <FilterBar
        preset={preset} onPreset={setPreset}
        account={account} onAccount={setAccount}
        accounts={allAccounts}
        multiAccount
        dateFrom={customRange.date_from} dateTo={customRange.date_to}
        onRange={setRange}
      />

      <CategoryCompare cats={compare} preset={preset} account={account} range={customRange}
        onRemove={(name) => setCompare(prev => prev.filter(n => n !== name))} />

      {/* Create new category */}
      <Card>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14 }}>Neue Kategorie</div>
        <div style={{ display: "flex", gap: 10 }}>
          <input
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && createCategory()}
            placeholder="Kategoriename …"
            style={{
              flex: 1, padding: "9px 14px", background: "var(--bg-2)", border: "1px solid var(--line)",
              borderRadius: 10, color: "var(--fg)", fontSize: 13, fontFamily: "inherit", outline: "none",
            }}
          />
          <Btn variant="primary" icon="plus" onClick={createCategory} disabled={creating || !newName.trim()}>
            {creating ? "…" : "Erstellen"}
          </Btn>
        </div>
      </Card>

      {/* Custom categories */}
      {custom.length > 0 && (
        <Card>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Eigene Kategorien</div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 14 }}>{custom.length} benutzerdefiniert · Klicken für Details</div>
          {custom.map(c => <CatRow key={c.id} c={c} isSelected={selectedCat?.id === c.id}
              compared={compare.includes(c.name)}
              compareDisabled={compare.length >= 5}
              onToggleDetail={toggleDetail} onToggleCompare={toggleCompare}
              onDelete={deleteCategory} maxSpend={maxSpend}
              preset={preset} account={account} range={customRange} />)}
        </Card>
      )}

      {/* Built-in categories */}
      <Card>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Eingebaute Kategorien</div>
        <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 14 }}>{builtIn.length} Kategorien · Klicken für Details</div>
        {builtIn.map(c => <CatRow key={c.id} c={c} isSelected={selectedCat?.id === c.id}
              compared={compare.includes(c.name)}
              compareDisabled={compare.length >= 5}
              onToggleDetail={toggleDetail} onToggleCompare={toggleCompare}
              onDelete={deleteCategory} maxSpend={maxSpend}
              preset={preset} account={account} range={customRange} />)}
      </Card>
    </div>
  );
};

window.PageCategories = PageCategories;
