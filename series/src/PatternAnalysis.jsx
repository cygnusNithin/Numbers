import React, { useState, useEffect } from "react";
import axios from "axios";
import "./App.css";

export default function PatternAnalysis() {
  const [analyzedData, setAnalyzedData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState(null);
  const [sortBy, setSortBy] = useState("score");
  const [filterTier, setFilterTier] = useState("all");
  const [selectedNumber, setSelectedNumber] = useState(null);

  // Fetch and analyze data from backend
  const fetchPatternData = async () => {
    setLoading(true);
    try {
      const res = await axios.get("http://localhost:5000/api/pattern-analysis");
      setAnalyzedData(res.data.analyzed);
      setStats(res.data.stats);
    } catch (err) {
      console.error("Failed to fetch pattern data:", err);
      alert("Failed to load pattern analysis");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPatternData();
  }, []);

  // Filter and sort data
  const displayData = React.useMemo(() => {
    let filtered = [...analyzedData];

    // Filter by tier
    if (filterTier !== "all") {
      const tier = parseInt(filterTier);
      filtered = filtered.filter((d) => d[`tier_${tier}`] > 0);
    }

    // Sort
    filtered.sort((a, b) => {
      switch (sortBy) {
        case "score":
          return b.score - a.score;
        case "highTier":
          return b.high_tier_total - a.high_tier_total;
        case "recent":
          return b.recent_high_tier - a.recent_high_tier;
        case "overdue":
          return b.overdue_ratio - a.overdue_ratio;
        case "hits":
          return b.total_hits - a.total_hits;
        default:
          return b.score - a.score;
      }
    });

    return filtered;
  }, [analyzedData, filterTier, sortBy]);

  const getStatusBadge = (item) => {
    if (item.overdue_ratio >= 1.5) {
      return <span className="badge overdue">OVERDUE</span>;
    } else if (item.recent_high_tier >= 2) {
      return <span className="badge hot">HOT 🔥</span>;
    }
    return <span className="badge normal">Normal</span>;
  };

  const getScoreColor = (score) => {
    if (score >= 80) return "#10b981"; // green
    if (score >= 60) return "#f59e0b"; // yellow
    if (score >= 40) return "#f97316"; // orange
    return "#6b7280"; // gray
  };

  return (
    <div className="pattern-container">
      {/* Header */}
      <div className="pattern-header">
        <h1>🎯 Lottery Pattern Analysis</h1>
        <p>5000 → 2000 → 1000 → 500 → 200 → 100 Prize Path</p>
        <button onClick={fetchPatternData} disabled={loading}>
          {loading ? "Loading..." : "🔄 Refresh Data"}
        </button>
      </div>

      {/* Statistics Dashboard */}
      {stats && (
        <div className="stats-grid">
          <div className="stat-card indigo">
            <div className="stat-label">Total Numbers</div>
            <div className="stat-value">{stats.total_numbers}</div>
          </div>
          <div className="stat-card yellow">
            <div className="stat-label">Avg Score</div>
            <div className="stat-value">{stats.avg_score}</div>
          </div>
          <div className="stat-card green">
            <div className="stat-label">High Scores (70+)</div>
            <div className="stat-value">{stats.high_score_count}</div>
          </div>
          <div className="stat-card orange">
            <div className="stat-label">Hot Numbers</div>
            <div className="stat-value">{stats.hot_numbers}</div>
          </div>
          <div className="stat-card red">
            <div className="stat-label">Overdue</div>
            <div className="stat-value">{stats.overdue_numbers}</div>
          </div>
          <div className="stat-card purple">
            <div className="stat-label">Elite (10+ HT)</div>
            <div className="stat-value">{stats.elite_performers}</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="filters-bar">
        <div className="filter-group">
          <label>Sort by:</label>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            <option value="score">Pattern Score</option>
            <option value="highTier">High-Tier Wins</option>
            <option value="recent">Recent Momentum</option>
            <option value="overdue">Overdue Ratio</option>
            <option value="hits">Total Hits</option>
          </select>
        </div>

        <div className="filter-group">
          <label>Filter by Prize:</label>
          <select
            value={filterTier}
            onChange={(e) => setFilterTier(e.target.value)}
          >
            <option value="all">All Prize Tiers</option>
            <option value="5000">₹5000 Winners Only</option>
            <option value="2000">₹2000 Winners Only</option>
            <option value="1000">₹1000 Winners Only</option>
            <option value="500">₹500 Winners Only</option>
            <option value="200">₹200 Winners Only</option>
            <option value="100">₹100 Winners Only</option>
          </select>
        </div>

        <div className="results-count">
          Showing <strong>{displayData.length}</strong> numbers
        </div>
      </div>

      {/* Data Table */}
      <div className="pattern-table-container">
        <table className="pattern-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Number</th>
              <th>Score</th>
              <th>Total Hits</th>
              <th>₹5000</th>
              <th>₹2000</th>
              <th>₹1000</th>
              <th>HT Total</th>
              <th>Recent 6mo</th>
              <th>Days Since</th>
              <th>Avg Gap</th>
              <th>Status</th>
              <th>Key Factors</th>
            </tr>
          </thead>
          <tbody>
            {displayData.slice(0, 100).map((item, index) => (
              <tr
                key={item.number}
                onClick={() => setSelectedNumber(item)}
                className={
                  selectedNumber?.number === item.number ? "selected" : ""
                }
              >
                <td className="rank">#{index + 1}</td>
                <td className="number">{item.number}</td>
                <td>
                  <div
                    className="score-badge"
                    style={{ backgroundColor: getScoreColor(item.score) }}
                  >
                    {item.score}
                  </div>
                </td>
                <td>{item.total_hits}</td>
                <td
                  className={item.tier_5000 > 0 ? "tier-highlight yellow" : ""}
                >
                  {item.tier_5000}
                </td>
                <td
                  className={item.tier_2000 > 0 ? "tier-highlight orange" : ""}
                >
                  {item.tier_2000}
                </td>
                <td
                  className={item.tier_1000 > 0 ? "tier-highlight green" : ""}
                >
                  {item.tier_1000}
                </td>
                <td className="tier-highlight purple">
                  {item.high_tier_total}
                </td>
                <td
                  className={
                    item.recent_high_tier >= 2 ? "tier-highlight red" : ""
                  }
                >
                  {item.recent_high_tier}
                </td>
                <td>{item.days_since_last}d</td>
                <td>{item.avg_gap_days.toFixed(1)}d</td>
                <td>{getStatusBadge(item)}</td>
                <td className="factors">
                  {item.factors.slice(0, 2).join(" • ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Detailed View Modal */}
      {selectedNumber && (
        <div className="modal-overlay" onClick={() => setSelectedNumber(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <button
              className="modal-close"
              onClick={() => setSelectedNumber(null)}
            >
              ✕
            </button>

            <div className="modal-header">
              <h2>Number: {selectedNumber.number}</h2>
              <div
                className="score-badge large"
                style={{ backgroundColor: getScoreColor(selectedNumber.score) }}
              >
                Score: {selectedNumber.score}
              </div>
            </div>

            <div className="modal-stats">
              <div className="modal-stat">
                <strong>Total Hits:</strong> {selectedNumber.total_hits}
              </div>
              <div className="modal-stat">
                <strong>Avg Gap:</strong>{" "}
                {selectedNumber.avg_gap_days.toFixed(1)}d
              </div>
              <div className="modal-stat">
                <strong>Days Since Last:</strong>{" "}
                {selectedNumber.days_since_last}d
              </div>
              <div className="modal-stat">
                <strong>Overdue Ratio:</strong>{" "}
                {selectedNumber.overdue_ratio.toFixed(2)}x
              </div>
              <div className="modal-stat">
                <strong>Last Date:</strong> {selectedNumber.last_date}
              </div>
            </div>

            <div className="tier-breakdown">
              <h3>Prize Tier Breakdown</h3>
              <div className="tier-grid">
                <div className="tier-item yellow">
                  ₹5000: <strong>{selectedNumber.tier_5000}</strong>
                </div>
                <div className="tier-item orange">
                  ₹2000: <strong>{selectedNumber.tier_2000}</strong>
                </div>
                <div className="tier-item green">
                  ₹1000: <strong>{selectedNumber.tier_1000}</strong>
                </div>
                <div className="tier-item blue">
                  ₹500: <strong>{selectedNumber.tier_500}</strong>
                </div>
                <div className="tier-item purple">
                  ₹200: <strong>{selectedNumber.tier_200}</strong>
                </div>
                <div className="tier-item gray">
                  ₹100: <strong>{selectedNumber.tier_100}</strong>
                </div>
              </div>
            </div>

            <div className="factors-list">
              <h3>Pattern Indicators</h3>
              {selectedNumber.factors.map((factor, i) => (
                <div key={i} className="factor-item">
                  • {factor}
                </div>
              ))}
            </div>

            <div className="recent-stats">
              <h3>Recent Activity (Last 6 Months)</h3>
              <p>
                Total Appearances:{" "}
                <strong>{selectedNumber.recent_total}</strong>
              </p>
              <p>
                High-Tier Wins:{" "}
                <strong>{selectedNumber.recent_high_tier}</strong>
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
