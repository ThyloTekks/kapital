// Page: Kategorien-Regeln

const PageRegeln = () => {
  const [rules, setRules] = React.useState(null);
  const [error, setError] = React.useState("");
  const [cats, setCats] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [pattern, setPattern] = React.useState("");
  const [category, setCategory] = React.useState("");
  const [field, setField] = React.useState("both");
  const [saving, setSaving] = React.useState(false);
  const [applying, setApplying] = React.useState(false);
  const toast = useToast();

  const fetchRules = React.useCallback(() => {
    setLoading(true);
    Promise.all([
      fetch("/api/regeln").then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`); return j; }),
      fetch("/api/categories").then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`); return j; }),
    ]).then(([r, c]) => {
      setRules(r);
      const cats = c.categories || c;
      setCats(cats);
      if (!category && cats.length > 0) setCategory(cats[0].id);
      setLoading(false);
    }).catch(e => { setError(e.message || "Unbekannter Fehler"); setLoading(false); });
  }, []);

  React.useEffect(() => { fetchRules(); }, [fetchRules]);

  const createRule = async () => {
    if (!pattern.trim() || !category) return;
    setSaving(true);
    const res = await fetch("/api/regeln", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pattern: pattern.trim(), category, field }),
    });
    setSaving(false);
    if (res.ok) {
      setPattern("");
      fetchRules();
      toast(`Regel "${pattern.trim()}" → ${category} erstellt`, "pos");
    } else {
      const d = await res.json().catch(() => ({}));
      toast(d.detail || "Fehler beim Erstellen", "neg");
    }
  };

  const deleteRule = async (p, f) => {
    const res = await fetch(`/api/regeln/${encodeURIComponent(p)}?field=${f}`, { method: "DELETE" });
    if (res.ok) {
      fetchRules();
      toast(`Regel "${p}" gelöscht`);
    } else {
      toast("Löschen fehlgeschlagen", "neg");
    }
  };

  const applyAll = async () => {
    setApplying(true);
    const res = await fetch("/api/regeln/apply", { method: "POST" });
    const d = await res.json().catch(() => ({}));
    setApplying(false);
    if (res.ok) toast(`Regeln angewendet auf ${d.affected} Buchungen`, "pos");
    else toast("Fehler beim Anwenden", "neg");
  };

  if (loading && !rules) return <Spinner />;

  const fieldLabel = (f) => ({ payee: "Empfänger", description: "Beschreibung", both: "Beide" }[f] || f);

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20, maxWidth: 900 }}>
      <WarningStrip warnings={error ? [error] : []} onDismiss={() => setError("")} />
      {/* Create rule */}
      <Card>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Neue Regel</div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <div style={{ flex: 2, minWidth: 200, display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", background: "var(--bg-2)", border: "1px solid var(--line)", borderRadius: 10 }}>
            <Icon name="search" size={13} stroke="var(--muted)" />
            <input
              value={pattern}
              onChange={e => setPattern(e.target.value)}
              onKeyDown={e => e.key === "Enter" && createRule()}
              placeholder="Stichwort (z.B. Netflix, Spotify …)"
              style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--fg)", fontSize: 13, fontFamily: "inherit" }}
            />
          </div>
          <select value={category} onChange={e => setCategory(e.target.value)} style={{
            flex: 1, minWidth: 140, padding: "9px 12px", background: "var(--bg-2)", border: "1px solid var(--line)",
            borderRadius: 10, color: "var(--fg)", fontSize: 13, fontFamily: "inherit", outline: "none",
          }}>
            {cats.map(c => <option key={c.id} value={c.id}>{c.icon || "•"} {c.name}</option>)}
          </select>
          <select value={field} onChange={e => setField(e.target.value)} style={{
            padding: "9px 12px", background: "var(--bg-2)", border: "1px solid var(--line)",
            borderRadius: 10, color: "var(--fg)", fontSize: 13, fontFamily: "inherit", outline: "none",
          }}>
            <option value="both">Empfänger + Beschreibung</option>
            <option value="payee">Nur Empfänger</option>
            <option value="description">Nur Beschreibung</option>
          </select>
          <Btn variant="primary" icon="plus" onClick={createRule} disabled={saving || !pattern.trim()}>
            {saving ? "…" : "Erstellen"}
          </Btn>
        </div>
        <div style={{ marginTop: 10, fontSize: 12, color: "var(--muted)" }}>
          Neue Regeln werden sofort auf alle Buchungen angewendet.
        </div>
      </Card>

      {/* Apply all button */}
      {rules?.length > 0 && (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Btn variant="secondary" icon="refresh" onClick={applyAll} disabled={applying}>
            {applying ? "Wende an …" : "Alle Regeln neu anwenden"}
          </Btn>
        </div>
      )}

      {/* Rules list */}
      {!rules || rules.length === 0 ? (
        <EmptyState title="Keine Regeln" desc="Erstelle eine Regel um Buchungen automatisch zu kategorisieren." />
      ) : (
        <Card padding={0}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontWeight: 600, fontSize: 15 }}>Regeln</div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>{rules.length} Regel{rules.length === 1 ? "" : "n"}</div>
          </div>
          {rules.map((r, i) => {
            const cat = cats.find(c => c.id === r.category);
            return (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 14, padding: "14px 20px",
                borderBottom: i < rules.length - 1 ? "1px solid var(--line)" : "none",
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <code style={{ fontSize: 13, fontFamily: "var(--mono)", fontWeight: 600, color: "var(--fg)", background: "var(--bg-2)", padding: "2px 8px", borderRadius: 6 }}>
                      {r.pattern}
                    </code>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>→</span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, padding: "2px 10px", borderRadius: 999,
                      background: `${cat?.color || "var(--muted)"}22`,
                      color: cat?.color || "var(--muted)",
                      border: `1px solid ${cat?.color || "var(--muted)"}44`,
                    }}>
                      {cat?.icon || "•"} {r.category}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)" }}>
                    Feld: {fieldLabel(r.field || "both")}
                    {r.count != null && ` · ${r.count} Treffer`}
                  </div>
                </div>
                <button onClick={() => deleteRule(r.pattern, r.field || "both")} style={{
                  background: "transparent", border: "1px solid var(--line)", cursor: "pointer",
                  color: "var(--muted)", fontSize: 12, padding: "5px 10px", borderRadius: 6,
                  fontFamily: "inherit",
                }}>Löschen</button>
              </div>
            );
          })}
        </Card>
      )}
    </div>
  );
};

window.PageRegeln = PageRegeln;
