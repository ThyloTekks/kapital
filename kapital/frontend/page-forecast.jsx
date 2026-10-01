// Page: Vermögensprognose

const PageForecast = () => {
  const { data: defaults, loading } = useFetch("/api/forecast/defaults");
  const [monthlySavings, setMonthlySavings] = React.useState(null);
  const [error, setError] = React.useState("");
  const [monthlyExpenses, setMonthlyExpenses] = React.useState(null);
  const [currentWealth, setCurrentWealth] = React.useState(null);
  const [annualReturn, setAnnualReturn] = React.useState(7);
  const [years, setYears] = React.useState(20);
  const [initialized, setInitialized] = React.useState(false);

  React.useEffect(() => {
    if (defaults && !initialized) {
      setMonthlySavings(Math.round(defaults.avg_monthly_savings));
      setMonthlyExpenses(Math.round(defaults.avg_monthly_expenses));
      setCurrentWealth(Math.round(defaults.current_wealth));
      setInitialized(true);
    }
  }, [defaults, initialized]);

  // Must be before any early return — Rules of Hooks
  const projection = React.useMemo(() => {
    const pts = [];
    let w = currentWealth || 0;
    const mr = (1 + annualReturn / 100) ** (1 / 12) - 1;
    for (let m = 0; m <= years * 12; m++) {
      if (m % 12 === 0) pts.push({ year: m / 12, value: Math.round(w) });
      w = w * (1 + mr) + (monthlySavings || 0);
    }
    return pts;
  }, [currentWealth, monthlySavings, annualReturn, years]);

  if (loading || !initialized) return <Spinner />;

  const finalValue = projection[projection.length - 1]?.value || 0;
  const totalContributed = (currentWealth || 0) + (monthlySavings || 0) * years * 12;
  const returns = finalValue - totalContributed;

  const NumberInput = ({ label, value, onChange, step = 100, prefix = "€", suffix = "" }) => (
    <div>
      <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 14px", background: "var(--bg-2)", border: "1px solid var(--line)", borderRadius: 10 }}>
        {prefix && <span style={{ color: "var(--muted)", fontSize: 13 }}>{prefix}</span>}
        <input
          type="number"
          value={value ?? ""}
          step={step}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--fg)", fontSize: 14, fontFamily: "var(--mono)", fontWeight: 600 }}
        />
        {suffix && <span style={{ color: "var(--muted)", fontSize: 13 }}>{suffix}</span>}
      </div>
    </div>
  );

  return (
    <div style={{ padding: "24px 32px 48px", display: "flex", flexDirection: "column", gap: 20 }}>
      <WarningStrip warnings={error ? [error] : []} onDismiss={() => setError("")} />
      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 20, alignItems: "start" }}>
        {/* Controls */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Card>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Parameter</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <NumberInput label="Aktuelles Vermögen" value={currentWealth} onChange={setCurrentWealth} step={1000} />
              <NumberInput label="Monatliche Sparrate" value={monthlySavings} onChange={setMonthlySavings} step={50} />
              <NumberInput label="Jährliche Rendite" value={annualReturn} onChange={v => setAnnualReturn(Math.max(0, Math.min(30, v)))} step={0.5} prefix="" suffix="%" />
              <NumberInput label="Anlagehorizont" value={years} onChange={v => setYears(Math.max(1, Math.min(60, Math.round(v))))} step={1} prefix="" suffix="Jahre" />
            </div>
          </Card>

          <Card>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14 }}>Ergebnis in {years} Jahren</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>Endvermögen</span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 18, fontWeight: 700, color: "var(--accent)" }}>{fmtEUR(finalValue)}</span>
              </div>
              <div style={{ height: 1, background: "var(--line)" }} />
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>Einzahlungen</span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 500 }}>{fmtEUR(totalContributed)}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>Zinsertrag</span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 500, color: returns > 0 ? "var(--pos)" : "var(--fg)" }}>
                  {returns >= 0 ? "+" : ""}{fmtEUR(returns)}
                </span>
              </div>
              {totalContributed > 0 && (
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>Zinsanteil</span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 500, color: "var(--accent)" }}>
                    {fmtPct(Math.max(0, returns / finalValue) * 100, { sign: false })}
                  </span>
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Chart */}
        <Card padding={0}>
          <div style={{ padding: "18px 22px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Vermögensentwicklung</div>
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>Prognose über {years} Jahre</div>
            </div>
          </div>
          <div style={{ padding: "14px 12px 16px" }}>
            <AreaChart
              data={projection}
              xKey="year"
              keys={["value"]}
              colors={["var(--accent)"]}
              height={340}
              showLegend={false}
              yFmt={(v) => fmtEUR(v)}
            />
          </div>
        </Card>
      </div>
    </div>
  );
};

window.PageForecast = PageForecast;
