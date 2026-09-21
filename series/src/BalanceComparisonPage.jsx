// src/BalanceComparisonPage.jsx
import React, { useEffect, useState } from "react";

export default function BalanceComparisonPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [viewMode, setViewMode] = useState("common"); // common | oldDb | newDb | topPredictions
  const [prizeFilter, setPrizeFilter] = useState("all"); // all | 3 | 2 | 1 | 0
  const [urgencyFilter, setUrgencyFilter] = useState("all");
  const [searchNumber, setSearchNumber] = useState("");

  useEffect(() => {
    fetch("http://localhost:5000/api/balance-comparison")
      .then((res) => res.json())
      .then((json) => {
        if (json.error) {
          setError(json.error);
        } else {
          setData(json);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorDisplay error={error} />;
  if (!data) return null;

  const urgencyColors = {
    critical: "#d32f2f",
    high: "#f57c00",
    medium: "#fbc02d",
    low: "#4caf50",
    upcoming: "#2196f3",
    unknown: "#9e9e9e",
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
  const filterNumbers = (numbers) => {
    let filtered = numbers;

    if (prizeFilter !== "all") {
      const count = parseInt(prizeFilter);
      filtered = filtered.filter((n) => {
        const prize5000Count =
          n.prize5000?.count ?? n.old?.prize5000?.count ?? 0;
        return prize5000Count === count;
      });
    }

    if (urgencyFilter !== "all") {
      filtered = filtered.filter((n) => {
        const urgency = n.prediction?.urgency ?? n.old?.prediction?.urgency;
        return urgency === urgencyFilter;
      });
    }

    if (searchNumber) {
      filtered = filtered.filter((n) => {
        const num = n.number;
        return num.includes(searchNumber);
      });
    }

    return filtered;
  };

  // Get current list based on view mode
  let currentList = [];
  let listTitle = "";

  if (viewMode === "common") {
    currentList = filterNumbers(data.commonRemaining || []);
    listTitle = `Common Remaining in Both DBs (${currentList.length})`;
  } else if (viewMode === "oldDb") {
    currentList = filterNumbers(data.lotteryData?.remainingNumbers || []);
    listTitle = `LotteryData Remaining (${currentList.length})`;
  } else if (viewMode === "newDb") {
    currentList = filterNumbers(data.lotteryDataNew?.remainingNumbers || []);
    listTitle = `LotteryDataNew Remaining (${currentList.length})`;
  } else if (viewMode === "topPredictions") {
    currentList = filterNumbers(data.topPredictions || []);
    listTitle = `Top Predictions - ₹5000 History (${currentList.length})`;
  }

  return (
    <div
      style={{
        padding: "20px",
        fontFamily: "Arial, sans-serif",
        maxWidth: "1800px",
        margin: "0 auto",
      }}
    >
      <h2>💰 Cycle 5 Balance Numbers - ₹5000 Prize Comparison</h2>
      <p style={{ color: "#666", marginBottom: "20px" }}>
        Compare remaining numbers in Cycle 5 from both databases with ₹5000
        prize history
      </p>

      {/* ========== CYCLE INFO CARDS ========== */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "20px",
          marginBottom: "24px",
        }}
      >
        {/* LotteryData Info */}
        <div
          style={{
            padding: "16px",
            background: "#fff3e0",
            borderRadius: "12px",
            border: "2px solid #ff9800",
          }}
        >
          <h4 style={{ margin: "0 0 12px", color: "#e65100" }}>
            📂 LotteryData (Old)
          </h4>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: "10px",
              fontSize: "12px",
            }}
          >
            <CycleInfoMini
              label="Cycle 2"
              data={data.cycleInfo.lotteryData.cycle2}
            />
            <CycleInfoMini
              label="Cycle 3"
              data={data.cycleInfo.lotteryData.cycle3}
            />
            <CycleInfoMini
              label="Cycle 4"
              data={data.cycleInfo.lotteryData.cycle4}
            />
            <CycleInfoMini
              label="Cycle 5"
              data={data.cycleInfo.lotteryData.cycle5}
              isCurrent
            />
          </div>
          <div
            style={{
              marginTop: "12px",
              padding: "10px",
              background: "#fff",
              borderRadius: "8px",
            }}
          >
            <div
              style={{
                display: "flex",
                gap: "12px",
                flexWrap: "wrap",
                fontSize: "12px",
              }}
            >
              <span>
                <strong style={{ color: "#d32f2f" }}>
                  {data.lotteryData?.summary.totalRemaining}
                </strong>{" "}
                Remaining
              </span>
              <span>
                <strong style={{ color: "#e91e63" }}>
                  {data.lotteryData?.summary.in5000AllThree}
                </strong>{" "}
                in ₹5000 (3/3)
              </span>
              <span>
                <strong style={{ color: "#9c27b0" }}>
                  {data.lotteryData?.summary.in5000Two}
                </strong>{" "}
                in ₹5000 (2/3)
              </span>
              <span>
                <strong style={{ color: "#673ab7" }}>
                  {data.lotteryData?.summary.in5000One}
                </strong>{" "}
                in ₹5000 (1/3)
              </span>
            </div>
          </div>
        </div>

        {/* LotteryDataNew Info */}
        <div
          style={{
            padding: "16px",
            background: "#e8f5e9",
            borderRadius: "12px",
            border: "2px solid #4caf50",
          }}
        >
          <h4 style={{ margin: "0 0 12px", color: "#2e7d32" }}>
            📂 LotteryDataNew (New)
          </h4>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: "10px",
              fontSize: "12px",
            }}
          >
            <CycleInfoMini
              label="Cycle 2"
              data={data.cycleInfo.lotteryDataNew.cycle2}
            />
            <CycleInfoMini
              label="Cycle 3"
              data={data.cycleInfo.lotteryDataNew.cycle3}
            />
            <CycleInfoMini
              label="Cycle 4"
              data={data.cycleInfo.lotteryDataNew.cycle4}
            />
            <CycleInfoMini
              label="Cycle 5"
              data={data.cycleInfo.lotteryDataNew.cycle5}
              isCurrent
            />
          </div>
          <div
            style={{
              marginTop: "12px",
              padding: "10px",
              background: "#fff",
              borderRadius: "8px",
            }}
          >
            <div
              style={{
                display: "flex",
                gap: "12px",
                flexWrap: "wrap",
                fontSize: "12px",
              }}
            >
              <span>
                <strong style={{ color: "#d32f2f" }}>
                  {data.lotteryDataNew?.summary.totalRemaining}
                </strong>{" "}
                Remaining
              </span>
              <span>
                <strong style={{ color: "#e91e63" }}>
                  {data.lotteryDataNew?.summary.in5000AllThree}
                </strong>{" "}
                in ₹5000 (3/3)
              </span>
              <span>
                <strong style={{ color: "#9c27b0" }}>
                  {data.lotteryDataNew?.summary.in5000Two}
                </strong>{" "}
                in ₹5000 (2/3)
              </span>
              <span>
                <strong style={{ color: "#673ab7" }}>
                  {data.lotteryDataNew?.summary.in5000One}
                </strong>{" "}
                in ₹5000 (1/3)
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ========== COMPARISON SUMMARY ========== */}
      <div
        style={{
          padding: "16px",
          background: "#e3f2fd",
          borderRadius: "12px",
          marginBottom: "24px",
        }}
      >
        <h4 style={{ margin: "0 0 12px", color: "#1565c0" }}>
          📊 Database Comparison
        </h4>
        <div style={{ display: "flex", gap: "20px", flexWrap: "wrap" }}>
          <ComparisonBadge
            label="Common in Both"
            value={data.comparison.commonRemainingCount}
            color="#2196f3"
            onClick={() => setViewMode("common")}
            active={viewMode === "common"}
          />
          <ComparisonBadge
            label="Only in LotteryData"
            value={data.comparison.onlyInOldCount}
            color="#ff9800"
            onClick={() => setViewMode("oldDb")}
            active={viewMode === "oldDb"}
          />
          <ComparisonBadge
            label="Only in LotteryDataNew"
            value={data.comparison.onlyInNewCount}
            color="#4caf50"
            onClick={() => setViewMode("newDb")}
            active={viewMode === "newDb"}
          />
          <ComparisonBadge
            label="Top ₹5000 Predictions"
            value={data.topPredictions?.length || 0}
            color="#e91e63"
            onClick={() => setViewMode("topPredictions")}
            active={viewMode === "topPredictions"}
          />
        </div>
      </div>

      {/* ========== FILTERS ========== */}
      <div
        style={{
          display: "flex",
          gap: "12px",
          marginBottom: "20px",
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        {/* Prize Filter */}
        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          <span style={{ fontSize: "13px", fontWeight: "bold" }}>
            ₹5000 Count:
          </span>
          {["all", "3", "2", "1", "0"].map((val) => (
            <button
              key={val}
              onClick={() => setPrizeFilter(val)}
              style={{
                padding: "6px 12px",
                borderRadius: "6px",
                border:
                  prizeFilter === val ? "2px solid #e91e63" : "1px solid #ddd",
                background: prizeFilter === val ? "#fce4ec" : "#fff",
                cursor: "pointer",
                fontWeight: prizeFilter === val ? "bold" : "normal",
              }}
            >
              {val === "all" ? "All" : `${val}/3`}
            </button>
          ))}
        </div>

        {/* Urgency Filter */}
        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          <span style={{ fontSize: "13px", fontWeight: "bold" }}>Urgency:</span>
          {["all", "critical", "high", "medium", "low", "upcoming"].map(
            (val) => (
              <button
                key={val}
                onClick={() => setUrgencyFilter(val)}
                style={{
                  padding: "6px 12px",
                  borderRadius: "6px",
                  border:
                    urgencyFilter === val
                      ? `2px solid ${urgencyColors[val] || "#666"}`
                      : "1px solid #ddd",
                  background:
                    urgencyFilter === val
                      ? urgencyColors[val] || "#666"
                      : "#fff",
                  color: urgencyFilter === val ? "#fff" : "#333",
                  cursor: "pointer",
                  fontWeight: urgencyFilter === val ? "bold" : "normal",
                  fontSize: "12px",
                  textTransform: "capitalize",
                }}
              >
                {val}
              </button>
            ),
          )}
        </div>

        {/* Search */}
        <input
          type="text"
          placeholder="Search number..."
          value={searchNumber}
          onChange={(e) => setSearchNumber(e.target.value)}
          style={{
            padding: "8px 14px",
            borderRadius: "8px",
            border: "1px solid #ddd",
            marginLeft: "auto",
            width: "150px",
          }}
        />
      </div>

      {/* ========== RESULTS HEADER ========== */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "16px",
        }}
      >
        <h3 style={{ margin: 0 }}>{listTitle}</h3>
      </div>

      {/* ========== MAIN TABLE ========== */}
      {viewMode === "common" || viewMode === "topPredictions" ? (
        <CommonComparisonTable
          data={currentList}
          urgencyColors={urgencyColors}
          prizeColors={prizeColors}
        />
      ) : (
        <SingleDbTable
          data={currentList}
          urgencyColors={urgencyColors}
          prizeColors={prizeColors}
          dbName={viewMode === "oldDb" ? "LotteryData" : "LotteryDataNew"}
        />
      )}

      {/* ========== TOP ₹5000 CARDS ========== */}
      {viewMode === "topPredictions" && (
        <div style={{ marginTop: "30px" }}>
          <h3 style={{ color: "#c2185b" }}>
            🏆 Top Numbers with ₹5000 Prize History (Both DBs)
          </h3>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
              gap: "16px",
              marginTop: "16px",
            }}
          >
            {currentList.slice(0, 30).map((item) => (
              <TopPredictionCard
                key={item.number}
                item={item}
                urgencyColors={urgencyColors}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ========== HELPER COMPONENTS ==========
function LoadingSpinner() {
  return (
    <p style={{ textAlign: "center", padding: "60px" }}>
      ⏳ Loading balance comparison...
    </p>
  );
}

function ErrorDisplay({ error }) {
  return (
    <div
      style={{
        padding: "40px",
        textAlign: "center",
        background: "#ffebee",
        borderRadius: "10px",
        margin: "20px",
      }}
    >
      <h3 style={{ color: "#c62828" }}>❌ Error</h3>
      <p>{error}</p>
    </div>
  );
}

function CycleInfoMini({ label, data, isCurrent }) {
  if (!data) return <div style={{ color: "#999" }}>{label}: —</div>;

  return (
    <div style={{ background: "#fff", padding: "8px", borderRadius: "6px" }}>
      <div style={{ fontWeight: "bold", marginBottom: "4px" }}>{label}</div>
      {isCurrent ? (
        <>
          <div style={{ fontSize: "11px" }}>
            Day: <strong>{data.currentDay}</strong>
          </div>
          <div style={{ fontSize: "10px", color: "#666" }}>
            {data.startDate}
          </div>
        </>
      ) : (
        <>
          <div style={{ fontSize: "11px" }}>
            <strong>{data.totalDays}</strong> days
          </div>
          <div style={{ fontSize: "10px", color: "#666" }}>
            {data.startDate}
          </div>
        </>
      )}
    </div>
  );
}

function ComparisonBadge({ label, value, color, onClick, active }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "12px 20px",
        borderRadius: "10px",
        background: active ? color : "#fff",
        color: active ? "#fff" : color,
        border: `2px solid ${color}`,
        cursor: "pointer",
        fontWeight: "bold",
        textAlign: "center",
        minWidth: "140px",
        transition: "all 0.2s ease",
      }}
    >
      <div style={{ fontSize: "28px" }}>{value}</div>
      <div style={{ fontSize: "11px" }}>{label}</div>
    </div>
  );
}

function CommonComparisonTable({ data, urgencyColors, prizeColors }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}
      >
        <thead>
          <tr style={{ background: "#f5f5f5" }}>
            <th style={thStyle}>Number</th>
            <th style={thStyle}>Total ₹5000</th>
            <th style={{ ...thStyle, background: "#fff3e0" }}>Old DB - C2</th>
            <th style={{ ...thStyle, background: "#fff3e0" }}>Old DB - C3</th>
            <th style={{ ...thStyle, background: "#fff3e0" }}>Old DB - C4</th>
            <th style={{ ...thStyle, background: "#fff3e0" }}>Old Urgency</th>
            <th style={{ ...thStyle, background: "#e8f5e9" }}>New DB - C2</th>
            <th style={{ ...thStyle, background: "#e8f5e9" }}>New DB - C3</th>
            <th style={{ ...thStyle, background: "#e8f5e9" }}>New DB - C4</th>
            <th style={{ ...thStyle, background: "#e8f5e9" }}>New Urgency</th>
            <th style={thStyle}>Avg Day</th>
          </tr>
        </thead>
        <tbody>
          {data.slice(0, 300).map((item, idx) => (
            <tr
              key={item.number}
              style={{
                background: idx % 2 === 0 ? "#fff" : "#f9f9f9",
                borderLeft: `4px solid ${item.combined.totalPrize5000Appearances >= 4 ? "#e91e63" : item.combined.totalPrize5000Appearances >= 2 ? "#9c27b0" : "#ccc"}`,
              }}
            >
              <td style={tdStyle}>
                <span style={numberBadge}>{item.number}</span>
              </td>
              <td style={tdStyle}>
                <Prize5000Badge
                  count={item.combined.totalPrize5000Appearances}
                  max={6}
                />
              </td>
              {/* Old DB */}
              <td style={{ ...tdStyle, background: "#fff3e011" }}>
                <CycleCell data={item.old?.cycle2} />
              </td>
              <td style={{ ...tdStyle, background: "#fff3e011" }}>
                <CycleCell data={item.old?.cycle3} />
              </td>
              <td style={{ ...tdStyle, background: "#fff3e011" }}>
                <CycleCell data={item.old?.cycle4} />
              </td>
              <td style={{ ...tdStyle, background: "#fff3e011" }}>
                <UrgencyBadge
                  urgency={item.old?.prediction.urgency}
                  colors={urgencyColors}
                />
              </td>
              {/* New DB */}
              <td style={{ ...tdStyle, background: "#e8f5e911" }}>
                <CycleCell data={item.new?.cycle2} />
              </td>
              <td style={{ ...tdStyle, background: "#e8f5e911" }}>
                <CycleCell data={item.new?.cycle3} />
              </td>
              <td style={{ ...tdStyle, background: "#e8f5e911" }}>
                <CycleCell data={item.new?.cycle4} />
              </td>
              <td style={{ ...tdStyle, background: "#e8f5e911" }}>
                <UrgencyBadge
                  urgency={item.new?.prediction.urgency}
                  colors={urgencyColors}
                />
              </td>
              <td style={tdStyle}>
                <strong>{item.combined.avgOfAvgDays || "—"}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.length > 300 && (
        <p style={{ color: "#666", marginTop: "10px", fontSize: "12px" }}>
          Showing 300 of {data.length}. Use filters or search to narrow down.
        </p>
      )}
    </div>
  );
}

function SingleDbTable({ data, urgencyColors, prizeColors, dbName }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}
      >
        <thead>
          <tr style={{ background: "#f5f5f5" }}>
            <th style={thStyle}>Number</th>
            <th style={thStyle}>₹5000 Count</th>
            <th style={thStyle}>Cycle 2</th>
            <th style={thStyle}>Cycle 3</th>
            <th style={thStyle}>Cycle 4</th>
            <th style={thStyle}>Avg Day</th>
            <th style={thStyle}>Range</th>
            <th style={thStyle}>Urgency</th>
            <th style={thStyle}>Days Overdue</th>
          </tr>
        </thead>
        <tbody>
          {data.slice(0, 300).map((item, idx) => (
            <tr
              key={item.number}
              style={{
                background: idx % 2 === 0 ? "#fff" : "#f9f9f9",
                borderLeft: `4px solid ${urgencyColors[item.prediction?.urgency] || "#ccc"}`,
              }}
            >
              <td style={tdStyle}>
                <span style={numberBadge}>{item.number}</span>
              </td>
              <td style={tdStyle}>
                <Prize5000Badge count={item.prize5000?.count || 0} max={3} />
              </td>
              <td style={tdStyle}>
                <CycleCell data={item.cycle2} />
              </td>
              <td style={tdStyle}>
                <CycleCell data={item.cycle3} />
              </td>
              <td style={tdStyle}>
                <CycleCell data={item.cycle4} />
              </td>
              <td style={tdStyle}>
                <strong>{item.stats?.avgDay || "—"}</strong>
              </td>
              <td style={tdStyle}>
                {item.stats?.range !== null ? (
                  <span
                    style={{
                      padding: "2px 6px",
                      borderRadius: "8px",
                      background:
                        item.stats.range <= 3
                          ? "#4caf50"
                          : item.stats.range <= 10
                            ? "#ff9800"
                            : "#f44336",
                      color: "#fff",
                      fontSize: "10px",
                    }}
                  >
                    ±{item.stats.range}
                  </span>
                ) : (
                  "—"
                )}
              </td>
              <td style={tdStyle}>
                <UrgencyBadge
                  urgency={item.prediction?.urgency}
                  colors={urgencyColors}
                />
              </td>
              <td style={tdStyle}>
                {item.prediction?.daysOverdue !== null ? (
                  <span
                    style={{
                      color:
                        item.prediction.daysOverdue > 0 ? "#d32f2f" : "#4caf50",
                      fontWeight: "bold",
                    }}
                  >
                    {item.prediction.daysOverdue > 0
                      ? `+${item.prediction.daysOverdue}`
                      : "0"}
                  </span>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.length > 300 && (
        <p style={{ color: "#666", marginTop: "10px", fontSize: "12px" }}>
          Showing 300 of {data.length}. Use filters or search to narrow down.
        </p>
      )}
    </div>
  );
}

function CycleCell({ data }) {
  if (!data) return <span style={{ color: "#ccc" }}>—</span>;

  return (
    <div>
      <div>
        <strong>D{data.day}</strong>
      </div>
      <div style={{ fontSize: "9px", color: "#666" }}>{data.date}</div>
      {data.in5000 && (
        <span style={{ color: "#e91e63", fontSize: "9px", fontWeight: "bold" }}>
          ★₹5000
        </span>
      )}
    </div>
  );
}

function UrgencyBadge({ urgency, colors }) {
  if (!urgency) return <span style={{ color: "#ccc" }}>—</span>;

  return (
    <span
      style={{
        padding: "2px 6px",
        borderRadius: "8px",
        background: colors[urgency] || "#9e9e9e",
        color: "#fff",
        fontSize: "9px",
        fontWeight: "bold",
        textTransform: "uppercase",
      }}
    >
      {urgency}
    </span>
  );
}

function Prize5000Badge({ count, max }) {
  const colors = {
    6: "#c2185b",
    5: "#d81b60",
    4: "#e91e63",
    3: "#e91e63",
    2: "#9c27b0",
    1: "#673ab7",
    0: "#9e9e9e",
  };

  return (
    <span
      style={{
        padding: "3px 8px",
        borderRadius: "10px",
        background: colors[count] || "#9e9e9e",
        color: "#fff",
        fontSize: "10px",
        fontWeight: "bold",
      }}
    >
      {count}/{max}
    </span>
  );
}

function TopPredictionCard({ item, urgencyColors }) {
  return (
    <div
      style={{
        padding: "16px",
        background: "#fff",
        borderRadius: "12px",
        border: `2px solid ${item.combined.totalPrize5000Appearances >= 4 ? "#e91e63" : "#9c27b0"}`,
        boxShadow: "0 3px 10px rgba(0,0,0,0.1)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "12px",
        }}
      >
        <span style={{ ...numberBadge, fontSize: "20px" }}>{item.number}</span>
        <Prize5000Badge
          count={item.combined.totalPrize5000Appearances}
          max={6}
        />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "12px",
          fontSize: "11px",
        }}
      >
        {/* Old DB */}
        <div
          style={{
            padding: "10px",
            background: "#fff3e0",
            borderRadius: "8px",
          }}
        >
          <div
            style={{
              fontWeight: "bold",
              marginBottom: "6px",
              color: "#e65100",
            }}
          >
            LotteryData
          </div>
          <div>
            C2: Day {item.old?.cycle2?.day || "—"}{" "}
            {item.old?.cycle2?.in5000 && "★"}
          </div>
          <div>
            C3: Day {item.old?.cycle3?.day || "—"}{" "}
            {item.old?.cycle3?.in5000 && "★"}
          </div>
          <div>
            C4: Day {item.old?.cycle4?.day || "—"}{" "}
            {item.old?.cycle4?.in5000 && "★"}
          </div>
          <div style={{ marginTop: "6px" }}>
            <UrgencyBadge
              urgency={item.old?.prediction.urgency}
              colors={urgencyColors}
            />
          </div>
        </div>

        {/* New DB */}
        <div
          style={{
            padding: "10px",
            background: "#e8f5e9",
            borderRadius: "8px",
          }}
        >
          <div
            style={{
              fontWeight: "bold",
              marginBottom: "6px",
              color: "#2e7d32",
            }}
          >
            LotteryDataNew
          </div>
          <div>
            C2: Day {item.new?.cycle2?.day || "—"}{" "}
            {item.new?.cycle2?.in5000 && "★"}
          </div>
          <div>
            C3: Day {item.new?.cycle3?.day || "—"}{" "}
            {item.new?.cycle3?.in5000 && "★"}
          </div>
          <div>
            C4: Day {item.new?.cycle4?.day || "—"}{" "}
            {item.new?.cycle4?.in5000 && "★"}
          </div>
          <div style={{ marginTop: "6px" }}>
            <UrgencyBadge
              urgency={item.new?.prediction.urgency}
              colors={urgencyColors}
            />
          </div>
        </div>
      </div>

      <div
        style={{
          marginTop: "12px",
          padding: "8px",
          background: "#f5f5f5",
          borderRadius: "6px",
          fontSize: "11px",
        }}
      >
        <strong>Combined Avg Day: {item.combined.avgOfAvgDays || "—"}</strong>
      </div>
    </div>
  );
}

// ========== STYLES ==========
const thStyle = {
  padding: "10px 6px",
  textAlign: "left",
  borderBottom: "2px solid #ddd",
  fontWeight: "bold",
  fontSize: "10px",
  position: "sticky",
  top: 0,
  background: "#f5f5f5",
};

const tdStyle = {
  padding: "8px 6px",
  borderBottom: "1px solid #eee",
  verticalAlign: "middle",
};

const numberBadge = {
  fontFamily: "monospace",
  fontWeight: "bold",
  fontSize: "14px",
  background: "#f0f0f0",
  padding: "4px 10px",
  borderRadius: "6px",
};
