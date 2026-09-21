import React from "react";
import { AlertCircle, CheckCircle2, HelpCircle } from "lucide-react";

const StatusBadge = ({ type }) => {
  if (!type)
    return (
      <span className="text-emerald-500 flex items-center gap-1 font-bold text-xs">
        <CheckCircle2 size={14} /> MATCH
      </span>
    );
  return (
    <span className="text-rose-500 bg-rose-50 px-2 py-0.5 rounded border border-rose-100 flex items-center gap-1 font-bold text-[10px]">
      <AlertCircle size={12} /> {type.replace("_", " ")}
    </span>
  );
};

export default function IntegrityDashboard({ report }) {
  return (
    <div className="p-6 bg-slate-50 min-h-screen font-sans">
      <div className="max-w-5xl mx-auto bg-white rounded-3xl shadow-2xl overflow-hidden border border-slate-200">
        <div className="bg-slate-900 p-6 text-white">
          <h1 className="text-xl font-black tracking-tight">
            PROJECT CHARLIE: INTEGRITY MONITOR
          </h1>
          <p className="text-slate-400 text-xs mt-1">
            Comparing Series Counts across 3-DB Infrastructure
          </p>
        </div>

        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-slate-100 text-slate-500 text-[10px] uppercase font-black tracking-widest border-b border-slate-200">
              <th className="p-4 text-left">Timeline</th>
              <th className="p-4 text-center">Old DB</th>
              <th className="p-4 text-center">New DB</th>
              <th className="p-4 text-center">Full DB</th>
              <th className="p-4 text-right">Integrity</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {report?.timeline.map((day) => {
              const counts = [
                day.sources.old.count,
                day.sources.new.count,
                day.sources.full.count,
              ];
              const max = Math.max(...counts);

              return (
                <tr
                  key={day.date}
                  className="hover:bg-blue-50/30 transition-colors group"
                >
                  <td className="p-4">
                    <span className="font-mono text-sm font-bold text-slate-700">
                      {day.date}
                    </span>
                  </td>

                  {/* DB Cells: Highlight red if count is lower than the max among the three */}
                  {[day.sources.old, day.sources.new, day.sources.full].map(
                    (src, i) => (
                      <td key={i} className="p-4 text-center">
                        <div
                          className={`inline-block px-3 py-1 rounded-lg font-black text-sm ${
                            src.count < max
                              ? "bg-rose-100 text-rose-600 animate-pulse"
                              : "bg-slate-50 text-slate-600"
                          }`}
                        >
                          {src.count}{" "}
                          <span className="text-[10px] font-normal opacity-70">
                            SER
                          </span>
                        </div>
                      </td>
                    ),
                  )}

                  <td className="p-4 text-right">
                    <StatusBadge type={day.mismatchType} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
