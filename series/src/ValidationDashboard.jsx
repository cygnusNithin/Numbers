import React, { useState, useEffect } from "react";
import axios from "axios";

const METHOD_META = {
  gap_based: { name: "Gap-Based", color: "#3b82f6" },
  frequency: { name: "Frequency", color: "#10b981" },
  hot_streak: { name: "Hot Streak", color: "#f59e0b" },
  tier_progression: { name: "Tier Prog.", color: "#8b5cf6" },
  seasonality: { name: "Seasonality", color: "#ec4899" },
  markov_chain: { name: "Markov", color: "#06b6d4" },
  moving_average: { name: "Moving Avg", color: "#f97316" },
};

const PRIZE_COLORS = {
  5000: { bg: "#d1fae5", text: "#065f46" },
  2000: { bg: "#e0e7ff", text: "#3730a3" },
  1000: { bg: "#fef3c7", text: "#92400e" },
  500: { bg: "#fed7aa", text: "#9a3412" },
  200: { bg: "#fce7f3", text: "#9d174d" },
  100: { bg: "#f1f5f9", text: "#475569" },
};

export default function ValidationDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeDay, setActiveDay] = useState(0);
  const [activeView, setActiveView] = useState("overview");

  const fetchValidation = async () => {
    setLoading(true);
    try {
      const res = await axios.get("http://localhost:5000/api/validate");
      setData(res.data);
    } catch (err) {
      console.error(err);
      alert("Validation failed. Check backend is running.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchValidation();
  }, []);

  if (loading)
    return (
      <Wrap>
        <div style={{ textAlign: "center", paddingTop: 100 }}>
          <div style={{ fontSize: 64, marginBottom: 16 }}>🔍</div>
          <h2 style={{ fontSize: 26, fontWeight: "bold", color: "#1e293b" }}>
            Validating Predictions…
          </h2>
          <p style={{ color: "#64748b", marginTop: 8 }}>
            Comparing CSV predictions vs MongoDB new draws
          </p>
        </div>
      </Wrap>
    );

  if (!data)
    return (
      <Wrap>
        <div style={{ textAlign: "center", paddingTop: 100 }}>
          <div style={{ fontSize: 64, marginBottom: 16 }}>⚠️</div>
          <h2 style={{ fontSize: 26, fontWeight: "bold", color: "#1e293b" }}>
            No Validation Data
          </h2>
          <p style={{ color: "#64748b", marginTop: 8 }}>
            No new draws found after 23/02/2026, or backend error
          </p>
          <Btn onClick={fetchValidation} style={{ marginTop: 20 }}>
            Retry
          </Btn>
        </div>
      </Wrap>
    );

  if (data.validation === null)
    return (
      <Wrap>
        <div style={{ textAlign: "center", paddingTop: 100 }}>
          <div style={{ fontSize: 64, marginBottom: 16 }}>📭</div>
          <h2 style={{ fontSize: 26, fontWeight: "bold", color: "#1e293b" }}>
            No New Draws Yet
          </h2>
          <p style={{ color: "#64748b", marginTop: 8 }}>{data.message}</p>
        </div>
      </Wrap>
    );

  const {
    summary,
    per_day,
    prediction_set_sizes,
    new_draw_dates,
    total_new_draws,
  } = data;
  const dayData = per_day[activeDay];

  const VIEWS = [
    { key: "overview", label: "📊 Overview" },
    { key: "per_day", label: "📅 Per Day" },
    { key: "methods", label: "🔬 Method Battle" },
    { key: "hits", label: "🎯 Hit Details" },
  ];

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
              background: "linear-gradient(135deg,#10b981,#3b82f6)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Prediction Validation
          </h1>
          <span
            style={{
              background: "linear-gradient(135deg,#10b981,#059669)",
              color: "white",
              fontSize: 11,
              fontWeight: 800,
              padding: "4px 12px",
              borderRadius: 20,
            }}
          >
            LIVE CHECK
          </span>
        </div>
        <p style={{ color: "#64748b", fontSize: 15, margin: "10px 0 6px" }}>
          CSV predictions (up to 23/02/2026) vs actual MongoDB draws
        </p>
        <p style={{ color: "#94a3b8", fontSize: 13, margin: "0 0 14px" }}>
          Checking {total_new_draws} new draw{total_new_draws > 1 ? "s" : ""}:{" "}
          {new_draw_dates.join(" · ")}
        </p>
        <Btn onClick={fetchValidation} disabled={loading}>
          🔄 Refresh
        </Btn>
      </div>

      {/* ── Big accuracy cards ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: 14,
          marginBottom: 22,
        }}
      >
        {[
          {
            label: "Top 50 Hit Rate",
            value: `${summary.avg_top50_hit_rate}%`,
            color: "#667eea",
            sub: `avg across ${total_new_draws} draw${total_new_draws > 1 ? "s" : ""}`,
          },
          {
            label: "Strong Buy Hit Rate",
            value: `${summary.avg_strong_buy_rate}%`,
            color: "#10b981",
            sub: `${prediction_set_sizes.strong_buy} predictions`,
          },
          {
            label: "Buy Hit Rate",
            value: `${summary.avg_buy_rate}%`,
            color: "#f59e0b",
            sub: `${prediction_set_sizes.buy} predictions`,
          },
          {
            label: "Best Method",
            value:
              METHOD_META[summary.best_method]?.name ?? summary.best_method,
            color: "#06b6d4",
            sub: `${summary.best_method_hit_rate}% hit rate`,
          },
          {
            label: "Consistent Hits",
            value: summary.consistent_hits?.length ?? 0,
            color: "#8b5cf6",
            sub: "hit in every new draw",
          },
          {
            label: "New Draws Checked",
            value: total_new_draws,
            color: "#f97316",
            sub: new_draw_dates[new_draw_dates.length - 1],
          },
        ].map((card) => (
          <div
            key={card.label}
            style={{
              background: `linear-gradient(135deg,${card.color},${card.color}cc)`,
              color: "white",
              borderRadius: 12,
              padding: "18px 16px",
              boxShadow: "0 3px 12px rgba(0,0,0,0.12)",
            }}
          >
            <div style={{ fontSize: 11, opacity: 0.85, marginBottom: 4 }}>
              {card.label}
            </div>
            <div style={{ fontSize: 26, fontWeight: "bold", marginBottom: 4 }}>
              {card.value}
            </div>
            <div style={{ fontSize: 10, opacity: 0.75 }}>{card.sub}</div>
          </div>
        ))}
      </div>

      {/* ── View tabs ── */}
      <div
        style={{
          display: "flex",
          gap: 6,
          background: "white",
          padding: 7,
          borderRadius: 11,
          boxShadow: "0 2px 8px rgba(0,0,0,0.07)",
          marginBottom: 16,
        }}
      >
        {VIEWS.map((v) => (
          <button
            key={v.key}
            onClick={() => setActiveView(v.key)}
            style={{
              padding: "9px 16px",
              borderRadius: 7,
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              border: "none",
              transition: "all 0.2s",
              backgroundColor: activeView === v.key ? "#667eea" : "transparent",
              color: activeView === v.key ? "white" : "#64748b",
            }}
          >
            {v.label}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════════════════════════
          VIEW: OVERVIEW
      ══════════════════════════════════════════════════════════ */}
      {activeView === "overview" && (
        <>
          {/* Category accuracy bar chart */}
          <Card style={{ marginBottom: 16 }}>
            <H3>📊 Category Hit Rates (avg across all new draws)</H3>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {[
                {
                  label: "Top 50",
                  rate: summary.avg_top50_hit_rate,
                  color: "#667eea",
                  size: prediction_set_sizes.top_50,
                },
                {
                  label: "Strong Buy",
                  rate: summary.avg_strong_buy_rate,
                  color: "#10b981",
                  size: prediction_set_sizes.strong_buy,
                },
                {
                  label: "Buy",
                  rate: summary.avg_buy_rate,
                  color: "#f59e0b",
                  size: prediction_set_sizes.buy,
                },
              ].map((cat) => (
                <div key={cat.label}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginBottom: 5,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: "#1e293b",
                      }}
                    >
                      {cat.label}{" "}
                      <span
                        style={{
                          fontWeight: 400,
                          color: "#94a3b8",
                          fontSize: 11,
                        }}
                      >
                        ({cat.size} numbers)
                      </span>
                    </span>
                    <span
                      style={{
                        fontSize: 14,
                        fontWeight: "bold",
                        color: cat.color,
                      }}
                    >
                      {cat.rate}%
                    </span>
                  </div>
                  <div
                    style={{
                      height: 10,
                      backgroundColor: "#f1f5f9",
                      borderRadius: 99,
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        width: `${Math.min(cat.rate, 100)}%`,
                        background: `linear-gradient(90deg,${cat.color},${cat.color}99)`,
                        borderRadius: 99,
                        transition: "width 0.6s ease",
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Consistent hits across all days */}
          {summary.consistent_hits?.length > 0 && (
            <Card style={{ marginBottom: 16 }}>
              <H3>⭐ Numbers that Hit in Every New Draw</H3>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {summary.consistent_hits.map((h) => (
                  <div
                    key={h.number}
                    style={{
                      background: "linear-gradient(135deg,#10b981,#059669)",
                      color: "white",
                      borderRadius: 10,
                      padding: "8px 14px",
                      textAlign: "center",
                    }}
                  >
                    <div
                      style={{
                        fontSize: 18,
                        fontWeight: "bold",
                        fontFamily: "monospace",
                      }}
                    >
                      {h.number}
                    </div>
                    <div style={{ fontSize: 10, opacity: 0.85 }}>
                      Rank #{h.rank} · Score {h.finalScore}
                    </div>
                    <div style={{ fontSize: 10, opacity: 0.85 }}>
                      {h.hit_count}/{total_new_draws} draws
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Method performance overview */}
          <Card>
            <H3>🔬 Method Hit Rates (Top 30 vs actual draws)</H3>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                gap: 10,
              }}
            >
              {Object.entries(summary.method_avg_hit_rates)
                .sort((a, b) => b[1] - a[1])
                .map(([method, rate], rank) => {
                  const m = METHOD_META[method];
                  const isBest = method === summary.best_method;
                  return (
                    <div
                      key={method}
                      style={{
                        background: isBest ? `${m.color}18` : "#f8fafc",
                        borderRadius: 10,
                        padding: "14px 14px",
                        border: isBest
                          ? `2px solid ${m.color}`
                          : "2px solid transparent",
                        position: "relative",
                      }}
                    >
                      {isBest && (
                        <span
                          style={{
                            position: "absolute",
                            top: -8,
                            right: 8,
                            background: m.color,
                            color: "white",
                            fontSize: 9,
                            fontWeight: 800,
                            padding: "2px 7px",
                            borderRadius: 8,
                          }}
                        >
                          🏆 BEST
                        </span>
                      )}
                      <div
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          color: m.color,
                          marginBottom: 2,
                        }}
                      >
                        #{rank + 1} {m.name}
                      </div>
                      <div
                        style={{
                          fontSize: 28,
                          fontWeight: "bold",
                          color: m.color,
                        }}
                      >
                        {rate}%
                      </div>
                      <div style={{ fontSize: 10, color: "#94a3b8" }}>
                        avg hit rate
                      </div>
                      <div
                        style={{
                          height: 5,
                          backgroundColor: "#e2e8f0",
                          borderRadius: 99,
                          marginTop: 8,
                        }}
                      >
                        <div
                          style={{
                            height: "100%",
                            width: `${Math.min(rate, 100)}%`,
                            backgroundColor: m.color,
                            borderRadius: 99,
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
            </div>
          </Card>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════
          VIEW: PER DAY
      ══════════════════════════════════════════════════════════ */}
      {activeView === "per_day" && (
        <>
          {/* Day selector */}
          {per_day.length > 1 && (
            <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
              {per_day.map((d, i) => (
                <button
                  key={d.date}
                  onClick={() => setActiveDay(i)}
                  style={{
                    padding: "8px 16px",
                    borderRadius: 8,
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                    border: "none",
                    backgroundColor: activeDay === i ? "#667eea" : "white",
                    color: activeDay === i ? "white" : "#64748b",
                    boxShadow: "0 2px 6px rgba(0,0,0,0.07)",
                  }}
                >
                  {d.date}
                </button>
              ))}
            </div>
          )}

          {/* Day summary cards */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
              gap: 12,
              marginBottom: 16,
            }}
          >
            {[
              {
                label: "Total Drawn",
                value: dayData.total_numbers_drawn,
                color: "#667eea",
              },
              {
                label: "Top 50 Hits",
                value: `${dayData.hits.top_50.count} (${dayData.hits.top_50.rate}%)`,
                color: "#10b981",
              },
              {
                label: "Strong Buy Hits",
                value: `${dayData.hits.strong_buy.count} (${dayData.hits.strong_buy.rate}%)`,
                color: "#f59e0b",
              },
              {
                label: "Buy Hits",
                value: `${dayData.hits.buy.count} (${dayData.hits.buy.rate}%)`,
                color: "#f97316",
              },
              {
                label: "Top 100 Hits",
                value: `${dayData.hits.top_100.count} (${dayData.hits.top_100.rate}%)`,
                color: "#8b5cf6",
              },
              {
                label: "Missed",
                value: dayData.missed_numbers,
                color: "#ef4444",
              },
            ].map((s) => (
              <div
                key={s.label}
                style={{
                  background: `linear-gradient(135deg,${s.color},${s.color}cc)`,
                  color: "white",
                  borderRadius: 11,
                  padding: "15px 14px",
                }}
              >
                <div style={{ fontSize: 11, opacity: 0.85, marginBottom: 3 }}>
                  {s.label}
                </div>
                <div style={{ fontSize: 20, fontWeight: "bold" }}>
                  {s.value}
                </div>
              </div>
            ))}
          </div>

          {/* Hit detail table for this day */}
          <Card style={{ padding: 0, overflow: "hidden" }}>
            <div
              style={{
                padding: "16px 20px",
                borderBottom: "1px solid #e2e8f0",
              }}
            >
              <H3>🎯 Top-50 Numbers That Hit on {dayData.date}</H3>
            </div>
            {dayData.top50_hit_details.length === 0 ? (
              <div
                style={{ padding: 24, textAlign: "center", color: "#94a3b8" }}
              >
                No Top-50 numbers appeared in this draw
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ backgroundColor: "#f8fafc" }}>
                      {[
                        "Predicted Rank",
                        "Number",
                        "Final Score",
                        "Signal",
                        "Actual Prize Won",
                      ].map((h, i) => (
                        <th
                          key={i}
                          style={{
                            padding: "10px 14px",
                            textAlign: i === 0 ? "left" : "center",
                            fontSize: 12,
                            fontWeight: 700,
                            color: "#64748b",
                            borderBottom: "1px solid #e2e8f0",
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {dayData.top50_hit_details.map((hit, idx) => {
                      const pc =
                        PRIZE_COLORS[hit.actual_prize] || PRIZE_COLORS[100];
                      return (
                        <tr
                          key={hit.number}
                          style={{
                            backgroundColor:
                              idx % 2 === 0 ? "white" : "#f8fafc",
                            borderBottom: "1px solid #e2e8f0",
                          }}
                        >
                          <td
                            style={{
                              padding: "10px 14px",
                              fontWeight: "bold",
                              color: "#667eea",
                            }}
                          >
                            #{hit.rank}
                          </td>
                          <td
                            style={{
                              padding: "10px 14px",
                              textAlign: "center",
                            }}
                          >
                            <span
                              style={{
                                fontFamily: "monospace",
                                fontSize: 16,
                                fontWeight: "bold",
                                color: "#1e293b",
                              }}
                            >
                              {hit.number}
                            </span>
                          </td>
                          <td
                            style={{
                              padding: "10px 14px",
                              textAlign: "center",
                            }}
                          >
                            <span
                              style={{
                                padding: "3px 10px",
                                borderRadius: 18,
                                fontSize: 13,
                                fontWeight: "bold",
                                backgroundColor:
                                  hit.finalScore >= 80
                                    ? "#d1fae5"
                                    : hit.finalScore >= 65
                                      ? "#fef3c7"
                                      : "#fed7aa",
                                color:
                                  hit.finalScore >= 80
                                    ? "#065f46"
                                    : hit.finalScore >= 65
                                      ? "#92400e"
                                      : "#9a3412",
                              }}
                            >
                              {hit.finalScore}
                            </span>
                          </td>
                          <td
                            style={{
                              padding: "10px 14px",
                              textAlign: "center",
                            }}
                          >
                            <span
                              style={{
                                fontSize: 11,
                                padding: "3px 9px",
                                borderRadius: 10,
                                fontWeight: "bold",
                                backgroundColor:
                                  hit.recommendation === "STRONG BUY"
                                    ? "#fee2e2"
                                    : hit.recommendation === "BUY"
                                      ? "#fed7aa"
                                      : hit.recommendation === "CONSIDER"
                                        ? "#fef3c7"
                                        : "#f1f5f9",
                                color:
                                  hit.recommendation === "STRONG BUY"
                                    ? "#dc2626"
                                    : hit.recommendation === "BUY"
                                      ? "#ea580c"
                                      : hit.recommendation === "CONSIDER"
                                        ? "#d97706"
                                        : "#64748b",
                              }}
                            >
                              {hit.recommendation}
                            </span>
                          </td>
                          <td
                            style={{
                              padding: "10px 14px",
                              textAlign: "center",
                            }}
                          >
                            <span
                              style={{
                                fontSize: 13,
                                padding: "4px 12px",
                                borderRadius: 12,
                                fontWeight: "bold",
                                backgroundColor: pc.bg,
                                color: pc.text,
                              }}
                            >
                              ₹{hit.actual_prize?.toLocaleString()}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════
          VIEW: METHOD BATTLE
      ══════════════════════════════════════════════════════════ */}
      {activeView === "methods" && (
        <Card>
          <H3>🔬 Method Battle — Which method predicted best?</H3>
          <p
            style={{
              color: "#64748b",
              fontSize: 13,
              marginBottom: 20,
              marginTop: -8,
            }}
          >
            Each method's Top 30 predictions checked against actual new draws
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {Object.entries(summary.method_avg_hit_rates)
              .sort((a, b) => b[1] - a[1])
              .map(([method, rate], rank) => {
                const m = METHOD_META[method];
                const isBest = rank === 0;
                return (
                  <div
                    key={method}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 16,
                      padding: "14px 16px",
                      borderRadius: 10,
                      background: isBest ? `${m.color}12` : "#f8fafc",
                      border: isBest
                        ? `1.5px solid ${m.color}40`
                        : "1.5px solid transparent",
                    }}
                  >
                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: "50%",
                        background: isBest ? m.color : "#e2e8f0",
                        color: isBest ? "white" : "#64748b",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 14,
                        fontWeight: "bold",
                        flexShrink: 0,
                      }}
                    >
                      {rank + 1}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          marginBottom: 6,
                        }}
                      >
                        <span
                          style={{
                            fontSize: 14,
                            fontWeight: 700,
                            color: m.color,
                          }}
                        >
                          {m.name} {isBest ? "🏆" : ""}
                        </span>
                        <span
                          style={{
                            fontSize: 15,
                            fontWeight: "bold",
                            color: m.color,
                          }}
                        >
                          {rate}%
                        </span>
                      </div>
                      <div
                        style={{
                          height: 8,
                          backgroundColor: "#e2e8f0",
                          borderRadius: 99,
                        }}
                      >
                        <div
                          style={{
                            height: "100%",
                            width: `${Math.min(rate, 100)}%`,
                            background: `linear-gradient(90deg,${m.color},${m.color}99)`,
                            borderRadius: 99,
                          }}
                        />
                      </div>
                    </div>
                    {/* Per day breakdown */}
                    <div style={{ display: "flex", gap: 6 }}>
                      {per_day.map((day) => (
                        <div
                          key={day.date}
                          style={{
                            textAlign: "center",
                            minWidth: 48,
                          }}
                        >
                          <div
                            style={{
                              fontSize: 10,
                              color: "#94a3b8",
                              marginBottom: 2,
                            }}
                          >
                            {day.date.slice(0, 5)}
                          </div>
                          <div
                            style={{
                              fontSize: 12,
                              fontWeight: "bold",
                              color:
                                day.method_hits[method].hit_rate >= 20
                                  ? m.color
                                  : "#94a3b8",
                            }}
                          >
                            {day.method_hits[method].hit_rate}%
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
          </div>

          {/* Weight recommendation */}
          <div
            style={{
              marginTop: 20,
              padding: "14px 16px",
              borderRadius: 10,
              background: "#f0fdf4",
              border: "1px solid #bbf7d0",
            }}
          >
            <div
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: "#166534",
                marginBottom: 8,
              }}
            >
              💡 Weight Tuning Suggestion for Phase 3
            </div>
            <p style={{ margin: 0, fontSize: 12, color: "#15803d" }}>
              Based on this validation, consider increasing the weight of{" "}
              <strong>{METHOD_META[summary.best_method]?.name}</strong>{" "}
              (currently{" "}
              {summary.best_method === "markov_chain"
                ? "15%"
                : summary.best_method === "moving_average"
                  ? "10%"
                  : summary.best_method === "gap_based"
                    ? "20%"
                    : summary.best_method === "seasonality"
                      ? "10%"
                      : "15%"}
              ). The actual hit rates from real draws give us the ground truth
              to calibrate weights before adding Bayesian + Clustering in Phase
              3.
            </p>
          </div>
        </Card>
      )}

      {/* ══════════════════════════════════════════════════════════
          VIEW: HIT DETAILS — all hits across all days
      ══════════════════════════════════════════════════════════ */}
      {activeView === "hits" && (
        <Card>
          <H3>🎯 All Hits Across All New Draws</H3>
          {per_day.map((day) => (
            <div key={day.date} style={{ marginBottom: 24 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  marginBottom: 10,
                }}
              >
                <span
                  style={{
                    background: "#667eea",
                    color: "white",
                    fontSize: 12,
                    fontWeight: 700,
                    padding: "3px 12px",
                    borderRadius: 20,
                  }}
                >
                  {day.date}
                </span>
                <span style={{ fontSize: 13, color: "#64748b" }}>
                  {day.hits.top_50.count} Top-50 hits ·{" "}
                  {day.hits.strong_buy.count} Strong Buy hits
                </span>
              </div>

              {day.top50_hit_details.length === 0 ? (
                <div
                  style={{
                    padding: "10px 14px",
                    background: "#fef2f2",
                    borderRadius: 8,
                    fontSize: 13,
                    color: "#dc2626",
                  }}
                >
                  No Top-50 hits on this draw
                </div>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {day.top50_hit_details.map((hit) => {
                    const pc =
                      PRIZE_COLORS[hit.actual_prize] || PRIZE_COLORS[100];
                    return (
                      <div
                        key={hit.number}
                        style={{
                          borderRadius: 10,
                          padding: "8px 14px",
                          border: "1px solid #e2e8f0",
                          backgroundColor: "white",
                          minWidth: 110,
                          textAlign: "center",
                        }}
                      >
                        <div
                          style={{
                            fontFamily: "monospace",
                            fontSize: 16,
                            fontWeight: "bold",
                            color: "#667eea",
                          }}
                        >
                          {hit.number}
                        </div>
                        <div
                          style={{
                            fontSize: 10,
                            color: "#94a3b8",
                            margin: "2px 0",
                          }}
                        >
                          Rank #{hit.rank} · Score {hit.finalScore}
                        </div>
                        <span
                          style={{
                            fontSize: 11,
                            padding: "2px 8px",
                            borderRadius: 8,
                            fontWeight: "bold",
                            backgroundColor: pc.bg,
                            color: pc.text,
                          }}
                        >
                          ₹{hit.actual_prize?.toLocaleString()}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </Card>
      )}
    </Wrap>
  );
}

// ── Helpers ───────────────────────────────────────────────────────
const Wrap = ({ children }) => (
  <div
    style={{
      width: "100%",
      maxWidth: 1400,
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
