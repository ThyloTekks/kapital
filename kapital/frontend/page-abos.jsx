// Page: Abonnements

const ABO_INTERVALS = [
  { id: "weekly",     label: "Wöchentlich" },
  { id: "biweekly",   label: "Zweiwöchentlich" },
  { id: "monthly",    label: "Monatlich" },
  { id: "bimonthly",  label: "Alle 2 Monate" },
  { id: "quarterly",  label: "Vierteljährlich" },
  { id: "halfyearly", label: "Halbjährlich" },
  { id: "yearly",     label: "Jährlich" },
];

const PageAbos = () => {
  const [data, setData] = React.useState(null);
  const [error, setError] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [cats, setCats] = React.useState([]);
  const toast = useToast();

  // Manual-add form state
  const [payee, setPayee] = React.useState("");
  const [amount, setAmount] = React.useState("");
  const [interval, setInterval] = React.useState("monthly");
  const [category, setCategory] = React.useState("Sonstiges");
  const [saving, setSaving] = React.useState(false);
  const [showAdd, setShowAdd] = React.useState(false);

  const fetchAbos = React.useCallback(() => {
    Promise.all([
      fetch("/api/abos").then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`); return j; }),
      fetch("/api/categories").then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`); return j; }),
    ]).then(([a, c]) => {
      setData(a);
      const list = c.categories || c || [];
      setCats(list);
      setLoading(false);
    }).catch(e => { setError(e.message || "Unbekannter Fehler"); setLoading(false); });
  }, []);

  React.useEffect(() => { fetchAbos(); }, [fetchAbos]);

  const intervalLabel = (iv) => ({
    weekly:     "wöchentlich",
    biweekly:   "zweiwöchentlich",
    monthly:    "monatlich",
    bimonthly:  "2-monatlich",
    quarterly:  "vierteljährlich",
    halfyearly: "halbjährlich",
    yearly:     "jährlich",
  }[iv] || iv);

  const intervalTone = (iv) => {
    if (iv === "yearly" || iv === "halfyearly") return "neutral";
    if (iv === "quarterly" || iv === "bimonthly") return "accent";
    return "pos";
  };

  const hideAbo = async (label) => {
    const res = await fetch("/api/abos/hide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label }),
    });
    if (res.ok) { fetchAbos(); toast(`"${label}" als kein Abo markiert`); }
    else toast("Fehler beim Ausblenden", "neg");
  };

  const unhideAbo = async (key) => {
    const res = await fetch("/api/abos/unhide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });
    if (res.ok) { fetchAbos(); toast("Wieder eingeblendet", "pos"); }
    else toast("Fehler", "neg");
  };

  const unforceAbo = async (key, label) => {
    const res = await fetch("/api/abos/unforce", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });
    if (res.ok) { fetchAbos(); toast(`Abo-Markierung für "${label}" entfernt`); }
    else toast("Fehler", "neg");
  };

  const deleteManual = async (id, label) => {
    const res = await fetch(`/api/abos/manual/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (res.ok) { fetchAbos(); toast(`"${label}" gelöscht`); }
    else toast("Löschen fehlgeschlagen", "neg");
  };

  const addManual = async () => {
    const amt = parseFloat(String(amount).replace(",", "."));
    if (!payee.trim() || !amt || amt <= 0) {
      toast("Name und gültiger Betrag erforderlich", "neg");
      return;
    }
    setSaving(true);
    const res = await fetch("/api/abos/manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payee: payee.trim(), avg_amount: amt, interval, category }),
    });
    setSaving(false);
    if (res.ok) {
      setPayee(""); setAmount("");
      setShowAdd(false);
      fetchAbos();
      toast(`Abo "${payee.trim()}" hinzugefügt`, "pos");
    } else {
      toast("Fehler beim Hinzufügen", "neg");
    }
  };

  if (loading) return <Spinner />;
  if (!data) return <EmptyState title="Keine Daten" desc="Importiere zuerst Kontodaten." />;

  const { subscriptions = [], total_monthly = 0, hidden = [] } = data;
  const maxCost = Math.max(...subscriptions.map(s => s.monthly_cost), 1);

  const inputStyle = {
    padding: "9px 12px", background: "var(--bg-2)", border: "1px solid var(--line)",
    borderRadius: 10, color: "var(--fg)", fontSize: 13, fontFamily: "inherit", outline: "none",
  };

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20 }}>
      <WarningStrip warnings={error ? [error] : []} onDismiss={() => setError("")} />
      {/* Summary */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        <Card>
          <Stat label="Monatliche Fixkosten" value={fmtEUR(total_monthly)} large deltaTone="neg" sub="alle Abos" />
        </Card>
        <Card>
          <Stat label="Jährliche Kosten" value={fmtEUR(total_monthly * 12)} sub="hochgerechnet" />
        </Card>
        <Card>
          <Stat label="Abonnements" value={String(subscriptions.length)} sub="erkannt + manuell" />
        </Card>
      </div>

      {/* Add manual subscription */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>Abo manuell hinzufügen</div>
          <Btn variant={showAdd ? "secondary" : "primary"} icon={showAdd ? "x" : "plus"} onClick={() => setShowAdd(v => !v)}>
            {showAdd ? "Abbrechen" : "Hinzufügen"}
          </Btn>
        </div>
        {showAdd && (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16 }}>
            <input
              value={payee}
              onChange={e => setPayee(e.target.value)}
              onKeyDown={e => e.key === "Enter" && addManual()}
              placeholder="Name (z.B. Spotify)"
              style={{ ...inputStyle, flex: 2, minWidth: 160 }}
            />
            <input
              value={amount}
              onChange={e => setAmount(e.target.value)}
              onKeyDown={e => e.key === "Enter" && addManual()}
              placeholder="Betrag €"
              inputMode="decimal"
              style={{ ...inputStyle, width: 110 }}
            />
            <select value={interval} onChange={e => setInterval(e.target.value)} style={{ ...inputStyle, minWidth: 150 }}>
              {ABO_INTERVALS.map(iv => <option key={iv.id} value={iv.id}>{iv.label}</option>)}
            </select>
            <select value={category} onChange={e => setCategory(e.target.value)} style={{ ...inputStyle, minWidth: 150 }}>
              {cats.length === 0 && <option value="Sonstiges">Sonstiges</option>}
              {cats.map(c => <option key={c.id} value={c.id}>{c.icon || "•"} {c.name || c.id}</option>)}
            </select>
            <Btn variant="primary" icon="plus" onClick={addManual} disabled={saving || !payee.trim()}>
              {saving ? "…" : "Speichern"}
            </Btn>
          </div>
        )}
      </Card>

      {/* List */}
      {subscriptions.length === 0 ? (
        <EmptyState title="Keine Abonnements" desc="Wiederkehrende Zahlungen werden automatisch erkannt — oder füge oben eines manuell hinzu." />
      ) : (
        <Card padding={0}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontWeight: 600, fontSize: 15 }}>Abonnements</div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>Sortiert nach monatlichen Kosten</div>
          </div>
          {subscriptions.map((s, i) => (
            <div key={`${s.manual ? "m" : "d"}-${s.id}-${i}`} style={{
              display: "flex", alignItems: "center", gap: 16, padding: "16px 20px",
              borderBottom: i < subscriptions.length - 1 ? "1px solid var(--line)" : "none",
            }}>
              {/* Cost bar indicator */}
              <div style={{ width: 4, height: 36, borderRadius: 2, background: "var(--accent)", opacity: 0.4 + (s.monthly_cost / maxCost) * 0.6, flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3, flexWrap: "wrap" }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{s.payee}</span>
                  <Pill tone={intervalTone(s.interval)} size="sm">{intervalLabel(s.interval)}</Pill>
                  {s.manual && <Pill tone="neutral" size="sm">manuell</Pill>}
                  {s.forced && <Pill tone="accent" size="sm">markiert</Pill>}
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)" }}>
                  {s.category}
                  {s.count != null && ` · ${s.count} Buchungen`}
                  {s.last_date && ` · zuletzt ${fmtDate(s.last_date)}`}
                </div>
              </div>
              <div style={{ textAlign: "right", flexShrink: 0 }}>
                <div style={{ fontFamily: "var(--mono)", fontWeight: 700, fontSize: 16 }}>
                  {fmtEUR(s.monthly_cost)}<span style={{ fontSize: 11, fontWeight: 400, color: "var(--muted)", marginLeft: 2 }}>/Mo</span>
                </div>
                {s.interval !== "monthly" && (
                  <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--mono)" }}>
                    Ø {fmtEUR(s.avg_amount)} pro Zahlung
                  </div>
                )}
                {/* Preisentwicklung. In einer Monatsansicht ist eine Erhöhung
                    strukturell unsichtbar: jeder einzelne Monat sieht normal
                    aus, und die Verdreifachung merkt man nach Jahren oder
                    gar nicht. */}
                {s.change_pct != null && Math.abs(s.change_pct) >= 5 && (
                  <div style={{ fontSize: 11, fontFamily: "var(--mono)", marginTop: 2,
                                color: s.change_pct > 0 ? "var(--warn)" : "var(--pos)" }}
                       title={`früher ${fmtEUR(s.first_amount)} · heute ${fmtEUR(s.last_amount)}`}>
                    {s.change_pct > 0 ? "▲" : "▼"} {Math.abs(Math.round(s.change_pct))} %
                    {" "}<span style={{ color: "var(--muted)" }}>
                      seit {s.changed_at ? fmtDate(s.changed_at) : "Beginn"}
                    </span>
                  </div>
                )}
                {/* Geteiltes Abo: brutto ist nicht dein Anteil. Bei Netflix
                    steckt ein Zusatzmitglied in derselben Abbuchung, und dafür
                    kommt regelmässig Geld zurück. */}
                {s.offset && s.offset.monthly > 0.5 && (
                  <div style={{ fontSize: 11, fontFamily: "var(--mono)", marginTop: 2, color: "var(--pos)" }}
                       title={(s.offset.quellen || []).map(q => `${q.von}: ${fmtEUR(q.monatlich)}/Mo`).join("\n")}>
                    − {fmtEUR(s.offset.monthly)} zurück ·{" "}
                    <span style={{ color: "var(--fg)" }}>
                      dein Anteil {fmtEUR(s.monthly_cost - s.offset.monthly)}
                    </span>
                  </div>
                )}
                <div style={{ fontSize: 10.5, color: "var(--muted)", fontFamily: "var(--mono)", marginTop: 2 }}>
                  {fmtEUR(s.annual_cost, { decimals: 0 })} / Jahr
                </div>
              </div>
              {/* Row action */}
              {s.manual ? (
                <button onClick={() => deleteManual(s.id, s.payee)} title="Abo löschen" style={{
                  background: "transparent", border: "1px solid var(--line)", cursor: "pointer",
                  color: "var(--muted)", fontSize: 12, padding: "5px 10px", borderRadius: 6, fontFamily: "inherit", flexShrink: 0,
                }}>Löschen</button>
              ) : s.forced ? (
                <button onClick={() => unforceAbo(s.key, s.payee)} title="Abo-Markierung entfernen" style={{
                  background: "transparent", border: "1px solid var(--line)", cursor: "pointer",
                  color: "var(--muted)", fontSize: 12, padding: "5px 10px", borderRadius: 6, fontFamily: "inherit", flexShrink: 0,
                }}>Nicht mehr markieren</button>
              ) : (
                <button onClick={() => hideAbo(s.payee)} title="Ist kein Abo — dauerhaft ausblenden" style={{
                  background: "transparent", border: "1px solid var(--line)", cursor: "pointer",
                  color: "var(--muted)", fontSize: 12, padding: "5px 10px", borderRadius: 6, fontFamily: "inherit", flexShrink: 0,
                }}>Kein Abo</button>
              )}
            </div>
          ))}
          {/* Total row */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 20px", borderTop: "1px solid var(--line)", background: "var(--bg-0)" }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Gesamt</span>
            <div style={{ fontFamily: "var(--mono)", fontWeight: 700, fontSize: 17, color: "var(--neg)" }}>
              {fmtEUR(total_monthly)}<span style={{ fontSize: 12, fontWeight: 400, color: "var(--muted)", marginLeft: 2 }}>/Monat</span>
            </div>
          </div>
        </Card>
      )}

      {/* Hidden (excluded) subscriptions */}
      {hidden.length > 0 && (
        <Card padding={0}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--line)", fontWeight: 600, fontSize: 14, color: "var(--muted)" }}>
            Ausgeblendet ({hidden.length}) — als „kein Abo“ markiert
          </div>
          {hidden.map((h, i) => (
            <div key={h.key} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "12px 20px",
              borderBottom: i < hidden.length - 1 ? "1px solid var(--line)" : "none",
            }}>
              <span style={{ fontSize: 13, color: "var(--muted)" }}>{h.label}</span>
              <button onClick={() => unhideAbo(h.key)} style={{
                background: "transparent", border: "1px solid var(--line)", cursor: "pointer",
                color: "var(--fg)", fontSize: 12, padding: "5px 10px", borderRadius: 6, fontFamily: "inherit",
              }}>Wieder einblenden</button>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
};

window.PageAbos = PageAbos;
