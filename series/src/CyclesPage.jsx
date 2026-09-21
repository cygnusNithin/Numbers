// src/CyclesPage.jsx
import React, { useEffect, useState } from "react";

export default function CyclesPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedCycle, setSelectedCycle] = useState(null);
  const [expandedDay, setExpandedDay] = useState(null);

  // ✅ NEW: for remaining numbers
  const [showRemaining, setShowRemaining] = useState(null); // cycleNumber or null
  const [remainingSearch, setRemainingSearch] = useState("");
  const [showPrizeRemaining, setShowPrizeRemaining] = useState(null); // { cycleNumber, prize }

  const [source, setSource] = useState("new");

  const endpoints = {
    old: "http://localhost:5000/api/cycles/lotterydata",
    new: "http://localhost:5000/api/cycles/lotterydatanew",
  };

  function load(which) {
    setSource(which);
    setLoading(true);
    setError(null);
    setSelectedCycle(null);
    setExpandedDay(null);
    setShowRemaining(null);
    setRemainingSearch("");
    setShowPrizeRemaining(null);

    fetch(endpoints[which])
      .then((res) => res.json())
      .then((json) => {
        setData(json);
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

  if (loading)
    return <p style={{ textAlign: "center" }}>⏳ Loading cycles...</p>;
  if (error)
    return <p style={{ textAlign: "center", color: "red" }}>❌ {error}</p>;
  if (!data) return null;

  const btnStyle = (active) => ({
    padding: "10px 18px",
    borderRadius: "10px",
    border: active ? "2px solid #2196F3" : "1px solid #ccc",
    background: active ? "#e3f2fd" : "#fff",
    cursor: "pointer",
    fontWeight: "bold",
    marginRight: "10px",
  });

  const prizeColors = {
    5000: "#e91e63",
    2000: "#9c27b0",
    1000: "#673ab7",
    500: "#3f51b5",
    200: "#2196f3",
    100: "#00bcd4",
  };

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif" }}>
      <h2>🔄 Lottery Cycles</h2>

      {/* Two buttons */}
      <div style={{ marginBottom: "20px" }}>
        <button style={btnStyle(source === "old")} onClick={() => load("old")}>
          Check LotteryData
        </button>
        <button style={btnStyle(source === "new")} onClick={() => load("new")}>
          Check LotteryDataNew
        </button>
      </div>

      {/* Overall Summary */}
      <div
        style={{
          display: "flex",
          gap: "16px",
          flexWrap: "wrap",
          marginBottom: "24px",
        }}
      >
        {[
          { label: "Total Cycles", value: data.summary.totalCycles },
          { label: "Completed", value: data.summary.completedCycles },
          { label: "Incomplete", value: data.summary.incompleteCycles },
          { label: "First Day", value: data.summary.firstDay },
          { label: "Last Day", value: data.summary.lastDay },
        ].map((item) => (
          <div
            key={item.label}
            style={{
              background: "#f0f4ff",
              borderRadius: "10px",
              padding: "14px 20px",
              minWidth: "140px",
              textAlign: "center",
              boxShadow: "0 2px 6px rgba(0,0,0,0.08)",
            }}
          >
            <div
              style={{ fontSize: "22px", fontWeight: "bold", color: "#333" }}
            >
              {item.value}
            </div>
            <div style={{ fontSize: "12px", color: "#777", marginTop: "4px" }}>
              {item.label}
            </div>
          </div>
        ))}
      </div>

      {/* Cycles List */}
      <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
        {data.cycles.map((cycle) => {
          const isRemainingOpen = showRemaining === cycle.cycleNumber;

          // Filter remaining numbers by search
          const filteredRemaining =
            cycle.remainingNumbersList?.filter((num) =>
              num.includes(remainingSearch),
            ) || [];

          return (
            <div
              key={cycle.cycleNumber}
              style={{
                border: cycle.isComplete
                  ? "2px solid #4CAF50"
                  : "2px solid #FF9800",
                borderRadius: "12px",
                padding: "16px",
                background: cycle.isComplete ? "#f9fff9" : "#fffaf0",
                boxShadow: "0 2px 8px rgba(0,0,0,0.07)",
              }}
            >
              {/* Header */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: "10px",
                }}
              >
                <h3 style={{ margin: 0 }}>
                  {cycle.isComplete ? "✅" : "🔄"} Cycle {cycle.cycleNumber}
                </h3>
                <span
                  style={{
                    background: cycle.isComplete ? "#4CAF50" : "#FF9800",
                    color: "white",
                    padding: "4px 12px",
                    borderRadius: "20px",
                    fontSize: "12px",
                    fontWeight: "bold",
                  }}
                >
                  {cycle.isComplete ? "Complete" : "In Progress"}
                </span>
              </div>

              {/* Cycle Details */}
              <div
                style={{
                  display: "flex",
                  gap: "20px",
                  flexWrap: "wrap",
                  marginTop: "12px",
                }}
              >
                <div>
                  <span style={{ color: "#777", fontSize: "12px" }}>
                    Start Date
                  </span>
                  <div style={{ fontWeight: "bold" }}>
                    {cycle.startDate || "—"}
                  </div>
                </div>
                <div>
                  <span style={{ color: "#777", fontSize: "12px" }}>
                    End Date
                  </span>
                  <div style={{ fontWeight: "bold" }}>
                    {cycle.endDate || "—"}
                  </div>
                </div>
                <div>
                  <span style={{ color: "#777", fontSize: "12px" }}>
                    Total Days
                  </span>
                  <div style={{ fontWeight: "bold" }}>{cycle.totalDays}</div>
                </div>
                <div>
                  <span style={{ color: "#777", fontSize: "12px" }}>
                    Unique Numbers
                  </span>
                  <div style={{ fontWeight: "bold" }}>
                    {cycle.totalUniqueNumbers.toLocaleString()} / 10,000
                  </div>
                </div>
                {!cycle.isComplete && (
                  <div>
                    <span style={{ color: "#777", fontSize: "12px" }}>
                      Remaining
                    </span>
                    <div style={{ fontWeight: "bold", color: "#FF5722" }}>
                      {cycle.remainingNumbers.toLocaleString()}
                    </div>
                  </div>
                )}
              </div>

              {/* Progress Bar */}
              <div
                style={{
                  marginTop: "12px",
                  background: "#e0e0e0",
                  borderRadius: "10px",
                  height: "10px",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${(cycle.totalUniqueNumbers / 10000) * 100}%`,
                    background: cycle.isComplete ? "#4CAF50" : "#FF9800",
                    height: "100%",
                    borderRadius: "10px",
                    transition: "width 0.5s ease",
                  }}
                />
              </div>
              <div
                style={{
                  fontSize: "12px",
                  color: "#777",
                  marginTop: "4px",
                  textAlign: "right",
                }}
              >
                {((cycle.totalUniqueNumbers / 10000) * 100).toFixed(2)}%
                complete
              </div>

              {/* ✅ Prize Categories Section */}
              {cycle.prizes && cycle.prizes.length > 0 && (
                <div
                  style={{
                    marginTop: "16px",
                    padding: "14px",
                    background: "#fafafa",
                    borderRadius: "10px",
                    border: "1px solid #eee",
                  }}
                >
                  <div
                    style={{
                      fontWeight: "bold",
                      marginBottom: "12px",
                      fontSize: "14px",
                    }}
                  >
                    🏆 Prize Categories Progress
                    {cycle.prizeLeader && (
                      <span
                        style={{
                          fontWeight: "normal",
                          color: "#666",
                          marginLeft: "10px",
                        }}
                      >
                        — Leader: <strong>₹{cycle.prizeLeader.prize}</strong> (
                        {cycle.prizeLeader.percentComplete}%)
                      </span>
                    )}
                  </div>

                  {cycle.completedPrizes &&
                    cycle.completedPrizes.length > 0 && (
                      <div style={{ marginBottom: "12px" }}>
                        <span
                          style={{
                            fontSize: "12px",
                            color: "#4CAF50",
                            fontWeight: "bold",
                          }}
                        >
                          ✅ Completed:{" "}
                          {cycle.completedPrizes.map((p) => `₹${p}`).join(", ")}
                        </span>
                      </div>
                    )}

                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "12px",
                    }}
                  >
                    {cycle.prizes.map((p) => {
                      const prizeRemainingKey = `${cycle.cycleNumber}-${p.prize}`;
                      const isPrizeRemainingOpen =
                        showPrizeRemaining === prizeRemainingKey;

                      return (
                        <div key={p.prize}>
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              fontSize: "13px",
                              marginBottom: "4px",
                            }}
                          >
                            <span style={{ fontWeight: "600" }}>
                              ₹{p.prize} {p.isComplete && "✅"}
                            </span>
                            <span style={{ color: "#555" }}>
                              {p.totalUniqueNumbers.toLocaleString()}/10,000 (
                              {p.percentComplete}%)
                            </span>
                          </div>

                          <div
                            style={{
                              background: "#e0e0e0",
                              borderRadius: "8px",
                              height: "8px",
                              overflow: "hidden",
                            }}
                          >
                            <div
                              style={{
                                width: `${p.percentComplete}%`,
                                background: prizeColors[p.prize] || "#673ab7",
                                height: "100%",
                                transition: "width 0.4s ease",
                              }}
                            />
                          </div>

                          <div
                            style={{
                              fontSize: "11px",
                              color: "#888",
                              marginTop: "3px",
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                            }}
                          >
                            <span>
                              Start: {p.startDate || "—"} | End:{" "}
                              {p.endDate || "—"} | Remaining:{" "}
                              {p.remainingNumbers.toLocaleString()}
                            </span>

                            {/* ✅ Show remaining numbers button for this prize */}
                            {!p.isComplete &&
                              p.remainingNumbersList?.length > 0 && (
                                <button
                                  onClick={() =>
                                    setShowPrizeRemaining(
                                      isPrizeRemainingOpen
                                        ? null
                                        : prizeRemainingKey,
                                    )
                                  }
                                  style={{
                                    padding: "3px 8px",
                                    fontSize: "10px",
                                    background: isPrizeRemainingOpen
                                      ? "#ff5722"
                                      : "#9c27b0",
                                    color: "#fff",
                                    border: "none",
                                    borderRadius: "4px",
                                    cursor: "pointer",
                                  }}
                                >
                                  {isPrizeRemainingOpen
                                    ? "Hide"
                                    : "View Remaining"}
                                </button>
                              )}
                          </div>

                          {/* ✅ Prize remaining numbers list */}
                          {isPrizeRemainingOpen && p.remainingNumbersList && (
                            <div
                              style={{
                                marginTop: "8px",
                                padding: "10px",
                                background: "#f3e5f5",
                                borderRadius: "8px",
                                maxHeight: "200px",
                                overflowY: "auto",
                              }}
                            >
                              <div
                                style={{
                                  fontSize: "12px",
                                  marginBottom: "6px",
                                  fontWeight: "bold",
                                }}
                              >
                                Remaining for ₹{p.prize}:{" "}
                                {p.remainingNumbersList.length.toLocaleString()}{" "}
                                numbers
                              </div>
                              <div
                                style={{
                                  display: "flex",
                                  flexWrap: "wrap",
                                  gap: "4px",
                                }}
                              >
                                {p.remainingNumbersList
                                  .slice(0, 500)
                                  .map((num, i) => (
                                    <span
                                      key={i}
                                      style={{
                                        background:
                                          prizeColors[p.prize] || "#673ab7",
                                        color: "#fff",
                                        padding: "2px 6px",
                                        borderRadius: "3px",
                                        fontSize: "11px",
                                        fontFamily: "monospace",
                                      }}
                                    >
                                      {num}
                                    </span>
                                  ))}
                                {p.remainingNumbersList.length > 500 && (
                                  <span
                                    style={{ fontSize: "11px", color: "#666" }}
                                  >
                                    ...+{p.remainingNumbersList.length - 500}{" "}
                                    more
                                  </span>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Buttons Row */}
              <div
                style={{
                  display: "flex",
                  gap: "10px",
                  marginTop: "14px",
                  flexWrap: "wrap",
                }}
              >
                {/* Toggle Daily Progress */}
                <button
                  onClick={() =>
                    setSelectedCycle(
                      selectedCycle === cycle.cycleNumber
                        ? null
                        : cycle.cycleNumber,
                    )
                  }
                  style={{
                    padding: "8px 16px",
                    background: "#2196F3",
                    color: "white",
                    border: "none",
                    borderRadius: "6px",
                    cursor: "pointer",
                    fontSize: "13px",
                  }}
                >
                  {selectedCycle === cycle.cycleNumber
                    ? "Hide Daily Progress"
                    : "Show Daily Progress"}
                </button>

                {/* ✅ Toggle Remaining Numbers (only for incomplete cycles) */}
                {!cycle.isComplete && cycle.remainingNumbers > 0 && (
                  <button
                    onClick={() => {
                      setShowRemaining(
                        isRemainingOpen ? null : cycle.cycleNumber,
                      );
                      setRemainingSearch("");
                    }}
                    style={{
                      padding: "8px 16px",
                      background: isRemainingOpen ? "#ff5722" : "#9c27b0",
                      color: "white",
                      border: "none",
                      borderRadius: "6px",
                      cursor: "pointer",
                      fontSize: "13px",
                    }}
                  >
                    {isRemainingOpen
                      ? "Hide Remaining Numbers"
                      : `Show Remaining Numbers (${cycle.remainingNumbers.toLocaleString()})`}
                  </button>
                )}
              </div>

              {/* ✅ Remaining Numbers Section (Overall Cycle) */}
              {isRemainingOpen && cycle.remainingNumbersList && (
                <div
                  style={{
                    marginTop: "16px",
                    padding: "16px",
                    background: "#fce4ec",
                    borderRadius: "10px",
                    border: "1px solid #f8bbd9",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: "12px",
                      flexWrap: "wrap",
                      gap: "10px",
                    }}
                  >
                    <div style={{ fontWeight: "bold", fontSize: "14px" }}>
                      🔢 Remaining Numbers:{" "}
                      {filteredRemaining.length.toLocaleString()}
                      {remainingSearch &&
                        ` (filtered from ${cycle.remainingNumbersList.length.toLocaleString()})`}
                    </div>

                    {/* Search Box */}
                    <input
                      type="text"
                      placeholder="Search number..."
                      value={remainingSearch}
                      onChange={(e) => setRemainingSearch(e.target.value)}
                      style={{
                        padding: "6px 12px",
                        borderRadius: "6px",
                        border: "1px solid #ccc",
                        fontSize: "13px",
                        width: "150px",
                      }}
                    />
                  </div>

                  {/* Numbers Grid */}
                  <div
                    style={{
                      maxHeight: "300px",
                      overflowY: "auto",
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "6px",
                    }}
                  >
                    {filteredRemaining.slice(0, 1000).map((num, i) => (
                      <span
                        key={i}
                        style={{
                          background: "#fff",
                          border: "1px solid #e91e63",
                          color: "#c2185b",
                          padding: "4px 10px",
                          borderRadius: "6px",
                          fontSize: "13px",
                          fontFamily: "monospace",
                          fontWeight: "600",
                        }}
                      >
                        {num}
                      </span>
                    ))}
                    {filteredRemaining.length > 1000 && (
                      <span
                        style={{
                          fontSize: "12px",
                          color: "#666",
                          padding: "6px",
                        }}
                      >
                        ...and {filteredRemaining.length - 1000} more
                      </span>
                    )}
                  </div>

                  {filteredRemaining.length === 0 && (
                    <div style={{ color: "#666", fontSize: "13px" }}>
                      No numbers match your search.
                    </div>
                  )}
                </div>
              )}

              {/* Daily Progress Table */}
              {selectedCycle === cycle.cycleNumber && (
                <div style={{ marginTop: "16px", overflowX: "auto" }}>
                  <table
                    style={{
                      width: "100%",
                      borderCollapse: "collapse",
                      fontSize: "13px",
                    }}
                  >
                    <thead>
                      <tr style={{ background: "#e3f2fd" }}>
                        <th style={thStyle}>Date</th>
                        <th style={thStyle}>New Unique</th>
                        <th style={thStyle}>Total Unique</th>
                        <th style={thStyle}>Progress</th>
                        <th style={thStyle}>Numbers Added</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cycle.dailyProgress.map((day, index) => {
                        const dayKey = `${cycle.cycleNumber}-${index}`;
                        const isExpanded = expandedDay === dayKey;

                        return (
                          <React.Fragment key={index}>
                            <tr
                              style={{
                                background:
                                  index % 2 === 0 ? "#fff" : "#f9f9f9",
                              }}
                            >
                              <td style={tdStyle}>{day.date}</td>
                              <td style={tdStyle}>
                                <span
                                  style={{
                                    color: "#4CAF50",
                                    fontWeight: "bold",
                                  }}
                                >
                                  +{day.newUnique}
                                </span>
                              </td>
                              <td style={tdStyle}>
                                {day.totalUnique.toLocaleString()}
                              </td>
                              <td style={tdStyle}>
                                <div
                                  style={{
                                    background: "#e0e0e0",
                                    borderRadius: "6px",
                                    height: "8px",
                                    width: "100%",
                                    minWidth: "80px",
                                  }}
                                >
                                  <div
                                    style={{
                                      width: `${(day.totalUnique / 10000) * 100}%`,
                                      background: "#2196F3",
                                      height: "100%",
                                      borderRadius: "6px",
                                    }}
                                  />
                                </div>
                              </td>
                              <td style={tdStyle}>
                                {day.numbersAdded &&
                                day.numbersAdded.length > 0 ? (
                                  <button
                                    onClick={() =>
                                      setExpandedDay(isExpanded ? null : dayKey)
                                    }
                                    style={{
                                      padding: "4px 10px",
                                      fontSize: "11px",
                                      background: isExpanded
                                        ? "#ff5722"
                                        : "#673ab7",
                                      color: "#fff",
                                      border: "none",
                                      borderRadius: "4px",
                                      cursor: "pointer",
                                    }}
                                  >
                                    {isExpanded
                                      ? "Hide"
                                      : `View ${day.numbersAdded.length}`}
                                  </button>
                                ) : (
                                  <span style={{ color: "#999" }}>—</span>
                                )}
                              </td>
                            </tr>

                            {isExpanded && day.numbersAdded && (
                              <tr>
                                <td
                                  colSpan={5}
                                  style={{
                                    padding: "12px",
                                    background: "#f3e5f5",
                                    borderBottom: "1px solid #ddd",
                                  }}
                                >
                                  <div
                                    style={{
                                      marginBottom: "8px",
                                      fontWeight: "bold",
                                    }}
                                  >
                                    Numbers Added on {day.date} (
                                    {day.numbersAdded.length} total):
                                  </div>

                                  <div
                                    style={{
                                      display: "flex",
                                      flexWrap: "wrap",
                                      gap: "6px",
                                      marginBottom: "12px",
                                    }}
                                  >
                                    {day.numbersAdded
                                      .slice(0, 200)
                                      .map((num, i) => (
                                        <span
                                          key={i}
                                          style={{
                                            background: "#fff",
                                            border: "1px solid #ccc",
                                            padding: "2px 8px",
                                            borderRadius: "4px",
                                            fontSize: "12px",
                                            fontFamily: "monospace",
                                          }}
                                        >
                                          {num}
                                        </span>
                                      ))}
                                    {day.numbersAdded.length > 200 && (
                                      <span
                                        style={{
                                          color: "#666",
                                          fontSize: "12px",
                                        }}
                                      >
                                        ...and {day.numbersAdded.length - 200}{" "}
                                        more
                                      </span>
                                    )}
                                  </div>

                                  {day.prizeNumbersAdded && (
                                    <div>
                                      <div
                                        style={{
                                          fontWeight: "bold",
                                          marginBottom: "6px",
                                        }}
                                      >
                                        By Prize Category:
                                      </div>
                                      {Object.entries(day.prizeNumbersAdded)
                                        .filter(([, nums]) => nums.length > 0)
                                        .sort((a, b) => b[0] - a[0])
                                        .map(([prize, nums]) => (
                                          <div
                                            key={prize}
                                            style={{ marginBottom: "8px" }}
                                          >
                                            <span
                                              style={{
                                                fontWeight: "600",
                                                color:
                                                  prizeColors[prize] || "#333",
                                              }}
                                            >
                                              ₹{prize} (+{nums.length}):
                                            </span>
                                            <div
                                              style={{
                                                display: "flex",
                                                flexWrap: "wrap",
                                                gap: "4px",
                                                marginTop: "4px",
                                              }}
                                            >
                                              {nums.slice(0, 50).map((n, i) => (
                                                <span
                                                  key={i}
                                                  style={{
                                                    background:
                                                      prizeColors[prize] ||
                                                      "#673ab7",
                                                    color: "#fff",
                                                    padding: "2px 6px",
                                                    borderRadius: "3px",
                                                    fontSize: "11px",
                                                    fontFamily: "monospace",
                                                  }}
                                                >
                                                  {n}
                                                </span>
                                              ))}
                                              {nums.length > 50 && (
                                                <span
                                                  style={{
                                                    fontSize: "11px",
                                                    color: "#666",
                                                  }}
                                                >
                                                  ...+{nums.length - 50} more
                                                </span>
                                              )}
                                            </div>
                                          </div>
                                        ))}
                                    </div>
                                  )}
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const thStyle = {
  padding: "10px 12px",
  textAlign: "left",
  borderBottom: "2px solid #ddd",
  fontWeight: "bold",
  background: "#e3f2fd",
};

const tdStyle = {
  padding: "10px 12px",
  borderBottom: "1px solid #eee",
  verticalAlign: "middle",
};
