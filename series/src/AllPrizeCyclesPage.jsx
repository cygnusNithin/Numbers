import React, { useEffect, useMemo, useState } from "react";

const API = "http://localhost:5000";

export default function AllPrizeCyclesPage() {
  const [dashboard, setDashboard] = useState(null);
  const [selectedPrize, setSelectedPrize] = useState(null);
  const [prizeData, setPrizeData] = useState(null);
  const [selectedCycle, setSelectedCycle] = useState(null);
  const [cycleDetail, setCycleDetail] = useState(null);

  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [loadingPrize, setLoadingPrize] = useState(false);
  const [loadingCycle, setLoadingCycle] = useState(false);
  const [error, setError] = useState("");

  const [remainingSearch, setRemainingSearch] = useState("");
  const [seenSearch, setSeenSearch] = useState("");

  const loadDashboard = async () => {
    try {
      setLoadingDashboard(true);
      setError("");

      const res = await fetch(`${API}/api/all-prize-cycles`);
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.details || json.error || "Failed to load dashboard");
      }

      setDashboard(json);

      if (json.prizeSummaries?.length) {
        setSelectedPrize((prev) => prev || json.prizeSummaries[0].prize);
      }
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoadingDashboard(false);
    }
  };

  const loadPrizeCycles = async (prize) => {
    if (!prize) return;

    try {
      setLoadingPrize(true);
      setError("");

      const res = await fetch(`${API}/api/all-prize-cycles/${prize}`);
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.details || json.error || "Failed to load prize cycles");
      }

      setPrizeData(json);

      if (json.cycles?.length) {
        const preferred =
          json.cycles.find((c) => c.cycleNumber === json.currentCycleNumber) ||
          json.cycles.find((c) => c.status === "IN_PROGRESS") ||
          json.cycles[json.cycles.length - 1];

        setSelectedCycle(preferred ? preferred.cycleNumber : null);
      } else {
        setSelectedCycle(null);
        setCycleDetail(null);
      }
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoadingPrize(false);
    }
  };

  const loadCycleDetail = async (prize, cycleNumber) => {
    if (!prize || !cycleNumber) return;

    try {
      setLoadingCycle(true);
      setError("");

      const res = await fetch(`${API}/api/all-prize-cycles/${prize}/${cycleNumber}`);
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.details || json.error || "Failed to load cycle detail");
      }

      setCycleDetail(json.cycle || null);
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoadingCycle(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, []);

  useEffect(() => {
    if (!selectedPrize) return;

    setPrizeData(null);
    setSelectedCycle(null);
    setCycleDetail(null);
    setRemainingSearch("");
    setSeenSearch("");

    loadPrizeCycles(selectedPrize);
  }, [selectedPrize]);

  useEffect(() => {
    if (selectedPrize && selectedCycle) {
      loadCycleDetail(selectedPrize, selectedCycle);
    }
  }, [selectedPrize, selectedCycle]);

  const filteredRemaining = useMemo(() => {
    const list = cycleDetail?.remainingNumbers || [];
    const q = remainingSearch.trim();
    if (!q) return list;
    return list.filter((n) => n.includes(q));
  }, [cycleDetail, remainingSearch]);

  const filteredSeen = useMemo(() => {
    const list = cycleDetail?.firstSeenNumbers || [];
    const q = seenSearch.trim().toLowerCase();
    if (!q) return list;

    return list.filter(
      (item) =>
        item.number.includes(q) ||
        String(item.firstSeenDate || "").toLowerCase().includes(q) ||
        String(item.firstSeenSerialNumber || "").toLowerCase().includes(q)
    );
  }, [cycleDetail, seenSearch]);

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
        <h1 style={styles.title}>All Prize Cycles</h1>
        <p style={styles.subtitle}>
          Prize-wise cycle tracking from first day to latest day using FullLotteryData.
        </p>
      </div>

      {error ? <div style={styles.errorBox}>{error}</div> : null}

      {dashboard?.datasetSummary && (
        <div style={styles.summaryGrid}>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Total Draws</div>
            <div style={styles.summaryValue}>
              {dashboard.datasetSummary.totalDraws}
            </div>
          </div>

          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>First Date</div>
            <div style={styles.summaryValueSmall}>
              {dashboard.datasetSummary.firstDate || "-"}
            </div>
          </div>

          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Latest Date</div>
            <div style={styles.summaryValueSmall}>
              {dashboard.datasetSummary.latestDate || "-"}
            </div>
          </div>

          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Prize Categories</div>
            <div style={styles.summaryValue}>
              {dashboard.datasetSummary.prizeCategories?.length || 0}
            </div>
          </div>
        </div>
      )}

      <div style={styles.layout}>
        <div style={styles.panel}>
          <h3 style={styles.panelHeading}>Prize Categories</h3>

          {loadingDashboard && <div>Loading prize categories...</div>}

          <div style={styles.list}>
            {(dashboard?.prizeSummaries || []).map((item) => (
              <button
                key={item.prize}
                onClick={() => setSelectedPrize(item.prize)}
                style={{
                  ...styles.selectBtn,
                  ...(selectedPrize === item.prize ? styles.selectBtnActive : {}),
                }}
              >
                <div style={styles.selectBtnTop}>
                  <div style={{ fontWeight: 800 }}>₹{item.prize}</div>
                  {renderBadge(item.currentStatus)}
                </div>

                <div style={styles.metaText}>
                  <div>Total Cycles: {item.totalCycles}</div>
                  <div>Completed: {item.completedCycles}</div>
                  <div>Seen: {item.currentUniqueNumbersSeen}</div>
                  <div>Remaining: {item.currentRemainingCount}</div>
                  <div>Progress: {item.currentProgressPercent}%</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div style={styles.panel}>
          <h3 style={styles.panelHeading}>
            {selectedPrize
              ? `Cycles for ₹${selectedPrize} (${prizeData?.totalCycles || 0})`
              : "Select Prize"}
          </h3>

          {loadingPrize && <div>Loading cycles...</div>}

          <div style={styles.list}>
            {(prizeData?.cycles || []).map((cycle) => (
              <button
                key={`${cycle.prize}-${cycle.cycleNumber}`}
                onClick={() => setSelectedCycle(cycle.cycleNumber)}
                style={{
                  ...styles.selectBtn,
                  ...(selectedCycle === cycle.cycleNumber
                    ? styles.selectBtnActive
                    : {}),
                }}
              >
                <div style={styles.selectBtnTop}>
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

        <div style={styles.detailPanel}>
          {!selectedCycle && <div style={styles.emptyBox}>Select a cycle</div>}
          {loadingCycle && <div style={styles.emptyBox}>Loading cycle details...</div>}

          {cycleDetail && !loadingCycle && (
            <>
              <div style={styles.detailHeader}>
                <div>
                  <h2 style={{ margin: 0 }}>
                    Prize ₹{cycleDetail.prize} — Cycle {cycleDetail.cycleNumber}
                  </h2>
                  <div style={{ marginTop: 8 }}>{renderBadge(cycleDetail.status)}</div>
                </div>

                <div style={styles.progressBox}>
                  <div style={styles.progressValue}>{cycleDetail.progressPercent}%</div>
                  <div style={styles.progressBarOuter}>
                    <div
                      style={{
                        ...styles.progressBarInner,
                        width: `${cycleDetail.progressPercent}%`,
                      }}
                    />
                  </div>
                </div>
              </div>

              <div style={styles.infoGrid}>
                <div style={styles.infoCard}>
                  <div style={styles.infoLabel}>Start</div>
                  <div style={styles.infoValue}>{cycleDetail.startDate || "-"}</div>
                  <div style={styles.infoSub}>{cycleDetail.startSerialNumber || ""}</div>
                </div>

                <div style={styles.infoCard}>
                  <div style={styles.infoLabel}>Latest / End</div>
                  <div style={styles.infoValue}>{cycleDetail.endDate || "-"}</div>
                  <div style={styles.infoSub}>{cycleDetail.endSerialNumber || ""}</div>
                </div>

                <div style={styles.infoCard}>
                  <div style={styles.infoLabel}>Draws</div>
                  <div style={styles.infoValue}>{cycleDetail.drawsCount}</div>
                </div>

                <div style={styles.infoCard}>
                  <div style={styles.infoLabel}>Seen</div>
                  <div style={styles.infoValue}>{cycleDetail.uniqueNumbersSeen}</div>
                </div>

                <div style={styles.infoCard}>
                  <div style={styles.infoLabel}>Remaining</div>
                  <div style={styles.infoValue}>{cycleDetail.remainingCount}</div>
                </div>
              </div>

              <div style={styles.section}>
                <h3 style={styles.sectionTitle}>Remaining Numbers</h3>
                <input
                  type="text"
                  placeholder="Search remaining number"
                  value={remainingSearch}
                  onChange={(e) => setRemainingSearch(e.target.value)}
                  style={styles.input}
                />
                <div style={styles.tagsWrap}>
                  {filteredRemaining.length ? (
                    filteredRemaining.map((num) => (
                      <span key={num} style={styles.tag}>
                        {num}
                      </span>
                    ))
                  ) : (
                    <div style={{ color: "#64748b" }}>No remaining numbers</div>
                  )}
                </div>
              </div>

              <div style={styles.section}>
                <h3 style={styles.sectionTitle}>First Seen Numbers</h3>
                <input
                  type="text"
                  placeholder="Search number / date / serial"
                  value={seenSearch}
                  onChange={(e) => setSeenSearch(e.target.value)}
                  style={styles.input}
                />

                <div style={styles.tableWrap}>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        <th style={styles.th}>Number</th>
                        <th style={styles.th}>First Seen Date</th>
                        <th style={styles.th}>Serial</th>
                        <th style={styles.th}>Record</th>
                        <th style={styles.th}>File</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSeen.map((item) => (
                        <tr key={`${item.number}-${item.firstSeenDate}`}>
                          <td style={styles.td}>{item.number}</td>
                          <td style={styles.td}>{item.firstSeenDate}</td>
                          <td style={styles.td}>{item.firstSeenSerialNumber}</td>
                          <td style={styles.td}>{item.recordNumber || "-"}</td>
                          <td style={styles.td}>{item.fileName || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div style={styles.section}>
                <h3 style={styles.sectionTitle}>Draw Timeline</h3>
                <div style={styles.tableWrap}>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        <th style={styles.th}>Date</th>
                        <th style={styles.th}>Serial</th>
                        <th style={styles.th}>Record</th>
                        <th style={styles.th}>Unique in Draw</th>
                        <th style={styles.th}>New in Cycle</th>
                        <th style={styles.th}>Seen After Draw</th>
                        <th style={styles.th}>Progress</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(cycleDetail.drawTimeline || []).map((draw, idx) => (
                        <tr key={`${draw.recordNumber}-${idx}`}>
                          <td style={styles.td}>{draw.date}</td>
                          <td style={styles.td}>{draw.serialNumber}</td>
                          <td style={styles.td}>{draw.recordNumber || "-"}</td>
                          <td style={styles.td}>{draw.uniqueNumbersInDraw}</td>
                          <td style={styles.td}>{draw.newNumbersCount}</td>
                          <td style={styles.td}>{draw.totalSeenAfterDraw}</td>
                          <td style={styles.td}>{draw.progressPercent}%</td>
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
    maxWidth: 900,
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
    fontSize: 30,
    fontWeight: 800,
  },
  summaryValueSmall: {
    fontSize: 18,
    fontWeight: 800,
  },
  layout: {
    display: "grid",
    gridTemplateColumns: "280px 320px 1fr",
    gap: 20,
    alignItems: "start",
  },
  panel: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 16,
  },
  detailPanel: {
    display: "grid",
    gap: 16,
  },
  panelHeading: {
    marginTop: 0,
    marginBottom: 12,
    fontSize: 20,
    fontWeight: 800,
  },
  list: {
    display: "grid",
    gap: 12,
  },
  selectBtn: {
    width: "100%",
    textAlign: "left",
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 14,
    padding: 14,
    cursor: "pointer",
  },
  selectBtnActive: {
    background: "#eff6ff",
    border: "1px solid #93c5fd",
  },
  selectBtnTop: {
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
  emptyBox: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 24,
    color: "#64748b",
  },
  detailHeader: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 18,
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
  infoGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 16,
  },
  infoCard: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 16,
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
  section: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 18,
  },
  sectionTitle: {
    marginTop: 0,
    marginBottom: 12,
    fontSize: 20,
    fontWeight: 800,
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    padding: "12px 14px",
    borderRadius: 12,
    border: "1px solid #cbd5e1",
    fontSize: 14,
    background: "#fff",
    outline: "none",
    marginBottom: 12,
  },
  tagsWrap: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  tag: {
    background: "#f8fafc",
    border: "1px solid #dbeafe",
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
  },
  td: {
    padding: 10,
    borderBottom: "1px solid #f1f5f9",
    fontSize: 14,
    verticalAlign: "top",
  },
};