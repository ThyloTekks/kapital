// Shared UI atoms — Kapital design system

// fmtMoney ist die ehrliche Variante: sie verlangt eine Währung. fmtEUR bleibt
// als Kurzform für Beträge, die per Definition in Euro sind (Kontobewegungen
// aus deutschen Bank-CSVs). Kurse aus yfinance sind das NICHT — die kommen in
// Börsenwährung und müssen ihre Währung mitbringen, sonst steht am Ende ein
// Dollarkurs mit Euro-Zeichen auf dem Schirm.
const fmtMoney = (v, currency = "EUR", { decimals = 2, sign = false } = {}) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  let s;
  try {
    s = new Intl.NumberFormat("de-DE", {
      style: "currency", currency: currency || "EUR",
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(v);
  } catch (e) {
    // Unbekannter Währungscode: lieber Zahl + Code als gar nichts.
    s = new Intl.NumberFormat("de-DE", {
      minimumFractionDigits: decimals, maximumFractionDigits: decimals,
    }).format(v) + " " + (currency || "");
  }
  return sign && v > 0 ? "+" + s : s;
};
const fmtEUR = (v, opts = {}) => fmtMoney(v, "EUR", opts);
const fmtPct = (v, { sign = true } = {}) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const s = (Math.abs(v)).toFixed(1) + " %";
  if (!sign) return s;
  return v >= 0 ? "+" + s : "−" + s;
};
const fmtDate = (d) => {
  if (!d) return "";
  return new Date(d + "T00:00:00").toLocaleDateString("de-DE", { day: "2-digit", month: "short", year: "numeric" });
};
const fmtDateShort = (d) => {
  if (!d) return "";
  return new Date(d + "T00:00:00").toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
};
const fmtNum = (v, decimals = 0) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return new Intl.NumberFormat("de-DE", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(v);
};

// ── Icons ─────────────────────────────────────────────────────────────────────
const Icon = ({ name, size = 18, stroke = "currentColor", strokeWidth = 1.6 }) => {
  const paths = {
    dashboard: <><path d="M3 3h7v9H3z"/><path d="M14 3h7v5h-7z"/><path d="M14 12h7v9h-7z"/><path d="M3 16h7v5H3z"/></>,
    upload:    <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/></>,
    list:      <><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><circle cx="3.5" cy="6" r="0.8" fill="currentColor"/><circle cx="3.5" cy="12" r="0.8" fill="currentColor"/><circle cx="3.5" cy="18" r="0.8" fill="currentColor"/></>,
    tag:       <><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><circle cx="7" cy="7" r="1.5"/></>,
    chart:     <><path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 5-7"/></>,
    forecast:  <><path d="M3 12c0-5 4-9 9-9s9 4 9 9"/><path d="M12 3v9l6 4"/></>,
    report:    <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 13h6"/><path d="M9 17h6"/></>,
    settings:  <><circle cx="12" cy="12" r="3"/><path d="M12 1v3M12 20v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M1 12h3M20 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/></>,
    portfolio: <><path d="M3 7h18v13H3z"/><path d="M8 7V4h8v3"/><path d="M3 13h18"/></>,
    calendar:  <><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></>,
    fire:      <><path d="M12 2c0 6-8 8-8 14a8 8 0 0 0 16 0c0-6-4-8-4-14"/><path d="M12 12c0 3-2 4-2 7a2 2 0 0 0 4 0c0-3-2-4-2-7"/></>,
    receipt:   <><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1z"/><path d="M9 7h6M9 11h6M9 15h4"/></>,
    year:      <><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></>,
    plus:      <><path d="M12 5v14"/><path d="M5 12h14"/></>,
    search:    <><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></>,
    filter:    <><path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/></>,
    download:  <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></>,
    file:      <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></>,
    bell:      <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></>,
    check:     <><path d="M20 6L9 17l-5-5"/></>,
    x:         <><path d="M18 6L6 18"/><path d="M6 6l12 12"/></>,
    pencil:    <><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></>,
    trash:     <><path d="M3 6h18"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></>,
    chevron:   <><path d="M9 18l6-6-6-6"/></>,
    sparkles:  <><path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/></>,
    bank:      <><path d="M3 21h18"/><path d="M3 10l9-7 9 7"/><path d="M5 21V10"/><path d="M19 21V10"/><path d="M9 21v-7"/><path d="M15 21v-7"/></>,
    info:      <><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></>,
    refresh:   <><path d="M23 4v6h-6"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></>,
    target:    <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
      {paths[name] || <circle cx="12" cy="12" r="4" fill="currentColor" />}
    </svg>
  );
};

// ── Pill ──────────────────────────────────────────────────────────────────────
const Pill = ({ children, tone = "neutral", size = "sm" }) => {
  const tones = {
    neutral: { bg: "var(--line-strong)", fg: "var(--muted)" },
    pos:     { bg: "var(--accent-soft)",  fg: "var(--pos)" },
    neg:     { bg: "var(--neg-soft)", fg: "var(--neg)" },
    accent:  { bg: "var(--accent-soft)",  fg: "var(--accent)" },
    warn:    { bg: "var(--warn-soft)",  fg: "var(--warn)" },
  };
  const t = tones[tone] || tones.neutral;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: size === "sm" ? "2px 8px" : "4px 10px",
      fontSize: size === "sm" ? 11 : 12, fontWeight: 500,
      borderRadius: 999, background: t.bg, color: t.fg, lineHeight: 1.4,
    }}>{children}</span>
  );
};

// ── Card ──────────────────────────────────────────────────────────────────────
// Drei Stufen statt einer. Vorher sah jede Karte gleich aus, wodurch auf der
// Übersicht fünf Blöcke gleich laut um Aufmerksamkeit konkurrierten. Jede Seite
// soll genau EINE Karte haben, die ihre Frage beantwortet.
//   primary — die Antwort der Seite
//   default — gleichrangiger Inhalt
//   quiet   — Beiwerk und Listen, ohne Rahmen
const Card = ({ children, padding = 20, style = {}, onClick, level = "default" }) => {
  const levels = {
    primary: { background: "var(--bg-raise)", border: "1px solid var(--line-strong)" },
    default: { background: "var(--bg-1)",     border: "1px solid var(--line)" },
    quiet:   { background: "transparent",     border: "1px solid transparent",
               borderTop: "1px solid var(--line)" },
  };
  return (
    <div onClick={onClick} style={{
      ...levels[level] || levels.default,
      borderRadius: level === "quiet" ? 0 : "var(--r-lg)",
      padding: level === "quiet" ? `${padding}px 0` : padding,
      ...style,
      cursor: onClick ? "pointer" : undefined,
    }}>{children}</div>
  );
};

// ── Stat ──────────────────────────────────────────────────────────────────────
const Stat = ({ label, value, delta, deltaTone, sub, large = false, tone }) => {
  // Das eine Bewegungsmoment der App: ändert sich die Zahl, blendet sie kurz
  // auf. Kein Hover-Effekt auf allem, keine Einblendung je Sektion.
  const [pulse, setPulse] = React.useState(0);
  const prev = React.useRef(value);
  React.useEffect(() => {
    if (prev.current !== value) { prev.current = value; setPulse(p => p + 1); }
  }, [value]);

  return (
  <div>
    <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500 }}>{label}</div>
    <div key={pulse} className="value-anim" style={{
      fontSize: large ? 32 : 22, fontFamily: "var(--mono)", fontWeight: 600,
      color: tone === "pos" ? "var(--pos)" : tone === "neg" ? "var(--neg)" : "var(--fg)",
      letterSpacing: "-0.02em", marginTop: 6, lineHeight: 1.1,
    }}>{value}</div>
    {(delta || sub) && (
      <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--muted)", flexWrap: "wrap" }}>
        {delta && <Pill tone={deltaTone || "neutral"}>{delta}</Pill>}
        {sub && <span>{sub}</span>}
      </div>
    )}
  </div>
  );
};

// ── Btn ───────────────────────────────────────────────────────────────────────
const Btn = ({ children, variant = "secondary", size = "md", icon, onClick, style = {}, disabled = false }) => {
  const variants = {
    primary:  { bg: "var(--accent)", fg: "var(--on-accent)", border: "transparent" },
    secondary:{ bg: "var(--bg-1)", fg: "var(--fg)", border: "var(--line)" },
    ghost:    { bg: "transparent", fg: "var(--muted)", border: "transparent" },
    danger:   { bg: "transparent", fg: "var(--neg)", border: "var(--line)" },
  };
  const v = variants[variant] || variants.secondary;
  const s = { sm: { padding: "5px 10px", fontSize: 12 }, md: { padding: "8px 14px", fontSize: 13 } }[size];
  return (
    <button onClick={onClick} disabled={disabled} style={{
      display: "inline-flex", alignItems: "center", gap: 6, ...s,
      borderRadius: 8, border: `1px solid ${v.border}`, background: v.bg, color: v.fg,
      fontWeight: 500, cursor: disabled ? "not-allowed" : "pointer", fontFamily: "inherit",
      opacity: disabled ? 0.5 : 1, transition: "all 0.12s", ...style,
    }}>
      {icon && <Icon name={icon} size={14} />}
      {children}
    </button>
  );
};

// ── Segmented ─────────────────────────────────────────────────────────────────
const Segmented = ({ options, value, onChange, size = "md" }) => (
  <div style={{ display: "inline-flex", background: "var(--bg-2)", border: "1px solid var(--line)", borderRadius: 8, padding: 3, gap: 2 }}>
    {options.map(o => (
      <button key={o.value} onClick={() => onChange(o.value)} style={{
        padding: size === "sm" ? "4px 10px" : "6px 12px",
        fontSize: size === "sm" ? 11 : 12, fontWeight: 500, borderRadius: 6, border: "none",
        background: value === o.value ? "var(--bg-0)" : "transparent",
        color: value === o.value ? "var(--fg)" : "var(--muted)",
        cursor: "pointer", fontFamily: "inherit",
      }}>{o.label}</button>
    ))}
  </div>
);

// ── ProgressRing ──────────────────────────────────────────────────────────────
const ProgressRing = ({ value, max = 100, size = 44, thickness = 4, color = "var(--accent)", label }) => {
  const r = size / 2 - thickness / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (Math.min(value, max) / max) * c;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--line)" strokeWidth={thickness} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={thickness}
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
          transform={`rotate(-90 ${size/2} ${size/2})`} />
      </svg>
      {label && <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontFamily: "var(--mono)", fontWeight: 600 }}>{label}</div>}
    </div>
  );
};

// ── Sidebar ───────────────────────────────────────────────────────────────────
// Gruppiert statt dreizehn gleichrangiger Einträge. Die Gliederung folgt den
// Fragen, die man an eine Finanz-App stellt — "wie stehe ich da", "was war
// diesen Monat", "wo will ich hin" — nicht der Reihenfolge, in der die Router
// entstanden sind.
const NAV_GROUPS = [
  { label: "Überblick", items: [
    { id: "dashboard",       label: "Übersicht",       icon: "dashboard" },
    { id: "transactions",    label: "Buchungen",       icon: "list" },
    { id: "categories",      label: "Kategorien",      icon: "tag" },
  ]},
  { label: "Monat", items: [
    { id: "monatsabschluss", label: "Monatsabschluss", icon: "target" },
    { id: "abos",            label: "Abos",            icon: "receipt" },
    { id: "upload",          label: "Import",          icon: "upload" },
  ]},
  { label: "Vermögen", items: [
    { id: "vermoegen",       label: "Vermögen",        icon: "bank" },
    { id: "portfolio",       label: "Portfolio",       icon: "portfolio" },
    { id: "forecast",        label: "Prognose",        icon: "forecast" },
    { id: "fire",            label: "FIRE-Rechner",    icon: "fire" },
  ]},
  { label: "Auswertung & Pflege", items: [
    { id: "jahresuebersicht",label: "Jahresübersicht", icon: "year" },
    { id: "steuer",          label: "Steuer",          icon: "file" },
    { id: "regeln",          label: "Regeln",          icon: "sparkles" },
  ]},
];

const NAV_ITEMS = NAV_GROUPS.flatMap(g => g.items);



// ── Diagrammfarben ───────────────────────────────────────────────────────────
// Die 18 Kategoriefarben sind als Punkte und Chips richtig — nebeneinander als
// 2px-Linien sind sie nicht unterscheidbar, weil sie nie dafür gewählt wurden.
// Für Verläufe deshalb eine eigene, abgestufte Sequenz mit ausreichendem
// Helligkeitsabstand; bei mehr als fünf Reihen hilft ohnehin keine Farbe mehr.
const CHART_SERIES = ["#7d9fe0", "#d1a24f", "#5fa774", "#b98ec9", "#7ec8c3"];

// Geld hat zwei Lautstärken. Ein Gewinn von 12 € und einer von 12.000 € sollen
// nicht gleich schreien — sonst stumpft die Farbe ab, wie beim roten
// Monatsabschluss.
const moneyTone = (value, { threshold = 250 } = {}) => {
  if (value === null || value === undefined || isNaN(value)) return "var(--muted)";
  const strong = Math.abs(value) >= threshold;
  if (value > 0) return strong ? "var(--pos)" : "var(--pos-dim)";
  if (value < 0) return strong ? "var(--neg)" : "var(--neg-dim)";
  return "var(--muted)";
};

// ── Hell / Dunkel ────────────────────────────────────────────────────────────
// Persönliche Finanzen sind Schreibtischarbeit bei Tageslicht, und
// Zahlenkolonnen lesen sich hell messbar besser. Dunkel bleibt die
// Voreinstellung, hell ist gleichwertig — nicht nachträglich drangeschraubt:
// beide Paletten sind vollständig definiert.
const THEME_KEY = "kapital.theme";

const applyTheme = (t) => {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(THEME_KEY, t); } catch (e) { /* privates Fenster */ }
};

const useTheme = () => {
  const [theme, setTheme] = React.useState(() => {
    try { return localStorage.getItem(THEME_KEY) || "dark"; } catch (e) { return "dark"; }
  });
  React.useEffect(() => { applyTheme(theme); }, [theme]);
  return [theme, setTheme];
};

const ThemeToggle = () => {
  const [theme, setTheme] = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      onClick={() => setTheme(next)}
      title={next === "light" ? "Helle Ansicht" : "Dunkle Ansicht"}
      aria-label={next === "light" ? "Zur hellen Ansicht wechseln" : "Zur dunklen Ansicht wechseln"}
      style={{
        display: "flex", alignItems: "center", gap: 8, width: "100%",
        padding: "7px 10px", borderRadius: "var(--r-sm)", border: "none",
        background: "transparent", color: "var(--muted)", fontSize: 12,
        fontFamily: "inherit", cursor: "pointer", textAlign: "left",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-2)"; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
    >
      <span style={{ fontSize: 13, width: 15, textAlign: "center" }}>{theme === "dark" ? "☾" : "☀"}</span>
      <span>{theme === "dark" ? "Dunkel" : "Hell"}</span>
    </button>
  );
};

const Sidebar = ({ active, setActive, openCount = 0 }) => (
  <aside style={{
    width: 220, background: "var(--bg-0)", borderRight: "1px solid var(--line)",
    padding: "20px 12px", display: "flex", flexDirection: "column", gap: 2,
    flexShrink: 0, height: "100vh", position: "sticky", top: 0, overflowY: "auto",
  }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 8px", marginBottom: 18 }}>
      <div style={{
        width: 28, height: 28, borderRadius: 7,
        background: "linear-gradient(135deg, var(--accent), #22c55e)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "var(--mono)", fontWeight: 700, fontSize: 13, color: "var(--on-accent)",
      }}>K</div>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: "-0.01em" }}>Kapital</div>
        <div style={{ fontSize: 10, color: "var(--muted)", fontFamily: "var(--mono)" }}>finance</div>
      </div>
    </div>

    {NAV_GROUPS.map(group => (
      <React.Fragment key={group.label}>
        <div style={{
          fontSize: 9.5, color: "var(--muted)", textTransform: "uppercase",
          letterSpacing: "0.1em", fontWeight: 600, padding: "14px 10px 5px",
        }}>{group.label}</div>
        {group.items.map(it => (
      <button key={it.id} onClick={() => setActive(it.id)} style={{
        display: "flex", alignItems: "center", gap: 9, padding: "8px 10px",
        borderRadius: 7, border: "none",
        background: active === it.id ? "var(--bg-2)" : "transparent",
        color: active === it.id ? "var(--fg)" : "var(--muted)",
        fontSize: 13, fontWeight: active === it.id ? 600 : 400,
        cursor: "pointer", textAlign: "left", transition: "all 0.1s",
        fontFamily: "inherit", position: "relative", width: "100%",
      }}
      onMouseEnter={(e) => { if (active !== it.id) e.currentTarget.style.background = "var(--line-strong)"; }}
      onMouseLeave={(e) => { if (active !== it.id) e.currentTarget.style.background = "transparent"; }}
      >
        {active === it.id && <span style={{ position: "absolute", left: -12, top: "50%", transform: "translateY(-50%)", width: 2, height: 16, background: "var(--accent)", borderRadius: 1 }} />}
        <Icon name={it.icon} size={15} />
        <span style={{ flex: 1 }}>{it.label}</span>
        {it.id === "monatsabschluss" && openCount > 0 && (
          <span style={{
            minWidth: 18, padding: "1px 5px", borderRadius: 9, background: "var(--warn-soft)",
            color: "var(--warn)", fontSize: 10, fontWeight: 600, fontFamily: "var(--mono)", textAlign: "center",
          }}>{openCount}</span>
        )}
      </button>
        ))}
      </React.Fragment>
    ))}

    <div style={{ flex: 1 }} />

    <ThemeToggle />

    <div style={{ padding: 10, background: "var(--bg-2)", borderRadius: "var(--r-sm)", border: "1px solid var(--line)", marginTop: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
        <Icon name="sparkles" size={12} stroke="var(--accent)" />
        <div style={{ fontSize: 11, fontWeight: 600 }}>Lokal · privat</div>
      </div>
      <div style={{ fontSize: 10, color: "var(--muted)", lineHeight: 1.45 }}>
        Alle Daten bleiben auf deinem Gerät
      </div>
    </div>
  </aside>
);

// ── TopBar ────────────────────────────────────────────────────────────────────
const TopBar = ({ title, subtitle, right }) => (
  <div style={{
    display: "flex", alignItems: "flex-end", justifyContent: "space-between",
    padding: "22px 32px 16px", borderBottom: "1px solid var(--line)", gap: 24,
  }}>
    <div>
      <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em", fontFamily: "var(--mono)" }}>{subtitle}</div>
      <h1 style={{ margin: "3px 0 0", fontSize: 24, fontWeight: 600, letterSpacing: "-0.02em" }}>{title}</h1>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>{right}</div>
  </div>
);

// ── Loading / Empty states ─────────────────────────────────────────────────────
const Spinner = () => (
  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 200 }}>
    <div style={{ width: 28, height: 28, border: "2px solid var(--line)", borderTopColor: "var(--accent)", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>
);

const EmptyState = ({ icon = "info", title = "Keine Daten", desc = "" }) => (
  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 60, gap: 12, color: "var(--muted)", textAlign: "center" }}>
    <Icon name={icon} size={32} stroke="var(--line)" />
    <div style={{ fontSize: 15, fontWeight: 500, color: "var(--fg)" }}>{title}</div>
    {desc && <div style={{ fontSize: 13, maxWidth: 320 }}>{desc}</div>}
  </div>
);

// ── Toast notification ─────────────────────────────────────────────────────────
const ToastContext = React.createContext(null);
const useToast = () => React.useContext(ToastContext);

const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = React.useState([]);
  const show = (msg, tone = "pos") => {
    const id = Date.now();
    setToasts(t => [...t, { id, msg, tone }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 3500);
  };
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div style={{ position: "fixed", bottom: 24, right: 24, display: "flex", flexDirection: "column", gap: 8, zIndex: 9999 }}>
        {toasts.map(t => (
          <div key={t.id} style={{
            padding: "10px 16px", borderRadius: 10,
            background: t.tone === "neg" ? "var(--neg)" : t.tone === "warn" ? "var(--warn)" : "var(--accent)",
            color: "var(--on-accent)", fontSize: 13, fontWeight: 500,
            boxShadow: "0 4px 20px var(--shadow)",
            animation: "slideUp 0.2s ease",
          }}>{t.msg}</div>
        ))}
      </div>
      <style>{`@keyframes slideUp { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }`}</style>
    </ToastContext.Provider>
  );
};


// ── Gemeinsamer Filterzustand ────────────────────────────────────────────────
// Zeitraum und Kontoauswahl lagen als useState in jeder Seite und waren beim
// Tabwechsel weg. Bei Presets ärgerlich, bei einem handgewählten Kalender-
// zeitraum richtig ärgerlich. sessionStorage statt localStorage: der Filter
// soll die Sitzung überleben, aber nicht wochenlang stillschweigend weitergelten.
const FILTER_KEY = "kapital.filter.v1";

const _readFilter = () => {
  try {
    const raw = sessionStorage.getItem(FILTER_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) { /* privates Fenster o. ä. — Voreinstellung genügt */ }
  return { preset: "all", account: "all", range: { date_from: "", date_to: "" } };
};

const useSharedFilter = () => {
  const [filter, setFilter] = React.useState(_readFilter);

  const update = React.useCallback((patch) => {
    setFilter(prev => {
      const next = { ...prev, ...patch };
      try { sessionStorage.setItem(FILTER_KEY, JSON.stringify(next)); } catch (e) {}
      return next;
    });
  }, []);

  return {
    preset: filter.preset,
    account: filter.account,
    range: filter.range || { date_from: "", date_to: "" },
    setPreset: (p) => update({ preset: p }),
    setAccount: (a) => update({ account: a }),
    setRange: (r) => update({ range: r, preset: "custom" }),
  };
};

// ── WarningStrip ──────────────────────────────────────────────────────────────
// Für Teilerfolge: die Daten sind da, aber etwas daran ist unsicher (Snapshot
// veraltet, kein Wechselkurs, Position rekonstruiert). Genau dieser Zustand
// wurde bisher als selbstbewusst falsche Zahl gerendert. Ein lokales
// Einzelplatz-Tool hat kein Monitoring — die Oberfläche IST das Dashboard.
const WarningStrip = ({ warnings, onDismiss }) => {
  const list = (warnings || []).filter(Boolean);
  if (!list.length) return null;
  return (
    <div role="status" style={{
      display: "flex", flexDirection: "column", gap: 6,
      padding: "10px 14px", borderRadius: 10,
      background: "var(--warn-soft)", border: "1px solid var(--warn-soft)",
    }}>
      {list.map((w, i) => (
        <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12.5, color: "var(--fg)" }}>
          <span style={{ color: "var(--warn)", flexShrink: 0, lineHeight: 1.5 }}>⚠</span>
          <span style={{ lineHeight: 1.5 }}>{typeof w === "string" ? w : w.message}</span>
        </div>
      ))}
      {onDismiss && (
        <button onClick={onDismiss} style={{
          alignSelf: "flex-start", marginTop: 2, background: "none", border: "none",
          color: "var(--muted)", fontSize: 11, fontFamily: "inherit", cursor: "pointer", padding: 0,
        }}>ausblenden</button>
      )}
    </div>
  );
};

Object.assign(window, {
  fmtEUR, fmtMoney, fmtPct, fmtDate, fmtDateShort, fmtNum,
  Icon, Pill, Card, Stat, Btn, Segmented, ProgressRing,
  Sidebar, TopBar, Spinner, EmptyState, WarningStrip, useSharedFilter,
  ThemeToggle, useTheme, applyTheme, CHART_SERIES, moneyTone,
  ToastContext, ToastProvider, useToast,
});
