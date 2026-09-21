import React, { useState, useEffect } from "react";
import axios from "axios";

const METHODS = [
  {
    key: "gap_based",
    name: "Gap-Based",
    weight: "20%",
    desc: "Overdue analysis",
    color: "#3b82f6",
    phase: 1,
  },
  {
    key: "frequency",
    name: "Frequency",
    weight: "15%",
    desc: "Hit rate & tier weights",
    color: "#10b981",
    phase: 1,
  },
  {
    key: "hot_streak",
    name: "Hot Streak",
    weight: "15%",
    desc: "6-month momentum",
    color: "#f59e0b",
    phase: 1,
  },
  {
    key: "tier_progression",
    name: "Tier Prog.",
    weight: "15%",
    desc: "100→5000 pattern",
    color: "#8b5cf6",
    phase: 1,
  },
  {
    key: "seasonality",
    name: "Seasonality",
    weight: "10%",
    desc: "Day/Month frequency",
    color: "#ec4899",
    phase: 1,
  },
  {
    key: "markov_chain",
    name: "Markov",
    weight: "15%",
    desc: "Tier transition probability",
    color: "#06b6d4",
    phase: 2,
  },
  {
    key: "moving_average",
    name: "Moving Avg",
    weight: "10%",
    desc: "Weighted 7/30/90-day rate",
    color: "#f97316",
    phase: 2,
  },
];

const scoreColor = (s) =>
  s >= 80
    ? { bg: "#d1fae5", text: "#065f46" }
    : s >= 65
      ? { bg: "#fef3c7", text: "#92400e" }
      : s >= 50
        ? { bg: "#fed7aa", text: "#9a3412" }
        : { bg: "#f1f5f9", text: "#475569" };

const recColor = (r = "") =>
  r.startsWith("STRONG BUY")
    ? { bg: "#fee2e2", text: "#dc2626" }
    : r.startsWith("BUY")
      ? { bg: "#fed7aa", text: "#ea580c" }
      : r.startsWith("CONSIDER")
        ? { bg: "#fef3c7", text: "#d97706" }
        : r.startsWith("WATCH")
          ? { bg: "#e0e7ff", text: "#4338ca" }
          : { bg: "#f1f5f9", text: "#64748b" };

export default function PredictionAnalysis() {
  const [predictions, setPredictions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("top_50");

  const fetchPredictions = async () => {
    setLoading(true);
    try {
      const res = await axios.get("http://localhost:5000/api/predictions");
      setPredictions(res.data);
    } catch (err) {
      console.error(err);
      alert("Failed to load predictions. Make sure the backend is running.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPredictions();
  }, []);

  if (loading)
    return (
      <Wrap>
        <div style={{ textAlign: "center", paddingTop: 100 }}>
          <div style={{ fontSize: 64, marginBottom: 16 }}>🔄</div>
          <h2 style={{ fontSize: 26, fontWeight: "bold", color: "#1e293b" }}>
            Running 7 Methods…
          </h2>
          <p style={{ color: "#64748b", marginTop: 8 }}>
            Phase 2 · Markov Chain &amp; Moving Average active
          </p>
        </div>
      </Wrap>
    );

  if (!predictions)
    return (
      <Wrap>
        <div style={{ textAlign: "center", paddingTop: 100 }}>
          <div style={{ fontSize: 64, marginBottom: 16 }}>⚠️</div>
          <h2 style={{ fontSize: 26, fontWeight: "bold", color: "#1e293b" }}>
            No Data
          </h2>
          <p style={{ color: "#64748b", marginTop: 8 }}>
            Check backend at localhost:5000
          </p>
          <Btn onClick={fetchPredictions} style={{ marginTop: 20 }}>
            Retry
          </Btn>
        </div>
      </Wrap>
    );

  const stats = predictions.statistics || {};
  const cats = predictions.categories || {};

  const TABS = [
    { key: "top_50", label: "🏆 Top 50" },
    {
      key: "strong_buy",
      label: `🔥 Strong Buy (${cats.strong_buy?.length ?? 0})`,
    },
    { key: "buy", label: `✅ Buy (${cats.buy?.length ?? 0})` },
    { key: "overdue", label: `⏰ Overdue (${cats.overdue?.length ?? 0})` },
    {
      key: "hot_streak",
      label: `⚡ Hot Streak (${cats.hot_streak?.length ?? 0})`,
    },
    {
      key: "high_tier_potential",
      label: `👑 High Tier (${cats.high_tier_potential?.length ?? 0})`,
    },
    {
      key: "markov_top",
      label: `🔗 Markov (${cats.markov_top?.length ?? 0})`,
      p2: true,
    },
    {
      key: "ma_momentum",
      label: `📈 MA (${cats.ma_momentum?.length ?? 0})`,
      p2: true,
    },
  ];

  const rows = cats[activeTab] || [];

  return (
    <Wrap>
      {/* ── Header ── */}
      <div style={{ textAlign: "center", marginBottom: 26 }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            justifyContent: "center",
          }}
        >
          <h1
            style={{
              fontSize: 36,
              fontWeight: "bold",
              margin: 0,
              background: "linear-gradient(135deg,#667eea,#764ba2)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Multi-Method Prediction Analysis
          </h1>
          <span
            style={{
              background: "linear-gradient(135deg,#f59e0b,#f97316)",
              color: "white",
              fontSize: 11,
              fontWeight: 800,
              padding: "4px 12px",
              borderRadius: 20,
            }}
          >
            PHASE 2
          </span>
        </div>
        <p style={{ color: "#64748b", fontSize: 16, margin: "10px 0 14px" }}>
          7 AI-Powered Methods · Markov Chain &amp; Moving Average Added
        </p>
        <Btn onClick={fetchPredictions} disabled={loading}>
          {loading ? "Analyzing…" : "🔄 Refresh Predictions"}
        </Btn>
      </div>

      {/* ── Methods grid ── */}
      <Card style={{ marginBottom: 18 }}>
        <H3>Active Prediction Methods</H3>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(148px, 1fr))",
            gap: 10,
          }}
        >
          {METHODS.map((m) => (
            <div
              key={m.key}
              style={{
                background: `${m.color}10`,
                borderRadius: 9,
                borderLeft: `4px solid ${m.color}`,
                padding: "13px 12px",
                position: "relative",
              }}
            >
              {m.phase === 2 && (
                <span
                  style={{
                    position: "absolute",
                    top: 6,
                    right: 6,
                    fontSize: 9,
                    fontWeight: 800,
                    padding: "2px 5px",
                    borderRadius: 5,
                    background: "#fef3c7",
                    color: "#b45309",
                  }}
                >
                  NEW
                </span>
              )}
              <div style={{ fontSize: 12, fontWeight: 700, color: m.color }}>
                {m.name}
              </div>
              <div
                style={{
                  fontSize: 21,
                  fontWeight: "bold",
                  color: m.color,
                  margin: "2px 0",
                }}
              >
                {m.weight}
              </div>
              <div style={{ fontSize: 10, color: m.color, opacity: 0.8 }}>
                {m.desc}
              </div>
            </div>
          ))}
        </div>

        {/* Phase 2 explainer */}
        <div
          style={{
            marginTop: 14,
            padding: "12px 16px",
            borderRadius: 9,
            background: "#fef9c3",
            border: "1px solid #fde68a",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 14,
          }}
        >
          <p style={{ margin: 0, fontSize: 12, color: "#78350f" }}>
            <strong style={{ color: "#06b6d4" }}>🔗 Markov Chain:</strong>{" "}
            Builds a prize-tier transition matrix from every number's history.
            Scores how likely a number transitions to ₹1000+ next, given its
            last prize tier. An escalating personal trajectory adds a bonus.
          </p>
          <p style={{ margin: 0, fontSize: 12, color: "#78350f" }}>
            <strong style={{ color: "#f97316" }}>📈 Moving Average:</strong>{" "}
            Weighted appearance rate across 7-day (×0.5), 30-day (×0.3) and
            90-day (×0.2) windows. Catches numbers whose frequency is
            accelerating before the hot-streak method catches up.
          </p>
        </div>
      </Card>

      {/* ── Stat cards ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: 12,
          marginBottom: 18,
        }}
      >
        {[
          {
            label: "Analyzed",
            value: stats.total_analyzed ?? 0,
            color: "#667eea",
          },
          { label: "Avg Score", value: stats.avg_score ?? 0, color: "#f59e0b" },
          {
            label: "Strong Buy",
            value: stats.strong_buy_count ?? 0,
            color: "#10b981",
          },
          { label: "Buy", value: stats.buy_count ?? 0, color: "#f97316" },
          {
            label: "Overdue",
            value: stats.overdue_count ?? 0,
            color: "#ef4444",
          },
          { label: "Hot", value: stats.hot_count ?? 0, color: "#8b5cf6" },
          {
            label: "🔗 Markov≥70",
            value: stats.markov_signals ?? 0,
            color: "#06b6d4",
          },
          { label: "📈 MA≥70", value: stats.ma_signals ?? 0, color: "#f97316" },
        ].map((s) => (
          <div
            key={s.label}
            style={{
              background: `linear-gradient(135deg,${s.color},${s.color}cc)`,
              color: "white",
              borderRadius: 11,
              padding: "16px 14px",
              boxShadow: "0 3px 10px rgba(0,0,0,0.1)",
            }}
          >
            <div style={{ fontSize: 11, opacity: 0.9, marginBottom: 3 }}>
              {s.label}
            </div>
            <div style={{ fontSize: 24, fontWeight: "bold" }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* ── Tabs ── */}
      <div
        style={{
          display: "flex",
          gap: 6,
          overflowX: "auto",
          background: "white",
          padding: 7,
          borderRadius: 11,
          boxShadow: "0 2px 8px rgba(0,0,0,0.07)",
          marginBottom: 16,
        }}
      >
        {TABS.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: "9px 13px",
                borderRadius: 7,
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                whiteSpace: "nowrap",
                transition: "all 0.2s",
                border: tab.p2 ? "1.5px dashed #fdba74" : "none",
                backgroundColor: active
                  ? tab.p2
                    ? "#f97316"
                    : "#667eea"
                  : "transparent",
                color: active ? "white" : "#64748b",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ── Table ── */}
      <Card style={{ padding: 0, overflow: "hidden", marginBottom: 18 }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr
                style={{
                  background: "linear-gradient(135deg,#667eea,#764ba2)",
                  color: "white",
                }}
              >
                {[
                  { h: "Rank" },
                  { h: "Number" },
                  { h: "Final" },
                  ...METHODS.map((m) => ({
                    h: m.name.split(" ")[0],
                    p2: m.phase === 2,
                  })),
                  { h: "Days" },
                  { h: "Overdue" },
                  { h: "₹5K" },
                  { h: "₹1K" },
                  { h: "Last ₹" },
                  { h: "Signal" },
                ].map((col, i) => (
                  <th
                    key={i}
                    style={{
                      padding: "12px 8px",
                      textAlign: i < 2 ? "left" : "center",
                      fontSize: 11,
                      fontWeight: 700,
                      whiteSpace: "nowrap",
                      backgroundColor: col.p2
                        ? "rgba(255,255,255,0.18)"
                        : undefined,
                    }}
                  >
                    {col.p2 ? `✦ ${col.h}` : col.h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((pred, idx) => {
                const sc = scoreColor(pred.finalScore);
                const rc = recColor(pred.recommendation);
                return (
                  <tr
                    key={pred.number}
                    style={{
                      backgroundColor: idx % 2 === 0 ? "white" : "#f8fafc",
                      borderBottom: "1px solid #e2e8f0",
                    }}
                  >
                    {/* Rank */}
                    <td
                      style={{
                        padding: "9px 8px",
                        fontWeight: "bold",
                        color: "#94a3b8",
                        fontSize: 12,
                      }}
                    >
                      #{idx + 1}
                    </td>
                    {/* Number */}
                    <td style={{ padding: "9px 8px" }}>
                      <span
                        style={{
                          fontFamily: "monospace",
                          fontSize: 16,
                          fontWeight: "bold",
                          color: "#667eea",
                        }}
                      >
                        {pred.number}
                      </span>
                    </td>
                    {/* Final */}
                    <td style={{ padding: "9px 8px", textAlign: "center" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "3px 9px",
                          borderRadius: 18,
                          fontWeight: "bold",
                          fontSize: 13,
                          backgroundColor: sc.bg,
                          color: sc.text,
                        }}
                      >
                        {pred.finalScore}
                      </span>
                    </td>
                    {/* 7 method scores */}
                    {METHODS.map((m) => {
                      const v = pred.scores?.[m.key] ?? 0;
                      const hi = v >= 70;
                      return (
                        <td
                          key={m.key}
                          style={{
                            padding: "9px 8px",
                            textAlign: "center",
                            fontWeight: 700,
                            fontSize: 12,
                            backgroundColor:
                              m.phase === 2 && hi ? `${m.color}18` : undefined,
                            color: hi ? m.color : "#94a3b8",
                          }}
                        >
                          {v}
                        </td>
                      );
                    })}
                    {/* Days since */}
                    <td
                      style={{
                        padding: "9px 8px",
                        textAlign: "center",
                        fontWeight: 600,
                        color: "#1e293b",
                        fontSize: 12,
                      }}
                    >
                      {pred.days_since_last}d
                    </td>
                    {/* Overdue */}
                    <td
                      style={{
                        padding: "9px 8px",
                        textAlign: "center",
                        fontWeight: "bold",
                        fontSize: 12,
                        color:
                          pred.overdue_ratio >= 1.5 ? "#ef4444" : "#64748b",
                      }}
                    >
                      {(pred.overdue_ratio ?? 0).toFixed(2)}x
                    </td>
                    {/* ₹5K count */}
                    <td
                      style={{
                        padding: "9px 8px",
                        textAlign: "center",
                        fontWeight: "bold",
                        color: "#f59e0b",
                      }}
                    >
                      {pred.tierCounts?.[5000] ?? 0}
                    </td>
                    {/* ₹1K count */}
                    <td
                      style={{
                        padding: "9px 8px",
                        textAlign: "center",
                        fontWeight: "bold",
                        color: "#10b981",
                      }}
                    >
                      {pred.tierCounts?.[1000] ?? 0}
                    </td>
                    {/* Last prize */}
                    <td style={{ padding: "9px 8px", textAlign: "center" }}>
                      <span
                        style={{
                          fontSize: 10,
                          padding: "2px 7px",
                          borderRadius: 9,
                          fontWeight: 700,
                          backgroundColor:
                            pred.last_prize >= 5000
                              ? "#d1fae5"
                              : pred.last_prize >= 1000
                                ? "#fef3c7"
                                : pred.last_prize >= 500
                                  ? "#fed7aa"
                                  : "#f1f5f9",
                          color:
                            pred.last_prize >= 5000
                              ? "#065f46"
                              : pred.last_prize >= 1000
                                ? "#92400e"
                                : pred.last_prize >= 500
                                  ? "#9a3412"
                                  : "#475569",
                        }}
                      >
                        ₹{pred.last_prize ?? "—"}
                      </span>
                    </td>
                    {/* Signal */}
                    <td style={{ padding: "9px 8px" }}>
                      <span
                        style={{
                          fontSize: 10,
                          padding: "3px 8px",
                          borderRadius: 10,
                          fontWeight: "bold",
                          backgroundColor: rc.bg,
                          color: rc.text,
                        }}
                      >
                        {pred.recommendation?.split(" - ")[0] ?? "N/A"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ── Legend ── */}
      <Card>
        <H3>📖 Score Guide</H3>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 24,
          }}
        >
          <div>
            <strong style={{ color: "#1e293b", fontSize: 13 }}>
              Final Score (0–100)
            </strong>
            {[
              ["80–100", "Excellent opportunity", "#10b981"],
              ["65–79", "Good potential", "#f59e0b"],
              ["50–64", "Monitor closely", "#f97316"],
              ["0–49", "Low priority", "#94a3b8"],
            ].map(([r, l, c]) => (
              <div
                key={r}
                style={{
                  display: "flex",
                  gap: 8,
                  marginTop: 6,
                  alignItems: "center",
                }}
              >
                <span
                  style={{
                    color: c,
                    fontWeight: 700,
                    minWidth: 56,
                    fontSize: 12,
                  }}
                >
                  {r}
                </span>
                <span style={{ color: "#64748b", fontSize: 12 }}>{l}</span>
              </div>
            ))}
          </div>

          <div>
            <strong style={{ color: "#1e293b", fontSize: 13 }}>
              Phase 1 Methods
            </strong>
            {METHODS.filter((m) => m.phase === 1).map((m) => (
              <div
                key={m.key}
                style={{ display: "flex", gap: 8, marginTop: 6 }}
              >
                <span
                  style={{
                    color: m.color,
                    fontWeight: 700,
                    minWidth: 78,
                    fontSize: 12,
                  }}
                >
                  {m.name}
                </span>
                <span style={{ color: "#64748b", fontSize: 11 }}>
                  {m.desc} · {m.weight}
                </span>
              </div>
            ))}
          </div>

          <div>
            <strong style={{ color: "#1e293b", fontSize: 13 }}>
              Phase 2 Methods (NEW)
            </strong>
            {METHODS.filter((m) => m.phase === 2).map((m) => (
              <div
                key={m.key}
                style={{ display: "flex", gap: 8, marginTop: 6 }}
              >
                <span
                  style={{
                    color: m.color,
                    fontWeight: 700,
                    minWidth: 90,
                    fontSize: 12,
                  }}
                >
                  {m.name}
                </span>
                <span style={{ color: "#64748b", fontSize: 11 }}>
                  {m.desc} · {m.weight}
                </span>
              </div>
            ))}
            <div
              style={{
                marginTop: 12,
                padding: "8px 11px",
                borderRadius: 8,
                background: "#fef3c7",
                fontSize: 11,
                color: "#92400e",
              }}
            >
              💡 Phase 3: <strong>Bayesian inference</strong> +{" "}
              <strong>K-Means clustering</strong>
            </div>
          </div>
        </div>
      </Card>
    </Wrap>
  );
}

// ── helpers ──────────────────────────────────────────────────────
const Wrap = ({ children }) => (
  <div
    style={{
      width: "100%",
      maxWidth: 1600,
      margin: "0 auto",
      padding: "18px 14px",
      backgroundColor: "#f8fafc",
      minHeight: "100vh",
    }}
  >
    {children}
  </div>
);
const Card = ({ children, style }) => (
  <div
    style={{
      backgroundColor: "white",
      borderRadius: 11,
      boxShadow: "0 2px 8px rgba(0,0,0,0.07)",
      padding: 20,
      ...style,
    }}
  >
    {children}
  </div>
);
const H3 = ({ children }) => (
  <h3
    style={{
      fontSize: 16,
      fontWeight: "bold",
      color: "#1e293b",
      marginTop: 0,
      marginBottom: 14,
    }}
  >
    {children}
  </h3>
);
const Btn = ({ children, onClick, disabled, style }) => (
  <button
    onClick={onClick}
    disabled={disabled}
    style={{
      padding: "10px 22px",
      backgroundColor: disabled ? "#cbd5e1" : "#667eea",
      color: "white",
      border: "none",
      borderRadius: 8,
      fontSize: 14,
      fontWeight: 600,
      cursor: disabled ? "not-allowed" : "pointer",
      ...style,
    }}
  >
    {children}
  </button>
);
