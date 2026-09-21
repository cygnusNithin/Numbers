import React, { useState, useEffect, useCallback } from "react";

// ============================================================
// API
// ============================================================
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:5000";

const fetchCycles = async (type) => {
  const endpoint = type === "forward" ? "forward-cycles" : "reverse-cycles";
  const res = await fetch(`${API_BASE}/api/${endpoint}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

const fetchCycleDetail = async (type, cycleNumber) => {
  const endpoint = type === "forward" ? "forward-cycles" : "reverse-cycles";
  const res = await fetch(`${API_BASE}/api/${endpoint}/${cycleNumber}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

const fetchWeekdayData = async (type, cycleNumber) => {
  const endpoint = type === "forward" ? "forward-cycles" : "reverse-cycles";
  const res = await fetch(`${API_BASE}/api/${endpoint}/${cycleNumber}/by-weekday`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

const fetchSerialData = async (type, cycleNumber) => {
  const endpoint = type === "forward" ? "forward-cycles" : "reverse-cycles";
  const res = await fetch(`${API_BASE}/api/${endpoint}/${cycleNumber}/by-serial`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

// ============================================================
// DESIGN TOKENS
// ============================================================
const C = {
  bg:          "#0a0e1a",
  bgCard:      "#111827",
  bgDark:      "#0d1117",
  border:      "#1f2937",
  textPrimary: "#f9fafb",
  textSec:     "#9ca3af",
  textMuted:   "#6b7280",
  green:       "#10b981",
  greenDim:    "#064e3b",
  yellow:      "#f59e0b",
  yellowDim:   "#78350f",
  blue:        "#3b82f6",
  blueDim:     "#1e3a5f",
  purple:      "#8b5cf6",
  purpleDim:   "#2e1065",
  cyan:        "#06b6d4",
  cyanDim:     "#0c4a6e",
  red:         "#ef4444",
  orange:      "#f97316",
};

// ============================================================
// PRIMITIVES
// ============================================================
const Badge = ({ children, color = C.blue, dim }) => (
  <span
    style={{
      display:         "inline-block",
      padding:         "2px 8px",
      borderRadius:    4,
      fontSize:        11,
      fontWeight:      700,
      fontFamily:      "monospace",
      color,
      backgroundColor: dim || `${color}22`,
      border:          `1px solid ${color}44`,
      whiteSpace:      "nowrap",
    }}
  >
    {children}
  </span>
);

const Card = ({ children, style, title }) => (
  <div
    style={{
      backgroundColor: C.bgCard,
      border:          `1px solid ${C.border}`,
      borderRadius:    10,
      padding:         20,
      marginBottom:    16,
      ...style,
    }}
  >
    {title && (
      <h3
        style={{
          margin:        "0 0 16px 0",
          color:         C.cyan,
          fontFamily:    "monospace",
          fontWeight:    700,
          fontSize:      14,
          letterSpacing: 1,
        }}
      >
        {title}
      </h3>
    )}
    {children}
  </div>
);

const Bar = ({ value, max, color = C.green, height = 8 }) => (
  <div
    style={{
      height,
      backgroundColor: C.border,
      borderRadius:    4,
      overflow:        "hidden",
      flex:            1,
    }}
  >
    <div
      style={{
        height:          "100%",
        width:           `${Math.min((value / max) * 100, 100)}%`,
        backgroundColor: color,
        borderRadius:    4,
        transition:      "width .4s ease",
      }}
    />
  </div>
);

const Spinner = () => (
  <div
    style={{
      display:        "flex",
      flexDirection:  "column",
      alignItems:     "center",
      justifyContent: "center",
      padding:        60,
      gap:            16,
    }}
  >
    <div
      style={{
        width:        48,
        height:       48,
        border:       `4px solid ${C.border}`,
        borderTop:    `4px solid ${C.cyan}`,
        borderRadius: "50%",
        animation:    "spin 0.8s linear infinite",
      }}
    />
    <span style={{ color: C.textMuted, fontFamily: "monospace", fontSize: 13 }}>
      Loading...
    </span>
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>
);

const ErrorBanner = ({ message, onRetry }) => (
  <div
    style={{
      backgroundColor: "#7f1d1d",
      border:          `1px solid ${C.red}44`,
      borderRadius:    8,
      padding:         20,
      display:         "flex",
      alignItems:      "center",
      justifyContent:  "space-between",
      fontFamily:      "monospace",
      marginBottom:    16,
    }}
  >
    <div>
      <div style={{ color: C.red, fontWeight: 700, marginBottom: 4 }}>❌ Error</div>
      <div style={{ color: C.textSec, fontSize: 12 }}>{message}</div>
    </div>
    {onRetry && (
      <button
        onClick={onRetry}
        style={{
          padding:         "8px 16px",
          backgroundColor: C.red,
          border:          "none",
          borderRadius:    4,
          color:           "#fff",
          fontFamily:      "monospace",
          fontSize:        12,
          cursor:          "pointer",
          fontWeight:      700,
        }}
      >
        ↺ Retry
      </button>
    )}
  </div>
);

// ============================================================
// WEEKDAY ANALYSIS TAB - FIXED
// ============================================================
const WeekdayTab = ({ type, cycleNumber }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const result = await fetchWeekdayData(type, cycleNumber);
        setData(result);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [type, cycleNumber]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBanner message={error} />;
  if (!data || !data.weekdayStats) return null;

  const stats = data.weekdayStats;
  const cycleDateRange = data.cycleDateRange;

  return (
    <div>
      <Card title="📅 WEEKDAY ANALYSIS">
        <div style={{ marginBottom: 20 }}>
          <div style={{ color: C.textMuted, fontSize: 12, marginBottom: 8 }}>
            Cycle Date Range: {cycleDateRange?.start} to {cycleDateRange?.end}
          </div>
          <div style={{ color: C.textMuted, fontSize: 12 }}>
            Total Days in Cycle: {cycleDateRange?.totalDays}
          </div>
        </div>

        <div
          style={{
            display:             "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))",
            gap:                 16,
          }}
        >
          {stats.map((stat, idx) => (
            <div
              key={idx}
              style={{
                padding:         "16px",
                backgroundColor: C.bgDark,
                border:          `1px solid ${C.blue}44`,
                borderRadius:    8,
              }}
            >
              <div style={{ 
                display: "flex", 
                justifyContent: "space-between", 
                alignItems: "center",
                marginBottom: 12 
              }}>
                <div style={{ color: C.blue, fontWeight: 900, fontSize: 16 }}>
                  {stat.day.toUpperCase()}
                </div>
                <Badge color={C.cyan}>{stat.totalDraws} draws</Badge>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                  <span style={{ color: C.textMuted }}>Numbers Added:</span>
                  <span style={{ color: C.green, fontWeight: 700 }}>{stat.totalNumbersAdded}</span>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                  <span style={{ color: C.textMuted }}>Avg/Draw:</span>
                  <span style={{ color: C.yellow, fontWeight: 700 }}>{stat.averagePerDraw}</span>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                  <span style={{ color: C.textMuted }}>Unique Numbers:</span>
                  <span style={{ color: C.purple, fontWeight: 700 }}>
                    {stat.uniqueNumbers.length}
                  </span>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                  <span style={{ color: C.textMuted }}>Dates Covered:</span>
                  <span style={{ color: C.cyan, fontWeight: 700 }}>
                    {stat.dates.length}
                  </span>
                </div>
              </div>

              {/* Missing Dates Section */}
              {stat.missingDates && stat.missingDates.length > 0 && (
                <div style={{ 
                  marginTop: 16, 
                  paddingTop: 16, 
                  borderTop: `1px solid ${C.red}44`,
                  backgroundColor: `${C.red}11`,
                  borderRadius: 6,
                  padding: "12px"
                }}>
                  <div style={{ 
                    color: C.red, 
                    fontWeight: 700, 
                    fontSize: 12, 
                    marginBottom: 8,
                    display: "flex",
                    alignItems: "center",
                    gap: 6
                  }}>
                    ⚠️ {stat.missingDates.length} Missing {stat.missingDates.length === 1 ? 'Date' : 'Dates'}
                  </div>
                  <div style={{ 
                    maxHeight: 150, 
                    overflowY: "auto",
                    fontSize: 11,
                    color: C.orange
                  }}>
                    {stat.missingDates.map((date, i) => (
                      <div key={i} style={{ 
                        padding: "4px 0",
                        borderBottom: i < stat.missingDates.length - 1 ? `1px solid ${C.red}33` : "none"
                      }}>
                        {date}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Sample Numbers */}
              <div style={{ 
                marginTop: 16, 
                paddingTop: 16, 
                borderTop: `1px solid ${C.border}`,
                fontSize: 11
              }}>
                <div style={{ color: C.textMuted, fontSize: 10, marginBottom: 6 }}>
                  Sample Numbers: {stat.uniqueNumbers.slice(0, 5).join(", ")}
                  {stat.uniqueNumbers.length > 5 ? `... +${stat.uniqueNumbers.length - 5}` : ""}
                </div>
                
                <div style={{ 
                  marginTop: 8,
                  fontSize: 10,
                  color: C.textMuted
                }}>
                  First Date: {stat.dates.length > 0 ? stat.dates[0] : "—"}
                  {stat.dates.length > 1 && ` | Last Date: ${stat.dates[stat.dates.length - 1]}`}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

// ============================================================
// SERIAL ANALYSIS TAB - FIXED
// ============================================================
const SerialTab = ({ type, cycleNumber }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedPrefix, setSelectedPrefix] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const result = await fetchSerialData(type, cycleNumber);
        setData(result);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [type, cycleNumber]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBanner message={error} />;
  if (!data || !data.serialStats) return null;

  const stats = data.serialStats;

  return (
    <div>
      <Card title="🎫 SERIAL PREFIX ANALYSIS">
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width:          "100%",
              borderCollapse: "collapse",
              fontFamily:     "monospace",
              fontSize:       12,
            }}
          >
            <thead style={{ backgroundColor: C.bgDark }}>
              <tr>
                {["Prefix", "Serial #", "Count", "Total #", "Avg/Draw", "Unique #"].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding:      "10px 8px",
                      textAlign:    "left",
                      color:        C.textSec,
                      fontWeight:   600,
                      borderBottom: `1px solid ${C.border}`,
                      whiteSpace:   "nowrap",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stats.map((stat, idx) => (
                <tr
                  key={idx}
                  style={{
                    backgroundColor: idx % 2 === 0 ? "#ffffff05" : "transparent",
                    borderBottom:    `1px solid ${C.border}`,
                    cursor:          "pointer",
                  }}
                  onClick={() => setSelectedPrefix(selectedPrefix === stat.prefix ? null : stat.prefix)}
                  onMouseEnter={(e) => e.currentTarget.style.backgroundColor = "#ffffff10"}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = idx % 2 === 0 ? "#ffffff05" : "transparent"}
                >
                  <td style={{ padding: "8px", color: C.yellow, fontWeight: 700 }}>
                    {stat.prefix}
                  </td>
                  <td style={{ padding: "8px", color: C.cyan, fontSize: 11 }}>
                    {stat.serialNumbers.length} serials
                  </td>
                  <td style={{ padding: "8px", color: C.cyan }}>{stat.count}</td>
                  <td style={{ padding: "8px", color: C.green, fontWeight: 700 }}>
                    {stat.totalNumbersAdded}
                  </td>
                  <td style={{ padding: "8px", color: C.purple }}>
                    {stat.averagePerDraw}
                  </td>
                  <td style={{ padding: "8px", color: C.blue }}>{stat.uniqueNumbers.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Detailed View for Selected Prefix */}
        {selectedPrefix && (
          <div style={{ marginTop: 20 }}>
            <Card title={`🔍 DETAILS FOR SERIAL PREFIX: ${selectedPrefix}`}>
              {stats.filter(s => s.prefix === selectedPrefix).map((stat, idx) => (
                <div key={idx}>
                  <div style={{ 
                    display: "flex", 
                    flexWrap: "wrap", 
                    gap: 16, 
                    marginBottom: 16,
                    padding: "12px",
                    backgroundColor: C.bgDark,
                    borderRadius: 6
                  }}>
                    <div><strong>Count:</strong> {stat.count} draws</div>
                    <div><strong>Total Numbers:</strong> {stat.totalNumbersAdded}</div>
                    <div><strong>Avg/Draw:</strong> {stat.averagePerDraw}</div>
                    <div><strong>Unique Numbers:</strong> {stat.uniqueNumbers.length}</div>
                  </div>

                  <div style={{ marginBottom: 16 }}>
                    <h4 style={{ color: C.cyan, marginBottom: 8 }}>📋 Serial Numbers ({stat.serialNumbers.length})</h4>
                    <div style={{ 
                      display: "flex", 
                      flexWrap: "wrap", 
                      gap: 8,
                      maxHeight: 200,
                      overflowY: "auto",
                      padding: "8px",
                      backgroundColor: C.bgDark,
                      borderRadius: 4
                    }}>
                      {stat.serialNumbers.map((serial, i) => (
                        <Badge key={i} color={C.blue} dim={C.blueDim}>
                          {serial}
                        </Badge>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h4 style={{ color: C.green, marginBottom: 8 }}>🎯 Unique Numbers ({stat.uniqueNumbers.length})</h4>
                    <div style={{ 
                      display: "grid", 
                      gridTemplateColumns: "repeat(auto-fill, minmax(80px, 1fr))", 
                      gap: 6,
                      maxHeight: 300,
                      overflowY: "auto",
                      padding: "8px",
                      backgroundColor: C.bgDark,
                      borderRadius: 4
                    }}>
                      {stat.uniqueNumbers.map((num, i) => (
                        <div
                          key={i}
                          style={{
                            padding: "6px",
                            backgroundColor: C.greenDim,
                            border: `1px solid ${C.green}44`,
                            borderRadius: 4,
                            textAlign: "center",
                            fontFamily: "monospace",
                            fontWeight: 700,
                            color: C.green,
                            fontSize: 12,
                          }}
                        >
                          {num}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </Card>
          </div>
        )}
      </Card>
    </div>
  );
};

// ============================================================
// OVERVIEW TAB
// ============================================================
const OverviewTab = ({ cycle }) => {
  return (
    <Card>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <h4 style={{ color: C.green, marginBottom: 12 }}>📋 Cycle Info</h4>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ padding: "10px", backgroundColor: C.bgDark, borderRadius: 6 }}>
              <div style={{ color: C.textMuted, fontSize: 10 }}>Start Date</div>
              <div style={{ color: C.green, fontWeight: 700 }}>
                {cycle.startDisplayDate} ({cycle.start})
              </div>
            </div>
            <div style={{ padding: "100px", backgroundColor: C.bgDark, borderRadius: 6 }}>
              <div style={{ color: C.textMuted, fontSize: 10 }}>End Date</div>
              <div style={{ color: C.yellow, fontWeight: 700 }}>
                {cycle.endDisplayDate} ({cycle.end})
              </div>
            </div>
            <div style={{ padding: "10px", backgroundColor: C.bgDark, borderRadius: 6 }}>
              <div style={{ color: C.textMuted, fontSize: 10 }}>Total Draws</div>
              <div style={{ color: C.cyan, fontSize: 18, fontWeight: 900 }}>
                {cycle.draws}
              </div>
            </div>
          </div>
        </div>

        <div>
          <h4 style={{ color: C.green, marginBottom: 12 }}>📊 Statistics</h4>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ padding: "10px", backgroundColor: C.bgDark, borderRadius: 6 }}>
              <div style={{ color: C.textMuted, fontSize: 10 }}>Avg New / Draw</div>
              <div style={{ color: C.green, fontSize: 18, fontWeight: 900 }}>
                {cycle.avgNewPerDay}
              </div>
            </div>
            <div style={{ padding: "10px", backgroundColor: C.bgDark, borderRadius: 6 }}>
              <div style={{ color: C.textMuted, fontSize: 10 }}>Max New in Draw</div>
              <div style={{ color: C.yellow, fontSize: 18, fontWeight: 900 }}>
                {cycle.maxNewInDraw}
              </div>
            </div>
            <div style={{ padding: "10px", backgroundColor: C.bgDark, borderRadius: 6 }}>
              <div style={{ color: C.textMuted, fontSize: 10 }}>Max Consecutive Zero</div>
              <div style={{ color: C.orange, fontSize: 18, fontWeight: 900 }}>
                {cycle.maxConsecutiveZero || "—"}
              </div>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
};

// ============================================================
// CYCLE DETAIL VIEW
// ============================================================
const CycleDetailView = ({ type, cycleNumber, onBack }) => {
  const [cycle, setCycle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const result = await fetchCycleDetail(type, cycleNumber);
        if (result.success) {
          setCycle(result.cycle);
        } else {
          throw new Error(result.message);
        }
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [type, cycleNumber]);

  if (loading) return <Spinner />;
  if (error)
    return (
      <ErrorBanner
        message={error}
        onRetry={() => window.location.reload()}
      />
    );
  if (!cycle) return null;

  const tabs = [
    { id: "overview", label: "📋 Overview" },
    { id: "weekday", label: "📅 By Weekday" },
    { id: "serial", label: "🎫 By Serial" },
  ];

  return (
    <div>
      {/* Header */}
      <div
        style={{
          display:        "flex",
          justifyContent: "space-between",
          alignItems:     "center",
          marginBottom:   20,
          padding:        "20px",
          backgroundColor: C.bgCard,
          border:         `1px solid ${C.border}`,
          borderRadius:   10,
        }}
      >
        <div>
          <button
            onClick={onBack}
            style={{
              padding:         "6px 12px",
              backgroundColor: C.border,
              border:          "none",
              borderRadius:    4,
              color:           C.textPrimary,
              cursor:          "pointer",
              fontSize:        12,
              fontFamily:      "monospace",
              marginBottom:    8,
            }}
          >
            ← Back to List
          </button>
          <h1
            style={{
              margin:        0,
              color:         C.cyan,
              fontFamily:    "monospace",
              fontWeight:    900,
              fontSize:      24,
              letterSpacing: 2,
            }}
          >
            {type === "forward" ? "FORWARD" : "REVERSE"} CYCLE {cycleNumber}
          </h1>
        </div>

        <Badge
          color={cycle.status === "complete" ? C.green : C.yellow}
          dim={cycle.status === "complete" ? C.greenDim : C.yellowDim}
        >
          {cycle.status === "complete" ? "✅ COMPLETE" : "⏳ PARTIAL"}
        </Badge>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 20, flexWrap: "wrap" }}>
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            style={{
              padding:         "8px 14px",
              borderRadius:    6,
              border:          `1px solid ${activeTab === t.id ? C.cyan : C.border}`,
              backgroundColor: activeTab === t.id ? `${C.cyan}22` : "transparent",
              color:           activeTab === t.id ? C.cyan : C.textSec,
              cursor:          "pointer",
              fontSize:        12,
              fontFamily:      "monospace",
              fontWeight:      600,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {activeTab === "overview" && <OverviewTab cycle={cycle} />}
      {activeTab === "weekday" && <WeekdayTab type={type} cycleNumber={cycleNumber} />}
      {activeTab === "serial" && <SerialTab type={type} cycleNumber={cycleNumber} />}
    </div>
  );
};

// ============================================================
// MAIN PAGE
// ============================================================
export default function ReverseCycles() {
  const [cycleType, setCycleType] = useState("reverse");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCycle, setSelectedCycle] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await fetchCycles(cycleType);
      if (!result.success) throw new Error(result.message);
      setData(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [cycleType]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div
      style={{
        minHeight:      "100vh",
        backgroundColor: C.bg,
        color:          C.textPrimary,
        fontFamily:     "sans-serif",
      }}
    >
      {/* Header */}
      <div
        style={{
          backgroundColor: C.bgCard,
          borderBottom:    `1px solid ${C.border}`,
          padding:         "20px 30px",
          display:         "flex",
          justifyContent:  "space-between",
          alignItems:      "center",
          position:        "sticky",
          top:             0,
          zIndex:          100,
        }}
      >
        <div>
          <h1
            style={{
              margin:        0,
              color:         C.cyan,
              fontFamily:    "monospace",
              fontSize:      22,
              fontWeight:    900,
              letterSpacing: 2,
            }}
          >
            🎰 CYCLE ANALYSIS
          </h1>
          <p
            style={{
              margin:     "6px 0 0",
              color:      C.textMuted,
              fontSize:   11,
              fontFamily: "monospace",
            }}
          >
            {data
              ? `✅ ${data.summary.totalDraws} draws • ${data.summary.dateRange.oldest} → ${data.summary.dateRange.newest}`
              : "Connecting..."}
          </p>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          {["reverse", "forward"].map((type) => (
            <button
              key={type}
              onClick={() => {
                setCycleType(type);
                setSelectedCycle(null);
              }}
              style={{
                padding:         "8px 16px",
                borderRadius:    6,
                border:          `1px solid ${cycleType === type ? C.cyan : C.border}`,
                backgroundColor: cycleType === type ? `${C.cyan}22` : "transparent",
                color:           cycleType === type ? C.cyan : C.textSec,
                cursor:          "pointer",
                fontSize:        12,
                fontFamily:      "monospace",
                fontWeight:      600,
              }}
            >
              {type === "reverse" ? "⬅️ Reverse" : "➡️ Forward"}
            </button>
          ))}

          <button
            onClick={load}
            disabled={loading}
            style={{
              padding:         "8px 14px",
              borderRadius:    6,
              border:          `1px solid ${C.border}`,
              backgroundColor: "transparent",
              color:           loading ? C.textMuted : C.textSec,
              cursor:          loading ? "not-allowed" : "pointer",
              fontFamily:      "monospace",
              fontSize:        12,
            }}
          >
            {loading ? "⟳ Loading..." : "↺ Refresh"}
          </button>
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: "24px 30px", maxWidth: 1600, margin: "0 auto" }}>
        {error && !loading && <ErrorBanner message={error} onRetry={load} />}

        {selectedCycle ? (
          <CycleDetailView
            type={cycleType}
            cycleNumber={selectedCycle}
            onBack={() => setSelectedCycle(null)}
          />
        ) : (
          <>
            {data && <StatsRow summary={data.summary} />}
            <Card title={`🔄 ${cycleType === "forward" ? "FORWARD" : "REVERSE"} CYCLES`}>
              <CyclesList
                cycles={data?.cycles || []}
                onSelectCycle={setSelectedCycle}
                loading={loading}
              />
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

// ============================================================
// STATS ROW (Add this if not already defined)
// ============================================================
const StatsRow = ({ summary }) => {
  const items = [
    { label: "Total Draws", value: summary?.totalDraws?.toLocaleString(), icon: "📋", color: C.cyan },
    { label: "Oldest", value: summary?.dateRange?.oldest, icon: "📅", color: C.yellow },
    { label: "Newest", value: summary?.dateRange?.newest, icon: "📅", color: C.green },
    { label: "Cycles", value: summary?.totalCycles, icon: "🔄", color: C.purple },
    { label: "Complete", value: summary?.completeCycles, icon: "✅", color: C.green },
    { label: "Partial", value: summary?.partialCycles, icon: "⏳", color: C.yellow },
  ];

  return (
    <div
      style={{
        display:             "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
        gap:                 12,
        marginBottom:        20,
      }}
    >
      {items.map((s) => (
        <div
          key={s.label}
          style={{
            backgroundColor: C.bgCard,
            border:          `1px solid ${C.border}`,
            borderRadius:    8,
            padding:         "14px 16px",
            textAlign:       "center",
          }}
        >
          <div style={{ fontSize: 24, marginBottom: 6 }}>{s.icon}</div>
          <div
            style={{
              color:        s.color,
              fontFamily:   "monospace",
              fontWeight:   900,
              fontSize:     16,
              marginBottom: 4,
            }}
          >
            {s.value ?? "—"}
          </div>
          <div style={{ color: C.textMuted, fontSize: 10, fontFamily: "monospace" }}>
            {s.label}
          </div>
        </div>
      ))}
    </div>
  );
};

// ============================================================
// CYCLES LIST (Add this if not already defined)
// ============================================================
const CyclesList = ({ cycles, onSelectCycle, loading }) => {
  if (loading) return <Spinner />;

  return (
    <div>
      {cycles.map((c) => (
        <Card key={c.cycle} style={{ marginBottom: 12, cursor: "pointer" }}>
          <div
            onClick={() => onSelectCycle(c.cycle)}
            style={{
              display:        "flex",
              justifyContent: "space-between",
              alignItems:     "center",
              padding:        "12px 0",
              cursor:         "pointer",
              transition:     "all 0.2s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.8")}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
          >
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
                <span
                  style={{
                    color:      C.cyan,
                    fontFamily: "monospace",
                    fontWeight: 900,
                    fontSize:   18,
                  }}
                >
                  CYCLE {c.cycle}
                </span>
                <Badge
                  color={c.status === "complete" ? C.green : C.yellow}
                  dim={c.status === "complete" ? C.greenDim : C.yellowDim}
                >
                  {c.status === "complete" ? "✅ COMPLETE" : "⏳ PARTIAL"}
                </Badge>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 16, fontSize: 12, color: C.textSec }}>
                <span>📅 {c.start} → {c.end}</span>
                <span>📊 {c.draws} draws</span>
                <span>⚡ {c.avgNewPerDay} avg/draw</span>
                {c.seenPct && (
                  <span>
                    👁 {c.seenCount}/10000 ({c.seenPct}%)
                  </span>
                )}
              </div>
            </div>
            <div style={{ fontSize: 24 }}>→</div>
          </div>
        </Card>
      ))}
    </div>
  );
};