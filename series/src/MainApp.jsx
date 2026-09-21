import { useState, useEffect } from "react";
import "./App.css";
import axios from "axios";

function MainApp() {
  const [input, setInput] = useState("");
  const [counts, setCounts] = useState({});
  const [userId, setUserId] = useState("");
  const [entries, setEntries] = useState([]); // all entries from DB
  const [filteredEntries, setFilteredEntries] = useState([]); // filtered by day/month
  const [date, setDate] = useState("");
  const [filterDay, setFilterDay] = useState("");
  const [filterMonth, setFilterMonth] = useState("");
  const [file, setFile] = useState(null);

  // =========================
  // COUNT PARSER
  // =========================
  useEffect(() => {
    const matches = input.match(/\b\d{4}\b/g);
    const newCounts = {};
    if (matches) {
      matches.forEach((num) => {
        newCounts[num] = (newCounts[num] || 0) + 1;
      });
    }
    setCounts(newCounts);
  }, [input]);

  // =========================
  // COLOR SYSTEM
  // =========================
  const getColor = (count, minCount, maxCount) => {
    if (count === 0) return "#ffcccc";
    const palette = [
      "#ff9999",
      "#ffcc99",
      "#ffff99",
      "#ccff99",
      "#99ff99",
      "#99ffcc",
      "#99ffff",
      "#99ccff",
      "#9999ff",
      "#cc99ff",
      "#ff99ff",
      "#ff99cc",
      "#ff6666",
      "#ffb366",
      "#ffff66",
      "#b3ff66",
      "#66ff66",
      "#66ffb3",
      "#66ffff",
      "#66b3ff",
    ];
    if (count <= palette.length) return palette[count - 1];
    const ratio = (count - minCount) / (maxCount - minCount || 1);
    const red = Math.floor(255 - 120 * ratio);
    const green = Math.floor(160 + (255 - 160) * ratio);
    return `rgb(${red}, ${green}, ${red})`;
  };

  // =========================
  // LOAD ALL USER DATA
  // =========================
  const loadAllData = async () => {
    try {
      const res = await axios.get("http://localhost:5000/mainall");
      const allEntries = res.data.entries || [];
      setEntries(allEntries);
      setFilteredEntries(allEntries); // initial unfiltered
      alert("✅ Loaded all entries from all users.");
    } catch (err) {
      console.error("Failed to load all data", err);
      alert("Failed to load all data");
    }
  };

  // =========================
  // FILTER FUNCTION
  // =========================
  useEffect(() => {
    if (!entries.length) return;

    const filtered = entries.filter((entry) => {
      const entryDate = new Date(entry.date);
      const matchDay =
        !filterDay || entryDate.getDate() === parseInt(filterDay);
      const matchMonth =
        !filterMonth || entryDate.getMonth() + 1 === parseInt(filterMonth);
      return matchDay && matchMonth;
    });

    setFilteredEntries(filtered);

    // recompute number frequency based on filtered data
    const newCounts = {};
    filtered.forEach((entry) => {
      if (entry.series && Array.isArray(entry.series)) {
        entry.series.forEach((series) => {
          if (series.numbers && Array.isArray(series.numbers)) {
            series.numbers.forEach(({ number, count }) => {
              newCounts[number] = (newCounts[number] || 0) + count;
            });
          }
        });
      }
    });

    const max = Math.max(...Object.values(newCounts), 1);
    setCounts({ ...newCounts, _max: max });
  }, [filterDay, filterMonth, entries]);

  // =========================
  // SAVE DATA TO DB
  // =========================
  const handleSubmit = async () => {
    if (!userId || !date || Object.keys(counts).length === 0) {
      alert("User ID, Date, and Numbers are required.");
      return;
    }

    try {
      const response = await axios.post("http://localhost:5000/submit", {
        userId,
        date,
        counts,
      });
      alert(response.data.message);
    } catch (error) {
      console.error("Error submitting data:", error);
      alert("Error saving data");
    }
  };

  // =========================
  // RENDER GRID
  // =========================
  const renderGrid = () => {
    const rows = [];
    const maxCount = counts._max || 1;
    const values = Object.values(counts).filter((v) => typeof v === "number");
    const minCount = values.length ? Math.min(...values) : 0;

    for (let i = 0; i <= 9999; i++) {
      const num = i.toString().padStart(4, "0");
      const count = counts[num] || 0;
      const bgColor = getColor(count, minCount, maxCount);
      rows.push(
        <div key={num} className="cell" style={{ backgroundColor: bgColor }}>
          <div>{num}</div>
          {count > 0 && <div className="count">{count}</div>}
        </div>,
      );
    }
    return rows;
  };

  // =========================
  // FILE UPLOAD FUNCTIONS
  // =========================
  const uploadFile = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await axios.post(
        "http://localhost:5000/api/upload",
        formData,
      );
      const { lotteryNo, drawDate, numbers } = res.data;
      setInput(numbers.join(" ") || "");
      setUserId(lotteryNo || "");
      setDate(drawDate || "");

      const checkRes = await axios.post(
        "http://localhost:5000/api/check-userid",
        { userId: lotteryNo },
      );

      if (checkRes.data.exists) {
        alert(`❌ User ID / Lottery No ${lotteryNo} already exists.`);
        return;
      }

      alert("✅ File uploaded and data extracted!");
    } catch (err) {
      console.error("Upload failed:", err);
      alert("Upload failed. Check console.");
    }
  };

  const autoUpload = async () => {
    try {
      const res = await axios.get("http://localhost:5000/api/auto-upload");
      console.log("📦 Auto Upload Results:", res.data);
    } catch (err) {
      console.error("Auto upload failed:", err);
      alert("Auto upload failed. Check console.");
    }
  };

  const allUpload = async () => {
    try {
      const res = await axios.get(
        "http://localhost:5000/api/all-upload-folder",
      );
      console.log("📦 All Upload Results:", res.data);
    } catch (err) {
      console.error("All upload failed:", err);
      alert("All upload failed. Check console.");
    }
  };

  const oldUpload = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await axios.post(
        "http://localhost:5000/api/old-upload",
        formData,
      );
      console.log("📦 Old Upload Results:", res.data);
    } catch (err) {
      console.error("Old upload failed:", err);
      alert("Old upload failed. Check console.");
    }
  };

  // =========================
  // UI
  // =========================
  return (
    <div className="main-wrapper">
      <div className="action-bar">
        {/* <input
          type="text"
          className="userid-box"
          placeholder="Enter User ID"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
        /> */}
        {/* <input
          type="text"
          className="date-box"
          placeholder="Enter the Date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        /> */}
        <button onClick={loadAllData} className="submit-btn blue">
          Load All User Data
        </button>
        {/* <button onClick={handleSubmit} className="submit-btn">
          Save to Database
        </button> */}

        {/* ✅ Filter options */}
        {/* <select
          value={filterDay}
          onChange={(e) => setFilterDay(e.target.value)}
          className="sort-dropdown"
        >
          <option value="">Filter by Day</option>
          {[...Array(31)].map((_, i) => (
            <option key={i + 1} value={i + 1}>{`Day ${i + 1}`}</option>
          ))}
        </select> */}

        {/* <select
          value={filterMonth}
          onChange={(e) => setFilterMonth(e.target.value)}
          className="sort-dropdown"
        >
          <option value="">Filter by Month</option>
          {[...Array(12)].map((_, i) => (
            <option key={i + 1} value={i + 1}>
              Month {i + 1}
            </option>
          ))}
        </select> */}

        {/* <input type="file" onChange={(e) => setFile(e.target.files[0])} />
        <button className="upload-btn" onClick={uploadFile}>
          Upload
        </button> */}
        <button className="auto-btn" onClick={autoUpload}>
          Auto
        </button>
        {/* <button className="oldUpload-btn" onClick={oldUpload}>
          OldData
        </button> */}
        <button className="all-Upload-btn" onClick={allUpload}>
          AllData
        </button>
      </div>

      {/* <textarea
        className="textbox"
        placeholder="Enter 4-digit numbers..."
        value={input}
        onChange={(e) => setInput(e.target.value)}
      /> */}

      <div className="grid">{renderGrid()}</div>
    </div>
  );
}

export default MainApp;
