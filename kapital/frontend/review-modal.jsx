// Zwangs-Zuordnung: Vollbild-Gate für alle offenen Buchungen eines Imports

const normPayee = (s) => (s || "").trim().toLowerCase();

const ReviewRow = ({ item, value, rule, categories, onCategory, onRule, sameCount }) => {
  const meta = categories.find((c) => c.id === value) || null;
  const suggested = item.suggestion;

  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 14, padding: "13px 20px",
      borderBottom: "1px solid var(--line)",
      background: value ? "var(--accent-soft)" : "transparent",
      transition: "background 0.18s",
    }}>
      {/* Status */}
      <div style={{
        width: 22, height: 22, borderRadius: 6, flexShrink: 0, marginTop: 2,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: value ? "var(--accent)" : "var(--bg-2)",
        border: value ? "none" : "1px solid var(--line)",
        transition: "all 0.18s",
      }}>
        {value ? <Icon name="check" size={13} stroke="var(--on-accent)" strokeWidth={2.6} /> : null}
      </div>

      {/* Buchung */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>
            {item.merchant || item.payee || "— ohne Empfänger —"}
          </span>
          {item.is_aggregator && item.merchant && (
            <span style={{ fontSize: 10, color: "var(--muted)" }}>über {item.payee.split(" ")[0]}</span>
          )}
          <span style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--mono)" }}>
            {fmtDate(item.date)}
          </span>
          {sameCount > 1 && (
            <Pill tone="neutral" size="sm">{sameCount}× im Monat</Pill>
          )}
        </div>
        <div style={{
          fontSize: 11, color: "var(--muted)", marginTop: 3,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 460,
        }} title={item.description}>
          {item.description}
        </div>

        {/* Regel */}
        {value && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={!!rule}
                onChange={(e) => onRule(item.id, e.target.checked ? (
                  item.is_aggregator && item.merchant
                    ? { pattern: item.merchant.slice(0, 40), field: "description" }
                    : { pattern: (item.payee || "").slice(0, 40), field: "payee" }
                ) : null)}
                style={{ accentColor: "var(--accent)", cursor: "pointer" }}
              />
              Regel merken
            </label>
            {rule && (
              <input
                value={rule.pattern}
                onChange={(e) => onRule(item.id, { ...rule, pattern: e.target.value })}
                placeholder="Stichwort im Empfänger"
                style={{
                  flex: 1, maxWidth: 260, background: "var(--bg-2)", border: "1px solid var(--line)",
                  borderRadius: 6, padding: "4px 8px", color: "var(--fg)", fontSize: 11,
                  fontFamily: "var(--mono)",
                }}
              />
            )}
          </div>
        )}
      </div>

      {/* Betrag */}
      <div style={{
        fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600, marginTop: 1,
        color: item.amount < 0 ? "var(--fg)" : "var(--pos)", whiteSpace: "nowrap",
      }}>
        {fmtEUR(item.amount, { sign: true })}
      </div>

      {/* Kategorie */}
      <div style={{ display: "flex", alignItems: "center", gap: 7, flexShrink: 0 }}>
        {suggested && value !== suggested && (
          <button
            onClick={() => onCategory(item.id, suggested)}
            title={`${item.suggestion_hits}× bisher so zugeordnet`}
            style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              background: "var(--accent-soft)", border: "1px solid var(--accent-soft)",
              color: "var(--accent)", padding: "5px 10px", borderRadius: 7,
              fontSize: 11, fontWeight: 500, cursor: "pointer", fontFamily: "inherit",
              whiteSpace: "nowrap",
            }}
          >
            <Icon name="sparkles" size={11} />
            {suggested}
          </button>
        )}
        <select
          value={value || ""}
          onChange={(e) => onCategory(item.id, e.target.value)}
          style={{
            background: "var(--bg-2)", border: `1px solid ${value ? "var(--accent-soft)" : "var(--line)"}`,
            borderRadius: 7, padding: "6px 9px", color: value ? "var(--fg)" : "var(--muted)",
            fontSize: 12, fontFamily: "inherit", cursor: "pointer", minWidth: 172,
          }}
        >
          <option value="">Kategorie wählen …</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
          ))}
        </select>
      </div>
    </div>
  );
};

const ReviewModal = ({ months = [], onClose, onFinished }) => {
  const [loading, setLoading] = React.useState(true);
  const [items, setItems] = React.useState([]);
  const [categories, setCategories] = React.useState([]);
  const [assigned, setAssigned] = React.useState({});
  const [rules, setRules] = React.useState({});
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [confirmExit, setConfirmExit] = React.useState(false);
  const toast = useToast();

  const load = React.useCallback(() => {
    setLoading(true);
    const q = months.length ? `?months=${encodeURIComponent(months.join(","))}` : "";
    fetch(`/api/review/open${q}`)
      .then((r) => r.json())
      .then((d) => {
        setItems(d.items || []);
        setCategories(d.categories || []);
        setAssigned({});
        setRules({});
        setLoading(false);
      })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [months.join(",")]);

  React.useEffect(() => { load(); }, [load]);

  // Gruppenschlüssel: der Händler, nicht der Empfänger. Bei PayPal & Co. ist
  // der Empfänger auf jeder Buchung derselbe — auf ihn zu gruppieren hätte eine
  // einzige Auswahl auf hunderte fremder Buchungen angewendet. Ein leerer
  // Schlüssel heisst ausdrücklich: nicht gruppieren.
  const keyOf = (i) => (i && i.group_key) || "";

  // Übernahme auf gleichartige Buchungen ist opt-out und wird angezeigt.
  const [cascade, setCascade] = React.useState(true);

  const setCategory = (id, cat) => {
    setAssigned((prev) => {
      const next = { ...prev };
      if (!cat) { delete next[id]; return next; }
      next[id] = cat;
      const src = items.find((i) => i.id === id);
      const key = keyOf(src);
      if (key && cascade) {
        items.forEach((i) => {
          if (i.id !== id && keyOf(i) === key && !prev[i.id]) next[i.id] = cat;
        });
      }
      return next;
    });
  };

  const setRule = (id, rule) => {
    setRules((prev) => {
      const next = { ...prev };
      if (!rule) delete next[id]; else next[id] = rule;
      return next;
    });
  };

  const payeeCounts = React.useMemo(() => {
    const m = {};
    items.forEach((i) => { const k = keyOf(i); if (k) m[k] = (m[k] || 0) + 1; });
    return m;
  }, [items]);

  // Grösste Gruppe im Stapel — macht sichtbar, wie weit eine Auswahl reicht.
  const cascadeMax = React.useMemo(
    () => Object.values(payeeCounts).reduce((m, n) => Math.max(m, n), 0),
    [payeeCounts]
  );

  const doneCount = Object.keys(assigned).length;
  const total = items.length;
  const allDone = total > 0 && doneCount === total;
  const pct = total ? Math.round((doneCount / total) * 100) : 100;

  const save = async (finish) => {
    const payload = Object.entries(assigned).map(([tx_hash, category]) => ({
      tx_hash, category,
      rule: rules[tx_hash] && rules[tx_hash].pattern.trim() ? rules[tx_hash] : null,
    }));
    if (!payload.length) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/review/assign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: payload }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Speichern fehlgeschlagen");
      // Übersprungene ausdrücklich nennen. Sie entstehen, wenn sich der
      // Bestand zwischen Laden und Speichern geändert hat — vorher meldete der
      // Toast nur die Erfolge, und die Buchung war danach still wieder offen.
      toast(
        `${d.updated} Buchungen zugeordnet` +
        (d.rules_added ? `, ${d.rules_added} Regeln angelegt` : "") +
        (d.skipped ? ` — ${d.skipped} nicht mehr auffindbar, bitte erneut prüfen` : "")
      );
      if (finish) {
        onFinished && onFinished();
        onClose();
      } else {
        load();
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  // Nach Monaten gruppieren
  const groups = React.useMemo(() => {
    const g = {};
    items.forEach((i) => { (g[i.month] = g[i.month] || []).push(i); });
    return Object.entries(g).sort((a, b) => b[0].localeCompare(a[0]));
  }, [items]);

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 8000,
      background: "rgba(6,9,13,0.86)", backdropFilter: "blur(6px)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
      animation: "gateIn 0.22s ease",
    }}>
      <style>{`
        @keyframes gateIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes gateUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
      `}</style>

      <div style={{
        width: "min(1080px, 100%)", maxHeight: "90vh", display: "flex", flexDirection: "column",
        background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 18,
        boxShadow: "0 24px 80px var(--shadow)", overflow: "hidden",
        animation: "gateUp 0.26s cubic-bezier(0.16,1,0.3,1)",
      }}>
        {/* Kopf */}
        <div style={{ padding: "20px 24px 16px", borderBottom: "1px solid var(--line)" }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 20 }}>
            <div>
              <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em", fontFamily: "var(--mono)" }}>
                Monatsabschluss · Schritt 1
              </div>
              <h2 style={{ margin: "4px 0 0", fontSize: 20, fontWeight: 600, letterSpacing: "-0.02em" }}>
                Offene Buchungen zuordnen
              </h2>
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 5 }}>
                {months.length
                  ? `Betroffene Monate: ${months.join(", ")}`
                  : "Alle offenen Buchungen"} · Erst danach gibt es Budget-Vergleich und Bewertung.
              </div>
            </div>
            <div style={{ textAlign: "right", flexShrink: 0 }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 22, fontWeight: 600, lineHeight: 1 }}>
                {doneCount}<span style={{ color: "var(--muted)", fontSize: 15 }}>/{total}</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>zugeordnet</div>
            </div>
          </div>

          {/* Fortschritt */}
          <div style={{ height: 4, background: "var(--bg-2)", borderRadius: 2, marginTop: 14, overflow: "hidden" }}>
            <div style={{
              height: "100%", width: `${pct}%`, borderRadius: 2,
              background: "linear-gradient(90deg, var(--accent), #22c55e)",
              transition: "width 0.35s cubic-bezier(0.16,1,0.3,1)",
            }} />
          </div>

          {/* Übernahme auf gleichartige Buchungen — sichtbar und abschaltbar.
              Vorher passierte das stillschweigend: eine Auswahl konnte hunderte
              weitere Buchungen mitziehen, ohne Hinweis und ohne Rückgängig. */}
          <label style={{
            display: "flex", alignItems: "center", gap: 8, marginTop: 12,
            fontSize: 12, color: "var(--muted)", cursor: "pointer",
          }}>
            <input type="checkbox" checked={cascade} onChange={(e) => setCascade(e.target.checked)} />
            <span>
              Gleiche Händler im Stapel mit zuordnen
              {cascadeMax > 1 && (
                <span style={{ color: "var(--warn)" }}>
                  {" "}— betrifft aktuell bis zu {cascadeMax} weitere Buchungen
                </span>
              )}
            </span>
          </label>
        </div>

        {/* Liste */}
        <div style={{ flex: 1, overflowY: "auto", minHeight: 200 }}>
          {loading ? (
            <Spinner />
          ) : total === 0 ? (
            <EmptyState icon="check" title="Alles zugeordnet"
              desc="In diesen Monaten ist keine Buchung mehr offen." />
          ) : (
            groups.map(([month, rows]) => (
              <div key={month}>
                <div style={{
                  position: "sticky", top: 0, zIndex: 1,
                  padding: "8px 20px", background: "var(--bg-2)",
                  borderBottom: "1px solid var(--line)",
                  fontSize: 11, fontWeight: 600, color: "var(--muted)",
                  fontFamily: "var(--mono)", letterSpacing: "0.05em",
                }}>
                  {month} · {rows.length} offen
                </div>
                {rows.map((item) => (
                  <ReviewRow
                    key={item.id}
                    item={item}
                    value={assigned[item.id] || ""}
                    rule={rules[item.id] || null}
                    categories={categories}
                    onCategory={setCategory}
                    onRule={setRule}
                    sameCount={cascade ? (payeeCounts[keyOf(item)] || 1) : 1}
                  />
                ))}
              </div>
            ))
          )}
        </div>

        {/* Fuß */}
        <div style={{
          padding: "14px 24px", borderTop: "1px solid var(--line)",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
          background: "var(--bg-1)",
        }}>
          <div style={{ fontSize: 11, color: error ? "var(--neg)" : "var(--muted)", minWidth: 0 }}>
            {error ? error
              : allDone ? "Alles zugeordnet — weiter zum Monatsabschluss."
              : total === 0 ? "Nichts mehr zu tun."
              : "Tipp: Buchungen mit gleichem Empfänger werden automatisch mit übernommen."}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            {!confirmExit ? (
              <button onClick={() => setConfirmExit(true)} style={{
                background: "transparent", border: "none", color: "var(--muted)",
                fontSize: 11, cursor: "pointer", fontFamily: "inherit", padding: "6px 4px",
              }}>Später</button>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 11, color: "var(--warn)" }}>Ohne Zuordnung schließen?</span>
                <Btn size="sm" onClick={onClose}>Ja</Btn>
                <Btn size="sm" onClick={() => setConfirmExit(false)}>Nein</Btn>
              </div>
            )}
            {total > 0 && !allDone && (
              <Btn size="md" onClick={() => save(false)} disabled={saving || doneCount === 0}>
                {saving ? "Speichere …" : `${doneCount} zwischenspeichern`}
              </Btn>
            )}
            <Btn
              variant="primary" size="md" icon="check"
              disabled={saving || (total > 0 && !allDone)}
              onClick={() => (total === 0 ? (onFinished && onFinished(), onClose()) : save(true))}
            >
              {saving ? "Speichere …" : "Fertig · zum Monatsabschluss"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
};

window.ReviewModal = ReviewModal;
