import React, { useState } from "react";

// ===============================
// ROLLER SEQUENCES (PASTE YOUR 72 HERE)
// ===============================
const rollerSequences = [
  { id: 1, pos: 1, seq: [7, 6, 8, 5, 9, 0, 3, 1, 2, 4] },
  { id: 1, pos: 2, seq: [7, 9, 2, 5, 1, 6, 3, 8, 0, 4] },
  { id: 1, pos: 3, seq: [7, 8, 9, 0, 1, 2, 3, 4, 5, 6] },
  { id: 1, pos: 4, seq: [7, 4, 1, 8, 6, 3, 5, 0, 2, 9] },
  { id: 2, pos: 1, seq: [7, 2, 4, 6, 9, 0, 1, 3, 5, 8] },
  { id: 2, pos: 2, seq: [7, 3, 8, 2, 0, 1, 9, 5, 6, 4] },
  { id: 2, pos: 3, seq: [7, 4, 1, 8, 6, 3, 5, 0, 2, 9] },
  { id: 2, pos: 4, seq: [7, 8, 9, 0, 1, 2, 3, 4, 5, 6] },
  { id: 3, pos: 1, seq: [7, 5, 3, 1, 0, 8, 6, 4, 2, 9] },
  { id: 3, pos: 2, seq: [7, 2, 4, 6, 9, 0, 1, 3, 5, 8] },
  { id: 3, pos: 3, seq: [7, 3, 8, 2, 0, 1, 9, 5, 6, 4] },
  { id: 3, pos: 4, seq: [7, 4, 1, 8, 6, 3, 5, 0, 2, 9] },
  { id: 4, pos: 1, seq: [7, 2, 4, 6, 9, 0, 1, 3, 5, 8] },
  { id: 4, pos: 2, seq: [7, 3, 8, 2, 0, 1, 9, 5, 6, 4] },
  { id: 4, pos: 3, seq: [7, 4, 1, 8, 6, 3, 5, 0, 2, 9] },
  { id: 4, pos: 4, seq: [7, 9, 2, 5, 1, 6, 3, 8, 0, 4] },
  { id: 5, pos: 1, seq: [7, 2, 4, 6, 9, 0, 1, 3, 5, 8] },
  { id: 5, pos: 2, seq: [7, 3, 8, 2, 0, 1, 9, 5, 6, 4] },
  { id: 5, pos: 3, seq: [7, 6, 8, 5, 9, 0, 3, 1, 2, 4] },
  { id: 5, pos: 4, seq: [7, 8, 9, 0, 1, 2, 3, 4, 5, 6] },
  { id: 6, pos: 1, seq: [7, 2, 4, 6, 9, 0, 1, 3, 5, 8] },
  { id: 6, pos: 2, seq: [7, 3, 8, 2, 0, 1, 9, 5, 6, 4] },
  { id: 6, pos: 3, seq: [7, 9, 2, 5, 1, 6, 3, 8, 0, 4] },
  { id: 6, pos: 4, seq: [7, 4, 1, 8, 6, 3, 5, 0, 2, 9] },
  { id: 7, pos: 1, seq: [7, 3, 8, 2, 0, 1, 9, 6, 5, 4] },
  { id: 7, pos: 2, seq: [7, 8, 9, 0, 1, 2, 3, 4, 5, 6] },
  { id: 7, pos: 3, seq: [7, 5, 3, 1, 0, 8, 6, 4, 2, 9] },
  { id: 7, pos: 4, seq: [7, 5, 3, 1, 0, 8, 6, 4, 2, 9] },
  { id: 8, pos: 1, seq: [7, 5, 1, 9, 6, 4, 2, 8, 3, 0] },
  { id: 8, pos: 2, seq: [7, 5, 9, 1, 3, 6, 8, 4, 0, 2] },
  { id: 8, pos: 3, seq: [7, 9, 2, 5, 1, 6, 3, 8, 0, 4] },
  { id: 8, pos: 4, seq: [7, 6, 8, 5, 9, 0, 3, 1, 2, 4] },
  { id: 9, pos: 1, seq: [7, 9, 2, 5, 1, 6, 3, 8, 0, 4] },
  { id: 9, pos: 2, seq: [7, 5, 1, 9, 6, 4, 2, 8, 3, 0] },
  { id: 9, pos: 3, seq: [7, 5, 9, 1, 3, 6, 8, 4, 0, 2] },
  { id: 9, pos: 4, seq: [7, 8, 9, 0, 1, 2, 3, 4, 5, 6] },
  { id: 10, pos: 1, seq: [7, 5, 1, 9, 6, 4, 2, 8, 3, 0] },
  { id: 10, pos: 2, seq: [7, 6, 5, 4, 3, 2, 1, 0, 9, 8] },
  { id: 10, pos: 3, seq: [7, 8, 9, 0, 1, 2, 3, 4, 5, 6] },
  { id: 10, pos: 4, seq: [7, 6, 8, 5, 9, 0, 3, 1, 2, 4] },
  { id: 11, pos: 1, seq: [7, 5, 1, 9, 6, 4, 2, 8, 3, 0] },
  { id: 11, pos: 2, seq: [7, 5, 9, 1, 3, 6, 8, 4, 0, 2] },
  { id: 11, pos: 3, seq: [7, 9, 2, 5, 1, 6, 3, 8, 0, 4] },
  { id: 11, pos: 4, seq: [7, 4, 1, 8, 6, 3, 5, 0, 2, 9] },
  { id: 12, pos: 1, seq: [7, 5, 1, 9, 6, 4, 2, 8, 3, 0] },
  { id: 12, pos: 2, seq: [7, 5, 9, 1, 3, 6, 8, 4, 0, 2] },
  { id: 12, pos: 3, seq: [7, 6, 5, 4, 3, 2, 1, 0, 9, 8] },
  { id: 12, pos: 4, seq: [7, 8, 9, 0, 1, 2, 3, 4, 5, 6] },
  { id: 13, pos: 1, seq: [7, 5, 9, 1, 3, 6, 8, 4, 0, 2] },
  { id: 13, pos: 2, seq: [7, 6, 5, 4, 3, 2, 1, 0, 9, 8] },
  { id: 13, pos: 3, seq: [7, 5, 1, 9, 6, 4, 2, 8, 3, 0] },
  { id: 13, pos: 4, seq: [7, 5, 3, 1, 0, 8, 6, 4, 2, 9] },
  { id: 14, pos: 1, seq: [7, 6, 5, 4, 3, 2, 1, 0, 9, 8] },
  { id: 14, pos: 2, seq: [7, 5, 3, 1, 0, 8, 6, 4, 2, 9] },
  { id: 14, pos: 3, seq: [7, 5, 1, 9, 6, 4, 2, 8, 3, 0] },
  { id: 14, pos: 4, seq: [7, 4, 1, 8, 6, 3, 5, 0, 2, 9] },
  { id: 15, pos: 1, seq: [7, 6, 8, 5, 9, 0, 3, 1, 2, 4] },
  { id: 15, pos: 2, seq: [7, 6, 5, 4, 3, 2, 1, 0, 9, 8] },
  { id: 15, pos: 3, seq: [7, 4, 1, 3, 6, 0, 8, 9, 5, 2] },
  { id: 15, pos: 4, seq: [7, 5, 9, 1, 3, 6, 8, 4, 0, 2] },
  { id: 16, pos: 1, seq: [7, 5, 9, 1, 3, 6, 8, 4, 0, 2] },
  { id: 16, pos: 2, seq: [7, 5, 3, 1, 0, 8, 6, 4, 2, 9] },
  { id: 16, pos: 3, seq: [7, 2, 4, 6, 9, 0, 1, 3, 5, 8] },
  { id: 16, pos: 4, seq: [7, 3, 8, 2, 0, 1, 9, 5, 6, 4] },
  { id: 17, pos: 1, seq: [7, 8, 9, 0, 1, 2, 3, 4, 5, 6] },
  { id: 17, pos: 2, seq: [7, 6, 8, 5, 9, 0, 3, 1, 2, 4] },
  { id: 17, pos: 3, seq: [7, 6, 5, 4, 3, 2, 1, 0, 9, 8] },
  { id: 17, pos: 4, seq: [7, 5, 3, 1, 0, 8, 6, 4, 2, 9] },
  { id: 18, pos: 1, seq: [7, 6, 8, 5, 9, 0, 3, 1, 2, 4] },
  { id: 18, pos: 2, seq: [7, 5, 3, 1, 0, 8, 6, 4, 2, 9] },
  { id: 18, pos: 3, seq: [7, 2, 4, 6, 9, 0, 1, 3, 5, 8] },
  { id: 18, pos: 4, seq: [7, 3, 8, 2, 0, 1, 9, 5, 6, 4] },
];

// ===============================
// ROLLER SEQUENCES
// ===============================

export default function DigitalMachine() {
  const [results, setResults] = useState([]);

  // ✅ Build mechanical properties only once
  const rollersBySet = useMemo(() => {
    const map = {};

    rollerSequences.forEach((r) => {
      if (!map[r.id]) map[r.id] = [];

      map[r.id].push({
        ...r,
        baseSpeed: 15 + Math.random() * 10,
        speedVariance: 3 + Math.random() * 4,
        brake: 4 + Math.random() * 3,
      });
    });

    // Ensure rollers sorted by position
    Object.keys(map).forEach((id) => {
      map[id].sort((a, b) => a.pos - b.pos);
    });

    return map;
  }, []);

  // ===============================
  // PHYSICS SPIN ENGINE
  // ===============================
  function spinRoller(roller, spinTime = 2.5) {
    const startIndex = Math.floor(Math.random() * 10);

    const speed =
      roller.baseSpeed + (Math.random() - 0.5) * roller.speedVariance;

    let steps = speed * spinTime - 0.5 * roller.brake * spinTime * spinTime;

    if (steps < 0) steps = Math.abs(steps); // prevent reverse motion

    let finalIndex = Math.floor(startIndex + steps) % 10;
    if (finalIndex < 0) finalIndex += 10;

    return roller.seq[finalIndex];
  }

  // ===============================
  // GENERATE ONE 4-DIGIT NUMBER
  // ===============================
  function generateNumber() {
    const chosenSet = Math.floor(Math.random() * 18) + 1;
    const setRollers = rollersBySet[chosenSet];

    if (!setRollers) return "0000"; // safety fallback

    const digits = setRollers.map((r) => spinRoller(r));
    return digits.join("");
  }

  // ===============================
  // GENERATE FULL DRAW (18 NUMBERS)
  // ===============================
  function generateDraw() {
    return Array.from({ length: 18 }, generateNumber);
  }

  return (
    <div style={{ padding: 20, fontFamily: "sans-serif" }}>
      <h2>🎰 Digital Roller Lottery Machine</h2>

      <button
        onClick={() => setResults(generateDraw())}
        style={{
          padding: "10px 20px",
          fontSize: 16,
          cursor: "pointer",
          marginBottom: 20,
        }}
      >
        SPIN MACHINE
      </button>

      {results.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(80px, 1fr))",
            gap: 10,
            maxWidth: 500,
          }}
        >
          {results.map((num, i) => (
            <div
              key={i}
              style={{
                padding: 10,
                border: "2px solid #333",
                textAlign: "center",
                fontSize: 22,
                fontWeight: "bold",
                background: "#f2f2f2",
                borderRadius: 6,
              }}
            >
              {num}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
