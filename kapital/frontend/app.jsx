// App root — wires Sidebar + TopBar + pages, no mock data

const PAGE_META = {
  dashboard:        { title: "Übersicht",        subtitle: "Dashboard" },
  upload:           { title: "Daten importieren", subtitle: "Import" },
  monatsabschluss:  { title: "Monatsabschluss",  subtitle: "Ziele & Bewertung" },
  transactions:     { title: "Buchungen",         subtitle: "Transaktionen" },
  categories:       { title: "Kategorien & Budgets", subtitle: "Kategorisierung" },
  portfolio:        { title: "Portfolio",          subtitle: "Trade Republic" },
  forecast:         { title: "Vermögensprognose", subtitle: "Forecast" },
  jahresuebersicht: { title: "Jahresübersicht",   subtitle: "Statistik" },
  abos:             { title: "Abonnements",        subtitle: "Abos & Wiederkehrend" },
  fire:             { title: "FIRE-Rechner",       subtitle: "Financial Independence" },
  steuer:           { title: "Steuervorbereitung", subtitle: "Kapitalerträge" },
  regeln:           { title: "Kategorien-Regeln",  subtitle: "Auto-Kategorisierung" },
  vermoegen:        { title: "Vermögen",           subtitle: "Verlauf & Konten" },
};

const PAGES = {
  dashboard:        PageDashboard,
  vermoegen:        PageVermoegen,
  upload:           PageUpload,
  monatsabschluss:  PageMonatsabschluss,
  transactions:     PageTransactions,
  categories:       PageCategories,
  portfolio:        PagePortfolio,
  forecast:         PageForecast,
  jahresuebersicht: PageJahresuebersicht,
  abos:             PageAbos,
  fire:             PageFire,
  steuer:           PageSteuer,
  regeln:           PageRegeln,
};

// Seite aus dem URL-Hash. Vorher war die aktive Seite reiner useState: kein
// Lesezeichen, kein Zurück-Button, und jedes Neuladen landete auf der
// Übersicht — bei dreizehn Ansichten spürbar.
const pageFromHash = () => {
  const id = (window.location.hash || "").replace(/^#\/?/, "").split("?")[0];
  return PAGES[id] ? id : "dashboard";
};

const App = () => {
  const [active, _setActive] = React.useState(pageFromHash);

  const setActive = React.useCallback((id) => {
    _setActive(id);
    if (pageFromHash() !== id) window.location.hash = `#/${id}`;
  }, []);

  // Zurück/Vorwärts im Browser bedienen
  React.useEffect(() => {
    const onHash = () => _setActive(pageFromHash());
    window.addEventListener("hashchange", onHash);
    if (!window.location.hash) window.location.replace(`#/${active}`);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const [review, setReview] = React.useState(null);   // { months: [...] } | null
  const [openTotal, setOpenTotal] = React.useState(0);
  const meta = PAGE_META[active] || PAGE_META.dashboard;
  const Page = PAGES[active] || PageDashboard;

  const refreshOpen = React.useCallback(() => {
    fetch("/api/review/status")
      .then((r) => r.json())
      .then((d) => setOpenTotal(d.open_total || 0))
      .catch(() => {});
  }, []);

  React.useEffect(() => { refreshOpen(); }, [refreshOpen]);

  // Andere Seiten (Import, Monatsabschluss) öffnen das Gate über ein Event
  React.useEffect(() => {
    const handler = (e) => setReview({ months: (e.detail && e.detail.months) || [] });
    window.addEventListener("kapital:review", handler);
    return () => window.removeEventListener("kapital:review", handler);
  }, []);

  return (
    <ToastProvider>
      <div className="app">
        <Sidebar active={active} setActive={setActive} openCount={openTotal} />
        <main className="main">
          <TopBar title={meta.title} subtitle={meta.subtitle} right={
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {openTotal > 0 && (
                <button
                  onClick={() => setReview({ months: [] })}
                  title="Offene Buchungen zuordnen"
                  style={{
                    display: "flex", alignItems: "center", gap: 7, padding: "6px 12px",
                    background: "var(--warn-soft)", border: "1px solid var(--warn-soft)",
                    borderRadius: 8, fontSize: 12, color: "var(--warn)", cursor: "pointer",
                    fontFamily: "inherit", fontWeight: 500,
                  }}
                >
                  <Icon name="bell" size={12} />
                  {openTotal} offen
                </button>
              )}
              <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "6px 12px", background: "var(--bg-1)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12, color: "var(--muted)" }}>
                <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--pos)" }} />
                Lokal
              </div>
              <Btn variant="primary" icon="plus" size="sm" onClick={() => setActive("upload")}>Import</Btn>
            </div>
          } />
          <div style={{ flex: 1, overflowY: "auto" }}>
            <Page />
          </div>
        </main>
      </div>

      {review && (
        <ReviewModal
          months={review.months}
          onClose={() => { setReview(null); refreshOpen(); }}
          onFinished={() => { refreshOpen(); setActive("monatsabschluss"); }}
        />
      )}
    </ToastProvider>
  );
};

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
