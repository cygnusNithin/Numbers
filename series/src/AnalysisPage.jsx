import React, { useEffect, useMemo, useState } from "react";

const ENDPOINTS = {
  old: "http://localhost:5000/api/analysis/lotterydata",
  new: "http://localhost:5000/api/analysis/lotterydatanew",
};

const colors = {
  bg: "#0b1220",
  panel: "#0f1a2b",
  panel2: "#101f35",
  text: "#e6edf6",
  mut: "#9fb0c3",
  line: "rgba(255,255,255,0.10)",
  blue: "#3b82f6",
  green: "#22c55e",
  yellow: "#f59e0b",
  red: "#ef4444",
  purple: "#a855f7",
};

const PRIZE_COLORS = {
  5000: "#ec4899",
  2000: "#a855f7",
  1000: "#6366f1",
  500: "#3b82f6",
  200: "#06b6d4",
  100: "#10b981",
};

const page = {
  padding: 22,
  fontFamily: "Inter, system-ui, Arial, sans-serif",
  color: colors.text,
  background: `linear-gradient(180deg, ${colors.bg}, #050913)`,
  minHeight: "100vh",
};

const card = (extra = {}) => ({
  background: `linear-gradient(180deg, ${colors.panel}, ${colors.panel2})`,
  border: `1px solid ${colors.line}`,
  borderRadius: 16,
  padding: 16,
  boxShadow: "0 10px 30px rgba(0,0,0,0.30)",
  ...extra,
});

const btn = (active = false) => ({
  padding: "10px 14px",
  borderRadius: 12,
  border: `1px solid ${active ? "rgba(59,130,246,0.8)" : colors.line}`,
  background: active ? "rgba(59,130,246,0.18)" : "rgba(255,255,255,0.03)",
  color: colors.text,
  cursor: "pointer",
  fontWeight: 900,
});

const chip = (bg, extra = {}) => ({
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  padding: "6px 10px",
  borderRadius: 999,
  background: bg,
  border: `1px solid ${colors.line}`,
  fontSize: 12,
  fontWeight: 900,
  ...extra,
});

function Badge({ tone = "muted", children }) {
  const bg =
    tone === "good"
      ? "rgba(34,197,94,0.18)"
      : tone === "warn"
        ? "rgba(245,158,11,0.18)"
        : tone === "bad"
          ? "rgba(239,68,68,0.18)"
          : "rgba(255,255,255,0.06)";

  const border =
    tone === "good"
      ? "rgba(34,197,94,0.35)"
      : tone === "warn"
        ? "rgba(245,158,11,0.35)"
        : tone === "bad"
          ? "rgba(239,68,68,0.35)"
          : colors.line;

  const color =
    tone === "good"
      ? "#b6f3c8"
      : tone === "warn"
        ? "#ffe2b3"
        : tone === "bad"
          ? "#ffc1c1"
          : colors.mut;

  return (
    <span style={{ ...chip(bg), border: `1px solid ${border}`, color }}>
      {children}
    </span>
  );
}

function Kpi({ label, value, sub }) {
  return (
    <div style={card({ padding: 14 })}>
      <div style={{ color: colors.mut, fontSize: 12, fontWeight: 900 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 950, marginTop: 6 }}>{value}</div>
      {sub ? (
        <div style={{ color: colors.mut, fontSize: 12, marginTop: 6 }}>
          {sub}
        </div>
      ) : null}
    </div>
  );
}

function Section({ title, right, children }) {
  return (
    <div style={card()}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 10,
          flexWrap: "wrap",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 950 }}>{title}</div>
        {right}
      </div>
      {children}
    </div>
  );
}

function Bar({ value, max, color, height = 10 }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div
      style={{
        height,
        borderRadius: 999,
        background: "rgba(255,255,255,0.06)",
        border: `1px solid ${colors.line}`,
        overflow: "hidden",
      }}
    >
      <div style={{ width: `${pct}%`, height: "100%", background: color }} />
    </div>
  );
}

function NumberChips({ items = [], max = 60 }) {
  const shown = items.slice(0, max);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {shown.map((x, i) => (
        <span
          key={i}
          style={{
            padding: "6px 10px",
            borderRadius: 10,
            background: "rgba(255,255,255,0.04)",
            border: `1px solid ${colors.line}`,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: 12,
            fontWeight: 900,
          }}
        >
          {String(x)}
        </span>
      ))}
      {items.length > max ? (
        <span style={{ color: colors.mut, fontSize: 12, alignSelf: "center" }}>
          +{items.length - max} more
        </span>
      ) : null}
    </div>
  );
}

function formatNum(x) {
  if (x === null || x === undefined) return "—";
  if (typeof x === "number") return x.toLocaleString();
  return String(x);
}

export default function AnalysisPage() {
  const [source, setSource] = useState("new");
  const [data, setData] = useState(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [tab, setTab] = useState("overview"); // overview | digits | patterns | prizes
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function load(which, d = "") {
    setSource(which);
    setLoading(true);
    setError(null);

    const url = d
      ? `${ENDPOINTS[which]}?date=${encodeURIComponent(d)}`
      : ENDPOINTS[which];

    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((json) => {
        setData(json);
        if (json.ok && json.targetDate) setSelectedDate(json.targetDate);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }

  useEffect(() => {
    load("new", "");
  }, []);

  const t = data?.tests || {};

  const digitSignificantCount = useMemo(
    () => (t.digitAnalysis || []).filter((p) => p.isSignificant).length,
    [t.digitAnalysis],
  );

  const modularSignificantCount = useMemo(
    () => (t.modularPatterns || []).filter((m) => m.isSignificant).length,
    [t.modularPatterns],
  );

  const evenPct = useMemo(() => {
    if (!t.evenOdd) return null;
    const total = (t.evenOdd.even ?? 0) + (t.evenOdd.odd ?? 0);
    if (!total) return null;
    return +(((t.evenOdd.even ?? 0) / total) * 100).toFixed(1);
  }, [t.evenOdd]);

  if (loading) {
    return (
      <div style={page}>
        <div style={{ maxWidth: 1250, margin: "0 auto" }}>
          <div style={{ fontSize: 22, fontWeight: 950 }}>Analysis</div>
          <div style={{ marginTop: 16, ...card() }}>Loading…</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={page}>
        <div style={{ maxWidth: 1250, margin: "0 auto" }}>
          <div style={{ fontSize: 22, fontWeight: 950 }}>Analysis</div>
          <div
            style={{
              marginTop: 14,
              ...card({ border: "1px solid rgba(239,68,68,0.5)" }),
            }}
          >
            <div style={{ fontWeight: 950, color: "#ffd1d1" }}>
              Request failed
            </div>
            <div style={{ marginTop: 8, color: colors.mut }}>{error}</div>
            <div style={{ marginTop: 12 }}>
              <button
                style={btn(true)}
                onClick={() => load(source, selectedDate)}
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!data) return null;

  if (data.ok === false) {
    return (
      <div style={page}>
        <div style={{ maxWidth: 1250, margin: "0 auto" }}>
          <div style={{ fontSize: 22, fontWeight: 950 }}>Analysis</div>
          <div
            style={{
              marginTop: 14,
              ...card({ border: "1px solid rgba(239,68,68,0.5)" }),
            }}
          >
            <div style={{ fontWeight: 950, color: "#ffd1d1" }}>API error</div>
            <div style={{ marginTop: 8, color: colors.mut }}>
              {data.error || "Unknown error"}
            </div>
            <div style={{ marginTop: 12 }}>
              <button style={btn(true)} onClick={() => load(source, "")}>
                Load latest
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const datasetFirst =
    data.summary?.firstDate || data.availableDates?.[0] || "—";
  const datasetLast =
    data.summary?.lastDate ||
    data.availableDates?.[data.availableDates.length - 1] ||
    "—";
  const datasetDays =
    data.summary?.totalDays ?? data.availableDates?.length ?? 0;

  return (
    <div style={page}>
      <div style={{ maxWidth: 1250, margin: "0 auto" }}>
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <div>
            <div style={{ fontSize: 24, fontWeight: 950 }}>
              Daily Number Analysis
            </div>
            <div
              style={{
                color: colors.mut,
                marginTop: 6,
                fontSize: 13,
                lineHeight: 1.5,
              }}
            >
              Dataset:{" "}
              <span style={{ color: colors.text, fontWeight: 950 }}>
                {datasetFirst} → {datasetLast}
              </span>{" "}
              · Days:{" "}
              <span style={{ color: colors.text, fontWeight: 950 }}>
                {datasetDays}
              </span>
              <br />
              Selected:{" "}
              <span style={{ color: colors.text, fontWeight: 950 }}>
                {data.targetDate}
              </span>{" "}
              · Numbers:{" "}
              <span style={{ color: colors.text, fontWeight: 950 }}>
                {formatNum(data.totalNumbers)}
              </span>{" "}
              · Anomalies:{" "}
              <span style={{ color: colors.text, fontWeight: 950 }}>
                {formatNum(data.anomalyCount)}
              </span>
            </div>

            {data.meta?.invalidDateCount > 0 ? (
              <div style={{ marginTop: 10 }}>
                <Badge tone="warn">
                  Skipped invalid date rows: {data.meta.invalidDateCount}
                </Badge>
              </div>
            ) : null}
          </div>

          {/* Controls */}
          <div
            style={{
              display: "flex",
              gap: 10,
              flexWrap: "wrap",
              alignItems: "center",
            }}
          >
            <button
              style={btn(source === "old")}
              onClick={() => load("old", selectedDate)}
            >
              Old DB
            </button>
            <button
              style={btn(source === "new")}
              onClick={() => load("new", selectedDate)}
            >
              New DB
            </button>

            <select
              value={selectedDate || data.targetDate || ""}
              onChange={(e) => {
                const d = e.target.value;
                setSelectedDate(d);
                load(source, d);
              }}
              style={{
                padding: "10px 12px",
                borderRadius: 12,
                border: `1px solid ${colors.line}`,
                background: "rgba(255,255,255,0.03)",
                color: colors.text,
                fontWeight: 900,
                outline: "none",
              }}
            >
              {(data.availableDates || []).map((d) => (
                <option key={d} value={d} style={{ background: "#0b1220" }}>
                  {d}
                </option>
              ))}
            </select>

            <button style={btn(false)} onClick={() => load(source, "")}>
              Latest
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div
          style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}
        >
          <button
            style={btn(tab === "overview")}
            onClick={() => setTab("overview")}
          >
            Overview
          </button>
          <button
            style={btn(tab === "digits")}
            onClick={() => setTab("digits")}
          >
            Digits
          </button>
          <button
            style={btn(tab === "patterns")}
            onClick={() => setTab("patterns")}
          >
            Patterns
          </button>
          <button
            style={btn(tab === "prizes")}
            onClick={() => setTab("prizes")}
          >
            Prizes
          </button>
        </div>

        {/* KPI Row */}
        <div
          style={{
            marginTop: 14,
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(4, minmax(0,1fr))",
          }}
        >
          <Kpi
            label="Mean"
            value={formatNum(t.basicStats?.mean)}
            sub={`Expected ≈ ${t.basicStats?.expectedMean ?? 4999.5}`}
          />
          <Kpi
            label="Std Dev"
            value={formatNum(t.basicStats?.stdDev)}
            sub={`Expected ≈ ${t.basicStats?.expectedStdDev ?? 2886.75}`}
          />
          <Kpi
            label="Even %"
            value={evenPct === null ? "—" : `${evenPct}%`}
            sub={
              t.evenOdd ? `${t.evenOdd.even} even / ${t.evenOdd.odd} odd` : "—"
            }
          />
          <Kpi
            label="Flags"
            value={`${digitSignificantCount + modularSignificantCount}`}
            sub={`${digitSignificantCount} digit · ${modularSignificantCount} modular`}
          />
        </div>

        {/* CONTENT */}
        <div style={{ marginTop: 14, display: "grid", gap: 12 }}>
          {tab === "overview" && (
            <>
              <Section
                title="Anomalies"
                right={
                  data.anomalyCount ? (
                    <Badge tone="warn">{data.anomalyCount} flagged</Badge>
                  ) : (
                    <Badge tone="good">None</Badge>
                  )
                }
              >
                {!data.anomalies?.length ? (
                  <div style={{ color: colors.mut }}>No anomalies flagged.</div>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 10,
                    }}
                  >
                    {data.anomalies.map((a, i) => (
                      <div
                        key={i}
                        style={{
                          padding: 12,
                          borderRadius: 14,
                          border: `1px solid ${colors.line}`,
                          background:
                            a.severity === "HIGH"
                              ? "rgba(239,68,68,0.10)"
                              : "rgba(245,158,11,0.10)",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            gap: 10,
                            flexWrap: "wrap",
                            alignItems: "center",
                          }}
                        >
                          <Badge tone={a.severity === "HIGH" ? "bad" : "warn"}>
                            {a.severity}
                          </Badge>
                          <span
                            style={{
                              color: colors.mut,
                              fontWeight: 900,
                              fontSize: 12,
                            }}
                          >
                            {a.type}
                          </span>
                        </div>
                        <div style={{ marginTop: 8, fontWeight: 950 }}>
                          {a.message}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Section>

              {data.meta?.invalidDateCount > 0 &&
              data.meta?.invalidDateExamples?.length ? (
                <Section
                  title="Invalid date examples (skipped)"
                  right={<Badge tone="warn">Fix these in DB</Badge>}
                >
                  <NumberChips items={data.meta.invalidDateExamples} max={20} />
                </Section>
              ) : null}

              <Section
                title="Cross-day overlap"
                right={<Badge tone="muted">prev/next day repeats</Badge>}
              >
                <div
                  style={{
                    display: "grid",
                    gap: 12,
                    gridTemplateColumns: "repeat(2, minmax(0,1fr))",
                  }}
                >
                  <div style={card({ padding: 14 })}>
                    <div
                      style={{
                        color: colors.mut,
                        fontWeight: 900,
                        fontSize: 12,
                      }}
                    >
                      Previous day
                    </div>
                    {t.crossDay?.previous ? (
                      <>
                        <div
                          style={{
                            marginTop: 6,
                            fontSize: 18,
                            fontWeight: 950,
                          }}
                        >
                          {t.crossDay.previous.overlapCount} overlaps (
                          {t.crossDay.previous.overlapPercent}%)
                        </div>
                        <div
                          style={{
                            marginTop: 6,
                            color: colors.mut,
                            fontSize: 12,
                          }}
                        >
                          Date {t.crossDay.previous.date} · Expected ~
                          {t.crossDay.previous.expectedOverlap}
                        </div>
                      </>
                    ) : (
                      <div style={{ marginTop: 8, color: colors.mut }}>—</div>
                    )}
                  </div>

                  <div style={card({ padding: 14 })}>
                    <div
                      style={{
                        color: colors.mut,
                        fontWeight: 900,
                        fontSize: 12,
                      }}
                    >
                      Next day
                    </div>
                    {t.crossDay?.next ? (
                      <>
                        <div
                          style={{
                            marginTop: 6,
                            fontSize: 18,
                            fontWeight: 950,
                          }}
                        >
                          {t.crossDay.next.overlapCount} overlaps (
                          {t.crossDay.next.overlapPercent}%)
                        </div>
                        <div
                          style={{
                            marginTop: 6,
                            color: colors.mut,
                            fontSize: 12,
                          }}
                        >
                          Date {t.crossDay.next.date} · Expected ~
                          {t.crossDay.next.expectedOverlap}
                        </div>
                      </>
                    ) : (
                      <div style={{ marginTop: 8, color: colors.mut }}>—</div>
                    )}
                  </div>
                </div>
              </Section>
            </>
          )}

          {tab === "digits" && (
            <>
              <Section
                title="Digit-position frequencies"
                right={
                  digitSignificantCount ? (
                    <Badge tone="warn">
                      {digitSignificantCount} significant
                    </Badge>
                  ) : (
                    <Badge tone="good">No significant bias</Badge>
                  )
                }
              >
                <div style={{ display: "grid", gap: 12 }}>
                  {(t.digitAnalysis || []).map((pos) => {
                    const maxFreq = Math.max(
                      ...pos.frequencies.map((x) => x.frequency),
                      1,
                    );
                    return (
                      <div key={pos.position} style={card({ padding: 14 })}>
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            gap: 10,
                            flexWrap: "wrap",
                            alignItems: "center",
                          }}
                        >
                          <div style={{ fontWeight: 950 }}>
                            {pos.positionLabel}
                          </div>
                          <div
                            style={{
                              display: "flex",
                              gap: 8,
                              flexWrap: "wrap",
                            }}
                          >
                            <Badge tone={pos.isSignificant ? "warn" : "muted"}>
                              chi² {pos.chiSquared}
                            </Badge>
                            {pos.isSignificant ? (
                              <Badge tone="bad">significant</Badge>
                            ) : (
                              <Badge tone="good">ok</Badge>
                            )}
                          </div>
                        </div>

                        <div
                          style={{
                            marginTop: 12,
                            display: "grid",
                            gap: 10,
                            gridTemplateColumns: "repeat(10, minmax(0,1fr))",
                          }}
                        >
                          {pos.frequencies.map((f) => {
                            const dev = f.deviationPercent;
                            const barColor =
                              Math.abs(dev) >= 15
                                ? dev > 0
                                  ? colors.green
                                  : colors.red
                                : "rgba(255,255,255,0.20)";
                            return (
                              <div
                                key={f.digit}
                                style={{ textAlign: "center" }}
                              >
                                <div style={{ fontSize: 12, fontWeight: 950 }}>
                                  {f.digit}
                                </div>
                                <div style={{ marginTop: 6 }}>
                                  <Bar
                                    value={f.frequency}
                                    max={maxFreq}
                                    color={barColor}
                                    height={10}
                                  />
                                </div>
                                <div
                                  style={{
                                    marginTop: 6,
                                    fontSize: 11,
                                    color: colors.mut,
                                  }}
                                >
                                  {f.frequency}
                                </div>
                                <div style={{ marginTop: 3 }}>
                                  <Badge
                                    tone={
                                      Math.abs(dev) >= 15
                                        ? dev > 0
                                          ? "good"
                                          : "bad"
                                        : "muted"
                                    }
                                  >
                                    {dev > 0 ? `+${dev}%` : `${dev}%`}
                                  </Badge>
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        {pos.biasedDigits?.length ? (
                          <div style={{ marginTop: 12 }}>
                            <div
                              style={{
                                color: colors.mut,
                                fontSize: 12,
                                fontWeight: 900,
                                marginBottom: 8,
                              }}
                            >
                              Most biased digits (|dev| &gt; 15%)
                            </div>
                            <div
                              style={{
                                display: "flex",
                                gap: 8,
                                flexWrap: "wrap",
                              }}
                            >
                              {pos.biasedDigits.slice(0, 8).map((d) => (
                                <Badge
                                  key={d.digit}
                                  tone={d.deviationPercent > 0 ? "good" : "bad"}
                                >
                                  {d.digit}:{" "}
                                  {d.deviationPercent > 0
                                    ? `+${d.deviationPercent}%`
                                    : `${d.deviationPercent}%`}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </Section>

              <Section
                title="Digit-sum distribution"
                right={<Badge tone="muted">0–36</Badge>}
              >
                {t.digitSumAnalysis?.distribution?.length ? (
                  <div style={card({ padding: 14 })}>
                    <div
                      style={{
                        display: "flex",
                        gap: 10,
                        flexWrap: "wrap",
                        alignItems: "center",
                      }}
                    >
                      <Badge tone="muted">
                        avg {t.digitSumAnalysis.averageDigitSum} (expected 18)
                      </Badge>
                      {t.digitSumAnalysis.peakDigitSum ? (
                        <Badge tone="muted">
                          peak {t.digitSumAnalysis.peakDigitSum[0]} (
                          {t.digitSumAnalysis.peakDigitSum[1]}x)
                        </Badge>
                      ) : null}
                    </div>

                    <div
                      style={{
                        marginTop: 12,
                        display: "flex",
                        gap: 6,
                        alignItems: "flex-end",
                        flexWrap: "wrap",
                      }}
                    >
                      {(() => {
                        const dist = t.digitSumAnalysis.distribution;
                        const max = Math.max(
                          ...dist.map((d) => d.frequency),
                          1,
                        );
                        return dist.map((d) => (
                          <div
                            key={d.digitSum}
                            style={{ width: 22, textAlign: "center" }}
                          >
                            <div
                              style={{
                                height: Math.max(2, (d.frequency / max) * 90),
                                width: 18,
                                margin: "0 auto",
                                borderRadius: 8,
                                background: "rgba(59,130,246,0.65)",
                                border: `1px solid ${colors.line}`,
                              }}
                            />
                            <div
                              style={{
                                marginTop: 6,
                                fontSize: 10,
                                color: colors.mut,
                              }}
                            >
                              {d.digitSum}
                            </div>
                          </div>
                        ));
                      })()}
                    </div>
                  </div>
                ) : (
                  <div style={{ color: colors.mut }}>No digit-sum data.</div>
                )}
              </Section>
            </>
          )}

          {tab === "patterns" && (
            <>
              <Section
                title="Modular patterns"
                right={
                  modularSignificantCount ? (
                    <Badge tone="warn">
                      {modularSignificantCount} significant
                    </Badge>
                  ) : (
                    <Badge tone="good">No significant modular bias</Badge>
                  )
                }
              >
                <div style={{ overflowX: "auto" }}>
                  <table
                    style={{
                      width: "100%",
                      borderCollapse: "collapse",
                      fontSize: 13,
                    }}
                  >
                    <thead>
                      <tr style={{ color: colors.mut, textAlign: "left" }}>
                        <th
                          style={{
                            padding: "10px 10px",
                            borderBottom: `1px solid ${colors.line}`,
                          }}
                        >
                          Mod
                        </th>
                        <th
                          style={{
                            padding: "10px 10px",
                            borderBottom: `1px solid ${colors.line}`,
                          }}
                        >
                          chi²
                        </th>
                        <th
                          style={{
                            padding: "10px 10px",
                            borderBottom: `1px solid ${colors.line}`,
                          }}
                        >
                          Sig?
                        </th>
                        <th
                          style={{
                            padding: "10px 10px",
                            borderBottom: `1px solid ${colors.line}`,
                          }}
                        >
                          Hot
                        </th>
                        <th
                          style={{
                            padding: "10px 10px",
                            borderBottom: `1px solid ${colors.line}`,
                          }}
                        >
                          Cold
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {(t.modularPatterns || [])
                        .slice()
                        .sort(
                          (a, b) => (b.chiSquared || 0) - (a.chiSquared || 0),
                        )
                        .map((m, idx) => (
                          <tr
                            key={m.modulus}
                            style={{
                              background:
                                idx % 2
                                  ? "rgba(255,255,255,0.02)"
                                  : "transparent",
                            }}
                          >
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                                fontWeight: 950,
                              }}
                            >
                              {m.modulus}
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                              }}
                            >
                              {m.chiSquared}
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                              }}
                            >
                              {m.isSignificant ? (
                                <Badge tone="warn">yes</Badge>
                              ) : (
                                <Badge tone="good">no</Badge>
                              )}
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                              }}
                            >
                              r={m.hotResidue?.residue} (
                              {m.hotResidue?.frequency})
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                              }}
                            >
                              r={m.coldResidue?.residue} (
                              {m.coldResidue?.frequency})
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </Section>

              <Section
                title="Gap analysis"
                right={<Badge tone="muted">sorted gaps</Badge>}
              >
                <div
                  style={{
                    display: "grid",
                    gap: 12,
                    gridTemplateColumns: "repeat(2, minmax(0,1fr))",
                  }}
                >
                  <Kpi
                    label="Avg gap"
                    value={formatNum(t.gapAnalysis?.averageGap)}
                    sub={`Expected ≈ ${formatNum(t.gapAnalysis?.expectedGap)}`}
                  />
                  <Kpi
                    label="Max gap"
                    value={formatNum(t.gapAnalysis?.maxGap)}
                    sub={
                      t.gapAnalysis?.maxGapBetween
                        ? `${t.gapAnalysis.maxGapBetween[0]} → ${t.gapAnalysis.maxGapBetween[1]}`
                        : "—"
                    }
                  />
                </div>

                {(t.gapAnalysis?.consecutivePairs || []).length ? (
                  <div style={{ marginTop: 12 }}>
                    <div
                      style={{
                        color: colors.mut,
                        fontSize: 12,
                        fontWeight: 900,
                        marginBottom: 8,
                      }}
                    >
                      Sample consecutive pairs
                    </div>
                    <NumberChips
                      items={t.gapAnalysis.consecutivePairs.map(
                        (p) => `${p[0]}-${p[1]}`,
                      )}
                      max={40}
                    />
                  </div>
                ) : null}
              </Section>

              <div
                style={{
                  display: "grid",
                  gap: 12,
                  gridTemplateColumns: "repeat(2, minmax(0,1fr))",
                }}
              >
                <Section
                  title="Complement pairs (sum=9999)"
                  right={
                    <Badge
                      tone={t.complementAnalysis?.isUnusual ? "warn" : "muted"}
                    >
                      {t.complementAnalysis?.pairsFound ?? 0} pairs
                    </Badge>
                  }
                >
                  <div style={{ color: colors.mut, fontSize: 12 }}>
                    Expected ≈ {t.complementAnalysis?.expectedPairs ?? "—"} ·{" "}
                    {t.complementAnalysis?.isUnusual
                      ? "Flagged unusual"
                      : "Looks normal"}
                  </div>
                  <div style={{ marginTop: 10 }}>
                    <NumberChips
                      items={(t.complementAnalysis?.pairs || []).map(
                        (p) => `${p[0]}↔${p[1]}`,
                      )}
                      max={40}
                    />
                  </div>
                </Section>

                <Section
                  title="Reverse pairs (abcd↔dcba)"
                  right={
                    <Badge tone="muted">
                      {t.reverseAnalysis?.pairsFound ?? 0} pairs
                    </Badge>
                  }
                >
                  <div style={{ color: colors.mut, fontSize: 12 }}>
                    Expected ≈ {t.reverseAnalysis?.expectedPairs ?? "—"}
                  </div>
                  <div style={{ marginTop: 10 }}>
                    <NumberChips
                      items={(t.reverseAnalysis?.pairs || []).map(
                        (p) => `${p[0]}↔${p[1]}`,
                      )}
                      max={40}
                    />
                  </div>
                </Section>
              </div>
            </>
          )}

          {tab === "prizes" && (
            <>
              <Section
                title="Prize-wise comparison"
                right={<Badge tone="muted">per prize</Badge>}
              >
                {!t.prizeComparison?.length ? (
                  <div style={{ color: colors.mut }}>No prize data.</div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table
                      style={{
                        width: "100%",
                        borderCollapse: "collapse",
                        fontSize: 13,
                      }}
                    >
                      <thead>
                        <tr style={{ color: colors.mut, textAlign: "left" }}>
                          <th
                            style={{
                              padding: "10px 10px",
                              borderBottom: `1px solid ${colors.line}`,
                            }}
                          >
                            Prize
                          </th>
                          <th
                            style={{
                              padding: "10px 10px",
                              borderBottom: `1px solid ${colors.line}`,
                            }}
                          >
                            Count
                          </th>
                          <th
                            style={{
                              padding: "10px 10px",
                              borderBottom: `1px solid ${colors.line}`,
                            }}
                          >
                            Mean
                          </th>
                          <th
                            style={{
                              padding: "10px 10px",
                              borderBottom: `1px solid ${colors.line}`,
                            }}
                          >
                            Even%
                          </th>
                          <th
                            style={{
                              padding: "10px 10px",
                              borderBottom: `1px solid ${colors.line}`,
                            }}
                          >
                            DigitSum
                          </th>
                          <th
                            style={{
                              padding: "10px 10px",
                              borderBottom: `1px solid ${colors.line}`,
                            }}
                          >
                            Range
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {t.prizeComparison.map((p, idx) => (
                          <tr
                            key={p.prize}
                            style={{
                              background:
                                idx % 2
                                  ? "rgba(255,255,255,0.02)"
                                  : "transparent",
                            }}
                          >
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                                fontWeight: 950,
                              }}
                            >
                              <span style={chip("rgba(255,255,255,0.04)")}>
                                <span
                                  style={{
                                    width: 10,
                                    height: 10,
                                    borderRadius: 999,
                                    background:
                                      PRIZE_COLORS[p.prize] || colors.purple,
                                    display: "inline-block",
                                  }}
                                />
                                ₹{p.prize}
                              </span>
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                              }}
                            >
                              {p.count}
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                              }}
                            >
                              {p.mean}
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                              }}
                            >
                              {p.evenPercent}%
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                              }}
                            >
                              {p.avgDigitSum}
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                                fontFamily: "ui-monospace, Menlo, monospace",
                              }}
                            >
                              {p.min}–{p.max}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>

              <div
                style={{
                  display: "grid",
                  gap: 12,
                  gridTemplateColumns: "repeat(2, minmax(0,1fr))",
                }}
              >
                <Section
                  title="Sum pairs"
                  right={<Badge tone="muted">5000 / 9999 / 10000</Badge>}
                >
                  {(t.sumPairs || []).map((sp) => (
                    <div
                      key={sp.targetSum}
                      style={card({ padding: 14, marginBottom: 10 })}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          gap: 10,
                          flexWrap: "wrap",
                        }}
                      >
                        <div style={{ fontWeight: 950 }}>
                          Target {sp.targetSum}
                        </div>
                        <Badge tone="muted">
                          {sp.pairsFound} pairs (exp ~{sp.expectedPairs})
                        </Badge>
                      </div>
                      <div style={{ marginTop: 10 }}>
                        <NumberChips
                          items={(sp.sample || []).map(
                            (p) => `${p[0]}+${p[1]}`,
                          )}
                          max={30}
                        />
                      </div>
                    </div>
                  ))}
                </Section>

                <Section
                  title="Multiplicative pairs"
                  right={<Badge tone="muted">×2 ×3 ×5 ×7</Badge>}
                >
                  {(t.multiplicativePatterns || []).map((mp) => (
                    <div
                      key={mp.multiplier}
                      style={card({ padding: 14, marginBottom: 10 })}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          gap: 10,
                          flexWrap: "wrap",
                        }}
                      >
                        <div style={{ fontWeight: 950 }}>×{mp.multiplier}</div>
                        <Badge tone={mp.isUnusual ? "warn" : "muted"}>
                          {mp.pairsFound} pairs (exp ~{mp.expectedPairs})
                        </Badge>
                      </div>
                      <div style={{ marginTop: 10 }}>
                        <NumberChips
                          items={(mp.sample || []).map(
                            (p) => `${p.base}×${p.multiplier}=${p.multiplied}`,
                          )}
                          max={24}
                        />
                      </div>
                    </div>
                  ))}
                </Section>
              </div>
            </>
          )}
        </div>

        <div
          style={{
            marginTop: 18,
            color: colors.mut,
            fontSize: 12,
            textAlign: "center",
          }}
        >
          If dataset start/latest looks wrong, check meta.invalidDateExamples
          (those rows are being skipped).
        </div>
      </div>
    </div>
  );
}
