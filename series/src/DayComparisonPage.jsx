// src/DayComparisonPage.jsx
import React, { useEffect, useState } from "react";

export default function DayComparisonPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [source, setSource] = useState("new");
  const [viewMode, setViewMode] = useState("exactMatch");
  const [searchNumber, setSearchNumber] = useState("");
  const [selectedDay, setSelectedDay] = useState(null);

  const endpoints = {
    old: "http://localhost:5000/api/day-comparison/lotterydata",
    new: "http://localhost:5000/api/day-comparison/lotterydatanew",
  };

  function load(which) {
    setSource(which);
    setLoading(true);
    setError(null);
    setSearchNumber("");
    setSelectedDay(null);

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

  const tabStyle = (active) => ({
    padding: "10px 16px",
    background: active ? "#673ab7" : "#fff",
    color: active ? "#fff" : "#333",
    border: "2px solid #673ab7",
    borderRadius: "8px",
    cursor: "pointer",
    fontWeight: "bold",
    fontSize: "13px",
  });

  const urgencyColors = {
    critical: "#d32f2f",
    high: "#f57c00",
    medium: "#fbc02d",
    low: "#4caf50",
    upcoming: "#2196f3",
  };

  // Filter functions
  const filterBySearch = (items) => {
    if (!searchNumber) return items;
    return items.filter((item) => item.number.includes(searchNumber));
  };

  return (
    <div
      style={{
        padding: "20px",
        fontFamily: "Arial, sans-serif",
        maxWidth: "1600px",
        margin: "0 auto",
      }}
    >
      <h2>📅 Day-by-Day Cycle Comparison (Cycles 2, 3, 4)</h2>
      <p style={{ color: "#666", marginBottom: "20px" }}>
        Find numbers that appear on the same day across multiple cycles to
        predict Cycle 5
      </p>

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

      {/* Loading/Error */}
      {loading && (
        <p style={{ textAlign: "center", padding: "40px" }}>⏳ Loading...</p>
      )}
      {error && (
        <div
          style={{
            padding: "20px",
            background: "#ffebee",
            borderRadius: "10px",
            color: "#c62828",
          }}
        >
          ❌ {error}
        </div>
      )}

      {!loading && !error && data && (
        <>
          {/* ========== SUMMARY CARDS ========== */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
              gap: "12px",
              marginBottom: "24px",
            }}
          >
            {/* Cycle Info Cards */}
            <div style={cardStyle("#e3f2fd")}>
              <div style={{ fontSize: "12px", color: "#666" }}>Cycle 2</div>
              <div style={{ fontWeight: "bold" }}>
                {data.summary.cycles.cycle2.totalDays} days
              </div>
              <div style={{ fontSize: "11px", color: "#888" }}>
                {data.summary.cycles.cycle2.startDate}
              </div>
            </div>
            <div style={cardStyle("#f3e5f5")}>
              <div style={{ fontSize: "12px", color: "#666" }}>Cycle 3</div>
              <div style={{ fontWeight: "bold" }}>
                {data.summary.cycles.cycle3.totalDays} days
              </div>
              <div style={{ fontSize: "11px", color: "#888" }}>
                {data.summary.cycles.cycle3.startDate}
              </div>
            </div>
            <div style={cardStyle("#fff3e0")}>
              <div style={{ fontSize: "12px", color: "#666" }}>Cycle 4</div>
              <div style={{ fontWeight: "bold" }}>
                {data.summary.cycles.cycle4.totalDays} days
              </div>
              <div style={{ fontSize: "11px", color: "#888" }}>
                {data.summary.cycles.cycle4.startDate}
              </div>
            </div>
            <div style={cardStyle("#e8f5e9")}>
              <div style={{ fontSize: "12px", color: "#666" }}>
                Cycle 5 (Current)
              </div>
              <div style={{ fontWeight: "bold" }}>
                Day {data.summary.cycles.cycle5?.currentDay || 0}
              </div>
              <div style={{ fontSize: "11px", color: "#888" }}>
                Remaining:{" "}
                {data.summary.cycles.cycle5?.numbersRemaining?.toLocaleString()}
              </div>
            </div>
            <div style={cardStyle("#fce4ec")}>
              <div style={{ fontSize: "12px", color: "#666" }}>Avg Cycle</div>
              <div style={{ fontWeight: "bold", color: "#c2185b" }}>
                {data.summary.avgCycleDays} days
              </div>
            </div>
          </div>

          {/* ========== MATCH STATISTICS ========== */}
          <div
            style={{
              padding: "16px",
              background: "#f5f5f5",
              borderRadius: "10px",
              marginBottom: "20px",
            }}
          >
            <h4 style={{ margin: "0 0 12px" }}>
              🎯 Numbers Matching Across Cycles 2, 3, 4
            </h4>
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <MatchBadge
                label="Exact Same Day (All 3)"
                count={data.summary.matches.exactSameDay}
                color="#4caf50"
                active={viewMode === "exactMatch"}
                onClick={() => setViewMode("exactMatch")}
              />
              <MatchBadge
                label="Same Day (2 Cycles)"
                count={data.summary.matches.sameDay2Cycles}
                color="#8bc34a"
                active={viewMode === "sameDay2"}
                onClick={() => setViewMode("sameDay2")}
              />
              <MatchBadge
                label="Within ±1 Day"
                count={data.summary.matches.within1Day}
                color="#03a9f4"
                active={viewMode === "within1"}
                onClick={() => setViewMode("within1")}
              />
              <MatchBadge
                label="Within ±2 Days"
                count={data.summary.matches.within2Days}
                color="#00bcd4"
                active={viewMode === "within2"}
                onClick={() => setViewMode("within2")}
              />
              <MatchBadge
                label="Within ±3 Days"
                count={data.summary.matches.within3Days}
                color="#009688"
                active={viewMode === "within3"}
                onClick={() => setViewMode("within3")}
              />
              <MatchBadge
                label="Within ±5 Days"
                count={data.summary.matches.within5Days}
                color="#607d8b"
                active={viewMode === "within5"}
                onClick={() => setViewMode("within5")}
              />
            </div>
          </div>

          {/* ========== SIMILARITY SCORES ========== */}
          <div
            style={{
              padding: "16px",
              background: "#e8eaf6",
              borderRadius: "10px",
              marginBottom: "20px",
            }}
          >
            <h4 style={{ margin: "0 0 12px" }}>📊 Cycle Similarity Analysis</h4>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                gap: "16px",
              }}
            >
              <SimilarityCard
                title="Cycle 2 vs 3"
                data={data.summary.similarity.cycle2_vs_3}
              />
              <SimilarityCard
                title="Cycle 2 vs 4"
                data={data.summary.similarity.cycle2_vs_4}
              />
              <SimilarityCard
                title="Cycle 3 vs 4"
                data={data.summary.similarity.cycle3_vs_4}
              />
            </div>
          </div>

          {/* ========== VIEW TABS ========== */}
          <div
            style={{
              display: "flex",
              gap: "10px",
              marginBottom: "20px",
              flexWrap: "wrap",
            }}
          >
            <button
              style={tabStyle(viewMode === "exactMatch")}
              onClick={() => setViewMode("exactMatch")}
            >
              ✅ Exact Match
            </button>
            <button
              style={tabStyle(viewMode === "within3")}
              onClick={() => setViewMode("within3")}
            >
              📍 Within 3 Days
            </button>
            <button
              style={tabStyle(viewMode === "dayByDay")}
              onClick={() => setViewMode("dayByDay")}
            >
              📅 Day-by-Day
            </button>
            <button
              style={tabStyle(viewMode === "hotDays")}
              onClick={() => setViewMode("hotDays")}
            >
              🔥 Hot Days
            </button>
            <button
              style={tabStyle(viewMode === "predictions")}
              onClick={() => setViewMode("predictions")}
            >
              🎯 Predictions
            </button>
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

          {/* ========== EXACT MATCH VIEW ========== */}
          {viewMode === "exactMatch" && (
            <div>
              <h3>
                ✅ Numbers Appearing on EXACT Same Day in All 3 Cycles (
                {data.exactSameDay.length})
              </h3>
              <p
                style={{
                  color: "#666",
                  fontSize: "13px",
                  marginBottom: "16px",
                }}
              >
                These numbers appeared on the same day number in Cycles 2, 3,
                and 4. Highly predictable!
              </p>

              {data.exactSameDay.length === 0 ? (
                <p style={{ color: "#999" }}>
                  No numbers found appearing on exact same day in all 3 cycles.
                </p>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table style={tableStyle}>
                    <thead>
                      <tr>
                        <th style={thStyle}>Number</th>
                        <th style={thStyle}>Day</th>
                        <th style={thStyle}>Cycle 2 Date</th>
                        <th style={thStyle}>Cycle 3 Date</th>
                        <th style={thStyle}>Cycle 4 Date</th>
                        <th style={thStyle}>Cycle 5 Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filterBySearch(data.exactSameDay).map((item, idx) => (
                        <tr
                          key={item.number}
                          style={{
                            background: idx % 2 === 0 ? "#fff" : "#f9f9f9",
                          }}
                        >
                          <td style={tdStyle}>
                            <span style={numberBadge}>{item.number}</span>
                          </td>
                          <td style={tdStyle}>
                            <strong
                              style={{ color: "#4caf50", fontSize: "18px" }}
                            >
                              Day {item.avgDay}
                            </strong>
                          </td>
                          <td style={tdStyle}>{item.cycle2.date}</td>
                          <td style={tdStyle}>{item.cycle3.date}</td>
                          <td style={tdStyle}>{item.cycle4.date}</td>
                          <td style={tdStyle}>
                            {item.appearedInCycle5 ? (
                              <span
                                style={{ color: "#4caf50", fontWeight: "bold" }}
                              >
                                ✅ Day {item.cycle5.day}
                              </span>
                            ) : (
                              <span
                                style={{ color: "#f57c00", fontWeight: "bold" }}
                              >
                                ⏳ Expected Day {item.avgDay}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ========== WITHIN 3 DAYS VIEW ========== */}
          {(viewMode === "within1" ||
            viewMode === "within2" ||
            viewMode === "within3" ||
            viewMode === "within5" ||
            viewMode === "sameDay2") && (
            <div>
              <h3>
                {viewMode === "sameDay2" &&
                  `📍 Same Day in 2 Cycles (${data.sameDay2Cycles.length})`}
                {viewMode === "within1" &&
                  `📍 Within ±1 Day (${data.within1Day.length})`}
                {viewMode === "within2" &&
                  `📍 Within ±2 Days (${data.within2Days.length})`}
                {viewMode === "within3" &&
                  `📍 Within ±3 Days (${data.within3Days.length})`}
                {viewMode === "within5" &&
                  `📍 Within ±5 Days (${data.within5Days.length})`}
              </h3>

              <div style={{ overflowX: "auto" }}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={thStyle}>Number</th>
                      <th style={thStyle}>Cycle 2</th>
                      <th style={thStyle}>Cycle 3</th>
                      <th style={thStyle}>Cycle 4</th>
                      <th style={thStyle}>Range</th>
                      <th style={thStyle}>Avg Day</th>
                      <th style={thStyle}>Cycle 5</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filterBySearch(
                      viewMode === "sameDay2"
                        ? data.sameDay2Cycles
                        : viewMode === "within1"
                          ? data.within1Day
                          : viewMode === "within2"
                            ? data.within2Days
                            : viewMode === "within3"
                              ? data.within3Days
                              : data.within5Days,
                    )
                      .slice(0, 200)
                      .map((item, idx) => (
                        <tr
                          key={item.number}
                          style={{
                            background: idx % 2 === 0 ? "#fff" : "#f9f9f9",
                          }}
                        >
                          <td style={tdStyle}>
                            <span style={numberBadge}>{item.number}</span>
                          </td>
                          <td style={tdStyle}>
                            <strong>Day {item.cycle2.day}</strong>
                            <div style={{ fontSize: "11px", color: "#666" }}>
                              {item.cycle2.date}
                            </div>
                          </td>
                          <td style={tdStyle}>
                            <strong>Day {item.cycle3.day}</strong>
                            <div style={{ fontSize: "11px", color: "#666" }}>
                              {item.cycle3.date}
                            </div>
                          </td>
                          <td style={tdStyle}>
                            <strong>Day {item.cycle4.day}</strong>
                            <div style={{ fontSize: "11px", color: "#666" }}>
                              {item.cycle4.date}
                            </div>
                          </td>
                          <td style={tdStyle}>
                            <span
                              style={{
                                padding: "3px 8px",
                                borderRadius: "10px",
                                background:
                                  item.range === 0
                                    ? "#4caf50"
                                    : item.range <= 2
                                      ? "#8bc34a"
                                      : "#ff9800",
                                color: "#fff",
                                fontSize: "12px",
                              }}
                            >
                              ±{item.range}
                            </span>
                          </td>
                          <td style={tdStyle}>
                            <strong>{item.avgDay}</strong>
                          </td>
                          <td style={tdStyle}>
                            {item.appearedInCycle5 ? (
                              <span style={{ color: "#4caf50" }}>
                                ✅ Day {item.cycle5.day}
                              </span>
                            ) : (
                              <span style={{ color: "#f57c00" }}>
                                ⏳ Pending
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ========== DAY-BY-DAY VIEW ========== */}
          {viewMode === "dayByDay" && (
            <div>
              <h3>📅 Day-by-Day Comparison</h3>
              <p
                style={{
                  color: "#666",
                  fontSize: "13px",
                  marginBottom: "16px",
                }}
              >
                See which numbers appeared on each day and find common numbers
                across cycles.
              </p>

              <div
                style={{
                  overflowX: "auto",
                  maxHeight: "600px",
                  overflowY: "auto",
                }}
              >
                <table style={tableStyle}>
                  <thead style={{ position: "sticky", top: 0 }}>
                    <tr>
                      <th style={thStyle}>Day</th>
                      <th style={{ ...thStyle, background: "#e3f2fd" }}>
                        Cycle 2
                      </th>
                      <th style={{ ...thStyle, background: "#f3e5f5" }}>
                        Cycle 3
                      </th>
                      <th style={{ ...thStyle, background: "#fff3e0" }}>
                        Cycle 4
                      </th>
                      <th style={{ ...thStyle, background: "#c8e6c9" }}>
                        Common (All 3)
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.dayByDayComparison.slice(0, 200).map((day) => (
                      <tr
                        key={day.day}
                        style={{
                          background:
                            day.commonInAll3.length > 0 ? "#e8f5e9" : "#fff",
                          cursor: "pointer",
                        }}
                        onClick={() =>
                          setSelectedDay(
                            selectedDay === day.day ? null : day.day,
                          )
                        }
                      >
                        <td style={tdStyle}>
                          <strong>Day {day.day}</strong>
                        </td>
                        <td style={{ ...tdStyle, background: "#e3f2fd33" }}>
                          <div>{day.cycle2.date || "—"}</div>
                          <div style={{ fontSize: "12px", color: "#666" }}>
                            {day.cycle2.count} numbers
                          </div>
                        </td>
                        <td style={{ ...tdStyle, background: "#f3e5f533" }}>
                          <div>{day.cycle3.date || "—"}</div>
                          <div style={{ fontSize: "12px", color: "#666" }}>
                            {day.cycle3.count} numbers
                          </div>
                        </td>
                        <td style={{ ...tdStyle, background: "#fff3e033" }}>
                          <div>{day.cycle4.date || "—"}</div>
                          <div style={{ fontSize: "12px", color: "#666" }}>
                            {day.cycle4.count} numbers
                          </div>
                        </td>
                        <td style={{ ...tdStyle, background: "#c8e6c933" }}>
                          {day.commonInAll3.length > 0 ? (
                            <span
                              style={{
                                padding: "4px 10px",
                                background: "#4caf50",
                                color: "#fff",
                                borderRadius: "12px",
                                fontWeight: "bold",
                              }}
                            >
                              {day.commonInAll3.length} matches
                            </span>
                          ) : (
                            <span style={{ color: "#999" }}>0</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Expanded Day Details */}
              {selectedDay && (
                <DayDetails
                  day={data.dayByDayComparison.find(
                    (d) => d.day === selectedDay,
                  )}
                  onClose={() => setSelectedDay(null)}
                />
              )}
            </div>
          )}

          {/* ========== HOT DAYS VIEW ========== */}
          {viewMode === "hotDays" && (
            <div>
              <h3>🔥 Hot Days - Days with Most Common Numbers</h3>
              <p
                style={{
                  color: "#666",
                  fontSize: "13px",
                  marginBottom: "16px",
                }}
              >
                Days where multiple numbers appeared across all 3 cycles. Great
                for predictions!
              </p>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
                  gap: "16px",
                }}
              >
                {data.hotDays.map((day) => (
                  <div
                    key={day.day}
                    style={{
                      padding: "16px",
                      background: "#fff",
                      borderRadius: "10px",
                      border: "2px solid #4caf50",
                      boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
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
                      <h4 style={{ margin: 0, color: "#333" }}>
                        Day {day.day}
                      </h4>
                      <span
                        style={{
                          padding: "4px 12px",
                          background: "#4caf50",
                          color: "#fff",
                          borderRadius: "20px",
                          fontWeight: "bold",
                        }}
                      >
                        {day.commonInAll3.length} matches
                      </span>
                    </div>

                    <div
                      style={{
                        fontSize: "12px",
                        color: "#666",
                        marginBottom: "12px",
                      }}
                    >
                      <div>
                        C2: {day.cycle2.date} | C3: {day.cycle3.date} | C4:{" "}
                        {day.cycle4.date}
                      </div>
                    </div>

                    <div
                      style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}
                    >
                      {day.commonInAll3.map((num) => (
                        <span key={num} style={numberBadgeSmall}>
                          {num}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ========== PREDICTIONS VIEW ========== */}
          {viewMode === "predictions" && (
            <div>
              <h3>🎯 Predictions for Cycle 5 ({data.predictions.length})</h3>
              <p
                style={{
                  color: "#666",
                  fontSize: "13px",
                  marginBottom: "16px",
                }}
              >
                Based on consistency across Cycles 2, 3, 4. Higher consistency =
                more predictable.
              </p>

              {/* Urgency Summary */}
              <div
                style={{
                  display: "flex",
                  gap: "10px",
                  marginBottom: "16px",
                  flexWrap: "wrap",
                }}
              >
                {Object.entries(data.summary.predictionsCount).map(
                  ([urgency, count]) => (
                    <span
                      key={urgency}
                      style={{
                        padding: "6px 14px",
                        borderRadius: "20px",
                        background: urgencyColors[urgency],
                        color: "#fff",
                        fontWeight: "bold",
                        fontSize: "12px",
                      }}
                    >
                      {urgency.toUpperCase()}: {count}
                    </span>
                  ),
                )}
              </div>

              <div style={{ overflowX: "auto" }}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={thStyle}>Number</th>
                      <th style={thStyle}>Urgency</th>
                      <th style={thStyle}>C2 Day</th>
                      <th style={thStyle}>C3 Day</th>
                      <th style={thStyle}>C4 Day</th>
                      <th style={thStyle}>Avg Day</th>
                      <th style={thStyle}>Range</th>
                      <th style={thStyle}>Consistency</th>
                      <th style={thStyle}>Days Overdue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filterBySearch(data.predictions)
                      .slice(0, 200)
                      .map((item, idx) => (
                        <tr
                          key={item.number}
                          style={{
                            background: idx % 2 === 0 ? "#fff" : "#f9f9f9",
                            borderLeft: `4px solid ${urgencyColors[item.urgency]}`,
                          }}
                        >
                          <td style={tdStyle}>
                            <span style={numberBadge}>{item.number}</span>
                          </td>
                          <td style={tdStyle}>
                            <span
                              style={{
                                padding: "4px 10px",
                                borderRadius: "12px",
                                background: urgencyColors[item.urgency],
                                color: "#fff",
                                fontWeight: "bold",
                                fontSize: "11px",
                                textTransform: "uppercase",
                              }}
                            >
                              {item.urgency}
                            </span>
                          </td>
                          <td style={tdStyle}>{item.cycle2Day}</td>
                          <td style={tdStyle}>{item.cycle3Day}</td>
                          <td style={tdStyle}>{item.cycle4Day}</td>
                          <td style={tdStyle}>
                            <strong>{item.avgDay}</strong>
                          </td>
                          <td style={tdStyle}>{item.predictedDayRange}</td>
                          <td style={tdStyle}>
                            <div
                              style={{
                                width: "60px",
                                height: "8px",
                                background: "#e0e0e0",
                                borderRadius: "4px",
                                overflow: "hidden",
                              }}
                            >
                              <div
                                style={{
                                  width: `${item.consistencyScore}%`,
                                  height: "100%",
                                  background:
                                    item.consistencyScore >= 90
                                      ? "#4caf50"
                                      : item.consistencyScore >= 75
                                        ? "#8bc34a"
                                        : "#ff9800",
                                }}
                              />
                            </div>
                            <span style={{ fontSize: "11px", color: "#666" }}>
                              {item.consistencyScore}%
                            </span>
                          </td>
                          <td style={tdStyle}>
                            <span
                              style={{
                                color:
                                  item.daysOverdue > 0 ? "#d32f2f" : "#4caf50",
                                fontWeight: "bold",
                              }}
                            >
                              {item.daysOverdue > 0
                                ? `+${item.daysOverdue}`
                                : "0"}
                            </span>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ========== HELPER COMPONENTS ==========
function MatchBadge({ label, count, color, active, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "10px 16px",
        borderRadius: "10px",
        background: active ? color : "#fff",
        color: active ? "#fff" : color,
        border: `2px solid ${color}`,
        cursor: "pointer",
        fontWeight: "bold",
        textAlign: "center",
        minWidth: "120px",
      }}
    >
      <div style={{ fontSize: "24px" }}>{count}</div>
      <div style={{ fontSize: "11px" }}>{label}</div>
    </div>
  );
}

function SimilarityCard({ title, data }) {
  return (
    <div style={{ background: "#fff", padding: "12px", borderRadius: "8px" }}>
      <div style={{ fontWeight: "bold", marginBottom: "8px" }}>{title}</div>
      <div style={{ fontSize: "12px", display: "grid", gap: "4px" }}>
        <div>
          Exact Match: <strong>{data.exactMatches}</strong> (
          {data.exactMatchPercent}%)
        </div>
        <div>
          Within ±1 Day: <strong>{data.within1}</strong> ({data.within1Percent}
          %)
        </div>
        <div>
          Within ±3 Days: <strong>{data.within3}</strong> ({data.within3Percent}
          %)
        </div>
        <div>
          Within ±5 Days: <strong>{data.within5}</strong> ({data.within5Percent}
          %)
        </div>
      </div>
    </div>
  );
}

function DayDetails({ day, onClose }) {
  if (!day) return null;

  return (
    <div
      style={{
        marginTop: "20px",
        padding: "20px",
        background: "#fff",
        borderRadius: "10px",
        border: "2px solid #2196f3",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "16px",
        }}
      >
        <h4 style={{ margin: 0 }}>Day {day.day} Details</h4>
        <button
          onClick={onClose}
          style={{
            padding: "6px 12px",
            background: "#f44336",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          Close
        </button>
      </div>

      {day.commonInAll3.length > 0 && (
        <div style={{ marginBottom: "16px" }}>
          <div
            style={{
              fontWeight: "bold",
              color: "#4caf50",
              marginBottom: "8px",
            }}
          >
            ✅ Common in All 3 Cycles ({day.commonInAll3.length}):
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
            {day.commonInAll3.map((num) => (
              <span
                key={num}
                style={{
                  ...numberBadgeSmall,
                  background: "#4caf50",
                  color: "#fff",
                }}
              >
                {num}
              </span>
            ))}
          </div>
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: "16px",
        }}
      >
        <div>
          <div
            style={{
              fontWeight: "bold",
              color: "#1976d2",
              marginBottom: "8px",
            }}
          >
            Cycle 2 ({day.cycle2.count} numbers):
          </div>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "4px",
              maxHeight: "150px",
              overflowY: "auto",
            }}
          >
            {day.cycle2.numbers.map((num) => (
              <span key={num} style={numberBadgeSmall}>
                {num}
              </span>
            ))}
          </div>
        </div>
        <div>
          <div
            style={{
              fontWeight: "bold",
              color: "#7b1fa2",
              marginBottom: "8px",
            }}
          >
            Cycle 3 ({day.cycle3.count} numbers):
          </div>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "4px",
              maxHeight: "150px",
              overflowY: "auto",
            }}
          >
            {day.cycle3.numbers.map((num) => (
              <span key={num} style={numberBadgeSmall}>
                {num}
              </span>
            ))}
          </div>
        </div>
        <div>
          <div
            style={{
              fontWeight: "bold",
              color: "#f57c00",
              marginBottom: "8px",
            }}
          >
            Cycle 4 ({day.cycle4.count} numbers):
          </div>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "4px",
              maxHeight: "150px",
              overflowY: "auto",
            }}
          >
            {day.cycle4.numbers.map((num) => (
              <span key={num} style={numberBadgeSmall}>
                {num}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ========== STYLES ==========
const cardStyle = (bg) => ({
  padding: "12px 16px",
  borderRadius: "10px",
  background: bg,
  boxShadow: "0 2px 6px rgba(0,0,0,0.08)",
});

const tableStyle = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "13px",
};

const thStyle = {
  padding: "12px",
  textAlign: "left",
  borderBottom: "2px solid #ddd",
  fontWeight: "bold",
  background: "#f5f5f5",
  position: "sticky",
  top: 0,
};

const tdStyle = {
  padding: "10px 12px",
  borderBottom: "1px solid #eee",
  verticalAlign: "middle",
};

const numberBadge = {
  fontFamily: "monospace",
  fontWeight: "bold",
  fontSize: "15px",
  background: "#f0f0f0",
  padding: "4px 10px",
  borderRadius: "4px",
};

const numberBadgeSmall = {
  fontFamily: "monospace",
  fontSize: "12px",
  background: "#f0f0f0",
  padding: "3px 8px",
  borderRadius: "4px",
};
