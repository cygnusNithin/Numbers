import { BrowserRouter as Router, Routes, Route, Link } from "react-router-dom";
import MainApp from "./MainApp";
import GridPage from "./GridPage";
import Roller from "./Roll";
import PatternAnalysis from "./PatternAnalysis";
import PredictionAnalysis from "./PredictionAnalysis";
import "./App.css";
import ValidationDashboard from "./ValidationDashboard";
import CyclesPage from "./CyclesPage";
import CycleComparisonPage from "./CycleComparisonPage";
import DayComparisonPage from "./DayComparisonPage";
import BalanceComparisonPage from "./BalanceComparisonPage";
import BalancePage from "./BalancePage";
import BacktrackPage from "./BacktrackPage";
import AnalysisPage from "./AnalysisPage";
import PrizeCyclesPage from "./PrizeCyclesPage";
import Cycles3DbPage from "./Cycles3DbPage";
import CompareThreeDBsPage from "./CompareThreeDBsPage";
import FullCyclesPage from "./FullCyclesPage";
import AllPrizeCyclesPage from "./AllPrizeCyclesPage";
import GlobalUniqueCyclesPage from "./GlobalUniqueCyclesPage";
import MergedCyclesPage from "./MergedCyclesPage";
import CurrentCycleComparisonPage from "./CurrentCycleComparisonPage";
import CompareNumbersPage from "./CompareNumbersPage";
import ProveRemainingNumbersPage from "./ProveRemainingNumbersPage";
import CyclesComparisonPage from "./CyclesComparisonPage";
import ReverseCyclespage from "./reverseCyclespage";

export default function App() {
  return (
    <Router>
      <div
        className="action-bar"
        style={{
          gap: "20px",
          padding: "15px",
          background: "#667eea",
          flexWrap: "wrap",
        }}
      >
        <Link
          to="/"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "8px 16px",
            background: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
          }}
        >
          🏠 Main App
        </Link>
        <Link
          to="/grid"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "8px 16px",
            background: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
          }}
        >
          🔢 Grid Page
        </Link>
        <Link
          to="/roller"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "8px 16px",
            background: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
          }}
        >
          🎰 Roller Machine
        </Link>
        <Link
          to="/pattern"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "8px 16px",
            background: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
          }}
        >
          🎯 Pattern Analysis
        </Link>
        <Link
          to="/predictions"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Predictions
        </Link>
        <Link
          to="/validate"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 validate
        </Link>
        <Link
          to="/cycles"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Cycles
        </Link>
        <Link
          to="/cycle-comparison"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Cycles Comparison
        </Link>
        <Link
          to="/day-comparison"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Days Comparison
        </Link>
        <Link
          to="/balance-comparison"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Balance Comparison
        </Link>
        <Link
          to="/balance"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Balance
        </Link>
        <Link
          to="/backtrack"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Backtrack
        </Link>
        <Link
          to="/analysis"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Analysis
        </Link>
        <Link
          to="/prize-cycles"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Prize Cycles
        </Link>
        <Link
          to="/cycles-3db"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Full DB
        </Link>
        <Link
          to="/compare-3-dbs"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Compare DB
        </Link>
        <Link
          to="/full-cycles"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 FullCycles
        </Link>
        <Link
          to="/all-prize-cycles"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Prize Cycles
        </Link>
        <Link
          to="/global-unique-cycles"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Global Analysis 
        </Link>
        <Link
          to="/merged-cycles"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Merged Cycles 
        </Link>
        <Link
          to="/current-cycle-comparison"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Cycle Comparison 
        </Link>
        <Link
          to="/compare-remaining-auto"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Compare Numbers 
        </Link>
        <Link
          to="/prove-numbers"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Prove Numbers 
        </Link>
        <Link
          to="/cycles-comparison"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Cycles Comparison 
        </Link>
        <Link
          to="/allreverse-cycles"
          style={{
            color: "white",
            textDecoration: "none",
            fontWeight: "600",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(255,255,255,0.2)",
            borderRadius: "8px",
            transition: "all 0.3s",
            display: "inline-block",
          }}
          onMouseOver={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.3)")
          }
          onMouseOut={(e) =>
            (e.target.style.backgroundColor = "rgba(255,255,255,0.2)")
          }
        >
          🎯 Forward-Reverse Cycles 
        </Link>
      </div>

      <Routes>
        <Route path="/" element={<MainApp />} />
        <Route path="/grid" element={<GridPage />} />
        <Route path="/roller" element={<Roller />} />
        <Route path="/pattern" element={<PatternAnalysis />} />
        <Route path="/predictions" element={<PredictionAnalysis />} />
        <Route path="/validate" element={<ValidationDashboard />} />
        <Route path="/cycles" element={<CyclesPage />} />
        <Route path="/cycle-comparison" element={<CycleComparisonPage />} />
        <Route path="/day-comparison" element={<DayComparisonPage />} />
        <Route path="/balance-comparison" element={<BalanceComparisonPage />} />
        <Route path="/balance" element={<BalancePage />} />
        <Route path="/backtrack" element={<BacktrackPage />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/prize-cycles" element={<PrizeCyclesPage />} />
        <Route path="/cycles-3db" element={<Cycles3DbPage />} />
        <Route path="/compare-3-dbs" element={<CompareThreeDBsPage />} />
        <Route path="/full-cycles" element={<FullCyclesPage />} />
        <Route path="/all-prize-cycles" element={<AllPrizeCyclesPage />} />
        <Route path="/global-unique-cycles" element={<GlobalUniqueCyclesPage />} />
        <Route path="/merged-cycles" element={<MergedCyclesPage />} />
        <Route path="/current-cycle-comparison" element={<CurrentCycleComparisonPage />} />
        <Route path="/compare-remaining-auto" element={<CompareNumbersPage />} />
        <Route path="/prove-numbers" element={<ProveRemainingNumbersPage />} />
        <Route path="/cycles-comparison" element={<CyclesComparisonPage />} />
        <Route path="/allreverse-cycles" element={<ReverseCyclespage />} />
      </Routes>
    </Router>
  );
}
