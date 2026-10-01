// Inline-SVG Charts — keine externen Libs

// Returns evenly-spaced, human-readable tick values covering [dMin, dMax]
const niceAxis = (dMin, dMax, targetTicks = 5) => {
  const span = dMax - dMin || 1;
  const rawStep = span / targetTicks;
  const exp = Math.floor(Math.log10(rawStep));
  const mag = Math.pow(10, exp);
  const r = rawStep / mag;
  const step = r <= 1 ? mag : r <= 2 ? 2 * mag : r <= 5 ? 5 * mag : 10 * mag;
  const axMin = Math.floor(dMin / step) * step;
  const axMax = Math.ceil(dMax / step) * step;
  const ticks = [];
  for (let v = axMin; v <= axMax + step * 0.001; v += step)
    ticks.push(parseFloat(v.toPrecision(10)));
  return { axMin, axMax, step, ticks };
};

const compactNum = (v) => {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return (v / 1_000_000).toFixed(1).replace(".", ",") + " Mio.";
  if (abs >= 1_000) return Math.round(v / 1_000) + " k";
  return v.toFixed(0);
};

const Sparkline = ({ values, width = 120, height = 32, stroke = "var(--accent)", fill = true, strokeWidth = 1.5 }) => {
  if (!values?.length) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return [x, y];
  });
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${d} L${width},${height} L0,${height} Z`;
  return (
    <svg width={width} height={height} style={{ display: "block", overflow: "visible" }}>
      {fill && <path d={area} fill={stroke} opacity="0.12" />}
      <path d={d} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

const AreaChart = ({ data, width = 800, height = 240, keys = [], colors = [], yFmt, xKey = "month", showAxis = true, showLegend = true }) => {
  const [tooltip, setTooltip] = React.useState(null);
  const svgRef = React.useRef(null);

  const padL = 72, padR = 16, padT = 16, padB = 32;
  const w = width - padL - padR;
  const h = height - padT - padB;
  const allVals = data.flatMap(d => keys.map(k => d[k]));
  const dataMin = Math.min(...allVals);
  const dataMax = Math.max(...allVals);

  const { axMin, axMax, ticks: yTicks } = niceAxis(dataMin, dataMax);

  const xScale = (i) => padL + (i / Math.max(data.length - 1, 1)) * w;
  const yScale = (v) => padT + h - ((v - axMin) / (axMax - axMin)) * h;

  const showTip = (e, d) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, d });
  };

  return (
    <div style={{ position: "relative" }}>
      <svg ref={svgRef} width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: "block" }} onMouseLeave={() => setTooltip(null)}>
        {showAxis && yTicks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={width - padR} y1={yScale(t)} y2={yScale(t)} stroke="var(--line)" strokeWidth="1" strokeDasharray={i === 0 ? "" : "2 4"} />
            <text x={padL - 8} y={yScale(t) + 4} textAnchor="end" fontSize="10" fill="var(--muted)" fontFamily="var(--mono)">
              {compactNum(t)}
            </text>
          </g>
        ))}
        {showAxis && data.map((d, i) => (
          (i % Math.ceil(data.length / 8) === 0 || i === data.length - 1) && (
            <text key={i} x={xScale(i)} y={height - padB + 16} textAnchor="middle" fontSize="10" fill="var(--muted)" fontFamily="var(--mono)">
              {d[xKey]}
            </text>
          )
        ))}
        {keys.map((k, ki) => {
          const color = colors[ki] || "var(--accent)";
          const pts = data.map((d, i) => [xScale(i), yScale(d[k])]);
          const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
          const area = `${line} L${pts[pts.length-1][0]},${padT + h} L${pts[0][0]},${padT + h} Z`;
          return (
            <g key={k}>
              <defs>
                <linearGradient id={`grad-${k}`} x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity="0.35" />
                  <stop offset="100%" stopColor={color} stopOpacity="0" />
                </linearGradient>
              </defs>
              {ki === 0 && <path d={area} fill={`url(#grad-${k})`} />}
              <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
              {pts.map((p, i) => (i === pts.length - 1) && <circle key={i} cx={p[0]} cy={p[1]} r="3.5" fill={color} stroke="var(--bg-1)" strokeWidth="2" />)}
            </g>
          );
        })}
        {/* invisible hover overlay per data point */}
        {data.map((d, i) => (
          <rect
            key={i}
            x={xScale(i) - w / data.length / 2}
            y={padT}
            width={w / data.length}
            height={h}
            fill="transparent"
            onMouseEnter={(e) => showTip(e, d)}
            onMouseMove={(e) => showTip(e, d)}
          />
        ))}
      </svg>
      {tooltip && (
        <div style={{
          position: "absolute",
          left: tooltip.x + 14,
          top: tooltip.y - 14,
          background: "var(--bg-1)",
          border: "1px solid var(--line)",
          borderRadius: 6,
          padding: "7px 12px",
          fontSize: 12,
          fontFamily: "var(--mono)",
          color: "var(--fg)",
          pointerEvents: "none",
          zIndex: 20,
          whiteSpace: "nowrap",
          boxShadow: "0 4px 12px var(--shadow)"
        }}>
          <div style={{ fontWeight: 600, marginBottom: 5 }}>{tooltip.d[xKey]}</div>
          {keys.map((k, i) => (
            <div key={k} style={{ color: colors[i] || "var(--accent)" }}>
              {k !== "value" && <span style={{ marginRight: 6 }}>{k}</span>}
              {yFmt ? yFmt(tooltip.d[k] ?? 0) : (tooltip.d[k] ?? 0).toLocaleString("de-DE")}
            </div>
          ))}
        </div>
      )}
      {showLegend && keys.length > 1 && (
        <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 11, color: "var(--muted)", paddingLeft: padL }}>
          {keys.map((k, i) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 10, height: 2, background: colors[i] || "var(--accent)", display: "inline-block" }} />
              {k}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// netKey (optional): zeichnet den Überschuss als Linie auf derselben Achse.
// Bewusst KEIN dritter Balken — bei 24 Monaten auf ~800 px ist ein Slot rund
// 30 px breit, da passt kein dritter Balken mehr hinein, und die Komponente ist
// an zwei gespiegelte Reihen gebunden. Eine Linie über den Balken beantwortet
// dieselbe Frage und bleibt lesbar.
// Misst den Container, statt eine feste viewBox darauf zu strecken. Mit
// preserveAspectRatio="none" wurde jede Beschriftung verzerrt, sobald die Karte
// nicht zufällig genau `width` breit war — und in der Höhe blieb unter dem
// Diagramm Platz stehen, weil die Karte im Grid mitwächst, das SVG aber nicht.
const useElementSize = () => {
  const [size, setSize] = React.useState({ w: 0, h: 0 });
  const obs = React.useRef(null);
  const ref = React.useCallback((node) => {
    if (obs.current) { obs.current.disconnect(); obs.current = null; }
    if (!node || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      const w = Math.round(r.width), h = Math.round(r.height);
      setSize((s) => (s.w === w && s.h === h) ? s : { w, h });
    });
    ro.observe(node);
    obs.current = ro;
  }, []);
  return [ref, size];
};

const BarChart = ({ data, width = 800, height = 220, fill = false, posKey = "in", negKey = "out", xKey = "label", yFmt, netKey = null, netLabel = "Überschuss" }) => {
  const [tooltip, setTooltip] = React.useState(null);
  const svgRef = React.useRef(null);
  const [boxRef, box] = useElementSize();

  // Gemessene Maße gewinnen; die Props sind nur noch der Startwert für den
  // ersten Frame (und die Vorgabe, wenn `fill` aus ist).
  const W = box.w || width;
  const H = Math.max(fill ? (box.h || height) : height, 140);

  const padL = 72, padR = 16, padT = 16, padB = 32;
  const w = W - padL - padR;
  const h = H - padT - padB;
  // Math.max(...[]) ist -Infinity und vergiftet die gesamte Achse (NaN-Attribute
  // im SVG). Mit dem freien Kalender-Zeitraum ist ein leerer Datensatz einen
  // Klick entfernt, deshalb hier abfangen statt sich darauf zu verlassen,
  // dass jeder Preset Daten enthält.
  if (!data || data.length === 0) {
    return (
      <div style={{ height: fill ? "100%" : height, flex: fill ? "1 1 auto" : undefined,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    color: "var(--muted)", fontSize: 13 }}>
        Keine Buchungen im gewählten Zeitraum
      </div>
    );
  }
  const rawMax = Math.max(
    ...data.map(d => Math.max(
      d[posKey] || 0, d[negKey] || 0, netKey ? Math.abs(d[netKey] || 0) : 0
    )),
    0
  );
  const { axMax: niceMax, ticks: posTicks } = niceAxis(0, rawMax, 4);
  const yScale = (v) => (v / niceMax) * (h / 2 - 4);
  const midY = padT + h / 2;
  const slot = w / data.length;
  const barW = Math.min(slot * 0.32, 22);

  const showTip = (e, d) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, d });
  };

  const fmt = (v) => yFmt ? yFmt(v) : v.toLocaleString("de-DE");

  return (
    <div ref={boxRef} style={{ position: "relative", width: "100%", minWidth: 0, minHeight: 0,
                               height: fill ? "100%" : height, flex: fill ? "1 1 auto" : undefined }}>
      <svg ref={svgRef} width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
           style={{ display: "block" }} onMouseLeave={() => setTooltip(null)}>
        <line x1={padL} x2={W - padR} y1={midY} y2={midY} stroke="var(--line)" strokeWidth="1" />
        {posTicks.filter(t => t > 0).map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={midY - yScale(t)} y2={midY - yScale(t)} stroke="var(--line)" strokeDasharray="2 4" />
            <line x1={padL} x2={W - padR} y1={midY + yScale(t)} y2={midY + yScale(t)} stroke="var(--line)" strokeDasharray="2 4" />
            <text x={padL - 8} y={midY - yScale(t) + 3} textAnchor="end" fontSize="10" fill="var(--muted)" fontFamily="var(--mono)">{compactNum(t)}</text>
            <text x={padL - 8} y={midY + yScale(t) + 3} textAnchor="end" fontSize="10" fill="var(--muted)" fontFamily="var(--mono)">−{compactNum(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const cx = padL + slot * i + slot / 2;
          const posH = yScale(d[posKey] || 0);
          const negH = yScale(d[negKey] || 0);
          const isHovered = tooltip?.d === d;
          return (
            <g key={i} onMouseEnter={(e) => showTip(e, d)} onMouseMove={(e) => showTip(e, d)}>
              <rect x={cx - barW - 1} y={midY - posH} width={barW} height={posH} fill="var(--pos)" rx="2" opacity={isHovered ? 1 : 0.85} />
              <rect x={cx + 1} y={midY} width={barW} height={negH} fill="var(--neg)" rx="2" opacity={isHovered ? 1 : 0.7} />
              <text x={cx} y={H - padB + 16} textAnchor="middle" fontSize="10" fill={isHovered ? "var(--fg)" : "var(--muted)"} fontFamily="var(--mono)">{d[xKey]}</text>
            </g>
          );
        })}

        {/* Überschusslinie: Einnahmen − (Ausgaben − Erstattungen). Ohne den
            Erstattungsterm könnte sie nie zur ausgewiesenen Sparrate passen. */}
        {netKey && (() => {
          const pts = data.map((d, i) => {
            const cx = padL + slot * i + slot / 2;
            const v = d[netKey] || 0;
            return [cx, midY - yScale(v)];
          });
          const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" ");
          return (
            <g>
              <path d={path} fill="none" stroke="var(--fg)" strokeWidth="1.6"
                    strokeLinejoin="round" strokeLinecap="round" opacity="0.85" />
              {pts.map((p, i) => (
                <circle key={i} cx={p[0]} cy={p[1]} r="2.4"
                        fill={(data[i][netKey] || 0) >= 0 ? "var(--pos)" : "var(--neg)"}
                        stroke="var(--bg-1)" strokeWidth="1.4" />
              ))}
            </g>
          );
        })()}
      </svg>
      {tooltip && (
        <div style={{
          position: "absolute",
          left: tooltip.x + 14,
          top: tooltip.y - 14,
          background: "var(--bg-1)",
          border: "1px solid var(--line)",
          borderRadius: 6,
          padding: "7px 12px",
          fontSize: 12,
          fontFamily: "var(--mono)",
          color: "var(--fg)",
          pointerEvents: "none",
          zIndex: 20,
          whiteSpace: "nowrap",
          boxShadow: "0 4px 12px var(--shadow)"
        }}>
          <div style={{ fontWeight: 600, marginBottom: 5, color: "var(--fg)" }}>{tooltip.d[xKey]}</div>
          <div style={{ color: "var(--pos)", marginBottom: 2 }}>▲ {fmt(tooltip.d[posKey] || 0)}</div>
          <div style={{ color: "var(--neg)" }}>▼ {fmt(tooltip.d[negKey] || 0)}</div>
          {tooltip.d.refunds > 0 && (
            <div style={{ color: "var(--warn)", marginTop: 2 }}>↩ {fmt(tooltip.d.refunds)} erstattet</div>
          )}
          {netKey && (
            <div style={{
              marginTop: 5, paddingTop: 5, borderTop: "1px solid var(--line)",
              color: (tooltip.d[netKey] || 0) >= 0 ? "var(--pos)" : "var(--neg)",
            }}>{netLabel}: {fmt(tooltip.d[netKey] || 0)}</div>
          )}
        </div>
      )}
    </div>
  );
};

const Donut = ({ data, size = 200, thickness = 28, centerLabel, centerValue }) => {
  const total = data.reduce((s, d) => s + d.value, 0);
  const r = size / 2 - thickness / 2 - 2;
  const cx = size / 2, cy = size / 2;
  let acc = 0;
  return (
    <svg width={size} height={size}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--line)" strokeWidth={thickness} opacity="0.4" />
      {data.map((d, i) => {
        const frac = d.value / total;
        const start = acc * 2 * Math.PI - Math.PI / 2;
        const end = (acc + frac) * 2 * Math.PI - Math.PI / 2;
        acc += frac;
        const large = frac > 0.5 ? 1 : 0;
        const x1 = cx + r * Math.cos(start);
        const y1 = cy + r * Math.sin(start);
        const x2 = cx + r * Math.cos(end);
        const y2 = cy + r * Math.sin(end);
        const path = `M${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2}`;
        return <path key={i} d={path} fill="none" stroke={d.color} strokeWidth={thickness} strokeLinecap="butt" />;
      })}
      {centerLabel && (
        <>
          <text x={cx} y={cy - 4} textAnchor="middle" fontSize="11" fill="var(--muted)" fontFamily="var(--mono)" style={{ textTransform: "uppercase", letterSpacing: "0.06em" }}>{centerLabel}</text>
          <text x={cx} y={cy + 16} textAnchor="middle" fontSize="18" fill="var(--fg)" fontFamily="var(--mono)" fontWeight="600">{centerValue}</text>
        </>
      )}
    </svg>
  );
};

const StackedBar = ({ segments, height = 8, total }) => {
  const sum = total || segments.reduce((s, x) => s + x.value, 0);
  return (
    <div style={{ display: "flex", height, borderRadius: height / 2, overflow: "hidden", background: "var(--line)" }}>
      {segments.map((s, i) => (
        <div key={i} style={{ width: `${(s.value / sum) * 100}%`, background: s.color }} title={`${s.label}: ${s.value}`} />
      ))}
    </div>
  );
};

Object.assign(window, { Sparkline, AreaChart, BarChart, Donut, StackedBar, niceAxis, compactNum });
