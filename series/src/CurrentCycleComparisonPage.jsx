import React, { useEffect, useMemo, useState } from "react";

const API = "http://localhost:5000";
const PRIZE_AMOUNTS = [5000, 2000, 1000, 500, 200, 100, 50];

export default function CurrentCycleComparisonPage() {
  const [data, setData] = useState(null);
  const [selectedView, setSelectedView] = useState("global"); // "global" or prize amount
  const [searchTerm, setSearchTerm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadData = async () => {
    try {
      setLoading(true);
      setError("");

      const res = await fetch(`${API}/api/current-cycle-comparison`);
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.details || json.error || "Failed to load data");
      }

      setData(json);
      setSelectedView("global");
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredNumbers = useMemo(() => {
    if (!data) return [];

    let list = [];
    if (selectedView === "global") {
      list = data.globalCycle.remainingNumbers || [];
    } else {
      const prize = Number(selectedView);
      list = data.prizeCycles[prize]?.remainingNumbers || [];
    }

    const q = searchTerm.trim().toLowerCase();
    if (!q) return list;

    return list.filter((num) => num.includes(q));
  }, [data, selectedView, searchTerm]);

  const renderProgressBar = (percent) => {
    const color =
      percent >= 99 ? "#16a34a" :
      percent >= 90 ? "#22c55e" :
      percent >= 75 ? "#3b82f6" :
      percent >= 50 ? "#f59e0b" :
      "#ef4444";

    return (
      <div style={styles.progressBarOuter}>
        <div
          style={{
            ...styles.progressBarInner,
            width: `${percent}%`,
            background: color,
          }}
        />
      </div>
    );
  };

  return (
    <div style={styles.page}>
      <div style={styles.hero}>
        <h1 style={styles.title}>Current Cycle Comparison</h1>
        <p style={styles.subtitle}>
          Compare remaining numbers in Global Cycle 5 with current prize block cycles.
          Search across all remaining numbers.
        </p>
      </div>

      {error ? <div style={styles.errorBox}>{error}</div> : null}

      {loading && <div style={styles.loading}>Loading...</div>}

      {data && (
        <>
          {/* Search Bar */}
          <div style={styles.searchSection}>
            <input
              type="text"
              placeholder="Search remaining numbers across all prizes..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={styles.searchInput}
            />
          </div>

          {/* Global Cycle 5 */}
          <div style={styles.sectionCard}>
            <h3 style={styles.sectionTitle}>Global Cycle 5 (IN_PROGRESS)</h3>
            <div style={styles.infoGrid}>
              <div style={styles.infoCard}>
                <div style={styles.infoLabel}>Start Date</div>
                <div style={styles.infoValue}>{data.globalCycle.startDate}</div>
              </div>
              <div style={styles.infoCard}>
                <div style={styles.infoLabel}>End Date</div>
                <div style={styles.infoValue}>{data.globalCycle.endDate}</div>
              </div>
              <div style={styles.infoCard}>
                <div style={styles.infoLabel}>Seen Numbers</div>
                <div style={styles.infoValue}>{data.globalCycle.uniqueNumbersSeen.toLocaleString()}</div>
              </div>
              <div style={styles.infoCard}>
                <div style={styles.infoLabel}>Remaining</div>
                <div style={styles.infoValue}>{data.globalCycle.remainingCount.toLocaleString()}</div>
              </div>
              <div style={styles.infoCard}>
                <div style={styles.infoLabel}>Progress</div>
                <div style={styles.infoValue}>{data.globalCycle.progressPercent}%</div>
              </div>
            </div>

            <button
              style={styles.viewButton}
              onClick={() => setSelectedView("global")}
            >
              View {data.globalCycle.remainingCount} Remaining Numbers
            </button>

            {selectedView === "global" && (
              <div style={styles.numbersSection}>
                <h4 style={styles.subTitle}>Remaining Numbers in Global Cycle 5</h4>
                <div style={styles.numbersGrid}>
                  {filteredNumbers.length > 0 ? (
                    filteredNumbers.map((num) => (
                      <span key={num} style={styles.numberTag}>
                        {num}
                      </span>
                    ))
                  ) : (
                    <div style={styles.noResults}>
                      No remaining numbers found matching "{searchTerm}".
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Prize Block Cycles */}
          <div style={styles.sectionCard}>
            <h3 style={styles.sectionTitle}>Current Prize Block Cycles</h3>
            <div style={styles.prizeGrid}>
              {PRIZE_AMOUNTS.map((prize) => {
                const pc = data.prizeCycles[prize];
                if (!pc) return null;

                return (
                  <div key={prize} style={styles.prizeCard}>
                    <div style={styles.prizeHeader}>
                      <div style={styles.prizeAmount}>₹{prize}</div>
                      <div style={styles.prizeCycle}>Cycle {pc.cycleNumber}</div>
                    </div>
                    {renderProgressBar(pc.progress)}
                    <div style={styles.prizeStats}>
                      <div><strong>Seen:</strong> {pc.seen.toLocaleString()}</div>
                      <div><strong>Rem:</strong> {pc.remaining.toLocaleString()}</div>
                      <div><strong>Prog:</strong> {pc.progress}%</div>
                    </div>
                    <button
                      style={styles.viewButton}
                      onClick={() => setSelectedView(String(prize))}
                    >
                      View {pc.remaining} Remaining Numbers
                    </button>
                  </div>
                );
              })}
            </div>

            {selectedView !== "global" && (
              <div style={styles.numbersSection}>
                <h4 style={styles.subTitle}>
                  Remaining Numbers in ₹{selectedView} Cycle {data.prizeCycles[Number(selectedView)]?.cycleNumber}
                </h4>
                <div style={styles.numbersGrid}>
                  {filteredNumbers.length > 0 ? (
                    filteredNumbers.map((num) => (
                      <span key={num} style={styles.numberTag}>
                        {num}
                      </span>
                    ))
                  ) : (
                    <div style={styles.noResults}>
                      No remaining numbers found matching "{searchTerm}".
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </>
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
  loading: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 24,
    textAlign: "center",
    color: "#64748b",
    marginBottom: 20,
  },
  searchSection: {
    marginBottom: 20,
  },
  searchInput: {
    width: "100%",
    padding: "16px 20px",
    borderRadius: 16,
    border: "2px solid #e2e8f0",
    fontSize: 18,
    fontWeight: 600,
    boxSizing: "border-box",
    boxShadow: "0 2px 8px rgba(15,23,42,0.1)",
  },
  sectionCard: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 24,
    marginBottom: 24,
    boxShadow: "0 4px 12px rgba(15,23,42,0.05)",
  },
  sectionTitle: {
    marginTop: 0,
    marginBottom: 20,
    fontSize: 26,
    fontWeight: 800,
    color: "#0f172a",
  },
  infoGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 16,
    marginBottom: 20,
  },
  infoCard: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 16,
    padding: 16,
  },
  infoLabel: {
    fontSize: 14,
    color: "#64748b",
    marginBottom: 8,
    fontWeight: 600,
  },
  infoValue: {
    fontSize: 24,
    fontWeight: 800,
    color: "#0f172a",
  },
  viewButton: {
    background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
    color: "#fff",
    border: "none",
    borderRadius: 12,
    padding: "14px 24px",
    fontSize: 16,
    fontWeight: 700,
    cursor: "pointer",
    marginTop: 16,
    transition: "all 0.2s ease",
  },
  numbersSection: {
    marginTop: 24,
    padding: 20,
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 16,
  },
  subTitle: {
    marginTop: 0,
    marginBottom: 16,
    fontSize: 22,
    fontWeight: 700,
    color: "#0f172a",
  },
  numbersGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 12,
    padding: 16,
    background: "#fff",
    borderRadius: 12,
    border: "1px solid #e2e8f0",
    maxHeight: 500,
    overflowY: "auto",
  },
  numberTag: {
    background: "#fff",
    border: "2px solid #e2e8f0",
    color: "#0f172a",
    borderRadius: 12,
    padding: "10px 16px",
    fontSize: 16,
    fontWeight: 700,
    minWidth: 80,
    textAlign: "center",
    cursor: "default",
    transition: "all 0.2s ease",
  },
  noResults: {
    padding: 32,
    textAlign: "center",
    color: "#64748b",
    fontSize: 18,
    fontStyle: "italic",
  },
  prizeGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: 24,
    marginTop: 20,
  },
  prizeCard: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 18,
    padding: 20,
    transition: "all 0.2s ease",
  },
  prizeCardHover: {
    transform: "translateY(-2px)",
    boxShadow: "0 6px 16px rgba(15,23,42,0.1)",
  },
  prizeHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 16,
  },
  prizeAmount: {
    fontSize: 24,
    fontWeight: 800,
    color: "#0f172a",
  },
  prizeCycle: {
    fontSize: 16,
    fontWeight: 700,
    color: "#1d4ed8",
    background: "#eff6ff",
    padding: "4px 12px",
    borderRadius: 999,
  },
  progressBarOuter: {
    width: "100%",
    height: 12,
    background: "#e2e8f0",
    borderRadius: 999,
    overflow: "hidden",
    marginBottom: 16,
  },
  progressBarInner: {
    height: "100%",
    borderRadius: 999,
    transition: "width 0.3s ease",
  },
  prizeStats: {
    fontSize: 16,
    color: "#475569",
    lineHeight: 1.8,
    marginBottom: 16,
  },
};