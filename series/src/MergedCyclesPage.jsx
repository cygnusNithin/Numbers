import React, { useEffect, useMemo, useState } from "react";

const API = "http://localhost:5000";

export default function MergedCyclesPage() {
  const [summaryData, setSummaryData] = useState(null);
  const [selectedCycle, setSelectedCycle] = useState(null);
  const [cycleDetail, setCycleDetail] = useState(null);

  const [remainingSearch, setRemainingSearch] = useState("");
  const [tableSearch, setTableSearch] = useState("");
  const [prizeRemainingSearch, setPrizeRemainingSearch] = useState("");

  const [loadingSummary, setLoadingSummary] = useState(false);
  const [loadingCycle, setLoadingCycle] = useState(false);
  const [error, setError] = useState("");

  const [expandedPrize, setExpandedPrize] = useState(null);

  const loadSummary = async () => {
    try {
      setLoadingSummary(true);
      setError("");

      const res = await fetch(`${API}/api/merged-cycles`);
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.details || json.error || "Failed to load cycles");
      }

      setSummaryData(json);

      if (json.cycles?.length) {
        const current =
          json.cycles.find(
            (c) => c.cycleNumber === json.datasetSummary?.currentCycleNumber
          ) || json.cycles[json.cycles.length - 1];

        setSelectedCycle((prev) => prev || current.cycleNumber);
      }
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoadingSummary(false);
    }
  };

  const loadCycleDetail = async (cycleNumber) => {
    if (!cycleNumber) return;

    try {
      setLoadingCycle(true);
      setError("");

      const res = await fetch(`${API}/api/merged-cycles/${cycleNumber}`);
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.details || json.error || "Failed to load cycle detail");
      }

      setCycleDetail(json);
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoadingCycle(false);
    }
  };

  useEffect(() => {
    loadSummary();
  }, []);

  useEffect(() => {
    if (selectedCycle) {
      loadCycleDetail(selectedCycle);
    }
  }, [selectedCycle]);

  const allTimePrizeList = useMemo(() => {
    const stats = summaryData?.currentPrizeCycles || {};
    return Object.entries(stats)
      .map(([prize, data]) => ({ prize: Number(prize), ...data }))
      .sort((a, b) => b.prize - a.prize);
  }, [summaryData]);

  const filteredRemaining = useMemo(() => {
    const list = cycleDetail?.cycle?.remainingNumbers || [];
    const q = remainingSearch.trim();
    if (!q) return list;
    return list.filter((n) => n.includes(q));
  }, [cycleDetail, remainingSearch]);

  const filteredTimeline = useMemo(() => {
    const list = cycleDetail?.cycle?.drawTimeline || [];
    const q = tableSearch.trim().toLowerCase();
    if (!q) return list;

    return list.filter((item) => {
      const newNumsText = (item.newGlobalNumbers || [])
        .map((n) => `${n.number} ${(n.prizes || []).join(",")}`)
        .join(" ")
        .toLowerCase();

      const prizeText = Object.entries(item.prizeUpdates || {})
        .map(([p, d]) => `${p} ${(d.newNumbers || []).join(",")}`)
        .join(" ")
        .toLowerCase();

      return (
        String(item.date || "").toLowerCase().includes(q) ||
        String(item.serialNumber || "").toLowerCase().includes(q) ||
        String(item.recordNumber || "").includes(q) ||
        newNumsText.includes(q) ||
        prizeText.includes(q)
      );
    });
  }, [cycleDetail, tableSearch]);

  const prizeStatsList = useMemo(() => {
    const stats = cycleDetail?.cycle?.prizeStats || {};
    return Object.entries(stats)
      .map(([prize, data]) => ({ prize: Number(prize), ...data }))
      .sort((a, b) => b.prize - a.prize);
  }, [cycleDetail]);

  const getFilteredPrizeRemaining = useMemo(() => {
    const q = prizeRemainingSearch.trim();
    return (list = []) => {
      if (!q) return list;
      return list.filter((n) => n.includes(q));
    };
  }, [prizeRemainingSearch]);

  const renderBadge = (status) => {
    const map = {
      COMPLETED: {
        background: "#dcfce7",
        color: "#166534",
        border: "1px solid #86efac",
      },
      IN_PROGRESS: {
        background: "#dbeafe",
        color: "#1d4ed8",
        border: "1px solid #93c5fd",
      },
    };

    const style = map[status] || {
      background: "#e5e7eb",
      color: "#374151",
      border: "1px solid #d1d5db",
    };

    return (
      <span
        style={{
          background: style.background,
          color: style.color,
          border: style.border,
          padding: "6px 10px",
          borderRadius: 999,
          fontWeight: 700,
          fontSize: 12,
        }}
      >
        {status}
      </span>
    );
  };

  return (
    <div style={styles.page}>
      <div style={styles.hero}>
        <h1 style={styles.title}>Merged Cycles — Global + Prize Blocks</h1>
        <p style={styles.subtitle}>
          All global unique-number cycles combined with current active prize-block cycles.
        </p>
      </div>

      {error ? <div style={styles.errorBox}>{error}</div> : null}

      {summaryData?.datasetSummary && (
        <div style={styles.summaryGrid}>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Total Draws</div>
            <div style={styles.summaryValue}>{summaryData.datasetSummary.totalDraws}</div>
          </div>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Total Cycles</div>
            <div style={styles.summaryValue}>{summaryData.datasetSummary.totalCycles}</div>
          </div>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Completed</div>
            <div style={styles.summaryValue}>{summaryData.datasetSummary.completedCycles}</div>
          </div>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Current Cycle</div>
            <div style={styles.summaryValue}>{summaryData.datasetSummary.currentCycleNumber}</div>
          </div>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Current Remaining</div>
            <div style={styles.summaryValue}>{summaryData.datasetSummary.currentRemainingCount}</div>
          </div>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Current Progress</div>
            <div style={styles.summaryValue}>{summaryData.datasetSummary.currentProgressPercent}%</div>
          </div>
        </div>
      )}

      {/* GLOBAL UNIQUE CYCLES LIST */}
      {summaryData?.cycles?.length > 0 && (
        <div style={styles.card}>
          <h3 style={styles.sectionTitle}>Global Unique Cycles (0000–9999)</h3>
          <div style={styles.cycleRowWrap}>
            {summaryData.cycles.map((cycle) => (
              <button
                key={cycle.cycleNumber}
                onClick={() => setSelectedCycle(cycle.cycleNumber)}
                style={{
                  ...styles.cycleChip,
                  ...(selectedCycle === cycle.cycleNumber
                    ? styles.cycleChipActive
                    : {}),
                }}
              >
                <strong>Cycle {cycle.cycleNumber}</strong>
                <div style={{ marginTop: 4 }}>{renderBadge(cycle.status)}</div>
                <div style={{ marginTop: 6, fontSize: 12, color: "#475569" }}>
                  {cycle.startDate} → {cycle.endDate}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* CURRENT PRIZE BLOCK CYCLES */}
      {allTimePrizeList.length > 0 && (
        <div style={styles.card}>
          <h3 style={styles.sectionTitle}>Current Prize Block Cycles</h3>
          <p style={styles.note}>
            Each prize block runs its own independent cycle (0000–9999). Shows the current active cycle for each prize.
          </p>

          <input
            type="text"
            placeholder="Search remaining numbers across all prizes"
            value={prizeRemainingSearch}
            onChange={(e) => setPrizeRemainingSearch(e.target.value)}
            style={styles.inputWide}
          />

          <div style={styles.prizeGrid}>
            {allTimePrizeList.map((item) => {
              const isExpanded = expandedPrize === item.prize;
              const filteredList = getFilteredPrizeRemaining(item.remainingNumbers || []);

              return (
                <div key={item.prize} style={styles.prizeCard}>
                  <div style={styles.prizeHeading}>₹{item.prize}</div>
                  <div style={styles.prizeCycleBadge}>
                    Cycle {item.prizeCycleNumber} {renderBadge(item.prizeCycleStatus)}
                  </div>
                  <div style={styles.prizeMeta}>Seen: {item.seen}</div>
                  <div style={styles.prizeMeta}>Remaining: {item.remaining}</div>
                  <div style={styles.prizeProgress}>
                    <div style={styles.progressBarOuter}>
                      <div
                        style={{
                          ...styles.progressBarInner,
                          width: `${item.progress}%`,
                          background:
                            item.progress >= 100
                              ? "#22c55e"
                              : "linear-gradient(90deg, #2563eb, #60a5fa)",
                        }}
                      />
                    </div>
                    <div style={styles.prizePercent}>{item.progress}%</div>
                  </div>

                  {item.remaining > 0 && (
                    <button
                      style={styles.toggleBtn}
                      onClick={() =>
                        setExpandedPrize(isExpanded ? null : item.prize)
                      }
                    >
                      {isExpanded ? "Hide Remaining Numbers" : `Show ${item.remaining} Remaining Numbers`}
                    </button>
                  )}

                  {item.remaining === 0 && (
                    <div style={styles.completedNote}>
                      ✅ All 10,000 numbers covered in Cycle {item.prizeCycleNumber}
                    </div>
                  )}

                  {isExpanded && item.remaining > 0 && (
                    <div style={styles.remainingSection}>
                      <div style={styles.remainingCount}>
                        Showing {filteredList.length} of {item.remaining}
                      </div>
                      <div style={styles.tagsWrap}>
                        {filteredList.map((num) => (
                          <span key={num} style={styles.grayTag}>{num}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div style={styles.layout}>
        <div style={styles.sidebar}>
          <div style={styles.sidebarTitle}>Cycles</div>
          {loadingSummary && <div>Loading...</div>}

          <div style={styles.cycleList}>
            {(summaryData?.cycles || []).map((cycle) => (
              <button
                key={cycle.cycleNumber}
                onClick={() => setSelectedCycle(cycle.cycleNumber)}
                style={{
                  ...styles.cycleButton,
                  ...(selectedCycle === cycle.cycleNumber
                    ? styles.cycleButtonActive
                    : {}),
                }}
              >
                <div style={styles.cycleTop}>
                  <div style={{ fontWeight: 800 }}>Cycle {cycle.cycleNumber}</div>
                  {renderBadge(cycle.status)}
                </div>

                <div style={styles.metaText}>
                  <div>Start: {cycle.startDate || "-"}</div>
                  <div>End: {cycle.endDate || "-"}</div>
                  <div>Draws: {cycle.drawsCount}</div>
                  <div>Seen: {cycle.uniqueNumbersSeen}</div>
                  <div>Remaining: {cycle.remainingCount}</div>
                  <div>Progress: {cycle.progressPercent}%</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div style={styles.main}>
          {!selectedCycle && <div style={styles.card}>Select a cycle</div>}
          {loadingCycle && <div style={styles.card}>Loading cycle details...</div>}

          {cycleDetail?.cycle && !loadingCycle && (
            <>
              <div style={styles.card}>
                <div style={styles.headerRow}>
                  <div>
                    <h2 style={{ margin: 0 }}>
                      Cycle {cycleDetail.cycle.cycleNumber}
                    </h2>
                    <div style={{ marginTop: 8 }}>
                      {renderBadge(cycleDetail.cycle.status)}
                    </div>
                  </div>

                  <div style={styles.progressBox}>
                    <div style={styles.progressValue}>
                      {cycleDetail.cycle.progressPercent}%
                    </div>
                    <div style={styles.progressBarOuter}>
                      <div
                        style={{
                          ...styles.progressBarInner,
                          width: `${cycleDetail.cycle.progressPercent}%`,
                        }}
                      />
                    </div>
                  </div>
                </div>

                <div style={styles.infoGrid}>
                  <div style={styles.infoCard}>
                    <div style={styles.infoLabel}>Start</div>
                    <div style={styles.infoValue}>{cycleDetail.cycle.startDate || "-"}</div>
                    <div style={styles.infoSub}>{cycleDetail.cycle.startSerialNumber || ""}</div>
                  </div>
                  <div style={styles.infoCard}>
                    <div style={styles.infoLabel}>End / Latest</div>
                    <div style={styles.infoValue}>{cycleDetail.cycle.endDate || "-"}</div>
                    <div style={styles.infoSub}>{cycleDetail.cycle.endSerialNumber || ""}</div>
                  </div>
                  <div style={styles.infoCard}>
                    <div style={styles.infoLabel}>Draws</div>
                    <div style={styles.infoValue}>{cycleDetail.cycle.drawsCount}</div>
                  </div>
                  <div style={styles.infoCard}>
                    <div style={styles.infoLabel}>Seen</div>
                    <div style={styles.infoValue}>{cycleDetail.cycle.uniqueNumbersSeen}</div>
                  </div>
                  <div style={styles.infoCard}>
                    <div style={styles.infoLabel}>Remaining</div>
                    <div style={styles.infoValue}>{cycleDetail.cycle.remainingCount}</div>
                  </div>
                </div>
              </div>

              <div style={styles.card}>
                <h3 style={styles.sectionTitle}>Prize Block Progress in This Global Cycle</h3>
                <div style={styles.prizeGrid}>
                  {prizeStatsList.map((item) => (
                    <div key={item.prize} style={styles.prizeCard}>
                      <div style={styles.prizeHeading}>₹{item.prize}</div>
                      <div style={styles.prizeMeta}>Seen: {item.seen}</div>
                      <div style={styles.prizeMeta}>Remaining: {item.remaining}</div>
                      <div style={styles.prizeProgress}>
                        <div style={styles.progressBarOuter}>
                          <div
                            style={{
                              ...styles.progressBarInner,
                              width: `${item.progress}%`,
                              background:
                                item.progress >= 100
                                  ? "#22c55e"
                                  : "linear-gradient(90deg, #2563eb, #60a5fa)",
                            }}
                          />
                        </div>
                        <div style={styles.prizePercent}>{item.progress}%</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div style={styles.card}>
                <h3 style={styles.sectionTitle}>Remaining Numbers</h3>
                <input
                  type="text"
                  placeholder="Search remaining number"
                  value={remainingSearch}
                  onChange={(e) => setRemainingSearch(e.target.value)}
                  style={styles.inputWide}
                />
                <div style={styles.tagsWrap}>
                  {filteredRemaining.map((num) => (
                    <span key={num} style={styles.grayTag}>{num}</span>
                  ))}
                </div>
              </div>

              <div style={styles.card}>
                <h3 style={styles.sectionTitle}>Cycle Draw Table</h3>
                <input
                  type="text"
                  placeholder="Search date / serial / record / number / prize"
                  value={tableSearch}
                  onChange={(e) => setTableSearch(e.target.value)}
                  style={styles.inputWide}
                />

                <div style={styles.tableWrap}>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        <th style={styles.th}>Date</th>
                        <th style={styles.th}>Serial</th>
                        <th style={styles.th}>New in Cycle</th>
                        <th style={styles.th}>Remaining After</th>
                        <th style={styles.th}>Progress</th>
                        <th style={styles.th}>Unique Numbers inside Prize Block (Prizes)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredTimeline.map((draw, idx) => (
                        <tr key={`${draw.recordNumber}-${idx}`}>
                          <td style={styles.td}>{draw.date}</td>
                          <td style={styles.td}>{draw.serialNumber}</td>
                          <td style={styles.td}>{draw.newGlobalNumbersCount}</td>
                          <td style={styles.td}>{draw.globalRemainingAfter}</td>
                          <td style={styles.td}>{draw.globalProgress}%</td>
                          <td style={styles.td}>
                            <div style={styles.tagsWrap}>
                              {(draw.newGlobalNumbers || []).length ? (
                                draw.newGlobalNumbers.map((item) => (
                                  <span key={item.number} style={styles.blueTag}>
                                    {item.number} ({(item.prizes || []).join(", ")})
                                  </span>
                                ))
                              ) : (
                                <span style={{ color: "#64748b" }}>-</span>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "linear-gradient(180deg, #f8fbff 0%, #eef4ff 100%)",
    padding: 24,
    color: "#0f172a",
  },
  hero: {
    marginBottom: 20,
  },
  title: {
    margin: 0,
    fontSize: 32,
    fontWeight: 800,
  },
  subtitle: {
    marginTop: 8,
    color: "#475569",
    lineHeight: 1.5,
    maxWidth: 1000,
  },
  errorBox: {
    background: "#fef2f2",
    border: "1px solid #fecaca",
    color: "#b91c1c",
    padding: 14,
    borderRadius: 12,
    marginBottom: 20,
  },
  summaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 16,
    marginBottom: 20,
  },
  summaryCard: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 18,
  },
  summaryLabel: {
    color: "#64748b",
    fontSize: 13,
    marginBottom: 8,
  },
  summaryValue: {
    fontSize: 28,
    fontWeight: 800,
  },
  card: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 18,
    marginBottom: 20,
  },
  sectionTitle: {
    marginTop: 0,
    marginBottom: 12,
    fontSize: 22,
    fontWeight: 800,
  },
  note: {
    color: "#64748b",
    fontSize: 14,
    marginBottom: 16,
    lineHeight: 1.5,
  },
  cycleRowWrap: {
    display: "flex",
    flexWrap: "wrap",
    gap: 12,
  },
  cycleChip: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 14,
    padding: 14,
    cursor: "pointer",
    textAlign: "center",
    minWidth: 180,
  },
  cycleChipActive: {
    background: "#eff6ff",
    border: "1px solid #93c5fd",
  },
  inputWide: {
    width: "100%",
    boxSizing: "border-box",
    padding: "12px 14px",
    borderRadius: 12,
    border: "1px solid #cbd5e1",
    fontSize: 14,
    marginBottom: 12,
  },
  prizeGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
    gap: 16,
  },
  prizeCard: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 14,
    padding: 16,
  },
  prizeHeading: {
    fontSize: 20,
    fontWeight: 800,
    marginBottom: 8,
  },
  prizeCycleBadge: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginBottom: 10,
    fontSize: 14,
    fontWeight: 700,
    color: "#334155",
  },
  prizeMeta: {
    color: "#475569",
    fontSize: 14,
    marginBottom: 4,
  },
  prizeProgress: {
    marginTop: 10,
    display: "flex",
    alignItems: "center",
    gap: 10,
  },
  progressBarOuter: {
    width: "100%",
    height: 12,
    background: "#e2e8f0",
    borderRadius: 999,
    overflow: "hidden",
  },
  progressBarInner: {
    height: "100%",
    background: "linear-gradient(90deg, #2563eb, #60a5fa)",
  },
  prizePercent: {
    fontWeight: 800,
    fontSize: 14,
    minWidth: 60,
  },
  toggleBtn: {
    marginTop: 12,
    background: "#fff",
    border: "1px solid #cbd5e1",
    borderRadius: 10,
    padding: "8px 12px",
    cursor: "pointer",
    fontWeight: 700,
    fontSize: 13,
    color: "#334155",
    width: "100%",
  },
  completedNote: {
    marginTop: 12,
    color: "#16a34a",
    fontWeight: 700,
    fontSize: 14,
  },
  remainingSection: {
    marginTop: 12,
  },
  remainingCount: {
    fontSize: 13,
    color: "#64748b",
    marginBottom: 8,
  },
  tagsWrap: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  grayTag: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    color: "#334155",
    borderRadius: 999,
    padding: "5px 9px",
    fontSize: 12,
  },
  layout: {
    display: "grid",
    gridTemplateColumns: "320px 1fr",
    gap: 20,
    alignItems: "start",
  },
  sidebar: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 16,
  },
  sidebarTitle: {
    fontSize: 20,
    fontWeight: 800,
    marginBottom: 12,
  },
  cycleList: {
    display: "grid",
    gap: 12,
  },
  cycleButton: {
    width: "100%",
    textAlign: "left",
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 14,
    padding: 14,
    cursor: "pointer",
  },
  cycleButtonActive: {
    background: "#eff6ff",
    border: "1px solid #93c5fd",
  },
  cycleTop: {
    display: "flex",
    justifyContent: "space-between",
    gap: 10,
    alignItems: "center",
    marginBottom: 10,
    flexWrap: "wrap",
  },
  metaText: {
    color: "#475569",
    fontSize: 13,
    lineHeight: 1.6,
  },
  main: {
    display: "grid",
    gap: 16,
  },
  headerRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    flexWrap: "wrap",
    alignItems: "center",
  },
  progressBox: {
    minWidth: 260,
  },
  progressValue: {
    fontSize: 26,
    fontWeight: 800,
    marginBottom: 10,
  },
  infoGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 16,
    marginTop: 16,
  },
  infoCard: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 14,
    padding: 14,
  },
  infoLabel: {
    fontSize: 13,
    color: "#64748b",
    marginBottom: 8,
  },
  infoValue: {
    fontSize: 22,
    fontWeight: 800,
  },
  infoSub: {
    marginTop: 6,
    color: "#475569",
    fontSize: 13,
  },
  blueTag: {
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    color: "#1d4ed8",
    borderRadius: 999,
    padding: "6px 10px",
    fontSize: 12,
    fontWeight: 700,
  },
  tableWrap: {
    overflowX: "auto",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
  },
  th: {
    textAlign: "left",
    padding: 10,
    borderBottom: "1px solid #e2e8f0",
    color: "#334155",
    fontSize: 13,
    verticalAlign: "top",
  },
  td: {
    padding: 10,
    borderBottom: "1px solid #f1f5f9",
    fontSize: 14,
    verticalAlign: "top",
  },
};