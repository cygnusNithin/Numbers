import React, { useEffect, useMemo, useState } from "react";

const API_BASE = "http://localhost:5000";

function pad4(n) {
  return String(n).padStart(4, "0");
}

export default function Cycle5000Page() {
  const [dbKey, setDbKey] = useState("db3"); // db3 => FullLotteryData, db4 => AbsoluteData
  const [steps, setSteps] = useState([]);
  const [selectedDateKey, setSelectedDateKey] = useState(null);

  const [mode, setMode] = useState("unique"); // "unique" | "balance"
  const [loadingCycle, setLoadingCycle] = useState(false);
  const [loadingNumbers, setLoadingNumbers] = useState(false);
  const [error, setError] = useState(null);

  const [cumulativeSet, setCumulativeSet] = useState(new Set()); // unique numbers upto selected date

  const allNumbers = useMemo(() => Array.from({ length: 10000 }, (_, i) => pad4(i)), []);

  const selectedStep = useMemo(() => {
    return steps.find((s) => s.dateKey === selectedDateKey) || null;
  }, [steps, selectedDateKey]);

  // Fetch cycle timeline
  useEffect(() => {
    const fetchCycle = async () => {
      setLoadingCycle(true);
      setError(null);
      setSteps([]);
      setSelectedDateKey(null);
      setCumulativeSet(new Set());

      try {
        const res = await fetch(`${API_BASE}/api/cycle-5000/${dbKey}`);
        if (!res.ok) throw new Error("Failed to fetch cycle timeline");

        const data = await res.json();
        const fetchedSteps = data.steps || [];
        setSteps(fetchedSteps);

        // day1 = first date in sorted array
        if (fetchedSteps.length > 0) {
          setSelectedDateKey(fetchedSteps[0].dateKey);
        }
      } catch (e) {
        setError(e.message || "Error while fetching cycle");
      } finally {
        setLoadingCycle(false);
      }
    };

    fetchCycle();
  }, [dbKey]);

  // Fetch cumulative unique numbers for selected date
  useEffect(() => {
    if (!selectedDateKey) return;

    const fetchCumulative = async () => {
      setLoadingNumbers(true);
      setError(null);
      try {
        const url = `${API_BASE}/api/cycle-5000/cumulative/${dbKey}?dateKey=${encodeURIComponent(
          selectedDateKey
        )}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch cumulative numbers");

        const data = await res.json();
        const set = new Set(data.numbers || []);
        setCumulativeSet(set);
      } catch (e) {
        setError(e.message || "Error while fetching cumulative numbers");
        setCumulativeSet(new Set());
      } finally {
        setLoadingNumbers(false);
      }
    };

    fetchCumulative();
  }, [dbKey, selectedDateKey]);

  const renderCell = (num) => {
    const isUnique = cumulativeSet.has(num);
    const active = mode === "unique" ? isUnique : !isUnique;

    // Colors
    const activeBg =
      mode === "unique" ? "rgba(59,130,246,0.75)" : "rgba(248,113,113,0.65)";
    const inactiveBg = "#f8fafc";

    return (
      <div
        key={num}
        title={
          mode === "unique"
            ? `#${num} : ${isUnique ? "Unique Drawn (₹5000)" : "Not drawn"}`
            : `#${num} : ${!isUnique ? "Balance (Not drawn yet)" : "Already drawn"}`
        }
        style={{
          background: active ? activeBg : inactiveBg,
          border: "1px solid #e2e8f0",
          borderRadius: 2,
          height: 12,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
        }}
      >
        {active ? (
          <span style={{ fontSize: 7, fontWeight: 800, color: "#0f172a" }}>{num}</span>
        ) : null}
      </div>
    );
  };

  return (
    <div style={{ padding: 16 }}>
      <div style={{ marginBottom: 14 }}>
        <h2 style={{ margin: 0, fontWeight: 900 }}>🟦 Cycle for Prize ₹5000</h2>
        <p style={{ margin: "8px 0 0", color: "#475569", fontWeight: 600, fontSize: 13 }}>
          Day-by-day cumulative <b>Unique</b> numbers, then <b>Balance</b> (not drawn) numbers.
        </p>

        <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
          <button
            onClick={() => setDbKey("db3")}
            style={{
              padding: "10px 14px",
              background: dbKey === "db3" ? "#2563eb" : "#e5e7eb",
              color: dbKey === "db3" ? "white" : "black",
              border: "none",
              borderRadius: 10,
              cursor: "pointer",
              fontWeight: 900,
            }}
          >
            📊 FullLotteryData (DB3)
          </button>

          <button
            onClick={() => setDbKey("db4")}
            style={{
              padding: "10px 14px",
              background: dbKey === "db4" ? "#7c3aed" : "#e5e7eb",
              color: dbKey === "db4" ? "white" : "black",
              border: "none",
              borderRadius: 10,
              cursor: "pointer",
              fontWeight: 900,
            }}
          >
            📈 AbsoluteData (DB4)
          </button>

          <div style={{ display: "flex", gap: 10, marginLeft: "auto", flexWrap: "wrap" }}>
            <button
              onClick={() => setMode("unique")}
              style={{
                padding: "10px 14px",
                background: mode === "unique" ? "#2563eb" : "#e5e7eb",
                color: mode === "unique" ? "white" : "black",
                border: "none",
                borderRadius: 10,
                cursor: "pointer",
                fontWeight: 900,
              }}
            >
              Unique Cycle
            </button>

            <button
              onClick={() => setMode("balance")}
              style={{
                padding: "10px 14px",
                background: mode === "balance" ? "#ef4444" : "#e5e7eb",
                color: mode === "balance" ? "white" : "black",
                border: "none",
                borderRadius: 10,
                cursor: "pointer",
                fontWeight: 900,
              }}
            >
              Balance Cycle
            </button>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div
        style={{
          background: "white",
          border: "1px solid #e2e8f0",
          borderRadius: 14,
          padding: 14,
          marginBottom: 14,
        }}
      >
        {loadingCycle ? (
          <p style={{ margin: 0, color: "#334155", fontWeight: 700 }}>⏳ Loading cycle timeline...</p>
        ) : selectedStep ? (
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <div
              style={{
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 12,
                padding: 12,
                textAlign: "center",
                minWidth: 190,
              }}
            >
              <div style={{ fontSize: 12, color: "#64748b", fontWeight: 800, textTransform: "uppercase" }}>
                Selected Date
              </div>
              <div style={{ fontSize: 18, fontWeight: 1000, color: "#0f172a" }}>
                {selectedStep.dateLabel}
              </div>
            </div>

            <div
              style={{
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 12,
                padding: 12,
                textAlign: "center",
                minWidth: 190,
              }}
            >
              <div style={{ fontSize: 12, color: "#64748b", fontWeight: 800, textTransform: "uppercase" }}>
                Unique Count (so far)
              </div>
              <div style={{ fontSize: 18, fontWeight: 1000, color: "#2563eb" }}>
                {selectedStep.uniqueCount}
              </div>
            </div>

            <div
              style={{
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 12,
                padding: 12,
                textAlign: "center",
                minWidth: 190,
              }}
            >
              <div style={{ fontSize: 12, color: "#64748b", fontWeight: 800, textTransform: "uppercase" }}>
                Balance Count (so far)
              </div>
              <div style={{ fontSize: 18, fontWeight: 1000, color: "#ef4444" }}>
                {selectedStep.balanceCount}
              </div>
            </div>

            <div style={{ marginLeft: "auto", color: "#475569", fontWeight: 800, fontSize: 13 }}>
              {mode === "unique" ? "Grid shows numbers already drawn (cumulative)." : "Grid shows numbers NOT drawn yet."}
            </div>
          </div>
        ) : (
          <p style={{ margin: 0, color: "red", fontWeight: 800 }}>No dates found for prize ₹5000.</p>
        )}

        {loadingNumbers && (
          <p style={{ marginTop: 10, color: "#334155", fontWeight: 800 }}>
            ⏳ Loading cumulative numbers into grid...
          </p>
        )}

        {error && (
          <p style={{ marginTop: 10, color: "red", fontWeight: 900 }}>❌ {error}</p>
        )}
      </div>

      {/* Dates always */}
      <div
        style={{
          background: "white",
          border: "1px solid #e2e8f0",
          borderRadius: 14,
          padding: 14,
          marginBottom: 14,
        }}
      >
        <h3 style={{ margin: "0 0 10px", fontSize: 16 }}>📅 Dates (day 1 → last)</h3>

        <div style={{ maxHeight: 140, overflowY: "auto", paddingRight: 6 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {steps.map((s) => {
              const active = s.dateKey === selectedDateKey;
              return (
                <button
                  key={s.dateKey}
                  onClick={() => setSelectedDateKey(s.dateKey)}
                  style={{
                    borderRadius: 12,
                    padding: 10,
                    minWidth: 190,
                    border: active ? "2px solid #2563eb" : "1px solid #e2e8f0",
                    cursor: "pointer",
                    background: active ? "#dbeafe" : "#f8fafc",
                    textAlign: "left",
                  }}
                >
                  <div style={{ fontWeight: 1000, color: "#0f172a" }}>{s.dateLabel}</div>
                  <div style={{ fontSize: 12, color: "#2563eb", fontWeight: 900 }}>
                    Unique: {s.uniqueCount}
                  </div>
                  <div style={{ fontSize: 12, color: "#ef4444", fontWeight: 900 }}>
                    Balance: {s.balanceCount}
                  </div>
                  <div style={{ fontSize: 11, color: "#64748b", fontWeight: 800 }}>
                    +Added today: {s.addedCount}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Grid */}
      <div
        style={{
          background: "white",
          border: "1px solid #e2e8f0",
          borderRadius: 14,
          padding: 10,
        }}
      >
        <div style={{ fontWeight: 1000, marginBottom: 10, color: "#0f172a" }}>
          {mode === "unique" ? "✅ Unique drawn numbers (cumulative)" : "🧯 Balance numbers (not drawn yet)"}{" "}
          for Prize ₹5000
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(100, 1fr)",
            gap: 0,
            userSelect: "none",
          }}
        >
          {allNumbers.map(renderCell)}
        </div>
      </div>
    </div>
  );
}