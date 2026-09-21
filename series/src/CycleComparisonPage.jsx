// src/CycleComparisonPage.jsx
import React, { useEffect, useState } from "react";

export default function CycleComparisonPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // ✅ Collection source
  const [source, setSource] = useState("new"); // "old" | "new"

  // Filters
  const [searchNumber, setSearchNumber] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [viewMode, setViewMode] = useState("predictions");

  const endpoints = {
    old: "http://localhost:5000/api/cycle-comparison/lotterydata",
    new: "http://localhost:5000/api/cycle-comparison/lotterydatanew",
  };

  function load(which) {
    setSource(which);
    setLoading(true);
    setError(null);
    setSearchNumber("");
    setPriorityFilter("all");

    fetch(endpoints[which])
      .then((res) => res.json())
      .then((json) => {
        if (json.error) {
          setError(json.error);
          setData(null);
        } else {
          setData(json);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }

  useEffect(() => {
    load("new");
  }, []);

  const btnStyle = (active) => ({
    padding: "10px 18px",
    borderRadius: "10px",
    border: active ? "2px solid #2196F3" : "1px solid #ccc",
    background: active ? "#e3f2fd" : "#fff",
    cursor: "pointer",
    fontWeight: "bold",
    marginRight: "10px",
  });

  const priorityColors = {
    critical: "#d32f2f",
    high: "#f57c00",
    medium: "#fbc02d",
    low: "#4caf50",
    upcoming: "#2196f3",
  };

  const prizeColors = {
    5000: "#e91e63",
    2000: "#9c27b0",
    1000: "#673ab7",
    500: "#3f51b5",
    200: "#2196f3",
    100: "#00bcd4",
  };

  // Filter logic
  let filteredPredictions = data?.predictions || [];
  let filteredComparison = data?.fullComparison || [];

  if (priorityFilter !== "all") {
    filteredPredictions = filteredPredictions.filter(
      (p) => p.prediction?.priority === priorityFilter,
    );
  }
  if (searchNumber) {
    filteredPredictions = filteredPredictions.filter((p) =>
      p.number.includes(searchNumber),
    );
    filteredComparison = filteredComparison.filter((n) =>
      n.number.includes(searchNumber),
    );
  }

  return (
    <div
      style={{
        padding: "20px",
        fontFamily: "Arial, sans-serif",
        maxWidth: "1400px",
        margin: "0 auto",
      }}
    >
      <h2>📊 Cycle Comparison & Prediction (Cycles 2-4 → Predict Cycle 5)</h2>

      {/* ========== COLLECTION BUTTONS ========== */}
      <div
        style={{
          marginBottom: "20px",
          padding: "16px",
          background: "#f5f5f5",
          borderRadius: "10px",
        }}
      >
        <div style={{ fontWeight: "bold", marginBottom: "10px" }}>
          📂 Select Collection:
        </div>
        <button style={btnStyle(source === "old")} onClick={() => load("old")}>
          Check LotteryData
        </button>
        <button style={btnStyle(source === "new")} onClick={() => load("new")}>
          Check LotteryDataNew
        </button>
        <span
          style={{
            marginLeft: "16px",
            padding: "6px 12px",
            background: source === "new" ? "#4caf50" : "#ff9800",
            color: "#fff",
            borderRadius: "20px",
            fontSize: "12px",
            fontWeight: "bold",
          }}
        >
          Active: {source === "new" ? "LotteryDataNew" : "LotteryData"}
        </span>
      </div>

      {/* ========== LOADING / ERROR ========== */}
      {loading && (
        <p style={{ textAlign: "center", padding: "40px" }}>
          ⏳ Loading comparison data...
        </p>
      )}
      {error && (
        <div
          style={{
            textAlign: "center",
            padding: "40px",
            background: "#ffebee",
            borderRadius: "10px",
            color: "#c62828",
          }}
        >
          <h3>❌ Error</h3>
          <p>{error}</p>
        </div>
      )}

      {/* ========== MAIN CONTENT ========== */}
      {!loading && !error && data && (
        <>
          {/* ========== SUMMARY CARDS ========== */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: "16px",
              marginBottom: "24px",
            }}
          >
            {/* Total Cycles */}
            <div style={cardStyle("#e8eaf6")}>
              <h4 style={{ margin: "0 0 8px" }}>📊 Total Cycles</h4>
              <div
                style={{
                  fontSize: "28px",
                  fontWeight: "bold",
                  color: "#3f51b5",
                }}
              >
                {data.summary.totalCyclesFound}
              </div>
            </div>

            {/* Cycle 2 */}
            <div style={cardStyle("#e3f2fd")}>
              <h4 style={{ margin: "0 0 8px" }}>📅 Cycle 2</h4>
              <div style={{ fontSize: "13px", color: "#555" }}>
                <div>
                  {data.summary.cycle2.startDate} →{" "}
                  {data.summary.cycle2.endDate}
                </div>
                <div>
                  <strong>{data.summary.cycle2.totalDays} days</strong>
                </div>
              </div>
            </div>

            {/* Cycle 3 */}
            <div style={cardStyle("#f3e5f5")}>
              <h4 style={{ margin: "0 0 8px" }}>📅 Cycle 3</h4>
              <div style={{ fontSize: "13px", color: "#555" }}>
                <div>
                  {data.summary.cycle3.startDate} →{" "}
                  {data.summary.cycle3.endDate}
                </div>
                <div>
                  <strong>{data.summary.cycle3.totalDays} days</strong>
                </div>
              </div>
            </div>

            {/* Cycle 4 */}
            <div style={cardStyle("#fff3e0")}>
              <h4 style={{ margin: "0 0 8px" }}>📅 Cycle 4</h4>
              <div style={{ fontSize: "13px", color: "#555" }}>
                <div>
                  {data.summary.cycle4.startDate} →{" "}
                  {data.summary.cycle4.endDate}
                </div>
                <div>
                  <strong>{data.summary.cycle4.totalDays} days</strong>
                </div>
              </div>
            </div>

            {/* Cycle 5 (Current/Prediction Target) */}
            <div style={cardStyle("#e8f5e9")}>
              <h4 style={{ margin: "0 0 8px" }}>
                🔄 Cycle {data.summary.cycle5?.cycleNumber || 5}{" "}
                {data.summary.cycle5?.isComplete ? "(Complete)" : "(Current)"}
              </h4>
              <div style={{ fontSize: "13px", color: "#555" }}>
                <div>Started: {data.summary.cycle5?.startDate || "—"}</div>
                <div>
                  Day: <strong>{data.summary.cycle5?.currentDay || 0}</strong>
                </div>
                <div>
                  Appeared:{" "}
                  <strong>
                    {data.summary.cycle5?.numbersAppeared?.toLocaleString()}
                  </strong>
                </div>
                <div>
                  Remaining:{" "}
                  <strong style={{ color: "#f57c00" }}>
                    {data.summary.cycle5?.numbersRemaining?.toLocaleString()}
                  </strong>
                </div>
              </div>
            </div>

            {/* Avg Cycle Days */}
            <div style={cardStyle("#fce4ec")}>
              <h4 style={{ margin: "0 0 8px" }}>📈 Avg Cycle</h4>
              <div
                style={{
                  fontSize: "28px",
                  fontWeight: "bold",
                  color: "#c2185b",
                }}
              >
                {data.summary.avgCycleDays} days
              </div>
            </div>
          </div>

          {/* ========== PREDICTION SUMMARY BADGES ========== */}
          <div
            style={{
              display: "flex",
              gap: "12px",
              flexWrap: "wrap",
              marginBottom: "20px",
              padding: "16px",
              background: "#f5f5f5",
              borderRadius: "10px",
            }}
          >
            <div style={{ fontWeight: "bold", marginRight: "10px" }}>
              🎯 Predictions:
            </div>
            {Object.entries(data.summary.predictions).map(
              ([priority, count]) => (
                <div
                  key={priority}
                  onClick={() =>
                    setPriorityFilter(
                      priority === priorityFilter ? "all" : priority,
                    )
                  }
                  style={{
                    padding: "6px 14px",
                    borderRadius: "20px",
                    background:
                      priorityFilter === priority
                        ? priorityColors[priority]
                        : "#fff",
                    color:
                      priorityFilter === priority
                        ? "#fff"
                        : priorityColors[priority],
                    border: `2px solid ${priorityColors[priority]}`,
                    cursor: "pointer",
                    fontWeight: "bold",
                    fontSize: "13px",
                  }}
                >
                  {priority.toUpperCase()}: {count}
                </div>
              ),
            )}
            {priorityFilter !== "all" && (
              <button
                onClick={() => setPriorityFilter("all")}
                style={{
                  padding: "6px 12px",
                  background: "#666",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                Clear Filter
              </button>
            )}
          </div>

          {/* ========== VIEW MODE TABS ========== */}
          <div style={{ display: "flex", gap: "10px", marginBottom: "20px" }}>
            {["predictions", "comparison", "patterns"].map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                style={{
                  padding: "10px 20px",
                  background: viewMode === mode ? "#2196f3" : "#fff",
                  color: viewMode === mode ? "#fff" : "#333",
                  border: "2px solid #2196f3",
                  borderRadius: "8px",
                  cursor: "pointer",
                  fontWeight: "bold",
                  textTransform: "capitalize",
                }}
              >
                {mode === "predictions" && "🎯 "}
                {mode === "comparison" && "📊 "}
                {mode === "patterns" && "🔍 "}
                {mode}
              </button>
            ))}
          </div>

          {/* ========== SEARCH ========== */}
          <div style={{ marginBottom: "20px" }}>
            <input
              type="text"
              placeholder="Search number (e.g., 1234)..."
              value={searchNumber}
              onChange={(e) => setSearchNumber(e.target.value)}
              style={{
                padding: "10px 16px",
                borderRadius: "8px",
                border: "2px solid #ddd",
                fontSize: "14px",
                width: "250px",
              }}
            />
            {searchNumber && (
              <button
                onClick={() => setSearchNumber("")}
                style={{
                  marginLeft: "10px",
                  padding: "10px 14px",
                  background: "#666",
                  color: "#fff",
                  border: "none",
                  borderRadius: "8px",
                  cursor: "pointer",
                }}
              >
                Clear
              </button>
            )}
          </div>

          {/* ========== PREDICTIONS VIEW ========== */}
          {viewMode === "predictions" && (
            <div>
              <h3>
                🎯 Predicted Numbers for Cycle{" "}
                {data.summary.cycle5?.cycleNumber || 5} (
                {filteredPredictions.length} numbers)
              </h3>
              <p
                style={{
                  color: "#666",
                  fontSize: "13px",
                  marginBottom: "16px",
                }}
              >
                Numbers that haven't appeared yet, sorted by how "overdue" they
                are based on Cycles 2-4 patterns.
              </p>

              <div style={{ overflowX: "auto" }}>
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    fontSize: "13px",
                  }}
                >
                  <thead>
                    <tr style={{ background: "#e3f2fd" }}>
                      <th style={thStyle}>Number</th>
                      <th style={thStyle}>Priority</th>
                      <th style={thStyle}>Expected Day</th>
                      <th style={thStyle}>Current Day</th>
                      <th style={thStyle}>Days Overdue</th>
                      <th style={thStyle}>Cycle 2</th>
                      <th style={thStyle}>Cycle 3</th>
                      <th style={thStyle}>Cycle 4</th>
                      <th style={thStyle}>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPredictions.slice(0, 200).map((item, idx) => (
                      <tr
                        key={item.number}
                        style={{
                          background: idx % 2 === 0 ? "#fff" : "#f9f9f9",
                          borderLeft: `4px solid ${priorityColors[item.prediction.priority]}`,
                        }}
                      >
                        <td style={tdStyle}>
                          <span style={numberBadge}>{item.number}</span>
                        </td>
                        <td style={tdStyle}>
                          <span
                            style={{
                              ...priorityBadge,
                              background:
                                priorityColors[item.prediction.priority],
                            }}
                          >
                            {item.prediction.priority}
                          </span>
                        </td>
                        <td style={tdStyle}>{item.prediction.expectedDay}</td>
                        <td style={tdStyle}>{item.prediction.currentDay}</td>
                        <td style={tdStyle}>
                          <span
                            style={{
                              color:
                                item.prediction.daysOverdue > 0
                                  ? "#d32f2f"
                                  : "#4caf50",
                              fontWeight: "bold",
                            }}
                          >
                            {item.prediction.daysOverdue > 0
                              ? `+${item.prediction.daysOverdue}`
                              : "0"}
                          </span>
                        </td>
                        <td style={tdStyle}>
                          {item.cycle2 ? (
                            <CycleCell
                              data={item.cycle2}
                              prizeColors={prizeColors}
                            />
                          ) : (
                            <span style={{ color: "#ccc" }}>—</span>
                          )}
                        </td>
                        <td style={tdStyle}>
                          {item.cycle3 ? (
                            <CycleCell
                              data={item.cycle3}
                              prizeColors={prizeColors}
                            />
                          ) : (
                            <span style={{ color: "#ccc" }}>—</span>
                          )}
                        </td>
                        <td style={tdStyle}>
                          {item.cycle4 ? (
                            <CycleCell
                              data={item.cycle4}
                              prizeColors={prizeColors}
                            />
                          ) : (
                            <span style={{ color: "#ccc" }}>—</span>
                          )}
                        </td>
                        <td style={tdStyle}>
                          <span
                            style={{
                              ...confidenceBadge,
                              background:
                                item.prediction.confidence === "high"
                                  ? "#4caf50"
                                  : item.prediction.confidence === "medium"
                                    ? "#ff9800"
                                    : "#9e9e9e",
                            }}
                          >
                            {item.prediction.confidence}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filteredPredictions.length > 200 && (
                  <p
                    style={{
                      color: "#666",
                      fontSize: "13px",
                      marginTop: "10px",
                    }}
                  >
                    Showing 200 of {filteredPredictions.length}. Use search to
                    find specific numbers.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* ========== COMPARISON VIEW ========== */}
          {viewMode === "comparison" && (
            <div>
              <h3>
                📊 Full Number Comparison ({filteredComparison.length} numbers)
              </h3>
              <p
                style={{
                  color: "#666",
                  fontSize: "13px",
                  marginBottom: "16px",
                }}
              >
                Side-by-side view of when each number appeared in Cycles 2, 3,
                4, and {data.summary.cycle5?.cycleNumber || 5}.
              </p>

              <div style={{ overflowX: "auto" }}>
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    fontSize: "13px",
                  }}
                >
                  <thead>
                    <tr>
                      <th style={thStyle}>Number</th>
                      <th style={{ ...thStyle, background: "#e3f2fd" }}>
                        Cycle 2
                      </th>
                      <th style={{ ...thStyle, background: "#f3e5f5" }}>
                        Cycle 3
                      </th>
                      <th style={{ ...thStyle, background: "#fff3e0" }}>
                        Cycle 4
                      </th>
                      <th style={{ ...thStyle, background: "#e8f5e9" }}>
                        Cycle {data.summary.cycle5?.cycleNumber || 5}
                      </th>
                      <th style={thStyle}>Avg Day</th>
                      <th style={thStyle}>Range</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredComparison.slice(0, 200).map((item, idx) => (
                      <tr
                        key={item.number}
                        style={{
                          background: item.appearedInCycle5
                            ? "#e8f5e9"
                            : idx % 2 === 0
                              ? "#fff"
                              : "#f9f9f9",
                        }}
                      >
                        <td style={tdStyle}>
                          <span style={numberBadge}>{item.number}</span>
                        </td>
                        <td style={{ ...tdStyle, background: "#e3f2fd33" }}>
                          {item.cycle2 ? (
                            <div>
                              <strong>Day {item.cycle2.dayNumber}</strong>
                              <div style={{ fontSize: "11px", color: "#666" }}>
                                {item.cycle2.date}
                              </div>
                            </div>
                          ) : (
                            <span style={{ color: "#ccc" }}>—</span>
                          )}
                        </td>
                        <td style={{ ...tdStyle, background: "#f3e5f533" }}>
                          {item.cycle3 ? (
                            <div>
                              <strong>Day {item.cycle3.dayNumber}</strong>
                              <div style={{ fontSize: "11px", color: "#666" }}>
                                {item.cycle3.date}
                              </div>
                            </div>
                          ) : (
                            <span style={{ color: "#ccc" }}>—</span>
                          )}
                        </td>
                        <td style={{ ...tdStyle, background: "#fff3e033" }}>
                          {item.cycle4 ? (
                            <div>
                              <strong>Day {item.cycle4.dayNumber}</strong>
                              <div style={{ fontSize: "11px", color: "#666" }}>
                                {item.cycle4.date}
                              </div>
                            </div>
                          ) : (
                            <span style={{ color: "#ccc" }}>—</span>
                          )}
                        </td>
                        <td style={{ ...tdStyle, background: "#e8f5e933" }}>
                          {item.cycle5 ? (
                            <div>
                              <strong style={{ color: "#4caf50" }}>
                                ✅ Day {item.cycle5.dayNumber}
                              </strong>
                              <div style={{ fontSize: "11px", color: "#666" }}>
                                {item.cycle5.date}
                              </div>
                            </div>
                          ) : (
                            <span
                              style={{ color: "#f57c00", fontWeight: "bold" }}
                            >
                              ⏳ Pending
                            </span>
                          )}
                        </td>
                        <td style={tdStyle}>
                          {item.stats.avgDay !== null ? (
                            <strong>{item.stats.avgDay}</strong>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td style={tdStyle}>
                          {item.stats.minDay !== null
                            ? `${item.stats.minDay} - ${item.stats.maxDay}`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filteredComparison.length > 200 && (
                  <p
                    style={{
                      color: "#666",
                      fontSize: "13px",
                      marginTop: "10px",
                    }}
                  >
                    Showing 200 of {filteredComparison.length}. Use search to
                    find specific numbers.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* ========== PATTERNS VIEW ========== */}
          {viewMode === "patterns" && (
            <div>
              <h3>🔍 Pattern Analysis</h3>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
                  gap: "20px",
                }}
              >
                {/* Always Early */}
                <div
                  style={{ ...patternCard, borderLeft: "4px solid #4caf50" }}
                >
                  <h4 style={{ color: "#4caf50", margin: "0 0 12px" }}>
                    🚀 Always Early ({data.patterns.alwaysEarly.length} numbers)
                  </h4>
                  <p
                    style={{
                      fontSize: "12px",
                      color: "#666",
                      marginBottom: "12px",
                    }}
                  >
                    Numbers that consistently appear in the first 30% of each
                    cycle.
                  </p>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "6px",
                      maxHeight: "200px",
                      overflowY: "auto",
                    }}
                  >
                    {data.patterns.alwaysEarly.map((n) => (
                      <span
                        key={n.number}
                        style={{
                          padding: "4px 10px",
                          borderRadius: "6px",
                          background:
                            n.cycle5Status === "appeared" ? "#4caf50" : "#fff",
                          color:
                            n.cycle5Status === "appeared" ? "#fff" : "#333",
                          border: "1px solid #4caf50",
                          fontFamily: "monospace",
                          fontSize: "12px",
                        }}
                      >
                        {n.number}
                        <span style={{ fontSize: "10px", marginLeft: "4px" }}>
                          ({n.avgDay}d)
                        </span>
                      </span>
                    ))}
                  </div>
                </div>

                {/* Always Late */}
                <div
                  style={{ ...patternCard, borderLeft: "4px solid #f57c00" }}
                >
                  <h4 style={{ color: "#f57c00", margin: "0 0 12px" }}>
                    🐢 Always Late ({data.patterns.alwaysLate.length} numbers)
                  </h4>
                  <p
                    style={{
                      fontSize: "12px",
                      color: "#666",
                      marginBottom: "12px",
                    }}
                  >
                    Numbers that consistently appear in the last 30% of each
                    cycle.
                  </p>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "6px",
                      maxHeight: "200px",
                      overflowY: "auto",
                    }}
                  >
                    {data.patterns.alwaysLate.map((n) => (
                      <span
                        key={n.number}
                        style={{
                          padding: "4px 10px",
                          borderRadius: "6px",
                          background:
                            n.cycle5Status === "appeared" ? "#f57c00" : "#fff",
                          color:
                            n.cycle5Status === "appeared" ? "#fff" : "#333",
                          border: "1px solid #f57c00",
                          fontFamily: "monospace",
                          fontSize: "12px",
                        }}
                      >
                        {n.number}
                        <span style={{ fontSize: "10px", marginLeft: "4px" }}>
                          ({n.avgDay}d)
                        </span>
                      </span>
                    ))}
                  </div>
                </div>

                {/* Stats */}
                <div
                  style={{ ...patternCard, borderLeft: "4px solid #2196f3" }}
                >
                  <h4 style={{ color: "#2196f3", margin: "0 0 12px" }}>
                    📈 Stats
                  </h4>
                  <div style={{ fontSize: "14px" }}>
                    <div style={{ marginBottom: "12px" }}>
                      <strong>Consistent Timing:</strong>{" "}
                      {data.patterns.consistentTiming} numbers
                      <p
                        style={{
                          fontSize: "11px",
                          color: "#666",
                          margin: "4px 0 0",
                        }}
                      >
                        Numbers with ≤20 day variance across cycles
                      </p>
                    </div>
                    <div>
                      <strong>High Variance:</strong>{" "}
                      {data.patterns.highVariance} numbers
                      <p
                        style={{
                          fontSize: "11px",
                          color: "#666",
                          margin: "4px 0 0",
                        }}
                      >
                        Numbers with &gt;50% cycle length variance
                        (unpredictable)
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ========== HELPER COMPONENTS ==========
function CycleCell({ data, prizeColors }) {
  return (
    <div>
      <div>Day {data.dayNumber}</div>
      <div style={{ fontSize: "11px", color: "#666" }}>{data.date}</div>
      <span
        style={{
          display: "inline-block",
          padding: "2px 6px",
          borderRadius: "4px",
          background: prizeColors[data.prize] || "#999",
          color: "#fff",
          fontSize: "10px",
          fontWeight: "bold",
          marginTop: "4px",
        }}
      >
        ₹{data.prize}
      </span>
    </div>
  );
}

// ========== STYLES ==========
const cardStyle = (bg) => ({
  padding: "16px",
  borderRadius: "10px",
  background: bg,
  boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
});

const patternCard = {
  padding: "16px",
  borderRadius: "10px",
  background: "#fff",
  boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
};

const thStyle = {
  padding: "12px",
  textAlign: "left",
  borderBottom: "2px solid #ddd",
  fontWeight: "bold",
  position: "sticky",
  top: 0,
  background: "#e3f2fd",
};

const tdStyle = {
  padding: "10px 12px",
  borderBottom: "1px solid #eee",
  verticalAlign: "top",
};

const numberBadge = {
  fontFamily: "monospace",
  fontWeight: "bold",
  fontSize: "15px",
  background: "#f0f0f0",
  padding: "4px 10px",
  borderRadius: "4px",
};

const priorityBadge = {
  padding: "4px 10px",
  borderRadius: "12px",
  color: "#fff",
  fontWeight: "bold",
  fontSize: "11px",
  textTransform: "uppercase",
};

const confidenceBadge = {
  padding: "3px 8px",
  borderRadius: "10px",
  color: "#fff",
  fontSize: "10px",
  fontWeight: "bold",
};
