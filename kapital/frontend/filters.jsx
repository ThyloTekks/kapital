// Shared filter bar — date presets + custom range + account (multi) + category

const DATE_PRESETS = [
  { label: "30 Tage",      value: "30d" },
  { label: "3 Monate",     value: "3m"  },
  { label: "6 Monate",     value: "6m"  },
  { label: "1 Jahr",       value: "12m" },
  { label: "Dieses Jahr",  value: "ytd" },
  { label: "Gesamt",       value: "all" },
];

const _pad = (n) => String(n).padStart(2, "0");
const _fmt = (d) => `${d.getFullYear()}-${_pad(d.getMonth() + 1)}-${_pad(d.getDate())}`;

const presetToDates = (preset) => {
  const today = new Date();
  const todayStr = _fmt(today);

  if (preset === "all") return { date_from: "", date_to: "" };
  // "custom" wird nicht aus einem Preset abgeleitet — die Daten kommen dann
  // aus dem Kalender. Der Aufrufer hält beides in EINEM Zustand, damit nie
  // zwei Bedienelemente gleichzeitig aktiv aussehen.
  if (preset === "custom") return null;

  let from = new Date(today);
  if (preset === "30d")  from.setDate(from.getDate() - 30);
  else if (preset === "3m")  from.setMonth(from.getMonth() - 3);
  else if (preset === "6m")  from.setMonth(from.getMonth() - 6);
  else if (preset === "12m") from.setFullYear(from.getFullYear() - 1);
  else if (preset === "ytd") from = new Date(today.getFullYear(), 0, 1);

  return { date_from: _fmt(from), date_to: todayStr };
};

const _fmtShort = (s) => {
  if (!s) return "";
  const [y, m, d] = s.split("-");
  return `${d}.${m}.${y}`;
};

// ── Kalender-Zeitraum ─────────────────────────────────────────────────────────
// Bewusst <input type="date">: ohne Build-Schritt gibt es keine Datums-
// bibliothek, und der native Wähler kann Tastatur und Lokalisierung bereits.
// Der native Wähler folgt `color-scheme`, das je Theme gesetzt wird.
const DateRangePicker = ({ open, dateFrom, dateTo, onApply, onClose }) => {
  const [from, setFrom] = React.useState(dateFrom || "");
  const [to, setTo] = React.useState(dateTo || "");
  const [err, setErr] = React.useState("");

  React.useEffect(() => { setFrom(dateFrom || ""); setTo(dateTo || ""); }, [dateFrom, dateTo, open]);
  if (!open) return null;

  const apply = () => {
    if (!from && !to) { setErr("Bitte mindestens ein Datum wählen."); return; }
    // Vertauschte Eingabe still korrigieren statt eine Fehlermeldung zu zeigen:
    // die Absicht ist eindeutig.
    const a = from && to && from > to ? to : from;
    const b = from && to && from > to ? from : to;
    setErr("");
    onApply({ date_from: a, date_to: b });
  };

  const field = {
    padding: "6px 10px", background: "var(--bg-2)", border: "1px solid var(--line)",
    borderRadius: 8, color: "var(--fg)", fontSize: 12, fontFamily: "inherit",
  };

  return (
    <div style={{
      position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 50,
      background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 12,
      padding: 14, boxShadow: "0 8px 28px var(--shadow)", minWidth: 268,
    }}>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, color: "var(--muted)" }}>
          Von
          <input type="date" value={from} max={to || undefined}
                 onChange={(e) => setFrom(e.target.value)} style={field} />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, color: "var(--muted)" }}>
          Bis
          <input type="date" value={to} min={from || undefined}
                 onChange={(e) => setTo(e.target.value)} style={field} />
        </label>
      </div>
      {err && <div style={{ fontSize: 11, color: "var(--neg)", marginTop: 8 }}>{err}</div>}
      <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
        <Btn variant="ghost" size="sm" onClick={onClose}>Abbrechen</Btn>
        <Btn variant="primary" size="sm" onClick={apply}>Übernehmen</Btn>
      </div>
    </div>
  );
};

// ── Konto-Mehrfachauswahl ─────────────────────────────────────────────────────
const AccountMultiSelect = ({ accounts, selected, onChange }) => {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);

  React.useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  // Leere Auswahl bedeutet "alle" — nie ein leeres Ergebnis, das wie
  // "keine Daten" aussieht.
  const isAll = !selected || selected.length === 0;
  const label = isAll
    ? "Alle Konten"
    : selected.length === 1 ? selected[0]
    : `${selected.length} Konten`;

  const toggle = (a) => {
    const cur = new Set(selected || []);
    if (cur.has(a)) cur.delete(a); else cur.add(a);
    const next = [...cur];
    onChange(next.length === accounts.length ? [] : next);
  };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button onClick={() => setOpen(o => !o)} aria-expanded={open} style={{
        padding: "7px 12px", background: "var(--bg-1)", border: "1px solid var(--line)",
        borderRadius: 10, color: isAll ? "var(--muted)" : "var(--fg)",
        fontSize: 12, fontFamily: "inherit", cursor: "pointer", display: "flex",
        alignItems: "center", gap: 6, whiteSpace: "nowrap",
      }}>
        {label}
        <span style={{ fontSize: 9, color: "var(--muted)" }}>▼</span>
      </button>
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 50,
          background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 12,
          padding: 6, boxShadow: "0 8px 28px var(--shadow)", minWidth: 210, maxHeight: 300,
          overflowY: "auto",
        }}>
          <button onClick={() => onChange([])} style={{
            display: "block", width: "100%", textAlign: "left", padding: "7px 10px",
            background: isAll ? "var(--accent-soft)" : "transparent", border: "none",
            borderRadius: 8, color: isAll ? "var(--accent)" : "var(--fg)",
            fontSize: 12, fontFamily: "inherit", cursor: "pointer",
          }}>Alle Konten</button>
          <div style={{ height: 1, background: "var(--line)", margin: "4px 0" }} />
          {accounts.map(a => {
            const on = !isAll && selected.includes(a);
            return (
              <label key={a} style={{
                display: "flex", alignItems: "center", gap: 8, padding: "7px 10px",
                borderRadius: 8, cursor: "pointer", fontSize: 12,
                background: on ? "var(--accent-soft)" : "transparent",
              }}>
                <input type="checkbox" checked={on} onChange={() => toggle(a)} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a}</span>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
};

const FilterBar = ({
  preset, onPreset,
  account, onAccount, accounts = [],
  category, onCategory, categories = [],
  showCategory = false,
  // Kalender-Zeitraum (optional; ohne diese Props verhält sich die Leiste wie vorher)
  dateFrom = "", dateTo = "", onRange,
  multiAccount = false,
}) => {
  const [calOpen, setCalOpen] = React.useState(false);
  const isCustom = preset === "custom";
  // account ist weiterhin ein String (Komma-Liste) — so bleibt der Vertrag zu
  // allen bestehenden Aufrufern und zur API unverändert.
  const selectedAccounts = (account && account !== "all")
    ? String(account).split(",").filter(Boolean) : [];

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      {/* Date preset pills */}
      <div style={{ display: "flex", gap: 3, padding: "3px", background: "var(--bg-1)", borderRadius: 10, border: "1px solid var(--line)" }}>
        {DATE_PRESETS.map(p => (
          <button key={p.value} onClick={() => onPreset(p.value)} style={{
            padding: "5px 12px", borderRadius: 7, border: "none",
            background: preset === p.value ? "var(--accent)" : "transparent",
            color: preset === p.value ? "var(--on-accent)" : "var(--muted)",
            fontFamily: "inherit", fontSize: 12, fontWeight: preset === p.value ? 600 : 400,
            cursor: "pointer", whiteSpace: "nowrap", lineHeight: 1.4,
          }}>{p.label}</button>
        ))}
      </div>

      {/* Freier Zeitraum. Genau EIN Bedienelement ist aktiv: wählt man einen
          Zeitraum, verliert die Preset-Reihe ihre Markierung und der Zeitraum
          erscheint als eigener Chip. */}
      {onRange && (
        <div style={{ position: "relative" }}>
          <button onClick={() => setCalOpen(o => !o)} aria-expanded={calOpen} style={{
            padding: "6px 12px", borderRadius: 10,
            border: `1px solid ${isCustom ? "var(--accent)" : "var(--line)"}`,
            background: isCustom ? "var(--accent-soft)" : "var(--bg-1)",
            color: isCustom ? "var(--accent)" : "var(--muted)",
            fontSize: 12, fontFamily: "inherit", cursor: "pointer",
            display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap",
          }}>
            <Icon name="calendar" size={13} />
            {isCustom ? `${_fmtShort(dateFrom) || "…"} – ${_fmtShort(dateTo) || "…"}` : "Zeitraum"}
          </button>
          {isCustom && (
            <button onClick={() => onPreset("6m")} title="Zeitraum zurücksetzen" style={{
              position: "absolute", right: -6, top: -6, width: 16, height: 16,
              borderRadius: 8, border: "1px solid var(--line)", background: "var(--bg-2)",
              color: "var(--muted)", fontSize: 10, lineHeight: 1, cursor: "pointer", padding: 0,
            }}>×</button>
          )}
          <DateRangePicker
            open={calOpen} dateFrom={dateFrom} dateTo={dateTo}
            onClose={() => setCalOpen(false)}
            onApply={(r) => { setCalOpen(false); onRange(r); }}
          />
        </div>
      )}

      {/* Account filter */}
      {accounts.length > 1 && (
        multiAccount ? (
          <AccountMultiSelect
            accounts={accounts}
            selected={selectedAccounts}
            onChange={(list) => onAccount(list.length ? list.join(",") : "all")}
          />
        ) : (
          <select value={account} onChange={e => onAccount(e.target.value)} style={{
            padding: "7px 12px", background: "var(--bg-1)", border: "1px solid var(--line)",
            borderRadius: 10, color: account === "all" ? "var(--muted)" : "var(--fg)",
            fontSize: 12, fontFamily: "inherit", cursor: "pointer",
          }}>
            <option value="all">Alle Konten</option>
            {accounts.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        )
      )}

      {/* Category filter (optional) */}
      {showCategory && categories.length > 0 && (
        <select value={category} onChange={e => onCategory(e.target.value)} style={{
          padding: "7px 12px", background: "var(--bg-1)", border: "1px solid var(--line)",
          borderRadius: 10, color: category === "all" ? "var(--muted)" : "var(--fg)",
          fontSize: 12, fontFamily: "inherit", cursor: "pointer",
        }}>
          <option value="all">Alle Kategorien</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      )}
    </div>
  );
};

window.FilterBar = FilterBar;
window.presetToDates = presetToDates;
window.DateRangePicker = DateRangePicker;
window.AccountMultiSelect = AccountMultiSelect;
