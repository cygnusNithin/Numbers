import React, { useEffect, useMemo, useState } from "react";

export default function CompareFourDBsPage() {
  const [filters, setFilters] = useState({
    fromDate: "",
    toDate: "",
    serialNumber: "",
    status: "",
  });

  const [data, setData] = useState({
    summary: null,
    rows: [],
    allPrizes: [],
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedKey, setExpandedKey] = useState("");

  const loadComparison = async () => {
    try {
      setLoading(true);
      setError("");

      const params = new URLSearchParams();

      if (filters.fromDate) params.append("fromDate", filters.fromDate);
      if (filters.toDate) params.append("toDate", filters.toDate);
      if (filters.serialNumber)
        params.append("serialNumber", filters.serialNumber);
      if (filters.status) params.append("status", filters.status);

      const res = await fetch(`http://localhost:5000/api/compare-3-dbs?${params.toString()}`);
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.details || json.error || "Failed to load comparison");
      }

      setData({
        summary: json.summary || null,
        rows: json.rows || [],
        allPrizes: json.allPrizes || [],
      });
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadComparison();
  }, []);

  const groupedByDate = useMemo(() => {
    const grouped = {};

    for (const row of data.rows || []) {
      const date = row.date || "Unknown Date";
      if (!grouped[date]) grouped[date] = [];
      grouped[date].push(row);
    }

    return grouped;
  }, [data.rows]);

  const allPrizes = useMemo(() => {
    const set = new Set((data.allPrizes || []).map(String));

    for (const row of data.rows || []) {
      [row.db1, row.db2, row.db3, row.db4].forEach((db) => {
        Object.keys(db?.series || {}).forEach((prize) => set.add(String(prize)));
      });
    }

    return Array.from(set).sort((a, b) => Number(b) - Number(a));
  }, [data]);

  const updateFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const clearFilters = () => {
    setFilters({
      fromDate: "",
      toDate: "",
      serialNumber: "",
      status: "",
    });
  };

  const renderBadge = (status) => {
    const map = {
      MATCH: {
        background: "#dcfce7",
        color: "#166534",
        border: "1px solid #86efac",
      },
      MISSING: {
        background: "#ffedd5",
        color: "#9a3412",
        border: "1px solid #fdba74",
      },
      MISMATCH: {
        background: "#fee2e2",
        color: "#991b1b",
        border: "1px solid #fca5a5",
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
          ...style,
          padding: "6px 10px",
          borderRadius: "999px",
          fontWeight: 700,
          fontSize: 12,
        }}
      >
        {status}
      </span>
    );
  };

  const renderNumberChips = (numbers = []) => {
    if (!numbers.length) {
      return <div style={{ color: "#94a3b8" }}>No numbers</div>;
    }

    return (
      <div style={styles.numberWrap}>
        {numbers.map((item) => (
          <span
            key={`${item.number}-${item.count}`}
            style={styles.numberChip}
          >
            {item.number}
            {item.count > 1 ? ` (${item.count})` : ""}
          </span>
        ))}
      </div>
    );
  };

  const renderDbPanel = (title, db, dbKey) => {
    const colorMap = {
      db1: { bg: "#f0f9ff", border: "#0284c7", title: "#0c4a6e" },
      db2: { bg: "#fef3c7", border: "#f59e0b", title: "#92400e" },
      db3: { bg: "#f3e8ff", border: "#9333ea", title: "#581c87" },
      db4: { bg: "#fee2e2", border: "#dc2626", title: "#7c2d12" },
    };

    const colors = colorMap[dbKey] || colorMap.db1;

    return (
      <div style={{ ...styles.dbCard, background: colors.bg, borderColor: colors.border }}>
        <div style={styles.dbHeader}>
          <div>
            <div style={{ ...styles.dbTitle, color: colors.title }}>{title}</div>
            {db ? (
              <div style={{ ...styles.dbSubTitle, color: colors.border }}>
                Total Numbers: {db.totalNumbers}
              </div>
            ) : (
              <div style={{ color: "#dc2626", fontWeight: 700 }}>Missing</div>
            )}
          </div>
        </div>

        {!db ? (
          <div style={{ color: "#94a3b8" }}>No record found in this DB</div>
        ) : (
          <>
            <div style={styles.metaRow}>
              {db.entryNumber != null && (
                <span style={styles.metaBadge}>Entry #{db.entryNumber}</span>
              )}
              {db.recordNumber != null && (
                <span style={styles.metaBadge}>Record #{db.recordNumber}</span>
              )}
              {db.fileName ? (
                <span style={styles.metaBadge}>File: {db.fileName}</span>
              ) : null}
            </div>

            {allPrizes.map((prize) => (
              <div key={`${title}-${prize}`} style={styles.prizeBox}>
                <div style={styles.prizeTitle}>Prize ₹{prize}</div>
                {renderNumberChips(db.series?.[prize] || [])}
              </div>
            ))}
          </>
        )}
      </div>
    );
  };

  const renderDiffPanel = (title, diffs = []) => {
    return (
      <div style={styles.diffPanel}>
        <div style={styles.dbTitle}>{title}</div>

        {!diffs.length ? (
          <div style={{ color: "#16a34a", fontWeight: 700, marginTop: 10 }}>
            No differences
          </div>
        ) : (
          <div style={{ marginTop: 12 }}>
            {diffs.map((diff) => (
              <div key={`${title}-${diff.prize}`} style={styles.diffCard}>
                <div style={styles.diffPrize}>Prize ₹{diff.prize}</div>

                <div style={styles.diffLine}>
                  <strong>Only in A:</strong>{" "}
                  {diff.onlyInA?.length
                    ? diff.onlyInA
                        .map((x) =>
                          x.count > 1 ? `${x.number} (${x.count})` : x.number
                        )
                        .join(", ")
                    : "-"}
                </div>

                <div style={styles.diffLine}>
                  <strong>Only in B:</strong>{" "}
                  {diff.onlyInB?.length
                    ? diff.onlyInB
                        .map((x) =>
                          x.count > 1 ? `${x.number} (${x.count})` : x.number
                        )
                        .join(", ")
                    : "-"}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>Compare 4 Lottery DBs</h1>
        <p style={styles.subtitle}>
          Compare LotteryData, LotteryDataNew, FullLotteryData and AbsoluteData by date,
          serial number, prize category and winning numbers.
        </p>
      </div>

      <div style={styles.filterCard}>
        <div style={styles.filterGrid}>
          <div>
            <label style={styles.label}>From Date</label>
            <input
              style={styles.input}
              type="date"
              value={filters.fromDate}
              onChange={(e) => updateFilter("fromDate", e.target.value)}
            />
          </div>

          <div>
            <label style={styles.label}>To Date</label>
            <input
              style={styles.input}
              type="date"
              value={filters.toDate}
              onChange={(e) => updateFilter("toDate", e.target.value)}
            />
          </div>

          <div>
            <label style={styles.label}>Serial Number</label>
            <input
              style={styles.input}
              type="text"
              placeholder="e.g. KR-456"
              value={filters.serialNumber}
              onChange={(e) => updateFilter("serialNumber", e.target.value)}
            />
          </div>

          <div>
            <label style={styles.label}>Status</label>
            <select
              style={styles.input}
              value={filters.status}
              onChange={(e) => updateFilter("status", e.target.value)}
            >
              <option value="">All</option>
              <option value="MATCH">MATCH</option>
              <option value="MISSING">MISSING</option>
              <option value="MISMATCH">MISMATCH</option>
            </select>
          </div>
        </div>

        <div style={styles.buttonRow}>
          <button style={styles.primaryButton} onClick={loadComparison}>
            {loading ? "Loading..." : "Compare"}
          </button>

          <button
            style={styles.secondaryButton}
            onClick={() => {
              clearFilters();
              setTimeout(() => {
                setData({ summary: null, rows: [], allPrizes: [] });
              }, 0);
            }}
          >
            Clear
          </button>
        </div>
      </div>

      {error ? <div style={styles.errorBox}>{error}</div> : null}

      {data.summary && (
        <div style={styles.summaryGrid}>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Total</div>
            <div style={styles.summaryValue}>{data.summary.total}</div>
          </div>

          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Matched</div>
            <div style={{ ...styles.summaryValue, color: "#15803d" }}>
              {data.summary.matched}
            </div>
          </div>

          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Missing</div>
            <div style={{ ...styles.summaryValue, color: "#c2410c" }}>
              {data.summary.missing}
            </div>
          </div>

          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Mismatch</div>
            <div style={{ ...styles.summaryValue, color: "#b91c1c" }}>
              {data.summary.mismatch}
            </div>
          </div>
        </div>
      )}

      {allPrizes.length > 0 && (
        <div style={styles.prizeLegend}>
          <strong>Prize Categories:</strong>{" "}
          {allPrizes.map((p) => `₹${p}`).join(", ")}
        </div>
      )}

      {!loading && !Object.keys(groupedByDate).length && (
        <div style={styles.emptyBox}>No comparison data found.</div>
      )}

      {Object.entries(groupedByDate).map(([date, rows]) => (
        <div key={date} style={styles.dateSection}>
          <div style={styles.dateHeader}>
            <h2 style={{ margin: 0 }}>{date}</h2>
            <span style={styles.dateCount}>{rows.length} record(s)</span>
          </div>

          <div style={styles.rowsWrap}>
            {rows.map((row) => (
              <div key={row.key} style={styles.rowCard}>
                <div style={styles.rowTop}>
                  <div>
                    <div style={styles.serialText}>{row.serialNumber}</div>
                    <div style={styles.reasonText}>
                      {row.missingIn?.length
                        ? `Missing in: ${row.missingIn.join(", ")}`
                        : row.mismatchReason?.length
                        ? row.mismatchReason.join(", ")
                        : "All four databases match"}
                    </div>
                  </div>

                  <div style={styles.rowTopRight}>
                    {renderBadge(row.status)}
                    <button
                      style={styles.viewButton}
                      onClick={() =>
                        setExpandedKey(expandedKey === row.key ? "" : row.key)
                      }
                    >
                      {expandedKey === row.key ? "Hide Details" : "View Details"}
                    </button>
                  </div>
                </div>

                <div style={styles.quickStats}>
                  <div style={styles.quickStatCard}>
                    <div style={styles.quickStatLabel}>LotteryData</div>
                    <div style={styles.quickStatValue}>
                      {row.db1 ? row.db1.totalNumbers : "Missing"}
                    </div>
                  </div>

                  <div style={styles.quickStatCard}>
                    <div style={styles.quickStatLabel}>LotteryDataNew</div>
                    <div style={styles.quickStatValue}>
                      {row.db2 ? row.db2.totalNumbers : "Missing"}
                    </div>
                  </div>

                  <div style={styles.quickStatCard}>
                    <div style={styles.quickStatLabel}>FullLotteryData</div>
                    <div style={styles.quickStatValue}>
                      {row.db3 ? row.db3.totalNumbers : "Missing"}
                    </div>
                  </div>

                  <div style={styles.quickStatCard}>
                    <div style={styles.quickStatLabel}>AbsoluteData</div>
                    <div style={styles.quickStatValue}>
                      {row.db4 ? row.db4.totalNumbers : "Missing"}
                    </div>
                  </div>
                </div>

                {expandedKey === row.key && (
                  <div style={styles.detailsArea}>
                    <div style={styles.dbGrid}>
                      {renderDbPanel("LotteryData", row.db1, "db1")}
                      {renderDbPanel("LotteryDataNew", row.db2, "db2")}
                      {renderDbPanel("FullLotteryData", row.db3, "db3")}
                      {renderDbPanel("AbsoluteData", row.db4, "db4")}
                    </div>

                    <div style={styles.diffGrid}>
                      {renderDiffPanel(
                        "LotteryData vs LotteryDataNew",
                        row.diffs?.db1VsDb2 || []
                      )}
                      {renderDiffPanel(
                        "LotteryData vs FullLotteryData",
                        row.diffs?.db1VsDb3 || []
                      )}
                      {renderDiffPanel(
                        "LotteryData vs AbsoluteData",
                        row.diffs?.db1VsDb4 || []
                      )}
                      {renderDiffPanel(
                        "LotteryDataNew vs FullLotteryData",
                        row.diffs?.db2VsDb3 || []
                      )}
                      {renderDiffPanel(
                        "LotteryDataNew vs AbsoluteData",
                        row.diffs?.db2VsDb4 || []
                      )}
                      {renderDiffPanel(
                        "FullLotteryData vs AbsoluteData",
                        row.diffs?.db3VsDb4 || []
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
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
  filterCard: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 20,
    padding: 20,
    marginBottom: 20,
    boxShadow: "0 12px 30px rgba(15,23,42,0.06)",
  },
  filterGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 16,
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
    outline: "none",
    background: "#fff",
  },
  buttonRow: {
    display: "flex",
    gap: 12,
    marginTop: 16,
    flexWrap: "wrap",
  },
  primaryButton: {
    background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
    color: "#fff",
    border: "none",
    borderRadius: 12,
    padding: "12px 18px",
    cursor: "pointer",
    fontWeight: 700,
  },
  secondaryButton: {
    background: "#fff",
    color: "#0f172a",
    border: "1px solid #cbd5e1",
    borderRadius: 12,
    padding: "12px 18px",
    cursor: "pointer",
    fontWeight: 700,
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
    fontSize: 30,
    fontWeight: 800,
  },
  prizeLegend: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 14,
    padding: 14,
    marginBottom: 20,
  },
  emptyBox: {
    background: "#fff",
    borderRadius: 18,
    padding: 24,
    textAlign: "center",
    color: "#64748b",
    border: "1px solid #e2e8f0",
  },
  dateSection: {
    marginBottom: 28,
  },
  dateHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap",
    marginBottom: 12,
    padding: "0 4px",
  },
  dateCount: {
    color: "#64748b",
    fontWeight: 600,
  },
  rowsWrap: {
    display: "grid",
    gap: 16,
  },
  rowCard: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 20,
    padding: 18,
    boxShadow: "0 10px 24px rgba(15,23,42,0.05)",
  },
  rowTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 16,
    flexWrap: "wrap",
  },
  serialText: {
    fontSize: 22,
    fontWeight: 800,
    marginBottom: 6,
  },
  reasonText: {
    color: "#64748b",
    fontSize: 14,
    lineHeight: 1.5,
  },
  rowTopRight: {
    display: "flex",
    gap: 10,
    alignItems: "center",
    flexWrap: "wrap",
  },
  viewButton: {
    background: "#fff",
    border: "1px solid #cbd5e1",
    borderRadius: 12,
    padding: "10px 14px",
    cursor: "pointer",
    fontWeight: 700,
  },
  quickStats: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
    gap: 12,
    marginTop: 16,
  },
  quickStatCard: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 14,
    padding: 14,
  },
  quickStatLabel: {
    fontSize: 13,
    color: "#64748b",
    marginBottom: 6,
  },
  quickStatValue: {
    fontSize: 22,
    fontWeight: 800,
  },
  detailsArea: {
    marginTop: 20,
    paddingTop: 20,
    borderTop: "1px solid #e2e8f0",
  },
  dbGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: 16,
    marginBottom: 20,
  },
  dbCard: {
    background: "#f8fbff",
    border: "2px solid #dbeafe",
    borderRadius: 18,
    padding: 16,
  },
  dbHeader: {
    marginBottom: 12,
  },
  dbTitle: {
    fontSize: 18,
    fontWeight: 800,
    marginBottom: 4,
  },
  dbSubTitle: {
    fontWeight: 700,
    fontSize: 13,
  },
  metaRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 12,
  },
  metaBadge: {
    background: "#e2e8f0",
    color: "#334155",
    padding: "4px 8px",
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 600,
  },
  prizeBox: {
    marginBottom: 14,
    paddingBottom: 12,
    borderBottom: "1px dashed #cbd5e1",
  },
  prizeTitle: {
    fontWeight: 800,
    marginBottom: 8,
    color: "#1e293b",
  },
  numberWrap: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  numberChip: {
    background: "#fff",
    border: "1px solid #cbd5e1",
    color: "#1e293b",
    borderRadius: 999,
    padding: "4px 8px",
    fontSize: 12,
    fontWeight: 600,
  },
  diffGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: 16,
  },
  diffPanel: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 16,
    padding: 16,
  },
  diffCard: {
    background: "#fafafa",
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    padding: 12,
    marginTop: 12,
  },
  diffPrize: {
    fontWeight: 800,
    marginBottom: 8,
  },
  diffLine: {
    color: "#334155",
    lineHeight: 1.5,
    marginBottom: 8,
    fontSize: 13,
  },
};