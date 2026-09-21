import React, { useEffect, useMemo, useState } from "react";
import "./App.css";

export default function GridPage({ countsData }) {
  const [counts, setCounts] = useState(countsData?.numberCounts || {});
  const [baseCounts, setBaseCounts] = useState(countsData?.numberCounts || {});
  const [prizeTotals, setPrizeTotals] = useState(countsData?.prizeTotals || {});
  const [source, setSource] = useState(countsData?.source || "db3");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Prize selection (grid updates instead of modal)
  const [selectedPrize, setSelectedPrize] = useState(null);
  const [prizeLoading, setPrizeLoading] = useState(false);

  // Fetch counts from selected database (ALL numbers overall)
  const fetchCounts = async (dbSource) => {
    setLoading(true);
    setError(null);
    setSelectedPrize(null); // reset prize mode when switching db / refetching

    try {
      const url =
        dbSource === "db3"
          ? "http://localhost:5000/api/counts-db3"
          : "http://localhost:5000/api/counts-db4";

      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch");

      const data = await res.json();
      setBaseCounts(data.numberCounts || {});
      setCounts(data.numberCounts || {});
      setPrizeTotals(data.prizeTotals || {});
    } catch (err) {
      setError(err.message || "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  };

  // If parent already passed countsData, use it first
  useEffect(() => {
    if (countsData?.numberCounts) {
      setBaseCounts(countsData.numberCounts);
      setCounts(countsData.numberCounts);
      setPrizeTotals(countsData.prizeTotals || {});
      setSource(countsData.source || "db3");
    } else {
      fetchCounts(source);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countsData]);

  // Fetch numbers for selected prize and update SAME grid counts
  const handlePrizeClick = async (prize) => {
    setSelectedPrize(prize);
    setPrizeLoading(true);
    setError(null);

    try {
      const res = await fetch(
        `http://localhost:5000/api/prize-numbers/${source}/${prize}`
      );

      if (!res.ok) throw new Error("Failed to fetch prize numbers");

      const data = await res.json();

      // Build a counts map: { "0001": 2, "0456": 1, ... }
      const map = {};
      (data.numbers || []).forEach((item) => {
        map[item.number] = item.count; // item.count is "hits count"
      });

      setCounts(map);
    } catch (err) {
      setCounts({});
      console.error("Error fetching prize numbers:", err);
      setError(err.message || "Failed to fetch prize numbers");
    } finally {
      setPrizeLoading(false);
    }
  };

  const handleShowAll = () => {
    setSelectedPrize(null);
    setCounts(baseCounts || {});
  };

  // Color scale based on frequency (only among current grid data)
  const { maxCount } = useMemo(() => {
    const vals = Object.values(counts).filter((v) => typeof v === "number");
    const mx = vals.length ? Math.max(...vals) : 0;
    return { maxCount: mx };
  }, [counts]);

  const getColor = (count) => {
    if (!count || count === 0) return "#ffffff";
    const ratio = count / (maxCount || 1); // 0..1
    const hue = 120 * ratio; // green-ish up to 120
    return `hsl(${hue}, 80%, 75%)`;
  };

  const totalNumbersDrawn = useMemo(() => {
    return Object.values(counts).reduce((a, b) => a + (Number(b) || 0), 0);
  }, [counts]);

  const totalUniqueNumbers = useMemo(() => {
    return Object.keys(counts).length;
  }, [counts]);

  const renderGrid = () => {
    const gridItems = [];

    for (let i = 0; i <= 9999; i++) {
      const num = i.toString().padStart(4, "0");
      const count = counts[num] || 0;

      gridItems.push(
        <div
          key={num}
          className="cell"
          style={{ backgroundColor: getColor(count) }}
          title={
            selectedPrize
              ? `#${num}: ${count} hits in Prize ₹${selectedPrize}`
              : `#${num}: ${count} hits`
          }
        >
          <div className="number">{num}</div>
          {count > 0 && <div className="count">{count}</div>}
        </div>
      );
    }

    return gridItems;
  };

  const handleSwitch = (newSource) => {
    setSource(newSource);
    handleShowAll();
    fetchCounts(newSource);
  };

  return (
    <div className="container">
      <div className="action-bar">
        <h3>🎯 Lottery Number Grid View</h3>

        {/* Database Source Toggle */}
        <div style={{ display: "flex", gap: "10px", marginTop: "10px" }}>
          <button
            onClick={() => handleSwitch("db3")}
            style={{
              padding: "10px 18px",
              backgroundColor: source === "db3" ? "#2563eb" : "#e0e0e0",
              color: source === "db3" ? "white" : "black",
              border: "none",
              borderRadius: "8px",
              cursor: "pointer",
              fontWeight: "bold",
              fontSize: "14px",
              transition: "all 0.3s",
            }}
          >
            📊 FullLotteryData (DB3)
          </button>

          <button
            onClick={() => handleSwitch("db4")}
            style={{
              padding: "10px 18px",
              backgroundColor: source === "db4" ? "#7c3aed" : "#e0e0e0",
              color: source === "db4" ? "white" : "black",
              border: "none",
              borderRadius: "8px",
              cursor: "pointer",
              fontWeight: "bold",
              fontSize: "14px",
              transition: "all 0.3s",
            }}
          >
            📈 AbsoluteData (DB4)
          </button>
        </div>

        <p
          style={{
            marginTop: "10px",
            color: "#555",
            fontSize: "13px",
            fontWeight: "600",
          }}
        >
          Showing:{" "}
          <strong>
            {selectedPrize ? `Prize ₹${selectedPrize}` : source === "db3" ? "FullLotteryData" : "AbsoluteData"}
          </strong>
        </p>

        {selectedPrize && (
          <div style={{ marginTop: "10px" }}>
            <button
              onClick={handleShowAll}
              style={{
                padding: "8px 14px",
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: "10px",
                cursor: "pointer",
                fontWeight: "800",
                color: "#0f172a",
              }}
            >
              ↩ Show All
            </button>
          </div>
        )}
      </div>

      {/* Stats Section */}
      {!loading && !error && (
        <div style={styles.statsContainer}>
          <div style={styles.statBox}>
            <div style={styles.statLabel}>Total Numbers Drawn (in view)</div>
            <div style={styles.statValue}>{totalNumbersDrawn}</div>
          </div>

          <div style={styles.statBox}>
            <div style={styles.statLabel}>Unique Numbers (in view)</div>
            <div style={styles.statValue}>{totalUniqueNumbers}</div>
          </div>

          <div style={styles.statBox}>
            <div style={styles.statLabel}>Unused Numbers</div>
            <div style={styles.statValue}>{10000 - totalUniqueNumbers}</div>
          </div>
        </div>
      )}

      {/* Prize Totals Section */}
      {!loading && !error && Object.keys(prizeTotals).length > 0 && (
        <div style={styles.prizeTotalsContainer}>
          <h4
            style={{
              margin: "0 0 16px 0",
              fontSize: "17px",
              fontWeight: "800",
              color: "#0f172a",
            }}
          >
            💰 Prize Categories Breakdown
          </h4>

          <div style={styles.prizeGrid}>
            {Object.entries(prizeTotals)
              .sort((a, b) => Number(b[0]) - Number(a[0]))
              .map(([prize, total]) => {
                const isSelected = String(prize) === String(selectedPrize);
                return (
                  <button
                    key={prize}
                    onClick={() => handlePrizeClick(prize)}
                    disabled={prizeLoading && isSelected}
                    style={{
                      ...styles.prizeCard,
                      background: isSelected
                        ? "linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%)"
                        : "linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%)",
                      borderColor: isSelected ? "#2563eb" : "#93c5fd",
                      color: isSelected ? "#fff" : "#0369a1",
                      boxShadow: isSelected
                        ? "0 8px 24px rgba(37, 99, 235, 0.4)"
                        : "0 2px 8px rgba(59, 130, 246, 0.1)",
                      transform: isSelected ? "scale(1.05)" : "scale(1)",
                      opacity: prizeLoading && !isSelected ? 0.85 : 1,
                    }}
                  >
                    <div
                      style={{
                        ...styles.prizeLabel,
                        color: isSelected ? "#fff" : "#0c4a6e",
                      }}
                    >
                      ₹{prize}
                    </div>
                    <div
                      style={{
                        ...styles.prizeValue,
                        color: isSelected ? "#fff" : "#0369a1",
                      }}
                    >
                      {total}
                    </div>
                  </button>
                );
              })}
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <p style={{ textAlign: "center", marginTop: "20px", fontSize: "16px" }}>
          ⏳ Loading data...
        </p>
      )}

      {prizeLoading && !loading && (
        <p style={{ textAlign: "center", marginTop: "10px", fontSize: "16px", color: "#334155" }}>
          ⏳ Loading prize numbers... (grid updating)
        </p>
      )}

      {/* Error state */}
      {error && (
        <p style={{ textAlign: "center", color: "red", marginTop: "20px", fontSize: "16px" }}>
          ❌ Error: {error}
        </p>
      )}

      {/* Grid */}
      {!loading && !error && <div className="grid">{renderGrid()}</div>}
    </div>
  );
}

const styles = {
  statsContainer: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
    gap: "12px",
    marginTop: "16px",
    marginBottom: "20px",
  },
  statBox: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: "12px",
    padding: "18px",
    textAlign: "center",
    transition: "all 0.3s ease",
  },
  statLabel: {
    fontSize: "11px",
    color: "#64748b",
    marginBottom: "10px",
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: "0.8px",
  },
  statValue: {
    fontSize: "28px",
    fontWeight: "900",
    color: "#0f172a",
  },

  prizeTotalsContainer: {
    background: "white",
    border: "1px solid #e2e8f0",
    borderRadius: "14px",
    padding: "22px",
    marginTop: "16px",
    marginBottom: "20px",
    boxShadow: "0 4px 12px rgba(15, 23, 42, 0.05)",
  },
  prizeGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
    gap: "12px",
  },
  prizeCard: {
    background: "linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%)",
    border: "1.5px solid #93c5fd",
    borderRadius: "12px",
    padding: "16px",
    textAlign: "center",
    transition: "all 0.3s ease",
    cursor: "pointer",
    fontFamily: "sans-serif",
  },
  prizeLabel: {
    fontSize: "13px",
    color: "#0c4a6e",
    marginBottom: "8px",
    fontWeight: "700",
    letterSpacing: "0.3px",
  },
  prizeValue: {
    fontSize: "24px",
    fontWeight: "900",
    color: "#0369a1",
  },
};