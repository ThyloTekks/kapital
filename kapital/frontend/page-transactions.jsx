// Page: Transactions

const PageTransactions = () => {
  const [search, setSearch] = React.useState("");
  const [filterCat, setFilterCat] = React.useState("all");
  const [filterAcc, setFilterAcc] = React.useState("all");
  const [filterSonder, setFilterSonder] = React.useState("all");
  const [offset, setOffset] = React.useState(0);
  const [sort, setSort] = React.useState("date_desc");
  const [editingId, setEditingId] = React.useState(null);
  const [selected, setSelected] = React.useState([]);
  const [deleting, setDeleting] = React.useState(false);
  const [bulking, setBulking] = React.useState(false);
  const [error, setError] = React.useState("");
  const [reloadTick, setReloadTick] = React.useState(0);
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [catList, setCatList] = React.useState([]);
  const toast = useToast();
  const PER_PAGE = 100;

  const fetchData = React.useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ search, category: filterCat, account: filterAcc, sonderausgabe: filterSonder, sort, limit: PER_PAGE, offset });
    fetch(`/api/transactions?${params}`)
      .then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`);
        return j;
      })
      // Fehler nicht wie "keine Daten" aussehen lassen — vorher landete jeder
      // 500er stumm in derselben leeren Tabelle.
      .then(d => { setData(d); setError(""); setLoading(false); })
      .catch(e => { setError(e.message || "Unbekannter Fehler"); setLoading(false); });
  }, [search, filterCat, filterAcc, filterSonder, sort, offset, reloadTick]);

  const fetchCats = React.useCallback(() => {
    fetch("/api/categories").then(r => r.json()).then(d => setCatList(d.categories || d)).catch(() => {});
  }, []);

  React.useEffect(() => { fetchCats(); }, [fetchCats]);

  // Bei Filter-/Suchwechsel zurück auf Seite 1 — sonst leere Liste bei kleinem Ergebnis.
  React.useEffect(() => { setOffset(0); }, [search, filterCat, filterAcc, filterSonder]);

  React.useEffect(() => {
    const t = setTimeout(fetchData, 250);
    return () => clearTimeout(t);
  }, [fetchData]);

  const toggleSonderausgabe = async (txHash, current) => {
    const res = await fetch(`/api/transactions/${txHash}/sonderausgabe`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_sonderausgabe: !current }),
    });
    if (res.ok) {
      fetchData();
      toast(!current ? "Als Sonderausgabe markiert" : "Sonderausgabe-Markierung entfernt");
    }
  };

  const toggleAbo = async (txHash, current, label) => {
    const res = await fetch(`/api/transactions/${txHash}/abo`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_abo: !current }),
    });
    if (res.ok) {
      fetchData();
      toast(!current
        ? `„${label}" als Abo markiert — auch künftige gleiche Buchungen`
        : "Abo-Markierung entfernt");
    } else {
      const d = await res.json().catch(() => ({}));
      toast(d.detail || "Fehler", "neg");
    }
  };

  const bulkUpdate = async (patch, label) => {
    setBulking(true);
    try {
      const res = await fetch("/api/transactions/bulk", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tx_hashes: selected, ...patch }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j.detail || `Serverfehler ${res.status}`);
      setSelected([]);
      setReloadTick(t => t + 1);
    } catch (e) {
      setError(`${label} fehlgeschlagen: ${e.message}`);
    } finally {
      setBulking(false);
    }
  };
  const bulkSonder = (flag) => bulkUpdate({ is_sonderausgabe: flag }, "Markieren");
  const bulkCategory = (cat) => bulkUpdate({ category: cat }, "Zuordnen");

  const deleteSelected = async () => {
    setDeleting(true);
    const res = await fetch("/api/transactions/bulk", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tx_hashes: selected }),
    });
    const d = await res.json().catch(() => ({}));
    setDeleting(false);
    if (res.ok) {
      setSelected([]);
      fetchData();
      toast(`${d.deleted} Buchung${d.deleted === 1 ? "" : "en"} gelöscht`);
    } else {
      toast("Löschen fehlgeschlagen", "neg");
    }
  };

  const updateCategory = async (txHash, category) => {
    const res = await fetch(`/api/transactions/${txHash}/category`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category }),
    });
    if (res.ok) {
      setEditingId(null);
      fetchData();
      toast(`Kategorie → ${category}`);
    }
  };

  const catMap = React.useMemo(() => {
    const m = {};
    catList.forEach(c => m[c.id] = c);
    return m;
  }, [catList]);

  if (loading && !data) return <Spinner />;

  const items = data?.items || [];
  const total = data?.total || 0;
  const categories = data?.categories || [];
  const accounts = data?.accounts || [];

  // Group by date
  const groups = {};
  items.forEach(t => {
    const d = t.date;
    if (!groups[d]) groups[d] = [];
    groups[d].push(t);
  });
  const sortedDates = Object.keys(groups).sort((a, b) => b.localeCompare(a));
  // Nach Betrag sortiert wird flach gerendert. Die Datumsgruppierung würde die
  // Sortierung sonst wieder aufheben: sie ordnet die Gruppen nach Datum, und
  // innerhalb einer Gruppe stünden zwei grosse Beträge zufällig weit
  // auseinander.
  const byAmount = sort.startsWith("amount");

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 16 }}>
      <WarningStrip warnings={error ? [error] : []} onDismiss={() => setError("")} />
      {/* Toolbar */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 200, display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 10 }}>
          <Icon name="search" size={14} stroke="var(--muted)" />
          <input value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
            placeholder="Suche nach Empfänger, Beschreibung …"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--fg)", fontSize: 13, fontFamily: "inherit" }} />
          <span style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--mono)" }}>{total}</span>
        </div>
        <select value={filterCat} onChange={(e) => { setFilterCat(e.target.value); setOffset(0); }} style={{
          padding: "9px 12px", background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 10,
          color: "var(--fg)", fontSize: 13, fontFamily: "inherit", outline: "none",
        }}>
          <option value="all">Alle Kategorien</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filterAcc} onChange={(e) => { setFilterAcc(e.target.value); setOffset(0); }} style={{
          padding: "9px 12px", background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 10,
          color: "var(--fg)", fontSize: 13, fontFamily: "inherit", outline: "none",
        }}>
          <option value="all">Alle Konten</option>
          {accounts.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={filterSonder} onChange={(e) => { setFilterSonder(e.target.value); setOffset(0); }} style={{
          padding: "9px 12px", background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 10,
          color: filterSonder === "true" ? "var(--warning)" : "var(--fg)", fontSize: 13, fontFamily: "inherit", outline: "none",
        }}>
          <option value="all">Alle Buchungen</option>
          <option value="false">Ohne Sonderausgaben</option>
          <option value="true">Nur Sonderausgaben</option>
        </select>
        <select value={sort} onChange={(e) => { setSort(e.target.value); setOffset(0); }} style={{
          padding: "9px 12px", background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 10,
          color: sort === "date_desc" ? "var(--fg)" : "var(--accent)", fontSize: 13, fontFamily: "inherit", outline: "none",
        }} title="Sortierung">
          <option value="date_desc">Neueste zuerst</option>
          <option value="date_asc">Älteste zuerst</option>
          <option value="amount_abs_desc">Betrag: grösste zuerst</option>
          <option value="amount_abs_asc">Betrag: kleinste zuerst</option>
          <option value="amount_asc">Grösste Ausgaben zuerst</option>
          <option value="amount_desc">Grösste Eingänge zuerst</option>
        </select>
        <Btn variant="secondary" icon="download" onClick={() => window.open("/api/transactions/export")}>CSV</Btn>
      </div>

      {/* Bulk bar */}
      {selected.length > 0 && (
        <Card padding={12}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 500 }}>{selected.length} ausgewählt</span>
            <div style={{ flex: 1 }} />
            {/* Sonderausgaben im Stapel — das Flag steuert die Grundlast, und
                bei tausenden Zeilen ist Einzelklicken der falsche Weg. */}
            <Btn variant="secondary" size="sm" disabled={bulking}
                 onClick={() => bulkSonder(true)}>⚑ Sonderausgabe</Btn>
            <Btn variant="ghost" size="sm" disabled={bulking}
                 onClick={() => bulkSonder(false)}>Markierung entfernen</Btn>
            <select value="" disabled={bulking} onChange={(e) => e.target.value && bulkCategory(e.target.value)}
              style={{ padding: "6px 10px", background: "var(--bg-2)", border: "1px solid var(--line)",
                       borderRadius: 8, color: "var(--fg)", fontSize: 12, fontFamily: "inherit" }}>
              <option value="">Kategorie zuweisen …</option>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <Btn variant="ghost" size="sm" onClick={() => setSelected([])}>Auswahl aufheben</Btn>
            <button onClick={deleteSelected} disabled={deleting} style={{
              padding: "5px 14px", borderRadius: 8, border: "1px solid var(--neg)",
              background: "transparent", color: "var(--neg)", fontSize: 12,
              fontFamily: "inherit", fontWeight: 500, cursor: deleting ? "not-allowed" : "pointer",
              opacity: deleting ? 0.5 : 1,
            }}>
              {deleting ? "Lösche …" : `${selected.length} löschen`}
            </button>
          </div>
        </Card>
      )}

      {/* Table */}
      {items.length === 0 ? <EmptyState title="Keine Buchungen" desc="Passe die Filter an oder importiere Daten." /> : (
        <Card padding={0}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--line)" }}>
                <th style={{ textAlign: "left", padding: "11px 20px", fontWeight: 500, width: 30 }}></th>
                <th style={{ textAlign: "left", padding: "11px 0", fontWeight: 500 }}>Buchungstext</th>
                <th style={{ textAlign: "left", padding: "11px 14px", fontWeight: 500, width: 190 }}>Kategorie</th>
                <th style={{ textAlign: "left", padding: "11px 14px", fontWeight: 500, width: 130 }}>Konto</th>
                <th style={{ textAlign: "center", padding: "11px 10px", fontWeight: 500, width: 40 }} title="Sonderausgabe">S</th>
                <th style={{ textAlign: "right", padding: "11px 20px", fontWeight: 500, width: 120 }}>Betrag</th>
              </tr>
            </thead>
            <tbody>
              {(byAmount ? [null] : sortedDates).map(date => (
                <React.Fragment key={date ?? "__flat__"}>
                  {!byAmount && (
                  <tr style={{ background: "var(--bg-0)" }}>
                    <td colSpan={6} style={{ padding: "7px 20px", fontSize: 11, color: "var(--muted)", fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--line)" }}>
                      {fmtDate(date)} · {groups[date].length} Buchung{groups[date].length === 1 ? "" : "en"}
                    </td>
                  </tr>
                  )}
                  {(byAmount ? items : groups[date]).map(t => {
                    const cat = catMap[t.category];
                    const catColor = cat?.color || "var(--muted)";
                    const isSelected = selected.includes(t.id);
                    return (
                      <tr key={t.id} style={{
                        borderBottom: "1px solid var(--line)",
                        background: isSelected ? "var(--accent-soft)" : "transparent",
                      }}>
                        <td style={{ padding: "11px 20px" }}>
                          <input type="checkbox" checked={isSelected}
                            onChange={() => setSelected(s => s.includes(t.id) ? s.filter(x => x !== t.id) : [...s, t.id])}
                            style={{ accentColor: "var(--accent)", cursor: "pointer" }} />
                        </td>
                        <td style={{ padding: "11px 0" }}>
                          <div style={{ fontWeight: 500 }}>{t.payee || t.description}</div>
                          {t.payee && t.description && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 1 }}>{t.description}</div>}
                          {t.is_transfer && <Pill tone="neutral" size="sm">Umbuchung</Pill>}
                        </td>
                        <td style={{ padding: "11px 14px", position: "relative" }}>
                          {editingId === t.id ? (
                            <div style={{
                              position: "absolute", top: 4, left: 4, zIndex: 20,
                              background: "var(--bg-1)", border: "1px solid var(--line)",
                              borderRadius: 10, padding: 6, minWidth: 210,
                              boxShadow: "0 12px 36px var(--shadow)",
                            }}>
                              {catList.map(c => (
                                <button key={c.id} onClick={() => updateCategory(t.id, c.id)} style={{
                                  display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", width: "100%",
                                  background: c.id === t.category ? "var(--bg-2)" : "transparent",
                                  border: "none", color: "var(--fg)", fontSize: 12, cursor: "pointer",
                                  fontFamily: "inherit", borderRadius: 6, textAlign: "left",
                                }}>
                                  <span style={{ width: 8, height: 8, borderRadius: 2, background: c.color, flexShrink: 0 }} />
                                  {c.name}
                                  {c.id === t.category && <span style={{ marginLeft: "auto", color: "var(--accent)" }}>✓</span>}
                                </button>
                              ))}
                              <button onClick={() => setEditingId(null)} style={{ display: "flex", justifyContent: "center", padding: "5px", width: "100%", background: "transparent", border: "none", color: "var(--muted)", fontSize: 11, cursor: "pointer", fontFamily: "inherit", marginTop: 4 }}>
                                ✕ Abbrechen
                              </button>
                            </div>
                          ) : (
                            <button onClick={() => setEditingId(t.id)} style={{
                              display: "inline-flex", alignItems: "center", gap: 7, padding: "3px 9px",
                              background: `${catColor}22`,
                              color: catColor,
                              border: `1px solid ${catColor}44`,
                              borderRadius: 999, fontSize: 11, cursor: "pointer", fontFamily: "inherit", fontWeight: 500,
                            }}>
                              {cat?.icon || "•"} {t.category}
                            </button>
                          )}
                        </td>
                        <td style={{ padding: "11px 14px", color: "var(--muted)", fontSize: 11 }}>{t.account}</td>
                        <td style={{ padding: "11px 10px", textAlign: "center" }}>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
                            <button
                              onClick={() => toggleAbo(t.id, t.is_abo, t.payee || t.description)}
                              title={t.is_abo ? "Abo-Markierung entfernen" : "Als Abo markieren (auch künftige gleiche Buchungen)"}
                              style={{
                                width: 22, height: 22, borderRadius: 4, border: "none", cursor: "pointer", fontSize: 12,
                                background: t.is_abo ? "rgba(56,189,248,0.15)" : "transparent",
                                color: t.is_abo ? "var(--accent)" : "var(--muted)",
                                display: "flex", alignItems: "center", justifyContent: "center",
                              }}
                            >🔁</button>
                            <button
                              onClick={() => toggleSonderausgabe(t.id, t.is_sonderausgabe)}
                              title={t.is_sonderausgabe ? "Sonderausgabe entfernen" : "Als Sonderausgabe markieren"}
                              style={{
                                width: 22, height: 22, borderRadius: 4, border: "none", cursor: "pointer", fontSize: 12,
                                background: t.is_sonderausgabe ? "rgba(245,158,11,0.15)" : "transparent",
                                color: t.is_sonderausgabe ? "var(--warn-dim)" : "var(--muted)",
                                display: "flex", alignItems: "center", justifyContent: "center",
                              }}
                            >⚑</button>
                          </div>
                        </td>
                        <td style={{
                          padding: "11px 20px", textAlign: "right", fontFamily: "var(--mono)", fontWeight: 500,
                          color: t.amount > 0 ? "var(--pos)" : "var(--fg)",
                        }}>
                          {fmtEUR(t.amount, { sign: t.amount > 0 })}
                          {t.is_sonderausgabe && <div style={{ fontSize: 9, color: "var(--warn-dim)", letterSpacing: "0.05em", textTransform: "uppercase", marginTop: 1 }}>Sonderausgabe</div>}
                        </td>
                      </tr>
                    );
                  })}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Pagination */}
      {total > PER_PAGE && (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 12 }}>
          <Btn variant="secondary" size="sm" onClick={() => setOffset(Math.max(0, offset - PER_PAGE))} disabled={offset === 0}>← Zurück</Btn>
          <span style={{ fontSize: 12, color: "var(--muted)", fontFamily: "var(--mono)" }}>
            {offset + 1}–{Math.min(offset + PER_PAGE, total)} von {total}
          </span>
          <Btn variant="secondary" size="sm" onClick={() => setOffset(offset + PER_PAGE)} disabled={offset + PER_PAGE >= total}>Weiter →</Btn>
        </div>
      )}
    </div>
  );
};

window.PageTransactions = PageTransactions;
