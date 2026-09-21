import React, { useEffect, useMemo, useState } from "react";

const ENDPOINTS = {
  old: {
    base: "http://localhost:5000/api/prizecycles/lotterydata",
    details: "http://localhost:5000/api/prizecycles/lotterydata/cycle-details",
  },
  new: {
    base: "http://localhost:5000/api/prizecycles/lotterydatanew",
    details:
      "http://localhost:5000/api/prizecycles/lotterydatanew/cycle-details",
  },
};

const colors = {
  bg: "#0b1220",
  panel: "#0f1a2b",
  panel2: "#101f35",
  text: "#e6edf6",
  mut: "#9fb0c3",
  line: "rgba(255,255,255,0.10)",
  blue: "#3b82f6",
  green: "#22c55e",
  yellow: "#f59e0b",
  red: "#ef4444",
  purple: "#a855f7",
};

const PRIZE_COLORS = {
  5000: "#ec4899",
  2000: "#a855f7",
  1000: "#6366f1",
  500: "#3b82f6",
  200: "#06b6d4",
  100: "#10b981",
};

const page = {
  padding: 22,
  fontFamily: "Inter, system-ui, Arial, sans-serif",
  color: colors.text,
  background: `linear-gradient(180deg, ${colors.bg}, #050913)`,
  minHeight: "100vh",
};

const card = (extra = {}) => ({
  background: `linear-gradient(180deg, ${colors.panel}, ${colors.panel2})`,
  border: `1px solid ${colors.line}`,
  borderRadius: 16,
  padding: 16,
  boxShadow: "0 10px 30px rgba(0,0,0,0.30)",
  ...extra,
});

const btn = (active = false) => ({
  padding: "10px 14px",
  borderRadius: 12,
  border: `1px solid ${active ? "rgba(59,130,246,0.8)" : colors.line}`,
  background: active ? "rgba(59,130,246,0.18)" : "rgba(255,255,255,0.03)",
  color: colors.text,
  cursor: "pointer",
  fontWeight: 900,
});

function Bar({ value, max, color, height = 10 }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div
      style={{
        height,
        borderRadius: 999,
        background: "rgba(255,255,255,0.06)",
        border: `1px solid ${colors.line}`,
        overflow: "hidden",
      }}
    >
      <div style={{ width: `${pct}%`, height: "100%", background: color }} />
    </div>
  );
}

function fmt(x) {
  if (x === null || x === undefined) return "—";
  if (typeof x === "number") return x.toLocaleString();
  return String(x);
}

function Modal({ open, onClose, title, children }) {
  if (!open) return null;
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        zIndex: 9999,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(1100px, 100%)",
          maxHeight: "90vh",
          overflow: "auto",
          ...card({ borderRadius: 18 }),
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            alignItems: "center",
          }}
        >
          <div style={{ fontSize: 18, fontWeight: 950 }}>{title}</div>
          <button style={btn(false)} onClick={onClose}>
            Close
          </button>
        </div>
        <div style={{ marginTop: 12 }}>{children}</div>
      </div>
    </div>
  );
}

function PillTabs({ value, onChange, tabs }) {
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      {tabs.map((t) => (
        <button
          key={t.value}
          style={btn(value === t.value)}
          onClick={() => onChange(t.value)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export default function PrizeCyclesPage() {
  const [source, setSource] = useState("new");
  const [data, setData] = useState(null);
  const [expandedPrize, setExpandedPrize] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // details modal state
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailPrize, setDetailPrize] = useState(null);
  const [detailCycle, setDetailCycle] = useState(null);
  const [detailMode, setDetailMode] = useState("stats"); // stats | remaining | timeline
  const [detailSearch, setDetailSearch] = useState("");
  const [detailPage, setDetailPage] = useState(0);
  const [detailPageSize, setDetailPageSize] = useState(200);
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailErr, setDetailErr] = useState(null);

  function load(which) {
    setSource(which);
    setLoading(true);
    setError(null);
    setData(null);
    setExpandedPrize(null);

    fetch(ENDPOINTS[which].base)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }

  async function loadDetails({ prize, cycle, mode, search, page, pageSize }) {
    setDetailLoading(true);
    setDetailErr(null);
    setDetailData(null);

    const url = new URL(ENDPOINTS[source].details);
    url.searchParams.set("prize", String(prize));
    url.searchParams.set("cycle", String(cycle));
    url.searchParams.set("mode", mode);
    url.searchParams.set("page", String(page));
    url.searchParams.set("pageSize", String(pageSize));
    if (search) url.searchParams.set("search", search);

    try {
      const r = await fetch(url.toString());
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const json = await r.json();
      setDetailData(json);
      setDetailLoading(false);
    } catch (e) {
      setDetailErr(e.message);
      setDetailLoading(false);
    }
  }

  function openDetails(prize, cycle) {
    setDetailPrize(prize);
    setDetailCycle(cycle);
    setDetailMode("stats");
    setDetailSearch("");
    setDetailPage(0);
    setDetailPageSize(200);
    setDetailOpen(true);

    loadDetails({
      prize,
      cycle,
      mode: "stats",
      search: "",
      page: 0,
      pageSize: 200,
    });
  }

  useEffect(() => {
    load("new");
  }, []);

  const prizesSorted = useMemo(() => {
    const arr = data?.prizes || [];
    return [...arr].sort((a, b) => b.prize - a.prize);
  }, [data]);

  const detailTitle = useMemo(() => {
    if (!detailPrize || !detailCycle) return "Cycle details";
    return `₹${detailPrize} · Cycle #${detailCycle}`;
  }, [detailPrize, detailCycle]);

  if (loading) return <div style={page}>Loading…</div>;
  if (error) return <div style={page}>Error: {error}</div>;
  if (!data) return null;
  if (data.ok === false) return <div style={page}>API error: {data.error}</div>;

  return (
    <div style={page}>
      <div style={{ maxWidth: 1250, margin: "0 auto" }}>
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <div>
            <div style={{ fontSize: 24, fontWeight: 950 }}>Prize Cycles</div>
            <div
              style={{
                color: colors.mut,
                marginTop: 6,
                fontSize: 13,
                lineHeight: 1.5,
              }}
            >
              Dataset:{" "}
              <span style={{ color: colors.text, fontWeight: 950 }}>
                {data.summary?.firstDate || "—"} →{" "}
                {data.summary?.lastDate || "—"}
              </span>{" "}
              · Days:{" "}
              <span style={{ color: colors.text, fontWeight: 950 }}>
                {fmt(data.summary?.totalDays)}
              </span>
              {data.meta?.invalidDateCount ? (
                <>
                  <br />
                  Invalid dates skipped:{" "}
                  <span style={{ color: colors.yellow, fontWeight: 950 }}>
                    {data.meta.invalidDateCount}
                  </span>
                </>
              ) : null}
            </div>
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button style={btn(source === "old")} onClick={() => load("old")}>
              Old DB
            </button>
            <button style={btn(source === "new")} onClick={() => load("new")}>
              New DB
            </button>
          </div>
        </div>

        {/* Prize cards */}
        <div
          style={{
            marginTop: 16,
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          }}
        >
          {prizesSorted.map((p) => {
            const isOpen = expandedPrize === p.prize;
            const cur = p.currentCycle;

            return (
              <div key={p.prize} style={card()}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 10,
                    alignItems: "center",
                    flexWrap: "wrap",
                  }}
                >
                  <div
                    style={{ display: "flex", gap: 10, alignItems: "center" }}
                  >
                    <div
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: 999,
                        background: PRIZE_COLORS[p.prize] || colors.purple,
                      }}
                    />
                    <div style={{ fontSize: 18, fontWeight: 950 }}>
                      ₹{p.prize}
                    </div>
                  </div>

                  <button
                    style={btn(isOpen)}
                    onClick={() => setExpandedPrize(isOpen ? null : p.prize)}
                  >
                    {isOpen ? "Hide cycles" : "View cycles"}
                  </button>
                </div>

                <div
                  style={{
                    marginTop: 10,
                    display: "flex",
                    gap: 12,
                    flexWrap: "wrap",
                    color: colors.mut,
                    fontSize: 13,
                  }}
                >
                  <div>
                    Completed:{" "}
                    <span style={{ color: colors.text, fontWeight: 950 }}>
                      {p.completedCycles}
                    </span>
                  </div>
                  <div>
                    Total:{" "}
                    <span style={{ color: colors.text, fontWeight: 950 }}>
                      {p.totalCycles}
                    </span>
                  </div>
                </div>

                {cur ? (
                  <div style={{ marginTop: 12 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        color: colors.mut,
                        fontSize: 12,
                        gap: 10,
                        flexWrap: "wrap",
                      }}
                    >
                      <span>
                        Current #{cur.cycleNumber} · Start {cur.startDate} ·
                        Last seen {cur.lastSeenDate || "—"}
                      </span>
                      <span style={{ color: colors.text, fontWeight: 950 }}>
                        {cur.totalUniqueNumbers.toLocaleString()}/10,000 (
                        {cur.percentComplete}%)
                      </span>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <Bar
                        value={cur.totalUniqueNumbers}
                        max={10000}
                        color={PRIZE_COLORS[p.prize] || colors.blue}
                      />
                    </div>
                  </div>
                ) : (
                  <div
                    style={{ marginTop: 12, color: colors.mut, fontSize: 13 }}
                  >
                    No numbers found for this prize yet.
                  </div>
                )}

                {isOpen && (
                  <div style={{ marginTop: 14 }}>
                    <div
                      style={{
                        color: colors.mut,
                        fontSize: 12,
                        fontWeight: 900,
                        marginBottom: 8,
                      }}
                    >
                      Cycles (most recent first) — click “Details”
                    </div>

                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 8,
                        maxHeight: 320,
                        overflowY: "auto",
                      }}
                    >
                      {[...p.cycles]
                        .slice()
                        .reverse()
                        .map((c) => (
                          <div
                            key={c.cycleNumber}
                            style={{
                              padding: 12,
                              borderRadius: 12,
                              border: `1px solid ${colors.line}`,
                              background: "rgba(255,255,255,0.03)",
                            }}
                          >
                            <div
                              style={{
                                display: "flex",
                                justifyContent: "space-between",
                                gap: 10,
                                flexWrap: "wrap",
                                alignItems: "center",
                              }}
                            >
                              <div style={{ fontWeight: 950 }}>
                                {c.isComplete ? "✅" : "🔄"} Cycle #
                                {c.cycleNumber}
                              </div>

                              <button
                                style={btn(false)}
                                onClick={() =>
                                  openDetails(p.prize, c.cycleNumber)
                                }
                              >
                                Details
                              </button>
                            </div>

                            <div
                              style={{
                                marginTop: 6,
                                color: colors.mut,
                                fontSize: 12,
                              }}
                            >
                              {c.startDate} → {c.endDate || "ongoing"} ·{" "}
                              {c.totalDays} days
                            </div>

                            <div
                              style={{
                                marginTop: 6,
                                color: colors.mut,
                                fontSize: 12,
                              }}
                            >
                              Unique:{" "}
                              <span
                                style={{ color: colors.text, fontWeight: 950 }}
                              >
                                {c.totalUniqueNumbers.toLocaleString()}
                              </span>
                              {" · "}
                              Remaining:{" "}
                              <span
                                style={{ color: colors.text, fontWeight: 950 }}
                              >
                                {c.remainingNumbers.toLocaleString()}
                              </span>
                              {" · "}
                              {c.percentComplete}%
                            </div>

                            <div style={{ marginTop: 8 }}>
                              <Bar
                                value={c.totalUniqueNumbers}
                                max={10000}
                                color={PRIZE_COLORS[p.prize] || colors.blue}
                              />
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Details modal */}
        <Modal
          open={detailOpen}
          onClose={() => {
            setDetailOpen(false);
            setDetailData(null);
            setDetailErr(null);
          }}
          title={detailTitle}
        >
          <PillTabs
            value={detailMode}
            onChange={(mode) => {
              setDetailMode(mode);
              setDetailPage(0);

              loadDetails({
                prize: detailPrize,
                cycle: detailCycle,
                mode,
                search: mode === "remaining" ? detailSearch : "",
                page: 0,
                pageSize: detailPageSize,
              });
            }}
            tabs={[
              { value: "stats", label: "Stats" },
              { value: "remaining", label: "Remaining" },
              { value: "timeline", label: "Timeline" },
            ]}
          />

          {detailLoading && (
            <div style={{ marginTop: 12, color: colors.mut }}>Loading…</div>
          )}
          {detailErr && (
            <div style={{ marginTop: 12, color: colors.red }}>
              Error: {detailErr}
            </div>
          )}
          {detailData?.ok === false && (
            <div style={{ marginTop: 12, color: colors.red }}>
              API error: {detailData.error}
            </div>
          )}

          {detailData?.ok && detailMode === "stats" && (
            <div
              style={{
                marginTop: 14,
                display: "grid",
                gap: 12,
                gridTemplateColumns: "repeat(3, minmax(0,1fr))",
              }}
            >
              {(() => {
                const c = detailData.cycleInfo;
                return (
                  <>
                    <div style={card({ padding: 14 })}>
                      <div
                        style={{
                          color: colors.mut,
                          fontSize: 12,
                          fontWeight: 900,
                        }}
                      >
                        Range
                      </div>
                      <div style={{ marginTop: 6, fontWeight: 950 }}>
                        {c.startDate} → {c.endDate || "ongoing"}
                      </div>
                      <div
                        style={{
                          marginTop: 6,
                          color: colors.mut,
                          fontSize: 12,
                        }}
                      >
                        {c.totalDays} days · Last seen {c.lastSeenDate || "—"}
                      </div>
                    </div>

                    <div style={card({ padding: 14 })}>
                      <div
                        style={{
                          color: colors.mut,
                          fontSize: 12,
                          fontWeight: 900,
                        }}
                      >
                        Unique / Remaining
                      </div>
                      <div style={{ marginTop: 6, fontWeight: 950 }}>
                        {c.totalUniqueNumbers.toLocaleString()} / 10,000
                      </div>
                      <div
                        style={{
                          marginTop: 6,
                          color: colors.mut,
                          fontSize: 12,
                        }}
                      >
                        Remaining: {c.remainingNumbers.toLocaleString()}
                      </div>
                    </div>

                    <div style={card({ padding: 14 })}>
                      <div
                        style={{
                          color: colors.mut,
                          fontSize: 12,
                          fontWeight: 900,
                        }}
                      >
                        Progress
                      </div>
                      <div style={{ marginTop: 6, fontWeight: 950 }}>
                        {c.percentComplete}%
                      </div>
                      <div style={{ marginTop: 8 }}>
                        <Bar
                          value={c.totalUniqueNumbers}
                          max={10000}
                          color={PRIZE_COLORS[c.prize] || colors.blue}
                        />
                      </div>
                    </div>
                  </>
                );
              })()}
            </div>
          )}

          {detailData?.ok && detailMode === "remaining" && (
            <div style={{ marginTop: 14 }}>
              <div
                style={{
                  display: "flex",
                  gap: 10,
                  flexWrap: "wrap",
                  alignItems: "center",
                }}
              >
                <input
                  value={detailSearch}
                  onChange={(e) => setDetailSearch(e.target.value)}
                  placeholder="Search remaining (e.g. 12, 007, 9999)"
                  style={{
                    padding: "10px 12px",
                    borderRadius: 12,
                    border: `1px solid ${colors.line}`,
                    background: "rgba(255,255,255,0.03)",
                    color: colors.text,
                    fontWeight: 900,
                    outline: "none",
                    width: 280,
                  }}
                />
                <select
                  value={detailPageSize}
                  onChange={(e) => {
                    const ps = parseInt(e.target.value, 10);
                    setDetailPageSize(ps);
                    setDetailPage(0);
                    loadDetails({
                      prize: detailPrize,
                      cycle: detailCycle,
                      mode: "remaining",
                      search: detailSearch,
                      page: 0,
                      pageSize: ps,
                    });
                  }}
                  style={{
                    padding: "10px 12px",
                    borderRadius: 12,
                    border: `1px solid ${colors.line}`,
                    background: "rgba(255,255,255,0.03)",
                    color: colors.text,
                    fontWeight: 900,
                    outline: "none",
                  }}
                >
                  {[100, 200, 500, 1000].map((n) => (
                    <option key={n} value={n} style={{ background: "#0b1220" }}>
                      {n}/page
                    </option>
                  ))}
                </select>

                <button
                  style={btn(false)}
                  onClick={() => {
                    setDetailPage(0);
                    loadDetails({
                      prize: detailPrize,
                      cycle: detailCycle,
                      mode: "remaining",
                      search: detailSearch,
                      page: 0,
                      pageSize: detailPageSize,
                    });
                  }}
                >
                  Apply
                </button>
              </div>

              {detailData.remaining && (
                <>
                  <div
                    style={{ marginTop: 10, color: colors.mut, fontSize: 12 }}
                  >
                    Total remaining (filtered):{" "}
                    <span style={{ color: colors.text, fontWeight: 950 }}>
                      {detailData.remaining.total.toLocaleString()}
                    </span>
                    {" · "}
                    Page {detailData.remaining.page + 1}
                  </div>

                  <div
                    style={{
                      marginTop: 12,
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 8,
                    }}
                  >
                    {detailData.remaining.items.map((n, i) => (
                      <span
                        key={i}
                        style={{
                          padding: "6px 10px",
                          borderRadius: 10,
                          border: `1px solid ${colors.line}`,
                          background: "rgba(255,255,255,0.03)",
                          fontFamily: "ui-monospace, Menlo, monospace",
                          fontWeight: 950,
                          fontSize: 12,
                        }}
                      >
                        {n}
                      </span>
                    ))}
                  </div>

                  <div
                    style={{
                      marginTop: 14,
                      display: "flex",
                      gap: 10,
                      flexWrap: "wrap",
                    }}
                  >
                    <button
                      style={btn(false)}
                      disabled={detailPage === 0}
                      onClick={() => {
                        const nextPage = Math.max(0, detailPage - 1);
                        setDetailPage(nextPage);
                        loadDetails({
                          prize: detailPrize,
                          cycle: detailCycle,
                          mode: "remaining",
                          search: detailSearch,
                          page: nextPage,
                          pageSize: detailPageSize,
                        });
                      }}
                    >
                      Prev
                    </button>
                    <button
                      style={btn(false)}
                      onClick={() => {
                        const nextPage = detailPage + 1;
                        setDetailPage(nextPage);
                        loadDetails({
                          prize: detailPrize,
                          cycle: detailCycle,
                          mode: "remaining",
                          search: detailSearch,
                          page: nextPage,
                          pageSize: detailPageSize,
                        });
                      }}
                    >
                      Next
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {detailData?.ok && detailMode === "timeline" && (
            <div style={{ marginTop: 14 }}>
              {detailData.timeline && (
                <>
                  <div style={{ color: colors.mut, fontSize: 12 }}>
                    Days in this cycle:{" "}
                    <span style={{ color: colors.text, fontWeight: 950 }}>
                      {detailData.timeline.total}
                    </span>
                  </div>

                  <div style={{ marginTop: 12, overflowX: "auto" }}>
                    <table
                      style={{
                        width: "100%",
                        borderCollapse: "collapse",
                        fontSize: 13,
                      }}
                    >
                      <thead>
                        <tr style={{ color: colors.mut, textAlign: "left" }}>
                          <th
                            style={{
                              padding: "10px 10px",
                              borderBottom: `1px solid ${colors.line}`,
                            }}
                          >
                            Date
                          </th>
                          <th
                            style={{
                              padding: "10px 10px",
                              borderBottom: `1px solid ${colors.line}`,
                            }}
                          >
                            New unique
                          </th>
                          <th
                            style={{
                              padding: "10px 10px",
                              borderBottom: `1px solid ${colors.line}`,
                            }}
                          >
                            Running total
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {detailData.timeline.items.map((d, idx) => (
                          <tr
                            key={idx}
                            style={{
                              background:
                                idx % 2
                                  ? "rgba(255,255,255,0.02)"
                                  : "transparent",
                            }}
                          >
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                                fontFamily: "ui-monospace, Menlo, monospace",
                              }}
                            >
                              {d.date}
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                              }}
                            >
                              +{d.newUnique}
                            </td>
                            <td
                              style={{
                                padding: "10px 10px",
                                borderBottom: `1px solid ${colors.line}`,
                              }}
                            >
                              {d.totalUnique}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div
                    style={{
                      marginTop: 14,
                      display: "flex",
                      gap: 10,
                      flexWrap: "wrap",
                    }}
                  >
                    <button
                      style={btn(false)}
                      disabled={detailPage === 0}
                      onClick={() => {
                        const nextPage = Math.max(0, detailPage - 1);
                        setDetailPage(nextPage);
                        loadDetails({
                          prize: detailPrize,
                          cycle: detailCycle,
                          mode: "timeline",
                          search: "",
                          page: nextPage,
                          pageSize: detailPageSize,
                        });
                      }}
                    >
                      Prev
                    </button>
                    <button
                      style={btn(false)}
                      onClick={() => {
                        const nextPage = detailPage + 1;
                        setDetailPage(nextPage);
                        loadDetails({
                          prize: detailPrize,
                          cycle: detailCycle,
                          mode: "timeline",
                          search: "",
                          page: nextPage,
                          pageSize: detailPageSize,
                        });
                      }}
                    >
                      Next
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </Modal>

        {/* Invalid date examples */}
        {data.meta?.invalidDateCount ? (
          <div style={{ marginTop: 16, ...card() }}>
            <div style={{ fontWeight: 950 }}>
              Invalid date examples (skipped)
            </div>
            <div style={{ marginTop: 8, color: colors.mut, fontSize: 12 }}>
              Fix these in DB (or improve parser) if they’re actually valid:
            </div>
            <div
              style={{
                marginTop: 10,
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              {(data.meta.invalidDateExamples || []).map((d, i) => (
                <span
                  key={i}
                  style={{
                    padding: "6px 10px",
                    borderRadius: 10,
                    border: `1px solid ${colors.line}`,
                    background: "rgba(255,255,255,0.03)",
                    fontFamily: "ui-monospace, Menlo, monospace",
                    fontWeight: 950,
                    fontSize: 12,
                  }}
                >
                  {d}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
