// src/BacktrackPage.jsx
import React, { useEffect, useState, useMemo } from "react";

// ─── constants ───────────────────────────────────────────────────────────────
const PRIZE_COLORS = {
  5000: "#e91e63",
  2000: "#9c27b0",
  1000: "#673ab7",
  500: "#3f51b5",
  200: "#2196f3",
  100: "#00bcd4",
};

const PAGE_SIZE = 200; // numbers per page in flat view

const ENDPOINTS = {
  old: "http://localhost:5000/api/cycles/backtrack/lotterydata",
  new: "http://localhost:5000/api/cycles/backtrack/lotterydatanew",
};

// ─── tiny style helpers ───────────────────────────────────────────────────────
const card = (extra = {}) => ({
  background: "#fff",
  borderRadius: "12px",
  padding: "16px 20px",
  boxShadow: "0 2px 10px rgba(0,0,0,0.08)",
  ...extra,
});

const tag = (color, extra = {}) => ({
  display: "inline-block",
  background: color,
  color: "#fff",
  padding: "2px 8px",
  borderRadius: "4px",
  fontSize: "11px",
  fontFamily: "monospace",
  fontWeight: "700",
  ...extra,
});

const btn = (bg, extra = {}) => ({
  padding: "8px 16px",
  background: bg,
  color: "#fff",
  border: "none",
  borderRadius: "8px",
  cursor: "pointer",
  fontWeight: "600",
  fontSize: "13px",
  ...extra,
});

const thS = {
  padding: "10px 12px",
  textAlign: "left",
  borderBottom: "2px solid #ddd",
  background: "#e3f2fd",
  fontWeight: "700",
  fontSize: "13px",
};

const tdS = {
  padding: "10px 12px",
  borderBottom: "1px solid #eee",
  verticalAlign: "top",
  fontSize: "13px",
};

// ─── component ────────────────────────────────────────────────────────────────
export default function BacktrackPage() {
  const [source, setSource] = useState("new");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // cycle selection
  const [selectedCycle, setSelectedCycle] = useState(null); // cycleNumber

  // view toggle inside a cycle
  const [viewMode, setViewMode] = useState("flat"); // "flat" | "byDay"

  // flat-view filters
  const [searchNum, setSearchNum] = useState("");
  const [filterPrize, setFilterPrize] = useState("all");
  const [page, setPage] = useState(0);

  // byDay expand
  const [expandedDay, setExpandedDay] = useState(null);

  // ── load ───────────────────────────────────────────────────────────────────
  function load(which) {
    setSource(which);
    setData(null);
    setLoading(true);
    setError(null);
    setSelectedCycle(null);
    setSearchNum("");
    setFilterPrize("all");
    setPage(0);
    setExpandedDay(null);

    fetch(ENDPOINTS[which])
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }

  useEffect(() => {
    load("new");
  }, []);

  // auto-select latest cycle when data loads
  useEffect(() => {
    if (data?.cycles?.length) {
      const latest = data.cycles[data.cycles.length - 1].cycleNumber;
      setSelectedCycle(latest);
    }
  }, [data]);

  // reset page when filters change
  useEffect(() => {
    setPage(0);
  }, [searchNum, filterPrize, selectedCycle, viewMode]);

  // ── derived ────────────────────────────────────────────────────────────────
  const cycle = useMemo(
    () => data?.cycles?.find((c) => c.cycleNumber === selectedCycle) || null,
    [data, selectedCycle],
  );

  const availablePrizes = useMemo(() => {
    if (!cycle) return [];
    const set = new Set(cycle.backtrackOrder.map((x) => x.prize));
    return [...set].sort((a, b) => b - a);
  }, [cycle]);

  const filteredBacktrack = useMemo(() => {
    if (!cycle) return [];
    return cycle.backtrackOrder.filter((item) => {
      const matchNum = searchNum ? item.number.includes(searchNum) : true;
      const matchPrize =
        filterPrize !== "all" ? String(item.prize) === filterPrize : true;
      return matchNum && matchPrize;
    });
  }, [cycle, searchNum, filterPrize]);

  const pagedBacktrack = useMemo(
    () => filteredBacktrack.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
    [filteredBacktrack, page],
  );

  const totalPages = Math.ceil(filteredBacktrack.length / PAGE_SIZE);

  // ── render ─────────────────────────────────────────────────────────────────
  if (loading)
    return (
      <div style={{ textAlign: "center", padding: "60px", fontSize: "18px" }}>
        ⏳ Loading backtrack data…
      </div>
    );

  if (error)
    return (
      <div style={{ textAlign: "center", padding: "60px", color: "red" }}>
        ❌ {error}
      </div>
    );

  if (!data) return null;

  return (
    <div
      style={{
        padding: "24px",
        fontFamily: "Arial, sans-serif",
        maxWidth: "1300px",
        margin: "0 auto",
      }}
    >
      {/* ── Page Title ── */}
      <h2 style={{ marginBottom: "6px" }}>
        ⏪ Backtrack — New Numbers (Last → First)
      </h2>
      <p style={{ color: "#666", marginBottom: "20px", fontSize: "14px" }}>
        Numbers that appeared <strong>for the first time</strong> in each cycle,
        listed from the
        <strong> most recent discovery back to the very first</strong>.
      </p>

      {/* ── Source Selector ── */}
      <div style={{ display: "flex", gap: "10px", marginBottom: "24px" }}>
        {["old", "new"].map((s) => (
          <button
            key={s}
            onClick={() => load(s)}
            style={{
              ...btn(source === s ? "#1565C0" : "#90a4ae"),
              opacity: 1,
            }}
          >
            {s === "old" ? "📦 LotteryData (Old)" : "🆕 LotteryDataNew"}
          </button>
        ))}
      </div>

      {/* ── Summary Cards ── */}
      <div
        style={{
          display: "flex",
          gap: "14px",
          flexWrap: "wrap",
          marginBottom: "28px",
        }}
      >
        {[
          { label: "Total Cycles", value: data.summary.totalCycles },
          { label: "Completed", value: data.summary.completedCycles },
          { label: "In Progress", value: data.summary.incompleteCycles },
          { label: "First Day", value: data.summary.firstDay },
          { label: "Last Day", value: data.summary.lastDay },
        ].map((item) => (
          <div
            key={item.label}
            style={{
              ...card({
                background: "#f0f4ff",
                minWidth: "130px",
                textAlign: "center",
              }),
            }}
          >
            <div
              style={{ fontSize: "22px", fontWeight: "bold", color: "#1565C0" }}
            >
              {item.value}
            </div>
            <div style={{ fontSize: "12px", color: "#777", marginTop: "4px" }}>
              {item.label}
            </div>
          </div>
        ))}
      </div>

      {/* ── Cycle Tabs ── */}
      <div
        style={{
          display: "flex",
          gap: "8px",
          flexWrap: "wrap",
          marginBottom: "24px",
          padding: "14px",
          background: "#f5f5f5",
          borderRadius: "12px",
        }}
      >
        <span
          style={{
            fontSize: "13px",
            fontWeight: "bold",
            color: "#555",
            alignSelf: "center",
            marginRight: "4px",
          }}
        >
          Select Cycle:
        </span>
        {data.cycles.map((c) => (
          <button
            key={c.cycleNumber}
            onClick={() => {
              setSelectedCycle(c.cycleNumber);
              setSearchNum("");
              setFilterPrize("all");
              setPage(0);
              setExpandedDay(null);
            }}
            style={{
              padding: "6px 14px",
              borderRadius: "20px",
              border:
                selectedCycle === c.cycleNumber
                  ? "2px solid #1565C0"
                  : "1px solid #ccc",
              background:
                selectedCycle === c.cycleNumber
                  ? "#1565C0"
                  : c.isComplete
                    ? "#e8f5e9"
                    : "#fff8e1",
              color: selectedCycle === c.cycleNumber ? "#fff" : "#333",
              cursor: "pointer",
              fontWeight: "600",
              fontSize: "13px",
            }}
          >
            {c.isComplete ? "✅" : "🔄"} Cycle {c.cycleNumber}
          </button>
        ))}
      </div>

      {/* ── Cycle Detail ── */}
      {cycle && (
        <div
          style={card({
            border: cycle.isComplete
              ? "2px solid #4CAF50"
              : "2px solid #FF9800",
          })}
        >
          {/* Header */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "10px",
              marginBottom: "16px",
            }}
          >
            <h3 style={{ margin: 0 }}>
              {cycle.isComplete ? "✅" : "🔄"} Cycle {cycle.cycleNumber}
              <span
                style={{
                  fontSize: "13px",
                  fontWeight: "normal",
                  color: "#777",
                  marginLeft: "10px",
                }}
              >
                {cycle.startDate} → {cycle.endDate || "ongoing"}
              </span>
            </h3>
            <span
              style={{
                background: cycle.isComplete ? "#4CAF50" : "#FF9800",
                color: "#fff",
                padding: "4px 14px",
                borderRadius: "20px",
                fontSize: "12px",
                fontWeight: "bold",
              }}
            >
              {cycle.isComplete ? "Complete" : "In Progress"}
            </span>
          </div>

          {/* Stats Row */}
          <div
            style={{
              display: "flex",
              gap: "20px",
              flexWrap: "wrap",
              marginBottom: "16px",
            }}
          >
            {[
              {
                label: "Unique Numbers",
                value: `${cycle.totalUniqueNumbers.toLocaleString()} / 10,000`,
              },
              {
                label: "Remaining",
                value: cycle.remainingNumbers.toLocaleString(),
                red: !cycle.isComplete,
              },
              { label: "Total Days", value: cycle.totalDays },
              { label: "Start", value: cycle.startDate || "—" },
              { label: "End", value: cycle.endDate || "—" },
            ].map((s) => (
              <div key={s.label}>
                <div style={{ fontSize: "11px", color: "#888" }}>{s.label}</div>
                <div
                  style={{
                    fontWeight: "bold",
                    color: s.red ? "#e53935" : "#222",
                  }}
                >
                  {s.value}
                </div>
              </div>
            ))}
          </div>

          {/* Progress Bar */}
          <div
            style={{
              background: "#e0e0e0",
              borderRadius: "10px",
              height: "10px",
              overflow: "hidden",
              marginBottom: "6px",
            }}
          >
            <div
              style={{
                width: `${(cycle.totalUniqueNumbers / 10000) * 100}%`,
                background: cycle.isComplete ? "#4CAF50" : "#FF9800",
                height: "100%",
                borderRadius: "10px",
                transition: "width 0.5s",
              }}
            />
          </div>
          <div
            style={{
              fontSize: "12px",
              color: "#777",
              textAlign: "right",
              marginBottom: "20px",
            }}
          >
            {((cycle.totalUniqueNumbers / 10000) * 100).toFixed(2)}% complete
          </div>

          {/* Prize Summary */}
          {cycle.prizes?.length > 0 && (
            <div
              style={{
                marginBottom: "20px",
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
                🏆 Prize Category Progress
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "10px",
                }}
              >
                {cycle.prizes.map((p) => (
                  <div key={p.prize}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        fontSize: "13px",
                        marginBottom: "3px",
                      }}
                    >
                      <span
                        style={{
                          fontWeight: "600",
                          color: PRIZE_COLORS[p.prize] || "#333",
                        }}
                      >
                        ₹{p.prize} {p.isComplete && "✅"}
                      </span>
                      <span style={{ color: "#555" }}>
                        {p.totalUniqueNumbers.toLocaleString()} / 10,000 &nbsp;(
                        {p.percentComplete}%)&nbsp;
                        <span style={{ color: "#e53935" }}>
                          {!p.isComplete &&
                            `— ${p.remainingNumbers.toLocaleString()} left`}
                        </span>
                      </span>
                    </div>
                    <div
                      style={{
                        background: "#e0e0e0",
                        borderRadius: "8px",
                        height: "7px",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${p.percentComplete}%`,
                          background: PRIZE_COLORS[p.prize] || "#673ab7",
                          height: "100%",
                        }}
                      />
                    </div>
                    <div
                      style={{
                        fontSize: "11px",
                        color: "#999",
                        marginTop: "2px",
                      }}
                    >
                      Start: {p.startDate || "—"} | End:{" "}
                      {p.endDate || "ongoing"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* View Mode Toggle */}
          <div
            style={{
              display: "flex",
              gap: "10px",
              marginBottom: "20px",
              flexWrap: "wrap",
            }}
          >
            <button
              onClick={() => setViewMode("flat")}
              style={btn(viewMode === "flat" ? "#1565C0" : "#90a4ae")}
            >
              🔢 Flat Backtrack List
            </button>
            <button
              onClick={() => setViewMode("byDay")}
              style={btn(viewMode === "byDay" ? "#1565C0" : "#90a4ae")}
            >
              📅 By Day (Reversed)
            </button>
          </div>

          {/* ════════════════════════════════════════════════
              VIEW MODE: FLAT LIST (last-new → first-new)
          ════════════════════════════════════════════════ */}
          {viewMode === "flat" && (
            <div>
              {/* Filters */}
              <div
                style={{
                  display: "flex",
                  gap: "12px",
                  flexWrap: "wrap",
                  marginBottom: "16px",
                  alignItems: "center",
                }}
              >
                <input
                  type="text"
                  placeholder="🔍 Search number (e.g. 0123)"
                  value={searchNum}
                  onChange={(e) => setSearchNum(e.target.value.trim())}
                  style={{
                    padding: "8px 12px",
                    borderRadius: "8px",
                    border: "1px solid #ccc",
                    fontSize: "13px",
                    width: "220px",
                  }}
                />

                <select
                  value={filterPrize}
                  onChange={(e) => setFilterPrize(e.target.value)}
                  style={{
                    padding: "8px 12px",
                    borderRadius: "8px",
                    border: "1px solid #ccc",
                    fontSize: "13px",
                  }}
                >
                  <option value="all">All Prizes</option>
                  {availablePrizes.map((p) => (
                    <option key={p} value={String(p)}>
                      ₹{p}
                    </option>
                  ))}
                </select>

                <span style={{ fontSize: "13px", color: "#555" }}>
                  Showing{" "}
                  <strong>{filteredBacktrack.length.toLocaleString()}</strong>{" "}
                  numbers
                  {(searchNum || filterPrize !== "all") &&
                    ` (filtered from ${cycle.backtrackOrder.length.toLocaleString()})`}
                </span>

                {(searchNum || filterPrize !== "all") && (
                  <button
                    onClick={() => {
                      setSearchNum("");
                      setFilterPrize("all");
                    }}
                    style={btn("#e53935", {
                      padding: "6px 12px",
                      fontSize: "12px",
                    })}
                  >
                    ✕ Clear Filters
                  </button>
                )}
              </div>

              {/* Table */}
              {filteredBacktrack.length === 0 ? (
                <div
                  style={{
                    color: "#888",
                    textAlign: "center",
                    padding: "30px",
                  }}
                >
                  No numbers match your filters.
                </div>
              ) : (
                <>
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
                          <th style={thS}>#</th>
                          <th style={thS}>Number</th>
                          <th style={thS}>Prize</th>
                          <th style={thS}>First Seen On</th>
                          <th style={thS}>Chronological Position</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pagedBacktrack.map((item, idx) => {
                          const globalIdx = page * PAGE_SIZE + idx + 1; // rank in filtered list
                          return (
                            <tr
                              key={idx}
                              style={{
                                background: idx % 2 === 0 ? "#fff" : "#f9f9f9",
                              }}
                            >
                              <td
                                style={{ ...tdS, color: "#999", width: "60px" }}
                              >
                                {globalIdx}
                              </td>
                              <td style={tdS}>
                                <span
                                  style={tag(
                                    PRIZE_COLORS[item.prize] || "#673ab7",
                                    { fontSize: "14px", padding: "4px 10px" },
                                  )}
                                >
                                  {item.number}
                                </span>
                              </td>
                              <td style={tdS}>
                                <span
                                  style={tag(
                                    PRIZE_COLORS[item.prize] || "#673ab7",
                                  )}
                                >
                                  ₹{item.prize}
                                </span>
                              </td>
                              <td style={{ ...tdS, fontFamily: "monospace" }}>
                                {item.date}
                              </td>
                              <td style={{ ...tdS, color: "#555" }}>
                                {/* position = original chronological rank */}#
                                {item.position.toLocaleString()}
                                {" of "}
                                {cycle.totalUniqueNumbers.toLocaleString()}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div
                      style={{
                        display: "flex",
                        gap: "8px",
                        justifyContent: "center",
                        marginTop: "16px",
                        flexWrap: "wrap",
                      }}
                    >
                      <button
                        disabled={page === 0}
                        onClick={() => setPage(0)}
                        style={btn("#607d8b", {
                          opacity: page === 0 ? 0.4 : 1,
                          padding: "6px 12px",
                        })}
                      >
                        ««
                      </button>
                      <button
                        disabled={page === 0}
                        onClick={() => setPage((p) => p - 1)}
                        style={btn("#607d8b", {
                          opacity: page === 0 ? 0.4 : 1,
                          padding: "6px 12px",
                        })}
                      >
                        ‹ Prev
                      </button>

                      {/* page numbers — show window of 5 */}
                      {Array.from({ length: totalPages }, (_, i) => i)
                        .filter((i) => Math.abs(i - page) <= 2)
                        .map((i) => (
                          <button
                            key={i}
                            onClick={() => setPage(i)}
                            style={btn(i === page ? "#1565C0" : "#e0e0e0", {
                              color: i === page ? "#fff" : "#333",
                              padding: "6px 12px",
                            })}
                          >
                            {i + 1}
                          </button>
                        ))}

                      <button
                        disabled={page >= totalPages - 1}
                        onClick={() => setPage((p) => p + 1)}
                        style={btn("#607d8b", {
                          opacity: page >= totalPages - 1 ? 0.4 : 1,
                          padding: "6px 12px",
                        })}
                      >
                        Next ›
                      </button>
                      <button
                        disabled={page >= totalPages - 1}
                        onClick={() => setPage(totalPages - 1)}
                        style={btn("#607d8b", {
                          opacity: page >= totalPages - 1 ? 0.4 : 1,
                          padding: "6px 12px",
                        })}
                      >
                        »»
                      </button>

                      <span
                        style={{
                          alignSelf: "center",
                          fontSize: "13px",
                          color: "#666",
                        }}
                      >
                        Page {page + 1} of {totalPages}
                        &nbsp;({filteredBacktrack.length.toLocaleString()}{" "}
                        total)
                      </span>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ════════════════════════════════════════════════
              VIEW MODE: BY DAY (newest day first)
          ════════════════════════════════════════════════ */}
          {viewMode === "byDay" && (
            <div>
              <div
                style={{
                  marginBottom: "12px",
                  fontSize: "13px",
                  color: "#555",
                }}
              >
                📅 <strong>{cycle.reversedDailyProgress.length}</strong> days
                shown (most recent first). Click a day to expand its new
                numbers.
              </div>

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
                      <th style={thS}>Date</th>
                      <th style={thS}>New Numbers That Day</th>
                      <th style={thS}>Running Total (at that day)</th>
                      <th style={thS}>Numbers</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cycle.reversedDailyProgress.map((day, idx) => {
                      const dayKey = `${cycle.cycleNumber}-${day.date}`;
                      const isOpen = expandedDay === dayKey;

                      return (
                        <React.Fragment key={dayKey}>
                          <tr
                            style={{
                              background: idx % 2 === 0 ? "#fff" : "#f9f9f9",
                            }}
                          >
                            <td
                              style={{
                                ...tdS,
                                fontFamily: "monospace",
                                fontWeight: "600",
                              }}
                            >
                              {day.date}
                            </td>
                            <td style={tdS}>
                              <span
                                style={{ color: "#4CAF50", fontWeight: "bold" }}
                              >
                                +{day.count.toLocaleString()}
                              </span>
                            </td>
                            <td style={tdS}>
                              {/* We don't have running total in reverse, so just show count */}
                              {day.count.toLocaleString()} new on this date
                            </td>
                            <td style={tdS}>
                              {day.numbersAdded.length > 0 ? (
                                <button
                                  onClick={() =>
                                    setExpandedDay(isOpen ? null : dayKey)
                                  }
                                  style={btn(isOpen ? "#e53935" : "#673ab7", {
                                    padding: "4px 12px",
                                    fontSize: "12px",
                                  })}
                                >
                                  {isOpen
                                    ? "Hide"
                                    : `View ${day.numbersAdded.length}`}
                                </button>
                              ) : (
                                <span style={{ color: "#bbb" }}>—</span>
                              )}
                            </td>
                          </tr>

                          {isOpen && (
                            <tr>
                              <td
                                colSpan={4}
                                style={{
                                  padding: "16px",
                                  background: "#f3e5f5",
                                  borderBottom: "1px solid #ddd",
                                }}
                              >
                                {/* Flat numbers for this day */}
                                <div
                                  style={{
                                    fontWeight: "bold",
                                    marginBottom: "10px",
                                  }}
                                >
                                  New numbers on {day.date} — reversed order (
                                  {day.numbersAdded.length} total):
                                </div>
                                <div
                                  style={{
                                    display: "flex",
                                    flexWrap: "wrap",
                                    gap: "5px",
                                    marginBottom: "16px",
                                  }}
                                >
                                  {day.numbersAdded
                                    .slice(0, 300)
                                    .map((x, i) => (
                                      <span
                                        key={i}
                                        style={tag(
                                          PRIZE_COLORS[x.prize] || "#673ab7",
                                          {
                                            fontSize: "12px",
                                            padding: "3px 8px",
                                          },
                                        )}
                                      >
                                        {x.number}
                                      </span>
                                    ))}
                                  {day.numbersAdded.length > 300 && (
                                    <span
                                      style={{
                                        fontSize: "12px",
                                        color: "#666",
                                        alignSelf: "center",
                                      }}
                                    >
                                      …+{day.numbersAdded.length - 300} more
                                    </span>
                                  )}
                                </div>

                                {/* By prize breakdown */}
                                {day.byPrize &&
                                  Object.keys(day.byPrize).length > 0 && (
                                    <div>
                                      <div
                                        style={{
                                          fontWeight: "bold",
                                          marginBottom: "8px",
                                          fontSize: "13px",
                                        }}
                                      >
                                        By Prize:
                                      </div>
                                      {Object.entries(day.byPrize)
                                        .sort((a, b) => b[0] - a[0])
                                        .map(([prize, nums]) => (
                                          <div
                                            key={prize}
                                            style={{ marginBottom: "10px" }}
                                          >
                                            <span
                                              style={{
                                                fontWeight: "700",
                                                color:
                                                  PRIZE_COLORS[prize] || "#333",
                                                fontSize: "13px",
                                              }}
                                            >
                                              ₹{prize} (+{nums.length}):
                                            </span>
                                            <div
                                              style={{
                                                display: "flex",
                                                flexWrap: "wrap",
                                                gap: "4px",
                                                marginTop: "5px",
                                              }}
                                            >
                                              {nums
                                                .slice(0, 100)
                                                .map((n, i) => (
                                                  <span
                                                    key={i}
                                                    style={tag(
                                                      PRIZE_COLORS[prize] ||
                                                        "#673ab7",
                                                    )}
                                                  >
                                                    {n}
                                                  </span>
                                                ))}
                                              {nums.length > 100 && (
                                                <span
                                                  style={{
                                                    fontSize: "11px",
                                                    color: "#666",
                                                  }}
                                                >
                                                  …+{nums.length - 100} more
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
            </div>
          )}
        </div>
      )}
    </div>
  );
}
