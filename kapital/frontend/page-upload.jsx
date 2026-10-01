// Page: Upload / Import

const AccountDeleteRow = ({ account, onDelete }) => {
  const [confirming, setConfirming] = React.useState(false);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
      <div style={{ width: 32, height: 32, borderRadius: 8, background: "var(--bg-2)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Icon name="bank" size={15} stroke="var(--muted)" />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 500 }}>{account.name}</div>
        <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--mono)" }}>{account.count} Buchungen</div>
      </div>
      {!confirming ? (
        <button onClick={() => setConfirming(true)} style={{
          background: "transparent", border: "1px solid var(--line)", color: "var(--muted)",
          padding: "4px 10px", borderRadius: 7, fontSize: 11, cursor: "pointer", fontFamily: "inherit",
        }}>Löschen</button>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, color: "var(--neg)" }}>{account.count} Buchungen löschen?</span>
          <button onClick={() => { onDelete(account.name); setConfirming(false); }} style={{
            background: "var(--neg)", border: "none", color: "#fff",
            padding: "4px 10px", borderRadius: 7, fontSize: 11, cursor: "pointer", fontFamily: "inherit", fontWeight: 600,
          }}>Ja</button>
          <button onClick={() => setConfirming(false)} style={{
            background: "transparent", border: "1px solid var(--line)", color: "var(--muted)",
            padding: "4px 10px", borderRadius: 7, fontSize: 11, cursor: "pointer", fontFamily: "inherit",
          }}>Nein</button>
        </div>
      )}
    </div>
  );
};


// ── Sicherung der Konfiguration ──────────────────────────────────────────────
// Die Buchungen liegen versioniert als Parquet. Die Handarbeit steckt in den
// JSON-Dateien — Regeln, Kontonamen, Budgets, ISIN-Zuordnungen. Genau die
// liessen sich bisher nicht sichern, und genau die lassen sich aus keinem
// Bankexport wiederherstellen.
const BackupCard = () => {
  const [withSecrets, setWithSecrets] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [report, setReport] = React.useState(null);
  const [err, setErr] = React.useState("");
  const fileRef = React.useRef(null);
  const toast = useToast();

  const pick = () => fileRef.current && fileRef.current.click();

  const onFile = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true); setErr(""); setReport(null);
    try {
      const payload = JSON.parse(await file.text());
      const res = await fetch("/api/settings/restore", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload, dry_run: true }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail || `Serverfehler ${res.status}`);
      setReport({ payload, ...j });
    } catch (e2) {
      setErr(e2.message || "Datei konnte nicht gelesen werden");
    } finally { setBusy(false); }
  };

  const applyRestore = async () => {
    if (!report) return;
    setBusy(true); setErr("");
    try {
      const res = await fetch("/api/settings/restore", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload: report.payload, dry_run: false }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail || `Serverfehler ${res.status}`);
      toast(`${j.written.length} Dateien zurückgespielt`, "pos");
      setReport(null);
    } catch (e2) {
      setErr(e2.message);
    } finally { setBusy(false); }
  };

  return (
    <Card>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Konfiguration sichern</div>
      <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 14, lineHeight: 1.55 }}>
        Regeln, Kontobezeichnungen, Budgets, ISIN-Zuordnungen und Abo-Ausnahmen.
        Die Buchungen selbst sind davon nicht betroffen — die liegen als Parquet
        mit fünf Vorgängerversionen.
      </div>

      <WarningStrip warnings={err ? [err] : []} onDismiss={() => setErr("")} />

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: err ? 12 : 0 }}>
        <Btn variant="primary" icon="download" disabled={busy}
             onClick={() => window.open(`/api/settings/backup?include_secrets=${withSecrets}`)}>
          Sicherung herunterladen
        </Btn>
        <Btn variant="secondary" icon="upload" disabled={busy} onClick={pick}>
          Sicherung einspielen …
        </Btn>
        <input ref={fileRef} type="file" accept="application/json,.json"
               onChange={onFile} style={{ display: "none" }} />
        <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, color: "var(--muted)", cursor: "pointer" }}>
          <input type="checkbox" checked={withSecrets} onChange={(e) => setWithSecrets(e.target.checked)} />
          API-Schlüssel mitsichern
        </label>
      </div>
      {withSecrets && (
        <div style={{ fontSize: 11, color: "var(--warn)", marginTop: 8 }}>
          Die Datei enthält dann deine API-Schlüssel im Klartext — nicht weitergeben.
        </div>
      )}

      {report && (
        <div style={{ marginTop: 16, padding: "12px 14px", background: "var(--bg-2)", borderRadius: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
            Vorschau — es wird noch nichts geschrieben
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
            {report.would_write.map(w => (
              <div key={w.file} style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{w.file}</span>
                <span style={{ color: "var(--muted)", fontFamily: "var(--mono)" }}>
                  {w.entries_new} Einträge {w.exists ? "· überschreibt vorhandene" : "· neu"}
                </span>
              </div>
            ))}
          </div>
          {report.rejected.length > 0 && (
            <div style={{ fontSize: 11, color: "var(--warn)", marginTop: 8 }}>
              Übersprungen (unbekannte Dateien): {report.rejected.join(", ")}
            </div>
          )}
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 10, lineHeight: 1.5 }}>
            Der bisherige Stand wird vorher in <code>data/_restore_backup_…</code> abgelegt.
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <Btn variant="primary" size="sm" onClick={applyRestore} disabled={busy}>
              {busy ? "…" : "Jetzt einspielen"}
            </Btn>
            <Btn variant="ghost" size="sm" onClick={() => setReport(null)}>Abbrechen</Btn>
          </div>
        </div>
      )}
    </Card>
  );
};

const PageUpload = () => {
  const [dragging, setDragging] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [results, setResults] = React.useState([]);
  const [accounts, setAccounts] = React.useState([]);
  const [confirmAll, setConfirmAll] = React.useState(false);
  const toast = useToast();

  const fetchAccounts = React.useCallback(() => {
    fetch("/api/transactions?limit=1")
      .then(r => r.json())
      .then(d => {
        // Get per-account counts by fetching once per account
        const accs = d.accounts || [];
        Promise.all(
          accs.map(a =>
            fetch(`/api/transactions?account=${encodeURIComponent(a)}&limit=1`)
              .then(r => r.json())
              .then(d2 => ({ name: a, count: d2.total }))
          )
        ).then(setAccounts);
      })
      .catch(() => {});
  }, []);

  React.useEffect(() => { fetchAccounts(); }, [fetchAccounts]);

  const deleteAccount = async (account) => {
    const res = await fetch(`/api/transactions/account/${encodeURIComponent(account)}`, { method: "DELETE" });
    const d = await res.json().catch(() => ({}));
    if (res.ok) {
      toast(`${d.deleted} Buchungen von "${account}" gelöscht`);
      fetchAccounts();
    } else {
      toast("Löschen fehlgeschlagen", "neg");
    }
  };

  const deleteAll = async () => {
    const res = await fetch("/api/transactions/all", { method: "DELETE" });
    const d = await res.json().catch(() => ({}));
    if (res.ok) {
      toast(`Alle ${d.deleted} Buchungen gelöscht`);
      setConfirmAll(false);
      fetchAccounts();
    } else {
      toast("Löschen fehlgeschlagen", "neg");
    }
  };

  const handleFiles = async (files) => {
    const list = Array.from(files);
    setUploading(true);
    const newResults = [];
    const touchedMonths = new Set();
    let openAfterImport = 0;
    for (const file of list) {
      try {
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch("/api/upload", { method: "POST", body: fd });
        // Defensiv parsen: bei Server-Fehlern kann die Antwort Plaintext sein,
        // nicht JSON → sonst "Unexpected token ... is not valid JSON".
        const txt = await res.text();
        let data;
        try { data = JSON.parse(txt); }
        catch { data = { ok: false, detail: txt.slice(0, 300) || `HTTP ${res.status}` }; }
        if (res.ok && data.ok) {
          newResults.push({ file: file.name, ...data, error: null });
          const msg = data.n_new > 0
            ? `+${data.n_new} Buchungen · ${data.format_name}`
            : `Alle Buchungen bereits vorhanden · ${data.format_name}`;
          toast(msg, data.n_new > 0 ? "pos" : "neutral");
          (data.affected_months || []).forEach((m) => touchedMonths.add(m));
          openAfterImport = Math.max(openAfterImport, data.n_open_affected || 0);
          fetchAccounts();
        } else {
          newResults.push({ file: file.name, error: data.detail || "Unbekannter Fehler" });
          toast(`${file.name}: Import fehlgeschlagen`, "neg");
        }
      } catch (e) {
        newResults.push({ file: file.name, error: e.message });
        toast(`${file.name}: Netzwerkfehler`, "neg");
      }
    }
    setResults(r => [...newResults, ...r]);
    setUploading(false);

    // Zwangs-Zuordnung: sobald ein Import einen Monat berührt hat, in dem noch
    // Buchungen offen sind, öffnet sich das Gate.
    if (touchedMonths.size > 0 && openAfterImport > 0) {
      const months = Array.from(touchedMonths).sort().reverse();
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent("kapital:review", { detail: { months } }));
      }, 450);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20, maxWidth: 760 }}>
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        style={{
          border: `2px dashed ${dragging ? "var(--accent)" : "var(--line)"}`,
          borderRadius: 16,
          padding: "52px 32px",
          textAlign: "center",
          background: dragging ? "var(--accent-soft)" : "var(--bg-1)",
          transition: "all 0.15s",
          cursor: "pointer",
        }}
        onClick={() => document.getElementById("file-input").click()}
      >
        <input id="file-input" type="file" multiple accept=".csv,.pdf" style={{ display: "none" }}
          onChange={(e) => handleFiles(e.target.files)} />
        <div style={{ fontSize: 36, marginBottom: 12 }}>
          {uploading ? "⏳" : dragging ? "📂" : "📤"}
        </div>
        <div style={{ fontSize: 17, fontWeight: 600, marginBottom: 6 }}>
          {uploading ? "Importiere …" : "CSV oder PDF hier ablegen"}
        </div>
        <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.6 }}>
          Unterstützte Formate: ING, DKB, Sparkasse, Comdirect, Trade Republic, PayPal<br />
          Mehrere Dateien gleichzeitig möglich · Duplikate werden automatisch erkannt
        </div>
        {!uploading && (
          <div style={{ marginTop: 20 }}>
            <Btn variant="primary" icon="upload">Dateien auswählen</Btn>
          </div>
        )}
      </div>

      {/* Format info */}
      <Card>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14 }}>Unterstützte Formate</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          {[
            { name: "ING", ext: "CSV", desc: "Girokonto, Tagesgeld, Extrakonto" },
            { name: "DKB", ext: "CSV", desc: "Girokonto, Visa-Karte" },
            { name: "Sparkasse", ext: "CSV", desc: "Girokonto" },
            { name: "Comdirect", ext: "CSV", desc: "Girokonto, Depot" },
            { name: "Trade Republic", ext: "CSV + PDF", desc: "Transaktionen, Depotauszug, Kontoauszug" },
            { name: "PayPal", ext: "CSV", desc: "Aktivitätsexport" },
          ].map((f, i) => (
            <div key={i} style={{ padding: "12px 14px", background: "var(--bg-2)", borderRadius: 10, border: "1px solid var(--line)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{f.name}</div>
                <Pill tone="neutral" size="sm">{f.ext}</Pill>
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>{f.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* Data management */}
      {accounts.length > 0 && (
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>Importierte Daten</div>
            {!confirmAll ? (
              <button onClick={() => setConfirmAll(true)} style={{
                background: "transparent", border: "1px solid var(--neg)", color: "var(--neg)",
                padding: "5px 12px", borderRadius: 8, fontSize: 12, cursor: "pointer", fontFamily: "inherit",
              }}>Alle Daten löschen</button>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12, color: "var(--neg)" }}>Wirklich alle Daten löschen?</span>
                <button onClick={deleteAll} style={{
                  background: "var(--neg)", border: "none", color: "#fff",
                  padding: "5px 12px", borderRadius: 8, fontSize: 12, cursor: "pointer", fontFamily: "inherit", fontWeight: 600,
                }}>Ja, löschen</button>
                <button onClick={() => setConfirmAll(false)} style={{
                  background: "transparent", border: "1px solid var(--line)", color: "var(--muted)",
                  padding: "5px 12px", borderRadius: 8, fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                }}>Abbrechen</button>
              </div>
            )}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {accounts.map(a => (
              <AccountDeleteRow key={a.name} account={a} onDelete={deleteAccount} />
            ))}
          </div>
        </Card>
      )}

      {/* Import results */}
      {results.length > 0 && (
        <Card padding={0}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 600, fontSize: 15 }}>Import-Ergebnisse</span>
            <button onClick={() => setResults([])} style={{ background: "transparent", border: "none", color: "var(--muted)", fontSize: 12, cursor: "pointer", fontFamily: "inherit" }}>
              Leeren
            </button>
          </div>
          {results.map((r, i) => (
            <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 14, padding: "14px 20px", borderBottom: i < results.length - 1 ? "1px solid var(--line)" : "none" }}>
              {/* Status icon */}
              <div style={{
                width: 32, height: 32, borderRadius: 8, flexShrink: 0, marginTop: 1,
                background: r.error ? "var(--neg-soft)" : r.n_new === 0 ? "var(--line-strong)" : "var(--accent-soft)",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15,
              }}>
                {r.error ? "✗" : r.n_new === 0 ? "=" : "✓"}
              </div>

              {/* Info */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontWeight: 500, fontSize: 13 }}>{r.file}</span>
                  {!r.error && r.format_name && (
                    <Pill tone="neutral" size="sm">{r.format_name}</Pill>
                  )}
                </div>
                {r.error ? (
                  <div style={{ fontSize: 11, color: "var(--neg)", marginTop: 4, lineHeight: 1.5, fontFamily: "var(--mono)", wordBreak: "break-word" }}>
                    {r.error}
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 14, marginTop: 5, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>
                      <span style={{ fontFamily: "var(--mono)", color: r.n_new > 0 ? "var(--pos)" : "var(--fg)", fontWeight: 600 }}>
                        {r.n_new > 0 ? `+${r.n_new}` : "±0"}
                      </span>{" "}neue Buchungen
                    </span>
                    {r.n_duplicates > 0 && (
                      <span style={{ fontSize: 11, color: "var(--muted)" }}>
                        <span style={{ fontFamily: "var(--mono)" }}>{r.n_duplicates}</span> Duplikate
                      </span>
                    )}
                    {r.n_parsed > 0 && (
                      <span style={{ fontSize: 11, color: "var(--muted)" }}>
                        <span style={{ fontFamily: "var(--mono)" }}>{r.n_parsed}</span> geparst
                      </span>
                    )}
                    {r.n_total > 0 && (
                      <span style={{ fontSize: 11, color: "var(--muted)" }}>
                        <span style={{ fontFamily: "var(--mono)" }}>{r.n_total}</span> gesamt
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </Card>
      )}

      <BackupCard />
    </div>
  );
};

window.PageUpload = PageUpload;
window.BackupCard = BackupCard;
