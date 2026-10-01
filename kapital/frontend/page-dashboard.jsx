// Page: Dashboard

const useFetch = (url) => {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const reload = React.useCallback(() => {
    setLoading(true);
    fetch(url).then(r => r.json()).then(d => { setData(d); setLoading(false); }).catch(e => { setError(e.message); setLoading(false); });
  }, [url]);
  React.useEffect(() => { reload(); }, [reload]);
  return { data, loading, error, reload };
};
window.useFetch = useFetch;


// ── Grundlast ────────────────────────────────────────────────────────────────
// Beantwortet: "was kostet ein normaler Monat, ohne die Ausreisser" — und
// daraus abgeleitet, wie viel monatlich übrig bliebe. Bewusst getrennt vom
// Datumsfilter oben: die Grundlast ist ein gleitender Schnitt über die letzten
// N ABGESCHLOSSENEN Monate, kein Ausschnitt. Der laufende Monat ist
// unvollständig und würde den Schnitt systematisch nach unten ziehen.
const BaselineCard = () => {
  const [months, setMonths] = React.useState(6);
  const [excluded, setExcluded] = React.useState(null);   // null = Server-Voreinstellung
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    setLoading(true); setError("");
    const params = new URLSearchParams({ months: String(months) });
    if (excluded !== null) params.set("exclude_categories", excluded.join(","));
    fetch(`/api/baseline?${params}`)
      .then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`);
        return j;
      })
      .then(d => { setData(d); if (excluded === null) setExcluded(d.excluded_categories || []); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [months, excluded === null ? "__init__" : excluded.join(",")]);

  const toggleCat = (c) => {
    const next = (excluded || []).includes(c)
      ? excluded.filter(x => x !== c)
      : [...(excluded || []), c];
    setExcluded(next);
    fetch("/api/baseline/config", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exclude_categories: next, months }),
    }).catch(() => {});
  };

  if (loading && !data) return <Card><Spinner /></Card>;
  if (error && !data) return (
    <Card><EmptyState icon="info" title="Grundlast nicht berechenbar" desc={error} /></Card>
  );
  if (!data || !data.n_months) return null;

  const maxSpend = Math.max(...data.per_month.map(m => m.total_spend), 1);

  return (
    <Card level="primary">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Grundlast
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>Was ein normaler Monat kostet</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
            Schnitt über {data.n_months} abgeschlossene Monate ({data.months[0]} – {data.months.at(-1)})
          </div>
        </div>
        <Segmented
          value={String(months)}
          onChange={(v) => setMonths(Number(v))}
          options={[{ value: "3", label: "3 Mon." }, { value: "6", label: "6 Mon." }, { value: "12", label: "12 Mon." }]}
        />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, marginBottom: 18 }}>
        <Stat label="Ø Einnahmen" value={fmtEUR(data.avg_income)} sub="pro Monat" />
        <Stat label="Ø Grundlast" value={fmtEUR(data.avg_spend)} sub="ohne Einmaliges" />
        <Stat
          label="Ø möglich zu sparen"
          value={fmtEUR(data.avg_savings)}
          large
          delta={data.avg_income > 0 ? `${Math.round(data.savings_rate * 100)} % der Einnahmen` : null}
          deltaTone={data.avg_savings >= 0 ? "pos" : "neg"}
          tone={data.avg_savings >= 0 ? "pos" : "neg"}
        />
      </div>

      {/* Was herausgerechnet wurde, gehört sichtbar dazu. Ein Schnitt, der
          stillschweigend Posten weglässt, ist eine Zahl, der man später nicht
          mehr traut. */}
      <div style={{
        display: "flex", alignItems: "flex-start", gap: 8, padding: "10px 12px",
        background: "var(--warn-soft)", border: "1px solid var(--warn-soft)",
        borderRadius: 10, fontSize: 12, marginBottom: 16,
      }}>
        <span style={{ color: "var(--warn)", lineHeight: 1.5 }}>≈</span>
        <div style={{ lineHeight: 1.55 }}>
          <strong>{fmtEUR(data.excluded_avg)}</strong> pro Monat sind herausgerechnet
          {data.sonderausgaben_avg > 0 && <> (davon {fmtEUR(data.sonderausgaben_avg)} Sonderausgaben)</>}.
          Voll gerechnet wären es <strong>{fmtEUR(data.avg_spend_incl_all)}</strong> Ausgaben pro Monat.
          <button onClick={() => setOpen(o => !o)} style={{
            background: "none", border: "none", padding: "0 0 0 6px", cursor: "pointer",
            color: "var(--accent)", fontSize: 12, fontFamily: "inherit",
          }}>{open ? "weniger" : "anpassen"}</button>
        </div>
      </div>

      {open && (
        <div style={{ marginBottom: 16, padding: "12px 14px", background: "var(--bg-2)", borderRadius: 10 }}>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>
            Kategorien, die als einmalig gelten und nicht in die Grundlast zählen:
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {(data.all_categories || []).map(c => {
              const on = (excluded || []).includes(c);
              return (
                <button key={c} onClick={() => toggleCat(c)} style={{
                  padding: "4px 10px", borderRadius: 999, fontSize: 11, cursor: "pointer",
                  fontFamily: "inherit",
                  border: `1px solid ${on ? "var(--warn)" : "var(--line)"}`,
                  background: on ? "var(--warn-soft)" : "transparent",
                  color: on ? "var(--warn)" : "var(--muted)",
                }}>{on ? "− " : "+ "}{c}</button>
              );
            })}
          </div>
        </div>
      )}

      {/* Monatsbalken: Grundlast massiv, Einmaliges schraffiert obendrauf.
          So sieht man sofort, ob ein Monat teuer war oder nur einen Ausreisser hatte. */}
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {data.per_month.map(m => (
          <div key={m.month} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 10, color: "var(--muted)", fontFamily: "var(--mono)", width: 52, flexShrink: 0 }}>
              {m.month.slice(2)}
            </span>
            <div style={{ flex: 1, height: 14, background: "var(--bg-2)", borderRadius: 3, overflow: "hidden", display: "flex" }}>
              <div style={{ width: `${(m.spend / maxSpend) * 100}%`, background: "var(--accent)", opacity: 0.75 }}
                   title={`Grundlast ${fmtEUR(m.spend)}`} />
              {m.excluded > 0 && (
                <div style={{ width: `${(m.excluded / maxSpend) * 100}%`, background: "var(--warn)", opacity: 0.55 }}
                     title={`einmalig ${fmtEUR(m.excluded)}`} />
              )}
            </div>
            <span style={{ fontSize: 11, fontFamily: "var(--mono)", width: 82, textAlign: "right", flexShrink: 0 }}>
              {fmtEUR(m.spend, { decimals: 0 })}
            </span>
            <span style={{ fontSize: 11, fontFamily: "var(--mono)", width: 82, textAlign: "right", flexShrink: 0,
                           color: m.savings >= 0 ? "var(--pos)" : "var(--neg)" }}>
              {fmtEUR(m.savings, { decimals: 0, sign: true })}
            </span>
          </div>
        ))}
        <div style={{ display: "flex", gap: 14, fontSize: 10, color: "var(--muted)", marginTop: 4, justifyContent: "flex-end" }}>
          <span><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: "var(--accent)", opacity: 0.75, marginRight: 4 }} />Grundlast</span>
          <span><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: "var(--warn)", opacity: 0.55, marginRight: 4 }} />einmalig</span>
          <span>rechts: übrig geblieben</span>
        </div>
      </div>

      {data.categories.length > 0 && (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--line)" }}>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>
            Grundlast nach Kategorie (Ø pro Monat)
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {data.categories.slice(0, 6).map(c => (
              <div key={c.category} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span>{c.category}</span>
                <span style={{ fontFamily: "var(--mono)" }}>{fmtEUR(c.avg)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
};

// ── Kontozeile mit Umbenennen ────────────────────────────────────────────────
// Auf Modulebene definiert: eine im Render deklarierte Komponente ist bei jedem
// Durchlauf ein neuer Typ, React hängt sie dann komplett neu ein und der
// Bearbeitungszustand ginge bei jedem Tastendruck verloren.
const AccountRow = ({ account: a, onRenamed }) => {
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState(a.name);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");

  const save = async () => {
    const name = value.trim();
    if (!name || name === a.name) { setEditing(false); setErr(""); return; }
    setBusy(true); setErr("");
    try {
      const res = await fetch(`/api/settings/accounts/${encodeURIComponent(a.id)}/label`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: name }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j.detail || "Umbenennen fehlgeschlagen");
      setEditing(false);
      onRenamed && onRenamed();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", padding: "11px 0", borderBottom: "1px solid var(--line)", gap: 12 }}>
      <div style={{ width: 34, height: 34, borderRadius: 8, background: "var(--bg-2)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)" }}>
        <Icon name={a.type === "Trade Republic" ? "portfolio" : "bank"} size={15} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        {editing ? (
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input
              autoFocus value={value} disabled={busy}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") save();
                if (e.key === "Escape") { setEditing(false); setValue(a.name); setErr(""); }
              }}
              style={{
                flex: 1, padding: "4px 8px", background: "var(--bg-2)",
                border: "1px solid var(--line)", borderRadius: 7,
                color: "var(--fg)", fontSize: 13, fontFamily: "inherit",
              }}
            />
            <Btn size="sm" variant="primary" onClick={save} disabled={busy}>OK</Btn>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 500 }}>{a.name}</span>
            <button
              onClick={() => { setValue(a.name); setEditing(true); }}
              title="Konto umbenennen"
              aria-label={`${a.name} umbenennen`}
              style={{ background: "none", border: "none", padding: 2, cursor: "pointer", color: "var(--muted)", lineHeight: 0 }}
            >
              <Icon name="pencil" size={12} />
            </button>
          </div>
        )}
        <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--mono)" }}>
          {a.type}
          {!a.calibrated && <span style={{ color: "var(--warn)" }}> · nur Zahlungsstrom</span>}
          {a.raw_labels && a.raw_labels.length > 1 && (
            <span style={{ color: "var(--muted)" }}> · {a.raw_labels.length} Bezeichnungen</span>
          )}
        </div>
        {err && <div style={{ fontSize: 11, color: "var(--neg)", marginTop: 2 }}>{err}</div>}
      </div>
      <div style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 600, color: a.balance < 0 ? "var(--neg)" : "var(--fg)" }}>
        {fmtEUR(a.balance)}
      </div>
    </div>
  );
};

const PageDashboard = () => {
  // Zeitraum und Konto sind seitenübergreifend — sonst ist ein handgewählter
  // Zeitraum nach einem Tabwechsel weg.
  const { preset, account, range: customRange, setPreset, setAccount, setRange: setCustomRange } = useSharedFilter();
  const [excludeSonder, setExcludeSonder] = React.useState(false);
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [range, setRange] = React.useState("monthly");
  const [topMode, setTopMode] = React.useState("items");

  const [reloadTick, setReloadTick] = React.useState(0);
  const reload = React.useCallback(() => setReloadTick(t => t + 1), []);
  const [loadError, setLoadError] = React.useState("");

  React.useEffect(() => {
    setLoading(true);
    const { date_from, date_to } = presetToDates(preset) || customRange;
    const params = new URLSearchParams({ account });
    if (date_from) params.set("date_from", date_from);
    if (date_to) params.set("date_to", date_to);
    if (excludeSonder) params.set("exclude_sonderausgaben", "true");
    fetch(`/api/dashboard?${params}`)
      .then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || `Serverfehler ${r.status}`);
        return j;
      })
      .then(d => { setData(d); setLoadError(""); setLoading(false); })
      // Fehler NICHT wie "keine Daten" aussehen lassen: vorher landete jeder
      // 500er in derselben Anzeige wie ein leerer Bestand.
      .catch(e => { setLoadError(e.message || "Unbekannter Fehler"); setLoading(false); });
  }, [preset, account, excludeSonder, customRange, reloadTick]);

  if (loading && !data) return <Spinner />;
  if (loadError && !data) return (
    <EmptyState icon="info" title="Daten konnten nicht geladen werden" desc={loadError} />
  );
  if (!data) return <EmptyState title="Keine Daten" desc="Importiere zuerst Kontodaten." />;
  if (data.empty_reason === "no_rows_in_range") return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div style={{ flex: 1 }}>
          <FilterBar
            preset={preset} onPreset={setPreset}
            account={account} onAccount={setAccount}
            accounts={data.all_accounts || []}
            multiAccount
            dateFrom={customRange.date_from} dateTo={customRange.date_to}
            onRange={setCustomRange}
          />
        </div>
      </div>
      <EmptyState icon="calendar" title="Keine Buchungen im gewählten Zeitraum"
        desc="Wähle einen anderen Zeitraum oder ein anderes Konto." />
    </div>
  );

  const s = data.summary;
  const topCats = data.top_categories || [];
  const maxCat = topCats[0]?.value || 1;
  const recent = data.recent_transactions || [];
  const allAccounts = data.all_accounts || [];
  const cf = range === "weekly" ? (data.weekly_cashflow || []) : (data.monthly_cashflow || []);
  const PRESET_LABELS = {
    "30d": "letzte 30 Tage", "3m": "letzte 3 Monate", "6m": "letzte 6 Monate",
    "12m": "letztes Jahr", "ytd": "dieses Jahr", "all": "gesamter Zeitraum",
  };
  const periodLabel = preset === "custom"
    ? `${fmtDate(customRange.date_from)} – ${fmtDate(customRange.date_to)}`
    : (PRESET_LABELS[preset] || "gesamter Zeitraum");

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Hinweise, wenn Zahlen nicht voll belastbar sind — statt sie einfach
          selbstbewusst falsch anzuzeigen. */}
      <WarningStrip warnings={data.warnings} />

      {/* Filter bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div style={{ flex: 1 }}>
          <FilterBar
            preset={preset}
            onPreset={setPreset}
            account={account} onAccount={setAccount}
            accounts={allAccounts}
            multiAccount
            dateFrom={customRange.date_from} dateTo={customRange.date_to}
            onRange={setCustomRange}
          />
        </div>
        <button
          onClick={() => setExcludeSonder(v => !v)}
          title="Sonderausgaben (einmalige Ausgaben) aus dem Cashflow herausrechnen"
          style={{
            display: "flex", alignItems: "center", gap: 7, padding: "8px 14px",
            borderRadius: 10, border: `1px solid ${excludeSonder ? "var(--warn-dim)" : "var(--line)"}`,
            background: excludeSonder ? "rgba(245,158,11,0.1)" : "var(--bg-1)",
            color: excludeSonder ? "var(--warn-dim)" : "var(--muted)",
            fontSize: 12, fontFamily: "inherit", fontWeight: 500, cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          ⚑ Sonderausgaben{excludeSonder ? " · ausgeblendet" : ""}
        </button>
      </div>

      {/* Hero stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16 }}>
        <Card>
          <Stat label="Einnahmen" value={fmtEUR(s.total_income)} delta={`+${((s.savings_rate || 0) * 100).toFixed(1)} % Sparrate`} deltaTone="pos" sub={preset === "all" ? "alle Buchungen" : "im Zeitraum"} large />
          <div style={{ marginTop: 12 }}>
            <Sparkline values={(data.monthly_cashflow || []).map(d => d.in)} width={240} height={36} stroke="var(--accent)" />
          </div>
        </Card>
        <Card>
          <Stat label="Ausgaben" value={fmtEUR(s.total_expenses)} delta={s.total_refunds > 0 ? `${fmtEUR(s.total_refunds)} Erstattungen` : undefined} deltaTone="neutral" sub="Konsum" />
          <div style={{ marginTop: 14, display: "flex", gap: 4, alignItems: "flex-end" }}>
            {(data.monthly_cashflow || []).slice(-5).map((d, i) => (
              <div key={i} style={{ width: 8, height: Math.max(4, d.out / (Math.max(...(data.monthly_cashflow || []).map(x => x.out)) || 1) * 36), background: "var(--neg)", opacity: 0.5 + i * 0.1, borderRadius: 1 }} />
            ))}
          </div>
        </Card>
        <Card>
          <Stat label="Investiert" value={fmtEUR(s.total_invested)} delta={s.total_invested > 0 ? fmtPct(s.total_invested / (s.total_income || 1) * 100, { sign: false }) + " des Einkommens" : "Keine Investitionen"} deltaTone="accent" sub="Vermögensaufbau" />
          <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 12 }}>
            <ProgressRing value={(s.total_invested / (s.total_income || 1)) * 100} max={50} color="var(--accent)" label={`${Math.round((s.total_invested / (s.total_income || 1)) * 100)}%`} size={48} />
            <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.4 }}>
              {fmtEUR(s.savings)} netto<br />gespart
            </div>
          </div>
        </Card>
        <Card>
          <Stat label="Buchungen" value={fmtNum(s.n_transactions)} sub="im Zeitraum" />
          <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)" }}>
              <span>Sparrate</span>
              <span style={{ fontFamily: "var(--mono)", color: "var(--fg)" }}>{fmtPct((s.savings_rate || 0) * 100, { sign: false })}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)" }}>
              <span>Netto-Cashflow</span>
              <span style={{ fontFamily: "var(--mono)", color: s.net_cashflow >= 0 ? "var(--pos)" : "var(--neg)" }}>{fmtEUR(s.net_cashflow, { sign: true })}</span>
            </div>
          </div>
        </Card>
      </div>

      <BaselineCard />

      {/* Cashflow chart + top categories */}
      {/* alignItems: start — sonst zieht die längere Top-Ausgaben-Liste die
          Cashflow-Karte auf ihre Höhe und unter den Balken bleibt ein leerer
          Streifen. Die Karte endet jetzt dort, wo das Diagramm endet. */}
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 16, alignItems: "start" }}>
        <Card padding={0} style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "18px 22px 0" }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Cashflow</div>
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>Ein- und Ausgaben</div>
            </div>
            <Segmented
              options={[{ label: "Woche", value: "weekly" }, { label: "Monat", value: "monthly" }]}
              value={range} onChange={setRange} size="sm"
            />
          </div>
          <div style={{ padding: "14px 12px 16px", display: "flex" }}>
            <BarChart data={cf} height={260} posKey="in" negKey="out" netKey="savings" netLabel="Überschuss" xKey="label" yFmt={(v) => fmtEUR(v, { decimals: 0 })} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", borderTop: "1px solid var(--line)" }}>
            {[
              { label: "Eingegangen", val: s.total_income, color: "var(--pos)", sign: true },
              { label: "Ausgegangen", val: -s.total_expenses, color: "var(--neg)", sign: true },
              { label: "Netto", val: s.net_cashflow, color: s.net_cashflow >= 0 ? "var(--pos)" : "var(--neg)", sign: true },
            ].map((x, i) => (
              <div key={i} style={{ padding: "14px 22px", borderRight: i < 2 ? "1px solid var(--line)" : "none" }}>
                <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{x.label}</div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 17, fontWeight: 600, color: x.color, marginTop: 4 }}>{fmtEUR(x.val, { sign: x.sign })}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, gap: 10, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Top Ausgaben</div>
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>
                {topMode === "items" ? "einzelne Buchungen" : "nach Kategorie"}
              </div>
              {/* Zeitraum benennen. Bei "Gesamt" stehen hier zwangsläufig
                  Buchungen von vor Jahren — ohne diese Zeile sieht das aus,
                  als würde der Datumsfilter nicht greifen. */}
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
                {periodLabel}
              </div>
            </div>
            {/* Beide Sichten behalten: die Kategorie-Aufteilung beantwortet
                "wo geht mein Geld hin", die Einzelbuchungen "was war
                ungewöhnlich". Das sind zwei Fragen, nicht eine. */}
            <Segmented
              value={topMode}
              onChange={setTopMode}
              options={[{ value: "items", label: "Buchungen" }, { value: "cats", label: "Kategorien" }]}
            />
          </div>
          {topMode === "items" ? (
            (data.top_expenses || []).length === 0 ? (
              <EmptyState title="Keine Ausgaben im Zeitraum"
                desc="Für den gewählten Filter gibt es keine Buchungen." />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                {(data.top_expenses || []).map(t => (
                  <div key={t.id} style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "9px 0", borderBottom: "1px solid var(--line)",
                  }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, flexShrink: 0,
                                   background: t.color || "var(--accent)", display: "inline-block" }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, overflow: "hidden",
                                    textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={t.description}>
                        {t.payee}
                        {t.is_sonderausgabe && (
                          <span style={{ color: "var(--warn-dim)", marginLeft: 6, fontSize: 10 }}>⚑</span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--muted)" }}>
                        {fmtDate(t.date)} · {t.category}
                      </div>
                    </div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600, flexShrink: 0 }}>
                      {fmtEUR(t.amount)}
                    </div>
                  </div>
                ))}
                {data.top_expenses_hidden > 0 && (
                  <div style={{ fontSize: 11, color: "var(--muted)", paddingTop: 10 }}>
                    {data.top_expenses_hidden} Buchungen aus{" "}
                    {(data.top_expenses_excluded || []).join(", ")} ausgeblendet —
                    einstellbar unter Einstellungen.
                  </div>
                )}
              </div>
            )
          ) : topCats.length === 0 ? <EmptyState title="Keine Daten" /> : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {topCats.map(c => (
                <div key={c.id}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: c.color || "var(--accent)", display: "inline-block" }} />
                      {c.name}
                    </div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 500 }}>{fmtEUR(c.value)}</div>
                  </div>
                  <div style={{ height: 4, background: "var(--bg-2)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ width: `${(c.value / maxCat) * 100}%`, height: "100%", background: c.color || "var(--accent)", opacity: 0.85 }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Accounts + recent transactions */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ fontSize: 16, fontWeight: 600 }}>Konten</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {(data.accounts || []).map(a => (
              <AccountRow key={a.id} account={a} onRenamed={reload} />
            ))}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 12, marginTop: 4 }}>
            {/* Der Zusatz "(Cashflow-Basis)" war die Entschuldigung dafür, dass
                hier kein Kontostand stand. Wo ein Saldo hinterlegt ist, steht
                jetzt der Saldo — dann darf die Zeile auch "Gesamt" heissen. */}
            <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              {(data.accounts || []).every(a => a.calibrated) ? "Gesamt" : "Gesamt (teils Cashflow-Basis)"}
            </span>
            <span style={{ fontFamily: "var(--mono)", fontSize: 15, fontWeight: 600 }}>{fmtEUR((data.accounts || []).reduce((s, a) => s + a.balance, 0))}</span>
          </div>
        </Card>

        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ fontSize: 16, fontWeight: 600 }}>Letzte Buchungen</div>
          </div>
          <div>
            {recent.map(t => (
              <div key={t.id} style={{ display: "flex", alignItems: "center", padding: "9px 0", borderBottom: "1px solid var(--line)", gap: 12 }}>
                <div style={{ width: 26, height: 26, borderRadius: 6, background: "var(--bg-2)", color: "var(--muted)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12 }}>
                  {t.is_transfer ? "↔" : t.amount > 0 ? "+" : "−"}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.payee || t.description}</div>
                  <div style={{ fontSize: 11, color: "var(--muted)" }}>{t.category} · {fmtDateShort(t.date)}</div>
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 500, color: t.amount > 0 ? "var(--pos)" : "var(--fg)" }}>
                  {fmtEUR(t.amount, { sign: t.amount > 0 })}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
};

window.PageDashboard = PageDashboard;
