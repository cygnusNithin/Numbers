import React, { useEffect, useMemo, useState } from "react";

const API_BASE = "http://localhost:5000";

const PRIZES = [50, 100, 200, 250, 300, 400, 500, 1000, 2000, 3000, 5000];

function CyclesComparisonPage() {
  const [dbKey, setDbKey] = useState("db3");
  const [selectedPrize, setSelectedPrize] = useState(5000);

  const [globalData, setGlobalData] = useState(null);
  const [prizeData, setPrizeData] = useState(null);

  const [loadingGlobal, setLoadingGlobal] = useState(false);
  const [loadingPrize, setLoadingPrize] = useState(false);
  const [error, setError] = useState(null);

  const fetchCycles = async (prize = null, setter, setLoading) => {
    setLoading(true);
    setError(null);
    try {
      const url = prize
        ? `${API_BASE}/api/cycles/${dbKey}?prize=${prize}`
        : `${API_BASE}/api/cycles/${dbKey}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch cycle data");
      const data = await res.json();
      setter(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCycles(null, setGlobalData, setLoadingGlobal);
  }, [dbKey]);

  useEffect(() => {
    if (selectedPrize) {
      fetchCycles(selectedPrize, setPrizeData, setLoadingPrize);
    } else {
      setPrizeData(null);
    }
  }, [dbKey, selectedPrize]);

  const renderCycleCard = (data, title, color) => {
    if (!data) return null;
    const curr = data.currentCycle;
    const progress = (curr.uniqueCount / 10000) * 100;
    return (
      <div
        style={{
          background: "white",
          border: `2px solid ${color}`,
          borderRadius: 16,
          padding: 20,
          marginBottom: 20,
        }}
      >
        <h3 style={{ margin: 0, color, fontWeight: 900 }}>{title}</h3>
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 14, color: "#475569" }}>
            Completed Cycles: <strong>{data.totalCompletedCycles}</strong>
          </div>
          <div style={{ fontSize: 14, color: "#475569" }}>
            Current Cycle: <strong>{curr.cycle}</strong>
          </div>
          <div style={{ fontSize: 14, color: "#475569" }}>
            Start Date: <strong>{curr.startDate || "—"}</strong>
          </div>
          <div style={{ fontSize: 14, color: "#475569" }}>
            Last Date: <strong>{curr.lastDate || "—"}</strong>
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 14, color: "#475569", marginBottom: 6 }}>
              Progress: {curr.uniqueCount} / 10000 ({progress.toFixed(2)}%)
            </div>
            <div
              style={{
                width: "100%",
                height: 12,
                background: "#e2e8f0",
                borderRadius: 6,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${progress}%`,
                  height: "100%",
                  background: color,
                  transition: "width 0.3s",
                }}
              />
            </div>
          </div>
          <div style={{ marginTop: 12, fontSize: 14, color: "#475569" }}>
            Remaining: <strong style={{ color: "#ef4444" }}>{curr.remainingCount}</strong> numbers
          </div>
          {curr.remainingNumbers?.length > 0 && curr.remainingNumbers.length <= 500 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", marginBottom: 6 }}>
                Remaining Numbers:
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(60px, 1fr))",
                  gap: 6,
                  maxHeight: 200,
                  overflowY: "auto",
                  padding: 8,
                  background: "#f8fafc",
                  borderRadius: 8,
                }}
              >
                {curr.remainingNumbers.map((n) => (
                  <div
                    key={n}
                    style={{
                      background: "#fee2e2",
                      color: "#991b1b",
                      padding: "4px 6px",
                      borderRadius: 4,
                      fontSize: 12,
                      fontWeight: 700,
                      textAlign: "center",
                    }}
                  >
                    {n}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderCyclesTable = (data, title) => {
    if (!data?.cycles?.length) return null;
    return (
      <div style={{ marginTop: 20 }}>
        <h4 style={{ margin: "0 0 10px", fontWeight: 800 }}>{title} — Completed Cycles</h4>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f1f5f9" }}>
                <th style={{ padding: 8, border: "1px solid #e2e8f0", textAlign: "left" }}>Cycle</th>
                <th style={{ padding: 8, border: "1px solid #e2e8f0", textAlign: "left" }}>Start Date</th>
                <th style={{ padding: 8, border: "1px solid #e2e8f0", textAlign: "left" }}>End Date</th>
                <th style={{ padding: 8, border: "1px solid #e2e8f0", textAlign: "right" }}>Unique</th>
              </tr>
            </thead>
            <tbody>
              {data.cycles.map((c) => (
                <tr key={c.cycle}>
                  <td style={{ padding: 8, border: "1px solid #e2e8f0", fontWeight: 700 }}>{c.cycle}</td>
                  <td style={{ padding: 8, border: "1px solid #e2e8f0" }}>{c.startDate}</td>
                  <td style={{ padding: 8, border: "1px solid #e2e8f0" }}>{c.endDate}</td>
                  <td style={{ padding: 8, border: "1px solid #e2e8f0", textAlign: "right" }}>{c.uniqueCount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div style={{ padding: 20, maxWidth: 1200, margin: "0 auto" }}>
      <h2 style={{ margin: 0, fontWeight: 900 }}>🔄 Cycle Comparison: Global vs Prize</h2>
      <p style={{ margin: "8px 0 20px", color: "#475569" }}>
        Compare how fast the full dataset completes 0000–9999 vs individual prize categories.
      </p>

      {/* Controls */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
        <div>
          <label style={{ display: "block", fontSize: 12, fontWeight: 700, marginBottom: 4 }}>Database</label>
          <select
            value={dbKey}
            onChange={(e) => setDbKey(e.target.value)}
            style={{ padding: 8, borderRadius: 8, border: "1px solid #cbd5e1", fontWeight: 700 }}
          >
            <option value="db3">DB3 (FullLotteryData)</option>
            <option value="db4">DB4 (AbsoluteData)</option>
          </select>
        </div>

        <div>
          <label style={{ display: "block", fontSize: 12, fontWeight: 700, marginBottom: 4 }}>Prize Category</label>
          <select
            value={selectedPrize}
            onChange={(e) => setSelectedPrize(Number(e.target.value))}
            style={{ padding: 8, borderRadius: 8, border: "1px solid #cbd5e1", fontWeight: 700 }}
          >
            {PRIZES.map((p) => (
              <option key={p} value={p}>₹{p}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: "#fee2e2", color: "#991b1b", padding: 12, borderRadius: 8, marginBottom: 20 }}>
          ❌ {error}
        </div>
      )}

      {/* Loading */}
      {(loadingGlobal || loadingPrize) && (
        <div style={{ textAlign: "center", color: "#475569", marginBottom: 20 }}>⏳ Loading cycle data...</div>
      )}

      {/* Comparison Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(350px, 1fr))", gap: 20 }}>
        {renderCycleCard(globalData, "🌍 Global Cycle (All Prizes)", "#2563eb")}
        {renderCycleCard(prizeData, `💰 Prize Cycle (₹${selectedPrize})`, "#7c3aed")}
      </div>

      {/* Comparison Summary */}
      {globalData && prizeData && (
        <div style={{ marginTop: 20, background: "#f8fafc", padding: 16, borderRadius: 12, border: "1px solid #e2e8f0" }}>
          <h4 style={{ margin: "0 0 12px", fontWeight: 800 }}>📊 Comparison Summary</h4>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
            <div>
              <div style={{ fontSize: 12, color: "#64748b", fontWeight: 700 }}>Global Cycles Completed</div>
              <div style={{ fontSize: 20, fontWeight: 900, color: "#2563eb" }}>{globalData.totalCompletedCycles}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: "#64748b", fontWeight: 700 }}>Prize Cycles Completed</div>
              <div style={{ fontSize: 20, fontWeight: 900, color: "#7c3aed" }}>{prizeData.totalCompletedCycles}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: "#64748b", fontWeight: 700 }}>Global Remaining</div>
              <div style={{ fontSize: 20, fontWeight: 900, color: "#ef4444" }}>{globalData.currentCycle.remainingCount}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: "#64748b", fontWeight: 700 }}>Prize Remaining</div>
              <div style={{ fontSize: 20, fontWeight: 900, color: "#ef4444" }}>{prizeData.currentCycle.remainingCount}</div>
            </div>
          </div>
        </div>
      )}

      {/* Completed Cycles Tables */}
      {renderCyclesTable(globalData, "Global Cycles")}
      {renderCyclesTable(prizeData, `Prize ₹${selectedPrize} Cycles`)}
    </div>
  );
}

export default CyclesComparisonPage;