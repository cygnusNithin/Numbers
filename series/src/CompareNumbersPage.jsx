import React, { useState } from "react";

export default function RemainingInHistoryPage() {
  const [selectedDb, setSelectedDb] = useState("db3");
  const [sourceDb, setSourceDb] = useState("db3");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [activePrize, setActivePrize] = useState(null);
  const [viewType, setViewType] = useState("remaining"); // "remaining" or "today"

  const handleAnalyze = async () => {
    try {
      setLoading(true);
      setError("");

      const res = await fetch(
        `http://localhost:5000/api/remaining-in-hit-history?dbKey=${selectedDb}&sourceDbKey=${sourceDb}`
      );

      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.error || "Analysis failed");
      }

      setResult(json);
      setActivePrize(Object.keys(json.remainingByPrize)[0] || null);
      setViewType("remaining");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>Remaining Numbers in Hit History</h1>
        <p style={styles.subtitle}>
          Show which of your 139 remaining numbers exist in each prize's hit history with their hit counts
        </p>
      </div>

      <div style={styles.card}>
        <div style={styles.gridInputs}>
          <div>
            <label style={styles.label}>Target DB (Remaining Numbers)</label>
            <select
              style={styles.input}
              value={selectedDb}
              onChange={(e) => setSelectedDb(e.target.value)}
            >
              <option value="db3">FullLotteryData (DB3)</option>
              <option value="db4">AbsoluteData (DB4)</option>
            </select>
          </div>

          <div>
            <label style={styles.label}>Source DB (Hit History)</label>
            <select
              style={styles.input}
              value={sourceDb}
              onChange={(e) => setSourceDb(e.target.value)}
            >
              <option value="db3">FullLotteryData (DB3)</option>
              <option value="db4">AbsoluteData (DB4)</option>
            </select>
          </div>
        </div>

        <button style={styles.primaryButton} onClick={handleAnalyze} disabled={loading}>
          {loading ? "Analyzing..." : "Analyze"}
        </button>
      </div>

      {error && <div style={styles.errorBox}>{error}</div>}

      {result && (
        <div>
          {/* Metadata */}
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>📋 Overview</h2>
            <div style={styles.grid}>
              <div style={styles.stat}>
                <div style={styles.statLabel}>Remaining Numbers</div>
                <div style={styles.statValue}>{result.metadata.remainingCount}</div>
              </div>
              <div style={styles.stat}>
                <div style={styles.statLabel}>Prize Tiers</div>
                <div style={styles.statValue}>{result.metadata.prizeCount}</div>
              </div>
              <div style={styles.stat}>
                <div style={styles.statLabel}>NOT in Any Prize</div>
                <div style={styles.statValue}>{result.notInAnyPrize.length}</div>
              </div>
            </div>
          </div>

          {/* View Type Selector */}
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Select View</h2>
            <div style={styles.viewSelector}>
              <button
                style={{
                  ...styles.viewButton,
                  background: viewType === "remaining" ? "#2563eb" : "#f1f5f9",
                  color: viewType === "remaining" ? "#fff" : "#0f172a",
                }}
                onClick={() => setViewType("remaining")}
              >
                Remaining Numbers
              </button>
              {result.todayByPrize && (
                <button
                  style={{
                    ...styles.viewButton,
                    background: viewType === "today" ? "#2563eb" : "#f1f5f9",
                    color: viewType === "today" ? "#fff" : "#0f172a",
                  }}
                  onClick={() => setViewType("today")}
                >
                  Today's Numbers
                </button>
              )}
            </div>
          </div>

          {/* Prize Selector */}
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Select Prize Tier</h2>
            <div style={styles.prizeSelector}>
              {Object.keys(
                viewType === "remaining" ? result.remainingByPrize : result.todayByPrize
              ).map((prize) => {
                const data =
                  viewType === "remaining"
                    ? result.remainingByPrize[prize]
                    : result.todayByPrize[prize];

                return (
                  <button
                    key={prize}
                    style={{
                      ...styles.prizeButton,
                      background: activePrize === prize ? "#2563eb" : "#f1f5f9",
                      color: activePrize === prize ? "#fff" : "#0f172a",
                    }}
                    onClick={() => setActivePrize(prize)}
                  >
                    ₹{prize} ({data.count})
                  </button>
                );
              })}
            </div>
          </div>

          {/* Numbers for Selected Prize */}
          {activePrize && (
            <div style={styles.card}>
              <h2 style={styles.cardTitle}>
                💰 Prize ₹{activePrize} - {viewType === "remaining" ? "Remaining" : "Today's"} Numbers in Hit History
              </h2>

              {viewType === "remaining" && (
                <div style={{ ...styles.stat, background: "#dcfce7", marginBottom: "20px" }}>
                  <div style={styles.statLabel}>Numbers Found in This Prize</div>
                  <div style={styles.statValue}>{result.remainingByPrize[activePrize].count}</div>
                  <div style={styles.statSubtext}>
                    out of {result.metadata.remainingCount} remaining
                  </div>
                </div>
              )}

              {viewType === "today" && (
                <div style={{ ...styles.stat, background: "#dcfce7", marginBottom: "20px", padding: "20px", borderRadius: "14px" }}>
                  <div style={styles.statLabel}>Today's Numbers in This Prize</div>
                  <div style={styles.statValue}>{result.todayByPrize[activePrize].count}</div>
                </div>
              )}

              {(viewType === "remaining"
                ? result.remainingByPrize[activePrize].numbers
                : result.todayByPrize[activePrize].numbers
              ).length > 0 ? (
                <div style={styles.tableWrapper}>
                  <table style={styles.table}>
                    <thead>
                      <tr style={styles.tableHeader}>
                        <th style={styles.th}>Number</th>
                        <th style={styles.th}>Total Hits</th>
                        <th style={styles.th}>Avg Gap (days)</th>
                        <th style={styles.th}>First Hit</th>
                        <th style={styles.th}>Last Hit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(viewType === "remaining"
                        ? result.remainingByPrize[activePrize].numbers
                        : result.todayByPrize[activePrize].numbers
                      ).map((num, idx) => (
                        <tr key={idx} style={styles.tableRow}>
                          <td style={{ ...styles.td, fontWeight: "bold", fontSize: "16px" }}>
                            {num.number}
                          </td>
                          <td style={styles.td}>{num.totalHits}</td>
                          <td style={styles.td}>{num.avgGapDays}d</td>
                          <td style={styles.td}>{num.firstDate || "N/A"}</td>
                          <td style={styles.td}>{num.lastDate}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ color: "#64748b", padding: "20px", textAlign: "center" }}>
                  No numbers found for this prize
                </div>
              )}
            </div>
          )}

          {/* Numbers NOT in Any Prize */}
          {result.notInAnyPrize.length > 0 && (
            <div style={styles.card}>
              <h2 style={styles.cardTitle}>
                ❓ Numbers NOT in Any Prize ({result.notInAnyPrize.length})
              </h2>
              <p style={{ color: "#64748b", marginBottom: "16px" }}>
                These {result.notInAnyPrize.length} numbers exist in remaining but don't appear in any prize's hit history
              </p>
              <div style={styles.numbersGrid}>
                {result.notInAnyPrize.slice(0, 100).map((num, idx) => (
                  <div key={idx} style={styles.numberBox}>
                    {num}
                  </div>
                ))}
              </div>
              {result.notInAnyPrize.length > 100 && (
                <p style={{ color: "#64748b", marginTop: "12px", fontSize: "12px" }}>
                  ... and {result.notInAnyPrize.length - 100} more
                </p>
              )}
            </div>
          )}
        </div>
      )}
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
  header: {
    marginBottom: 24,
  },
  title: {
    margin: 0,
    fontSize: 32,
    fontWeight: 800,
    marginBottom: 8,
  },
  subtitle: {
    margin: 0,
    fontSize: 16,
    color: "#475569",
  },
  card: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 20,
    padding: 24,
    marginBottom: 20,
    boxShadow: "0 10px 24px rgba(15,23,42,0.05)",
  },
  cardTitle: {
    margin: "0 0 16px 0",
    fontSize: 20,
    fontWeight: 800,
  },
  gridInputs: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: 16,
    marginBottom: 16,
  },
  label: {
    display: "block",
    marginBottom: 8,
    fontWeight: 700,
    fontSize: 14,
    color: "#334155",
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    padding: 12,
    borderRadius: 12,
    border: "1px solid #cbd5e1",
    fontSize: 14,
    outline: "none",
    background: "#fff",
  },
  primaryButton: {
    background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
    color: "#fff",
    border: "none",
    borderRadius: 12,
    padding: "12px 24px",
    cursor: "pointer",
    fontWeight: 700,
    width: "100%",
  },
  errorBox: {
    background: "#fef2f2",
    border: "1px solid #fecaca",
    color: "#b91c1c",
    padding: 16,
    borderRadius: 12,
    marginBottom: 20,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
    gap: 12,
    marginTop: 16,
  },
  stat: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 14,
    padding: 16,
  },
  statLabel: {
    fontSize: 12,
    color: "#64748b",
    marginBottom: 8,
    fontWeight: 700,
  },
  statValue: {
    fontSize: 28,
    fontWeight: 800,
    color: "#0f172a",
  },
  statSubtext: {
    fontSize: 11,
    color: "#94a3b8",
    marginTop: 8,
  },
  viewSelector: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  viewButton: {
    padding: "10px 16px",
    borderRadius: 12,
    border: "1px solid #cbd5e1",
    cursor: "pointer",
    fontWeight: 700,
    fontSize: 13,
    transition: "all 0.3s",
  },
  prizeSelector: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  prizeButton: {
    padding: "10px 16px",
    borderRadius: 12,
    border: "1px solid #cbd5e1",
    cursor: "pointer",
    fontWeight: 700,
    fontSize: 13,
    transition: "all 0.3s",
  },
  tableWrapper: {
    overflowX: "auto",
    marginTop: 16,
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
  },
  tableHeader: {
    background: "#f1f5f9",
  },
  tableRow: {
    borderBottom: "1px solid #e2e8f0",
  },
  th: {
    textAlign: "left",
    padding: 12,
    fontWeight: 700,
    fontSize: 12,
  },
  td: {
    padding: 12,
  },
  numbersGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(80px, 1fr))",
    gap: 8,
    marginTop: 12,
  },
  numberBox: {
    background: "#fee2e2",
    border: "2px solid #fca5a5",
    borderRadius: 10,
    padding: 12,
    textAlign: "center",
    fontWeight: 700,
    fontSize: 14,
  },
};