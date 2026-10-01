// Page: FIRE-Rechner

const PageFire = () => {
  const { data: defaults, loading } = useFetch("/api/fire/defaults");
  const [monthlyExpenses, setMonthlyExpenses] = React.useState(null);
  const [error, setError] = React.useState("");
  const [monthlySavings, setMonthlySavings] = React.useState(null);
  const [currentWealth, setCurrentWealth] = React.useState(0);
  const [annualReturn, setAnnualReturn] = React.useState(7);
  const [inflation, setInflation] = React.useState(2);
  const [swr, setSwr] = React.useState(4);
  const [initialized, setInitialized] = React.useState(false);
  const [result, setResult] = React.useState(null);
  const [computing, setComputing] = React.useState(false);

  React.useEffect(() => {
    if (defaults && !initialized) {
      setMonthlyExpenses(Math.round(defaults.avg_monthly_expenses));
      setMonthlySavings(Math.round(defaults.avg_monthly_savings));
      setInitialized(true);
    }
  }, [defaults, initialized]);

  const compute = React.useCallback(async () => {
    if (monthlyExpenses == null || monthlySavings == null) return;
    setComputing(true);
    const params = new URLSearchParams({
      monthly_expenses: monthlyExpenses,
      monthly_savings: monthlySavings,
      current_wealth: currentWealth,
      annual_return: annualReturn,
      inflation,
      swr,
    });
    const res = await fetch(`/api/fire/compute?${params}`);
    const d = await res.json();
    setResult(d);
    setComputing(false);
  }, [monthlyExpenses, monthlySavings, currentWealth, annualReturn, inflation, swr]);

  React.useEffect(() => {
    if (initialized) compute();
  }, [initialized, compute]);

  if (loading || !initialized) return <Spinner />;

  const NumberInput = ({ label, value, onChange, step = 100, suffix = "", prefix = "€" }) => (
    <div>
      <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 14px", background: "var(--bg-2)", border: "1px solid var(--line)", borderRadius: 10 }}>
        {prefix && <span style={{ color: "var(--muted)", fontSize: 13 }}>{prefix}</span>}
        <input
          type="number" value={value ?? ""} step={step}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          onBlur={compute}
          style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--fg)", fontSize: 14, fontFamily: "var(--mono)", fontWeight: 600 }}
        />
        {suffix && <span style={{ color: "var(--muted)", fontSize: 13 }}>{suffix}</span>}
      </div>
    </div>
  );

  const yearsStr = result?.years_to_fire != null
    ? `${result.years_to_fire} Jahre`
    : "Noch nicht erreichbar";

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20 }}>
      <WarningStrip warnings={error ? [error] : []} onDismiss={() => setError("")} />
      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 20, alignItems: "start" }}>
        {/* Input panel */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Einnahmen & Ausgaben</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <NumberInput label="Monatliche Ausgaben" value={monthlyExpenses} onChange={setMonthlyExpenses} />
              <NumberInput label="Monatliche Sparrate" value={monthlySavings} onChange={setMonthlySavings} />
              <NumberInput label="Aktuelles Vermögen" value={currentWealth} onChange={setCurrentWealth} step={1000} />
            </div>
          </Card>

          <Card>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Annahmen</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <NumberInput label="Jährliche Rendite" value={annualReturn} onChange={v => setAnnualReturn(Math.max(0, Math.min(30, v)))} step={0.5} prefix="" suffix="%" />
              <NumberInput label="Inflation" value={inflation} onChange={v => setInflation(Math.max(0, Math.min(20, v)))} step={0.5} prefix="" suffix="%" />
              <NumberInput label="Entnahmerate (SWR)" value={swr} onChange={v => setSwr(Math.max(1, Math.min(10, v)))} step={0.25} prefix="" suffix="%" />
            </div>
          </Card>

          <Btn variant="primary" onClick={compute} disabled={computing}>
            {computing ? "Berechne …" : "Berechnen"}
          </Btn>
        </div>

        {/* Results panel */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {result && (
            <>
              {/* Hero */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14 }}>
                <Card style={{ gridColumn: "1 / -1" }}>
                  <div style={{ textAlign: "center", padding: "16px 0" }}>
                    <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Zeit bis FIRE</div>
                    <div style={{ fontSize: 48, fontWeight: 800, fontFamily: "var(--mono)", color: result.years_to_fire != null ? "var(--accent)" : "var(--muted)", lineHeight: 1 }}>
                      {result.years_to_fire != null ? result.years_to_fire : "∞"}
                    </div>
                    {result.years_to_fire != null && <div style={{ fontSize: 14, color: "var(--muted)", marginTop: 6 }}>Jahre · {result.months_to_fire} Monate</div>}
                  </div>
                </Card>
                <Card>
                  <Stat label="FIRE-Zahl" value={fmtEUR(result.fire_number)} large sub={`${swr}% Entnahmerate`} />
                </Card>
                <Card>
                  <Stat label="Fehlender Betrag" value={fmtEUR(result.gap)} deltaTone={result.gap <= 0 ? "pos" : "neg"}
                    delta={result.gap <= 0 ? "Ziel erreicht!" : "noch aufzubauen"} />
                </Card>
                <Card>
                  <Stat label="Jährliche Ausgaben" value={fmtEUR(result.annual_expenses)} sub="bei FIRE" />
                </Card>
                <Card>
                  <Stat label="Passives Einkommen" value={fmtEUR(result.passive_income_at_fire)} deltaTone="pos"
                    delta="bei FIRE-Zahl" sub="jährlich" />
                </Card>
              </div>

              {/* Projection chart */}
              {result.projection?.length > 0 && (
                <Card padding={0}>
                  <div style={{ padding: "18px 22px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Vermögensentwicklung</div>
                      <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>Prognose vs. FIRE-Ziel</div>
                    </div>
                  </div>
                  <div style={{ padding: "14px 12px 4px" }}>
                    <AreaChart
                      data={result.projection}
                      xKey="year"
                      keys={["value"]}
                      colors={["var(--accent)"]}
                      height={280}
                      showLegend={false}
                      yFmt={(v) => fmtEUR(v)}
                    />
                  </div>
                  <div style={{ display: "flex", gap: 20, padding: "12px 22px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)" }}>
                      <div style={{ width: 12, height: 2, background: "var(--accent)", borderRadius: 1 }} /> Vermögen
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)" }}>
                      <div style={{ width: 12, height: 2, background: "var(--neg)", borderRadius: 1, borderTop: "2px dashed var(--neg)" }} /> FIRE-Ziel
                    </div>
                  </div>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

window.PageFire = PageFire;
