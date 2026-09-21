import React, { useEffect, useMemo, useState } from "react";

export default function FullCyclesPage() {
  const [fromCycle, setFromCycle] = useState(1);
  const [summaryData, setSummaryData] = useState(null);
  const [selectedCycle, setSelectedCycle] = useState(null);
  const [cycleDetail, setCycleDetail] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState("");
  const [remainingSearch, setRemainingSearch] = useState("");
  const [seenSearch, setSeenSearch] = useState("");

  const loadSummary = async (startCycle = fromCycle) => {
    try {
      setLoadingSummary(true);
      setError("");

      const res = await fetch(
  `http://localhost:5000/api/full-lottery-cycles?fromCycle=${encodeURIComponent(startCycle)}`
);
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.details || json.error || "Failed to load cycles");
      }

      setSummaryData(json);

      if (json.cycles?.length) {
        const firstCycle = json.cycles[0].cycleNumber;
        setSelectedCycle((prev) => prev || firstCycle);
      } else {
        setSelectedCycle(null);
        setCycleDetail(null);
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
      setLoadingDetail(true);
      setError("");

      const res = await fetch(`http://localhost:5000/api/full-lottery-cycles/${cycleNumber}`);
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.details || json.error || "Failed to load cycle");
      }

      setCycleDetail(json.cycle || null);
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoadingDetail(false);
    }
  };

  useEffect(() => {
    loadSummary(1);
  }, []);

  useEffect(() => {
    if (selectedCycle) {
      loadCycleDetail(selectedCycle);
    }
  }, [selectedCycle]);

  const filteredRemainingNumbers = useMemo(() => {
    const list = cycleDetail?.remainingNumbers || [];
    const q = remainingSearch.trim();
    if (!q) return list;
    return list.filter((n) => n.includes(q));
  }, [cycleDetail, remainingSearch]);

  const filteredSeenNumbers = useMemo(() => {
    const list = cycleDetail?.firstSeenNumbers || [];
    const q = seenSearch.trim();
    if (!q) return list;
    return list.filter(
      (item) =>
        item.number.includes(q) ||
        item.firstSeenSerialNumber?.toLowerCase().includes(q.toLowerCase()) ||
        item.firstSeenDate?.includes(q)
    );
  }, [cycleDetail, seenSearch]);

  const renderStatusBadge = (status) => {
    const styles = {
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

    const style = styles[status] || {
      background: "#e5e7eb",
      color: "#374151",
      border: "1px solid #d1d5db",
    };

    return (
      <span
        style={{
          ...style,
          padding: "6px 12px",
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
        <h1 style={styles.title}>Full Lottery Cycle Tracker</h1>
        <p style={styles.subtitle}>
          Track real number cycles for <strong>FullLotteryData</strong> using
          all prize categories together. A cycle completes when all numbers from
          0000 to 9999 appear at least once.
        </p>
      </div>

      <div style={styles.topBar}>
        <div style={styles.topBarLeft}>
          <label style={styles.label}>Start from cycle</label>
          <input
            type="number"
            min="1"
            value={fromCycle}
            onChange={(e) => setFromCycle(Number(e.target.value || 1))}
            style={styles.input}
          />
        </div>

        <div style={styles.topBarButtons}>
          <button
            style={styles.primaryButton}
            onClick={() => loadSummary(fromCycle)}
          >
            {loadingSummary ? "Loading..." : "Load Cycles"}
          </button>
        </div>
      </div>

      {error ? <div style={styles.errorBox}>{error}</div> : null}

      {summaryData?.summary && (
        <div style={styles.summaryGrid}>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Total Draws</div>
            <div style={styles.summaryValue}>
              {summaryData.summary.totalDraws}
            </div>
          </div>

          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Total Cycles</div>
            <div style={styles.summaryValue}>
              {summaryData.summary.totalCycles}
            </div>
          </div>

          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Completed Cycles</div>
            <div style={styles.summaryValue}>
              {summaryData.summary.completedCycles}
            </div>
          </div>

          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Current Progress</div>
            <div style={styles.summaryValue}>
              {summaryData.summary.currentProgressPercent}%
            </div>
          </div>
        </div>
      )}

      <div style={styles.layout}>
        <div style={styles.sidebar}>
          <div style={styles.sidebarTitle}>Cycles</div>

          {!summaryData?.cycles?.length && !loadingSummary && (
            <div style={{ color: "#64748b" }}>No cycles found</div>
          )}

          <div style={styles.cycleList}>
            {(summaryData?.cycles || []).map((cycle) => (
              <button
                key={cycle.cycleNumber}
                style={{
                  ...styles.cycleButton,
                  ...(selectedCycle === cycle.cycleNumber
                    ? styles.cycleButtonActive
                    : {}),
                }}
                onClick={() => setSelectedCycle(cycle.cycleNumber)}
              >
                <div style={styles.cycleButtonTop}>
                  <div style={{ fontWeight: 800 }}>Cycle {cycle.cycleNumber}</div>
                  {renderStatusBadge(cycle.status)}
                </div>

                <div style={styles.cycleMeta}>
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

        <div style={styles.mainPanel}>
          {!selectedCycle && <div style={styles.emptyCard}>Select a cycle</div>}

          {selectedCycle && loadingDetail && (
            <div style={styles.emptyCard}>Loading cycle details...</div>
          )}

          {cycleDetail && !loadingDetail && (
            <>
              <div style={styles.detailHeader}>
                <div>
                  <h2 style={{ margin: 0 }}>Cycle {cycleDetail.cycleNumber}</h2>
                  <div style={{ marginTop: 8 }}>
                    {renderStatusBadge(cycleDetail.status)}
                  </div>
                </div>

                <div style={styles.progressCard}>
                  <div style={styles.progressLabel}>Progress</div>
                  <div style={styles.progressValue}>
                    {cycleDetail.progressPercent}%
                  </div>
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
                  <div style={styles.infoValue}>
                    {cycleDetail.startDate || "-"}
                  </div>
                  <div style={styles.infoSub}>
                    {cycleDetail.startSerialNumber || ""}
                  </div>
                </div>

                <div style={styles.infoCard}>
                  <div style={styles.infoLabel}>End / Latest</div>
                  <div style={styles.infoValue}>
                    {cycleDetail.endDate || "-"}
                  </div>
                  <div style={styles.infoSub}>
                    {cycleDetail.endSerialNumber || ""}
                  </div>
                </div>

                <div style={styles.infoCard}>
                  <div style={styles.infoLabel}>Draws in Cycle</div>
                  <div style={styles.infoValue}>{cycleDetail.drawsCount}</div>
                </div>

                <div style={styles.infoCard}>
                  <div style={styles.infoLabel}>Unique Numbers Seen</div>
                  <div style={styles.infoValue}>
                    {cycleDetail.uniqueNumbersSeen}
                  </div>
                </div>

                <div style={styles.infoCard}>
                  <div style={styles.infoLabel}>Remaining Numbers</div>
                  <div style={styles.infoValue}>
                    {cycleDetail.remainingCount}
                  </div>
                </div>
              </div>

              <div style={styles.section}>
                <h3 style={styles.sectionTitle}>Remaining Numbers to Complete Cycle</h3>
                <input
                  type="text"
                  placeholder="Search remaining number"
                  value={remainingSearch}
                  onChange={(e) => setRemainingSearch(e.target.value)}
                  style={styles.input}
                />

                <div style={styles.numberGrid}>
                  {filteredRemainingNumbers.length ? (
                    filteredRemainingNumbers.map((num) => (
                      <span key={num} style={styles.numberTag}>
                        {num}
                      </span>
                    ))
                  ) : (
                    <div style={{ color: "#64748b" }}>No remaining numbers</div>
                  )}
                </div>
              </div>

              <div style={styles.section}>
                <h3 style={styles.sectionTitle}>Numbers Already Covered in This Cycle</h3>
                <input
                  type="text"
                  placeholder="Search seen number / date / serial"
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
                        <th style={styles.th}>Serial Number</th>
                        <th style={styles.th}>Record</th>
                        <th style={styles.th}>File</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSeenNumbers.map((item) => (
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
                      {cycleDetail.drawTimeline.map((draw, idx) => (
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
  topBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "end",
    gap: 16,
    flexWrap: "wrap",
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 16,
    marginBottom: 20,
  },
  topBarLeft: {
    minWidth: 220,
  },
  topBarButtons: {
    display: "flex",
    gap: 10,
  },
  label: {
    display: "block",
    marginBottom: 8,
    fontWeight: 700,
    fontSize: 13,
    color: "#334155",
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
  primaryButton: {
    background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
    color: "#fff",
    border: "none",
    borderRadius: 12,
    padding: "12px 18px",
    fontWeight: 700,
    cursor: "pointer",
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
    boxShadow: "0 10px 24px rgba(15,23,42,0.05)",
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
  layout: {
    display: "grid",
    gridTemplateColumns: "320px 1fr",
    gap: 20,
  },
  sidebar: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 16,
    height: "fit-content",
  },
  sidebarTitle: {
    fontSize: 18,
    fontWeight: 800,
    marginBottom: 12,
  },
  cycleList: {
    display: "grid",
    gap: 12,
  },
  cycleButton: {
    textAlign: "left",
    width: "100%",
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
  cycleButtonTop: {
    display: "flex",
    justifyContent: "space-between",
    gap: 10,
    alignItems: "center",
    marginBottom: 10,
    flexWrap: "wrap",
  },
  cycleMeta: {
    color: "#475569",
    fontSize: 13,
    lineHeight: 1.6,
  },
  mainPanel: {
    display: "grid",
    gap: 20,
  },
  emptyCard: {
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
  progressCard: {
    minWidth: 260,
  },
  progressLabel: {
    fontSize: 13,
    color: "#64748b",
    marginBottom: 6,
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
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
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
    fontSize: 24,
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
  numberGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  numberTag: {
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