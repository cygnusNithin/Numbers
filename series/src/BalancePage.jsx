// src/BalancePage.jsx
import React, { useEffect, useState, useMemo } from "react";

const DB_LABELS = {
  old: "📁 LotteryData",
  new: "📁 LotteryDataNew",
};

const DB_COLORS = {
  old: { primary: "#2563eb", light: "#eff6ff", border: "#93c5fd" },
  new: { primary: "#7c3aed", light: "#f5f3ff", border: "#c4b5fd" },
};

const PRED_COLORS = {
  HIGH: { bg: "#dcfce7", border: "#4ade80", text: "#14532d", label: "🟢 HIGH" },
  MEDIUM: {
    bg: "#fef9c3",
    border: "#facc15",
    text: "#713f12",
    label: "🟡 MEDIUM",
  },
  LOW: { bg: "#ffedd5", border: "#fb923c", text: "#7c2d12", label: "🟠 LOW" },
  NEW: { bg: "#f3f4f6", border: "#d1d5db", text: "#374151", label: "⚪ NEW" },
};

const PAGE_SIZE = 100;

// ── hook ──────────────────────────────────────────────────────────────────────
function useBalance(dbKey) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function load() {
    setLoading(true);
    setError(null);
    setData(null);
    fetch(`http://localhost:5000/api/cycles/balance/${dbKey}`)
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

  return { data, loading, error, load };
}

// ── main ──────────────────────────────────────────────────────────────────────
export default function BalancePage() {
  const oldDB = useBalance("old");
  const newDB = useBalance("new");

  useEffect(() => {
    oldDB.load();
    newDB.load();
  }, []);

  const bothLoaded = oldDB.data && newDB.data;

  return (
    <div
      style={{ padding: 20, fontFamily: "Arial, sans-serif", maxWidth: 1600 }}
    >
      <h2 style={{ marginBottom: 6 }}>⚖️ Cycle 5 Balance Numbers</h2>
      <p style={{ color: "#6b7280", fontSize: 13, marginBottom: 20 }}>
        Numbers <strong>not yet appeared</strong> in cycle 5, compared against
        the top prize category (Prize 5000) from cycles 2–4.
      </p>

      {/* Reload buttons */}
      <div
        style={{ display: "flex", gap: 10, marginBottom: 24, flexWrap: "wrap" }}
      >
        <button
          onClick={oldDB.load}
          disabled={oldDB.loading}
          style={actionBtn(DB_COLORS.old.primary, oldDB.loading)}
        >
          {oldDB.loading ? "⏳ Loading…" : "🔄 Reload LotteryData"}
        </button>
        <button
          onClick={newDB.load}
          disabled={newDB.loading}
          style={actionBtn(DB_COLORS.new.primary, newDB.loading)}
        >
          {newDB.loading ? "⏳ Loading…" : "🔄 Reload LotteryDataNew"}
        </button>
        <button
          onClick={() => {
            oldDB.load();
            newDB.load();
          }}
          disabled={oldDB.loading || newDB.loading}
          style={actionBtn("#059669", oldDB.loading || newDB.loading)}
        >
          🔄 Reload Both
        </button>
      </div>

      {/* Side-by-side panels */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 20,
          marginBottom: 28,
        }}
      >
        <BalancePanel db={oldDB} dbKey="old" color={DB_COLORS.old} />
        <BalancePanel db={newDB} dbKey="new" color={DB_COLORS.new} />
      </div>

      {/* Cross DB comparison */}
      {bothLoaded && (
        <CrossBalanceComparison oldData={oldDB.data} newData={newDB.data} />
      )}
    </div>
  );
}

// ── single DB balance panel ───────────────────────────────────────────────────
function BalancePanel({ db, dbKey, color }) {
  const [tab, setTab] = useState("topPrize");
  const [filterPred, setFilterPred] = useState("ALL");
  const [filterTop, setFilterTop] = useState("ALL"); // ALL | 3 | 2 | 1 | 0
  const [filterSearch, setSearch] = useState("");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    if (!db.data?.balanceList) return [];
    return db.data.balanceList.filter((n) => {
      if (filterPred !== "ALL" && n.prediction !== filterPred) return false;
      if (filterSearch && !n.number.includes(filterSearch.trim())) return false;
      if (filterTop !== "ALL" && n.topPrizeCount !== Number(filterTop))
        return false;
      return true;
    });
  }, [db.data, filterPred, filterSearch, filterTop]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div
      style={{
        border: `2px solid ${color.border}`,
        borderRadius: 14,
        padding: 18,
        background: color.light,
        minWidth: 0,
      }}
    >
      <h3 style={{ margin: "0 0 14px", color: color.primary, fontSize: 16 }}>
        {DB_LABELS[dbKey]}
      </h3>

      {db.loading && (
        <p style={{ textAlign: "center", padding: 30, color: "#9ca3af" }}>
          ⏳ Loading balance numbers…
        </p>
      )}
      {db.error && <p style={{ color: "red" }}>❌ {db.error}</p>}

      {db.data && (
        <>
          {/* C5 Status bar */}
          <div
            style={{
              background: "#fff",
              border: `1px solid ${color.border}`,
              borderRadius: 10,
              padding: 12,
              marginBottom: 14,
            }}
          >
            <div
              style={{
                fontWeight: "bold",
                fontSize: 13,
                color: color.primary,
                marginBottom: 8,
              }}
            >
              ⚙️ Cycle 5 Status
            </div>
            <div
              style={{
                display: "flex",
                gap: 16,
                flexWrap: "wrap",
                fontSize: 12,
              }}
            >
              <span>
                📅 Start: <b>{db.data.c5Status.startDate || "—"}</b>
              </span>
              <span>
                📅 Last: <b>{db.data.c5Status.lastDate || "—"}</b>
              </span>
              <span>
                ⏱ Days: <b>{db.data.c5Status.totalDays}</b>
              </span>
              <span>
                ✅ Seen:{" "}
                <b>
                  {db.data.c5Status.totalUniqueNumbers.toLocaleString()}/10000
                </b>
              </span>
              <span style={{ color: "#e65100", fontWeight: "bold" }}>
                ⚖️ Balance: {db.data.c5Status.balanceCount.toLocaleString()}
              </span>
              <span style={{ color: "#7c3aed" }}>
                🏆 Top Prize seen: <b>{db.data.c5Status.topPrizeSeenCount}</b>
              </span>
            </div>

            {/* Overall progress bar */}
            <div
              style={{
                marginTop: 10,
                background: "#e0e0e0",
                borderRadius: 8,
                height: 10,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${(db.data.c5Status.totalUniqueNumbers / 10000) * 100}%`,
                  background: color.primary,
                  height: "100%",
                  borderRadius: 8,
                  transition: "width 0.4s",
                }}
              />
            </div>
            <div
              style={{
                fontSize: 11,
                color: "#6b7280",
                textAlign: "right",
                marginTop: 3,
              }}
            >
              {((db.data.c5Status.totalUniqueNumbers / 10000) * 100).toFixed(2)}
              % complete
            </div>
          </div>

          {/* Summary stat chips */}
          <div
            style={{
              display: "flex",
              gap: 8,
              flexWrap: "wrap",
              marginBottom: 14,
            }}
          >
            {[
              {
                label: "⚖️ Total balance",
                value: db.data.summary.totalBalance,
                bg: "#f3f4f6",
              },
              {
                label: `🏆 Top ${db.data.topPrize} all 3`,
                value: db.data.summary.topPrizeAll3,
                bg: "#ddd6fe",
              },
              {
                label: `🏆 Top ${db.data.topPrize} 2/3`,
                value: db.data.summary.topPrizeAny2,
                bg: "#ede9fe",
              },
              {
                label: `🏆 Top ${db.data.topPrize} 1/3`,
                value: db.data.summary.topPrizeAny1,
                bg: "#f5f3ff",
              },
              {
                label: "🟢 HIGH",
                value: db.data.summary.highPrediction,
                bg: "#dcfce7",
              },
              {
                label: "🟡 MEDIUM",
                value: db.data.summary.mediumPrediction,
                bg: "#fef9c3",
              },
              {
                label: "🟠 LOW",
                value: db.data.summary.lowPrediction,
                bg: "#ffedd5",
              },
              {
                label: "⚪ NEW (never seen)",
                value: db.data.summary.newNumbers,
                bg: "#f3f4f6",
              },
            ].map((s) => (
              <div
                key={s.label}
                style={{
                  background: s.bg,
                  borderRadius: 8,
                  padding: "8px 12px",
                  textAlign: "center",
                  minWidth: 90,
                  boxShadow: "0 1px 4px rgba(0,0,0,0.05)",
                }}
              >
                <div style={{ fontSize: 18, fontWeight: "bold" }}>
                  {s.value.toLocaleString()}
                </div>
                <div style={{ fontSize: 10, color: "#555", marginTop: 2 }}>
                  {s.label}
                </div>
              </div>
            ))}
          </div>

          {/* Prize summary bars */}
          <PrizeSummaryBars
            prizeSummary={db.data.prizeSummary}
            topPrize={db.data.topPrize}
            color={color}
          />

          {/* Tabs */}
          <div
            style={{
              display: "flex",
              gap: 0,
              flexWrap: "wrap",
              borderBottom: `2px solid ${color.border}`,
              marginBottom: 14,
              marginTop: 16,
            }}
          >
            {[
              { key: "topPrize", label: `🏆 Top Prize ${db.data.topPrize}` },
              {
                key: "high",
                label: `🟢 HIGH (${db.data.summary.highPrediction})`,
              },
              {
                key: "all",
                label: `📋 All Balance (${db.data.summary.totalBalance.toLocaleString()})`,
              },
            ].map((t) => (
              <button
                key={t.key}
                onClick={() => {
                  setTab(t.key);
                  setPage(0);
                }}
                style={{
                  padding: "7px 14px",
                  border: "none",
                  borderBottom:
                    tab === t.key
                      ? `3px solid ${color.primary}`
                      : "3px solid transparent",
                  background: "transparent",
                  fontWeight: tab === t.key ? "bold" : "normal",
                  color: tab === t.key ? color.primary : "#6b7280",
                  cursor: "pointer",
                  fontSize: 12,
                  whiteSpace: "nowrap",
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Tab: Top Prize */}
          {tab === "topPrize" && (
            <TopPrizeBalanceTab data={db.data} color={color} />
          )}

          {/* Tab: HIGH */}
          {tab === "high" && (
            <ChipGrid
              numbers={db.data.balanceList.filter(
                (n) => n.prediction === "HIGH",
              )}
              color={color}
              topPrize={db.data.topPrize}
            />
          )}

          {/* Tab: All — full table with filters */}
          {tab === "all" && (
            <>
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  flexWrap: "wrap",
                  marginBottom: 10,
                  padding: 10,
                  background: "#fff",
                  borderRadius: 8,
                  border: "1px solid #e5e7eb",
                }}
              >
                <input
                  placeholder="Search number…"
                  value={filterSearch}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setPage(0);
                  }}
                  style={inputStyle}
                />
                <select
                  value={filterPred}
                  onChange={(e) => {
                    setFilterPred(e.target.value);
                    setPage(0);
                  }}
                  style={inputStyle}
                >
                  <option value="ALL">All predictions</option>
                  {Object.entries(PRED_COLORS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v.label}
                    </option>
                  ))}
                </select>
                <select
                  value={filterTop}
                  onChange={(e) => {
                    setFilterTop(e.target.value);
                    setPage(0);
                  }}
                  style={inputStyle}
                >
                  <option value="ALL">All top prize</option>
                  <option value="3">🏆 In top prize all 3 cycles</option>
                  <option value="2">🏆 In top prize 2 cycles</option>
                  <option value="1">🏆 In top prize 1 cycle</option>
                  <option value="0">Not in top prize</option>
                </select>
                <span
                  style={{ fontSize: 12, color: "#555", alignSelf: "center" }}
                >
                  {filtered.length.toLocaleString()} numbers
                </span>
                <button
                  style={{ ...smBtn("#6b7280"), fontSize: 11 }}
                  onClick={() => {
                    setFilterPred("ALL");
                    setSearch("");
                    setFilterTop("ALL");
                    setPage(0);
                  }}
                >
                  Reset
                </button>
              </div>

              <div style={{ overflowX: "auto" }}>
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    fontSize: 12,
                  }}
                >
                  <thead>
                    <tr style={{ background: "#f3f4f6" }}>
                      {[
                        "Number",
                        `Top ${db.data.topPrize}`,
                        "Prediction",
                        "Avg Day",
                        "Appeared In",
                        "C2 Day",
                        "C2 Date",
                        "C2 Prize",
                        "C3 Day",
                        "C3 Date",
                        "C3 Prize",
                        "C4 Day",
                        "C4 Date",
                        "C4 Prize",
                      ].map((h) => (
                        <th key={h} style={thStyle}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((n, i) => {
                      const pc = PRED_COLORS[n.prediction];
                      return (
                        <tr
                          key={n.number}
                          style={{
                            background:
                              n.topPrizeCount === 3
                                ? "#faf5ff"
                                : n.topPrizeCount === 2
                                  ? "#f5f3ff"
                                  : n.prediction === "HIGH"
                                    ? "#f0fdf4"
                                    : i % 2 === 0
                                      ? "#fff"
                                      : "#fafafa",
                          }}
                        >
                          <td
                            style={{
                              ...tdStyle,
                              fontFamily: "monospace",
                              fontWeight: "bold",
                            }}
                          >
                            {n.number}
                          </td>

                          {/* Top prize badge */}
                          <td style={{ ...tdStyle, textAlign: "center" }}>
                            {n.topPrizeCount > 0 ? (
                              <span
                                style={{
                                  background:
                                    n.topPrizeCount === 3
                                      ? "#ddd6fe"
                                      : n.topPrizeCount === 2
                                        ? "#ede9fe"
                                        : "#f5f3ff",
                                  border: "1px solid #a78bfa",
                                  color: "#4c1d95",
                                  padding: "1px 8px",
                                  borderRadius: 10,
                                  fontSize: 11,
                                  fontWeight: "bold",
                                }}
                              >
                                🏆 {n.topPrizeCount}/3
                              </span>
                            ) : (
                              <span style={{ color: "#d1d5db", fontSize: 11 }}>
                                —
                              </span>
                            )}
                          </td>

                          <td style={tdStyle}>
                            <span
                              style={{
                                background: pc.bg,
                                border: `1px solid ${pc.border}`,
                                color: pc.text,
                                padding: "1px 7px",
                                borderRadius: 10,
                                fontSize: 10,
                              }}
                            >
                              {pc.label}
                            </span>
                          </td>
                          <td style={{ ...tdStyle, textAlign: "center" }}>
                            {n.avgDay ?? "—"}
                          </td>
                          <td style={{ ...tdStyle, textAlign: "center" }}>
                            {n.appearedIn}/3
                          </td>

                          <CycleCell entry={n.c2} color={color} />
                          <CycleCell entry={n.c3} color={color} />
                          <CycleCell entry={n.c4} color={color} />
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={page}
                totalPages={totalPages}
                setPage={setPage}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}

// ── Top Prize Balance Tab ─────────────────────────────────────────────────────
function TopPrizeBalanceTab({ data, color }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* All 3 cycles — strongest */}
      <BalanceGroup
        title={`⭐ Balance numbers in Top Prize ${data.topPrize} — ALL 3 cycles (C2, C3, C4)`}
        subtitle={`${data.topPrizeAll3.length} numbers. Were under Prize ${data.topPrize} in every reference cycle. Highest priority.`}
        numbers={data.topPrizeAll3}
        bg="#ddd6fe"
        border="#7c3aed"
        textColor="#4c1d95"
        defaultOpen
        topPrize={data.topPrize}
      />

      {/* 2 of 3 cycles */}
      <BalanceGroup
        title={`🏆 Balance numbers in Top Prize ${data.topPrize} — 2 of 3 cycles`}
        subtitle={`${data.topPrizeAny2.length} numbers. Good signal — under top prize in 2 reference cycles.`}
        numbers={data.topPrizeAny2}
        bg="#ede9fe"
        border="#a78bfa"
        textColor="#5b21b6"
        topPrize={data.topPrize}
      />

      {/* HIGH but not in top prize */}
      <BalanceGroup
        title={`🟢 HIGH prediction — NOT in Top Prize ${data.topPrize}`}
        subtitle={`${data.highNotTop.length} numbers appeared in all 3 cycles (C2, C3, C4) but under other prize categories.`}
        numbers={data.highNotTop}
        bg="#dcfce7"
        border="#4ade80"
        textColor="#14532d"
        topPrize={data.topPrize}
      />
    </div>
  );
}

// ── Balance Group (collapsible chip grid) ─────────────────────────────────────
function BalanceGroup({
  title,
  subtitle,
  numbers,
  bg,
  border,
  textColor,
  defaultOpen = false,
  topPrize,
}) {
  const [show, setShow] = useState(defaultOpen);
  const [search, setSearch] = useState("");
  const [pg, setPg] = useState(0);
  const PSIZE = 200;

  const filtered = search.trim()
    ? numbers.filter((n) => n.number.includes(search.trim()))
    : numbers;

  const totalPgs = Math.ceil(filtered.length / PSIZE);
  const slice = filtered.slice(pg * PSIZE, (pg + 1) * PSIZE);

  useEffect(() => {
    setPg(0);
  }, [search]);

  return (
    <div
      style={{
        background: bg,
        border: `1px solid ${border}`,
        borderRadius: 10,
        padding: 14,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <div>
          <div style={{ fontWeight: "bold", color: textColor, fontSize: 13 }}>
            {title}
          </div>
          <div
            style={{
              fontSize: 11,
              color: textColor,
              opacity: 0.8,
              marginTop: 2,
            }}
          >
            {subtitle}
          </div>
        </div>
        <button
          onClick={() => setShow((s) => !s)}
          style={{
            padding: "5px 14px",
            borderRadius: 6,
            background: textColor,
            color: "#fff",
            border: "none",
            cursor: "pointer",
            fontSize: 12,
          }}
        >
          {show ? "▲ Hide" : "▼ Show"}
        </button>
      </div>

      {show && (
        <div style={{ marginTop: 10 }}>
          {/* Search within group */}
          <input
            placeholder="Search in this group…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ ...inputStyle, marginBottom: 8, width: 160 }}
          />
          <div style={{ fontSize: 11, color: textColor, marginBottom: 6 }}>
            Showing {slice.length} of {filtered.length}
          </div>

          {/* Chips */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 6,
              maxHeight: 300,
              overflowY: "auto",
            }}
          >
            {slice.map((n) => {
              const pc = PRED_COLORS[n.prediction];
              return (
                <div
                  key={n.number}
                  title={`${n.prediction} | Avg Day: ${n.avgDay ?? "?"} | Top Prize ${topPrize}: ${n.topPrizeCount}/3 cycles | C2:${n.c2?.prize ?? "—"} C3:${n.c3?.prize ?? "—"} C4:${n.c4?.prize ?? "—"}`}
                  style={{
                    background: "#fff",
                    border: `1px solid ${border}`,
                    borderRadius: 6,
                    padding: "4px 8px",
                    fontSize: 11,
                    fontFamily: "monospace",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    minWidth: 56,
                    cursor: "default",
                  }}
                >
                  <span style={{ fontWeight: "bold", color: textColor }}>
                    {n.number}
                  </span>
                  <span style={{ fontSize: 9, color: "#6b7280" }}>
                    {pc.label}
                  </span>
                  <span style={{ fontSize: 9, color: "#6b7280" }}>
                    ~d{n.avgDay ?? "?"} | 🏆{n.topPrizeCount}/3
                  </span>
                </div>
              );
            })}
          </div>
          <Pagination page={pg} totalPages={totalPgs} setPage={setPg} small />
        </div>
      )}
    </div>
  );
}

// ── Prize Summary Bars ────────────────────────────────────────────────────────
function PrizeSummaryBars({ prizeSummary, topPrize, color }) {
  const [show, setShow] = useState(false);
  const maxSeen = Math.max(...prizeSummary.map((p) => p.seenInC5), 1);

  return (
    <div>
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          marginBottom: 6,
        }}
      >
        <span style={{ fontSize: 13, fontWeight: "bold", color: "#374151" }}>
          📊 Per-Prize Category — Cycle 5 Progress
        </span>
        <button
          style={{ ...smBtn(color.primary), fontSize: 11 }}
          onClick={() => setShow((s) => !s)}
        >
          {show ? "Hide" : "Show"}
        </button>
      </div>

      {show && (
        <div
          style={{
            background: "#fff",
            border: `1px solid ${color.border}`,
            borderRadius: 10,
            padding: 12,
          }}
        >
          {prizeSummary.map((p) => (
            <div key={p.prize} style={{ marginBottom: 10 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 12,
                  marginBottom: 3,
                }}
              >
                <span
                  style={{
                    fontWeight: p.top ? "bold" : "normal",
                    color: p.top ? "#7c3aed" : "#374151",
                  }}
                >
                  {p.top ? "🏆 " : ""}Prize {p.prize}
                  {p.top && (
                    <span
                      style={{ fontSize: 10, color: "#7c3aed", marginLeft: 4 }}
                    >
                      (TOP)
                    </span>
                  )}
                </span>
                <span style={{ color: "#6b7280" }}>
                  Seen in C5: <b>{p.seenInC5}</b>
                  {p.inAll3Cycles > 0 && (
                    <span style={{ color: "#7c3aed", marginLeft: 8 }}>
                      🏆 {p.inAll3Cycles} balance nums in all 3 cycles
                    </span>
                  )}
                </span>
              </div>
              <div
                style={{
                  background: "#e0e0e0",
                  borderRadius: 6,
                  height: 8,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${(p.seenInC5 / maxSeen) * 100}%`,
                    background: p.top ? "#7c3aed" : color.primary,
                    height: "100%",
                    borderRadius: 6,
                    transition: "width 0.4s",
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Chip Grid (simple) ────────────────────────────────────────────────────────
function ChipGrid({ numbers, color, topPrize }) {
  const [pg, setPg] = useState(0);
  const PSIZE = 200;
  const total = Math.ceil(numbers.length / PSIZE);
  const slice = numbers.slice(pg * PSIZE, (pg + 1) * PSIZE);

  if (!numbers.length)
    return (
      <p style={{ color: "#9ca3af", fontSize: 13 }}>
        No numbers in this group.
      </p>
    );

  return (
    <div>
      <div style={{ fontSize: 12, color: "#555", marginBottom: 6 }}>
        {numbers.length.toLocaleString()} numbers
      </div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 5,
          maxHeight: 280,
          overflowY: "auto",
        }}
      >
        {slice.map((n) => {
          const pc = PRED_COLORS[n.prediction];
          return (
            <div
              key={n.number}
              title={`${n.prediction} | Avg Day: ${n.avgDay ?? "?"} | Top ${topPrize}: ${n.topPrizeCount}/3`}
              style={{
                background: n.topPrizeCount > 0 ? "#f5f3ff" : pc.bg,
                border:
                  n.topPrizeCount > 0
                    ? "1px solid #a78bfa"
                    : `1px solid ${pc.border}`,
                borderRadius: 5,
                padding: "3px 7px",
                fontSize: 11,
                fontFamily: "monospace",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
              }}
            >
              <span
                style={{
                  fontWeight: "bold",
                  color: n.topPrizeCount > 0 ? "#4c1d95" : pc.text,
                }}
              >
                {n.number}
              </span>
              <span style={{ fontSize: 9, color: "#6b7280" }}>
                ~d{n.avgDay ?? "?"}
              </span>
              {n.topPrizeCount > 0 && (
                <span style={{ fontSize: 9, color: "#7c3aed" }}>
                  🏆{n.topPrizeCount}/3
                </span>
              )}
            </div>
          );
        })}
      </div>
      <Pagination page={pg} totalPages={total} setPage={setPg} small />
    </div>
  );
}

// ── Cross DB Balance Comparison ───────────────────────────────────────────────
function CrossBalanceComparison({ oldData, newData }) {
  const [show, setShow] = useState(false);
  const [tab, setTab] = useState("strongest");

  const crossMap = useMemo(() => {
    const newMap = {};
    newData.balanceList.forEach((n) => {
      newMap[n.number] = n;
    });
    return oldData.balanceList
      .filter((n) => newMap[n.number])
      .map((o) => {
        const nw = newMap[o.number];
        return {
          number: o.number,
          oldPred: o.prediction,
          newPred: nw.prediction,
          oldTopCount: o.topPrizeCount,
          newTopCount: nw.topPrizeCount,
          oldAvgDay: o.avgDay,
          newAvgDay: nw.avgDay,
          bothHigh: o.prediction === "HIGH" && nw.prediction === "HIGH",
          topIn3Both: o.topPrizeCount === 3 && nw.topPrizeCount === 3,
          topIn2Both: o.topPrizeCount >= 2 && nw.topPrizeCount >= 2,
          strongest:
            o.prediction === "HIGH" &&
            nw.prediction === "HIGH" &&
            o.topPrizeCount === 3 &&
            nw.topPrizeCount === 3,
        };
      });
  }, [oldData, newData]);

  const strongest = crossMap.filter((n) => n.strongest);
  const topIn3Both = crossMap.filter((n) => n.topIn3Both && !n.strongest);
  const topIn2Both = crossMap.filter((n) => n.topIn2Both && !n.topIn3Both);
  const bothHigh = crossMap.filter((n) => n.bothHigh && !n.strongest);

  return (
    <div
      style={{
        border: "2px solid #f59e0b",
        borderRadius: 14,
        padding: 20,
        background: "#fffbeb",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 10,
          alignItems: "center",
          flexWrap: "wrap",
          marginBottom: 16,
        }}
      >
        <h3 style={{ margin: 0, color: "#92400e" }}>
          🔀 Cross-DB Balance Comparison
        </h3>
        <button style={smBtn("#d97706")} onClick={() => setShow((s) => !s)}>
          {show ? "▲ Hide" : "▼ Show"}
        </button>
      </div>

      {/* Cross stats */}
      <div
        style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}
      >
        {[
          {
            label: "⭐ Strongest (HIGH + top prize x3 both DBs)",
            value: strongest.length,
            bg: "#dcfce7",
          },
          {
            label: "🏆 Top prize x3 in both DBs",
            value: topIn3Both.length,
            bg: "#ddd6fe",
          },
          {
            label: "🏆 Top prize ≥2 in both DBs",
            value: topIn2Both.length,
            bg: "#ede9fe",
          },
          {
            label: "🟢 HIGH in both DBs",
            value: bothHigh.length,
            bg: "#d1fae5",
          },
          {
            label: "📋 In balance of both DBs",
            value: crossMap.length,
            bg: "#f3f4f6",
          },
        ].map((s) => (
          <div
            key={s.label}
            style={{
              background: s.bg,
              borderRadius: 8,
              padding: "10px 14px",
              textAlign: "center",
              minWidth: 130,
              boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
            }}
          >
            <div style={{ fontSize: 22, fontWeight: "bold" }}>
              {s.value.toLocaleString()}
            </div>
            <div style={{ fontSize: 10, color: "#555", marginTop: 2 }}>
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {show && (
        <>
          {/* Tabs */}
          <div
            style={{
              display: "flex",
              gap: 0,
              borderBottom: "2px solid #fcd34d",
              marginBottom: 16,
            }}
          >
            {[
              { key: "strongest", label: `⭐ Strongest (${strongest.length})` },
              {
                key: "top3both",
                label: `🏆 Top×3 both (${topIn3Both.length})`,
              },
              {
                key: "top2both",
                label: `🏆 Top×2 both (${topIn2Both.length})`,
              },
              { key: "bothhigh", label: `🟢 Both HIGH (${bothHigh.length})` },
              { key: "fulltable", label: `📋 Full Table (${crossMap.length})` },
            ].map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                style={{
                  padding: "7px 14px",
                  border: "none",
                  borderBottom:
                    tab === t.key
                      ? "3px solid #d97706"
                      : "3px solid transparent",
                  background: "transparent",
                  fontWeight: tab === t.key ? "bold" : "normal",
                  color: tab === t.key ? "#92400e" : "#6b7280",
                  cursor: "pointer",
                  fontSize: 12,
                  whiteSpace: "nowrap",
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === "strongest" && (
            <CrossChipGroup
              numbers={strongest}
              bg="#dcfce7"
              border="#4ade80"
              textColor="#14532d"
              label="⭐ STRONGEST"
            />
          )}
          {tab === "top3both" && (
            <CrossChipGroup
              numbers={topIn3Both}
              bg="#ddd6fe"
              border="#7c3aed"
              textColor="#4c1d95"
              label="🏆 TOP×3"
            />
          )}
          {tab === "top2both" && (
            <CrossChipGroup
              numbers={topIn2Both}
              bg="#ede9fe"
              border="#a78bfa"
              textColor="#5b21b6"
              label="🏆 TOP×2"
            />
          )}
          {tab === "bothhigh" && (
            <CrossChipGroup
              numbers={bothHigh}
              bg="#d1fae5"
              border="#34d399"
              textColor="#065f46"
              label="🟢 HIGH"
            />
          )}
          {tab === "fulltable" && (
            <CrossFullTable numbers={crossMap} topPrize={oldData.topPrize} />
          )}
        </>
      )}
    </div>
  );
}

function CrossChipGroup({ numbers, bg, border, textColor, label }) {
  const [pg, setPg] = useState(0);
  const PSIZE = 200;
  const total = Math.ceil(numbers.length / PSIZE);
  const slice = numbers.slice(pg * PSIZE, (pg + 1) * PSIZE);

  return (
    <div
      style={{
        background: bg,
        border: `1px solid ${border}`,
        borderRadius: 10,
        padding: 12,
      }}
    >
      <div
        style={{
          fontWeight: "bold",
          color: textColor,
          marginBottom: 8,
          fontSize: 13,
        }}
      >
        {label} — {numbers.length} numbers (balance in both DBs)
      </div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 5,
          maxHeight: 280,
          overflowY: "auto",
        }}
      >
        {slice.map((n) => (
          <div
            key={n.number}
            title={`OLD: ${n.oldPred} top${n.oldTopCount}/3 avgD${n.oldAvgDay ?? "?"} | NEW: ${n.newPred} top${n.newTopCount}/3 avgD${n.newAvgDay ?? "?"}`}
            style={{
              background: "#fff",
              border: `1px solid ${border}`,
              borderRadius: 5,
              padding: "3px 7px",
              fontSize: 11,
              fontFamily: "monospace",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
            }}
          >
            <span style={{ fontWeight: "bold", color: textColor }}>
              {n.number}
            </span>
            <span style={{ fontSize: 9, color: "#6b7280" }}>
              🏆{n.oldTopCount}/{n.newTopCount}
            </span>
            <span style={{ fontSize: 9, color: "#6b7280" }}>
              ~d{n.oldAvgDay ?? "?"}/{n.newAvgDay ?? "?"}
            </span>
          </div>
        ))}
      </div>
      <Pagination page={pg} totalPages={total} setPage={setPg} small />
    </div>
  );
}

function CrossFullTable({ numbers, topPrize }) {
  const [pg, setPg] = useState(0);
  const total = Math.ceil(numbers.length / PAGE_SIZE);
  const slice = numbers.slice(pg * PAGE_SIZE, (pg + 1) * PAGE_SIZE);

  return (
    <>
      <div style={{ overflowX: "auto" }}>
        <table
          style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}
        >
          <thead>
            <tr style={{ background: "#fef3c7" }}>
              {[
                "Number",
                "OLD Pred",
                `OLD Top ${topPrize}`,
                "OLD Avg Day",
                "NEW Pred",
                `NEW Top ${topPrize}`,
                "NEW Avg Day",
                "Signal",
              ].map((h) => (
                <th key={h} style={thStyle}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.map((n, i) => {
              const op = PRED_COLORS[n.oldPred];
              const np = PRED_COLORS[n.newPred];
              return (
                <tr
                  key={n.number}
                  style={{
                    background: n.strongest
                      ? "#f0fdf4"
                      : n.topIn3Both
                        ? "#faf5ff"
                        : i % 2 === 0
                          ? "#fff"
                          : "#fffbeb",
                  }}
                >
                  <td
                    style={{
                      ...tdStyle,
                      fontFamily: "monospace",
                      fontWeight: "bold",
                    }}
                  >
                    {n.number}
                  </td>
                  <td style={tdStyle}>
                    <span
                      style={{
                        background: op.bg,
                        border: `1px solid ${op.border}`,
                        color: op.text,
                        padding: "1px 6px",
                        borderRadius: 10,
                        fontSize: 10,
                      }}
                    >
                      {op.label}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, textAlign: "center" }}>
                    <TopBadge count={n.oldTopCount} />
                  </td>
                  <td style={{ ...tdStyle, textAlign: "center" }}>
                    {n.oldAvgDay ?? "—"}
                  </td>

                  <td style={tdStyle}>
                    <span
                      style={{
                        background: np.bg,
                        border: `1px solid ${np.border}`,
                        color: np.text,
                        padding: "1px 6px",
                        borderRadius: 10,
                        fontSize: 10,
                      }}
                    >
                      {np.label}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, textAlign: "center" }}>
                    <TopBadge count={n.newTopCount} />
                  </td>
                  <td style={{ ...tdStyle, textAlign: "center" }}>
                    {n.newAvgDay ?? "—"}
                  </td>

                  <td style={{ ...tdStyle, textAlign: "center" }}>
                    {n.strongest ? (
                      <span
                        style={{
                          background: "#dcfce7",
                          border: "1px solid #4ade80",
                          color: "#14532d",
                          padding: "1px 7px",
                          borderRadius: 10,
                          fontSize: 10,
                          fontWeight: "bold",
                        }}
                      >
                        ⭐ STRONGEST
                      </span>
                    ) : n.topIn3Both ? (
                      <span
                        style={{
                          background: "#ddd6fe",
                          border: "1px solid #7c3aed",
                          color: "#4c1d95",
                          padding: "1px 7px",
                          borderRadius: 10,
                          fontSize: 10,
                        }}
                      >
                        🏆 TOP×3
                      </span>
                    ) : n.bothHigh ? (
                      <span
                        style={{
                          background: "#d1fae5",
                          border: "1px solid #34d399",
                          color: "#065f46",
                          padding: "1px 7px",
                          borderRadius: 10,
                          fontSize: 10,
                        }}
                      >
                        🟢 BOTH HIGH
                      </span>
                    ) : (
                      <span style={{ color: "#9ca3af", fontSize: 10 }}>—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pagination page={pg} totalPages={total} setPage={setPg} />
    </>
  );
}

function TopBadge({ count }) {
  if (!count)
    return <span style={{ color: "#d1d5db", fontSize: 11 }}>0/3</span>;
  return (
    <span
      style={{
        background:
          count === 3 ? "#ddd6fe" : count === 2 ? "#ede9fe" : "#f5f3ff",
        border: "1px solid #a78bfa",
        color: "#4c1d95",
        padding: "1px 7px",
        borderRadius: 8,
        fontSize: 11,
        fontWeight: "bold",
      }}
    >
      🏆 {count}/3
    </span>
  );
}

// ── Shared tiny components ────────────────────────────────────────────────────
function CycleCell({ entry, color }) {
  if (!entry)
    return (
      <>
        <td style={{ ...tdStyle, color: "#d1d5db", textAlign: "center" }}>—</td>
        <td style={{ ...tdStyle, color: "#d1d5db" }}>—</td>
        <td style={{ ...tdStyle, color: "#d1d5db" }}>—</td>
      </>
    );
  return (
    <>
      <td
        style={{
          ...tdStyle,
          textAlign: "center",
          color: color.primary,
          fontWeight: "bold",
        }}
      >
        D{entry.day}
      </td>
      <td style={tdStyle}>{entry.date}</td>
      <td style={{ ...tdStyle, color: "#6b7280" }}>{entry.prize}</td>
    </>
  );
}

function Pagination({ page, totalPages, setPage, small }) {
  if (totalPages <= 1) return null;
  const fs = small ? 10 : 12;
  const pad = small ? "2px 7px" : "4px 10px";
  return (
    <div
      style={{
        display: "flex",
        gap: 5,
        marginTop: 10,
        flexWrap: "wrap",
        alignItems: "center",
      }}
    >
      <button
        disabled={page === 0}
        onClick={() => setPage((p) => p - 1)}
        style={{
          padding: pad,
          borderRadius: 5,
          border: "1px solid #ccc",
          cursor: page === 0 ? "not-allowed" : "pointer",
          fontSize: fs,
        }}
      >
        ← Prev
      </button>
      {Array.from({ length: totalPages }, (_, i) => i)
        .filter(
          (i) => i === 0 || i === totalPages - 1 || Math.abs(i - page) <= 2,
        )
        .reduce((acc, i, idx, arr) => {
          if (idx > 0 && i - arr[idx - 1] > 1) acc.push("…");
          acc.push(i);
          return acc;
        }, [])
        .map((item, idx) =>
          item === "…" ? (
            <span key={`d-${idx}`} style={{ color: "#999", fontSize: fs }}>
              …
            </span>
          ) : (
            <button
              key={item}
              onClick={() => setPage(item)}
              style={{
                padding: pad,
                borderRadius: 5,
                fontSize: fs,
                cursor: "pointer",
                border: item === page ? "2px solid #6366f1" : "1px solid #ccc",
                background: item === page ? "#ede9fe" : "#fff",
                fontWeight: item === page ? "bold" : "normal",
              }}
            >
              {item + 1}
            </button>
          ),
        )}
      <button
        disabled={page === totalPages - 1}
        onClick={() => setPage((p) => p + 1)}
        style={{
          padding: pad,
          borderRadius: 5,
          border: "1px solid #ccc",
          cursor: page === totalPages - 1 ? "not-allowed" : "pointer",
          fontSize: fs,
        }}
      >
        Next →
      </button>
    </div>
  );
}

// ── Style helpers ─────────────────────────────────────────────────────────────
const actionBtn = (bg, disabled) => ({
  padding: "8px 18px",
  borderRadius: 10,
  border: "none",
  background: disabled ? "#9ca3af" : bg,
  color: "white",
  fontWeight: "bold",
  fontSize: 13,
  cursor: disabled ? "not-allowed" : "pointer",
});

const smBtn = (bg) => ({
  padding: "5px 12px",
  borderRadius: 6,
  border: "none",
  background: bg,
  color: "white",
  cursor: "pointer",
  fontSize: 12,
  fontWeight: "bold",
});

const inputStyle = {
  padding: "5px 8px",
  borderRadius: 6,
  border: "1px solid #ccc",
  fontSize: 12,
};

const thStyle = {
  padding: "7px 10px",
  textAlign: "left",
  borderBottom: "1px solid #e5e7eb",
  fontWeight: "bold",
  whiteSpace: "nowrap",
};

const tdStyle = {
  padding: "6px 10px",
  borderBottom: "1px solid #f3f4f6",
  verticalAlign: "middle",
};
