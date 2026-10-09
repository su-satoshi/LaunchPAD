"use client";
import { useSearch } from "@/lib/SearchContext";
import { CheckCircle2, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const AVG_SECONDS_PER_JOB = 0.5;

export default function SearchProgressPanel() {
  const { isSearching, progress, completedAt, startSearch } = useSearch();
  const [visible, setVisible] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [eta, setEta] = useState<string | null>(null);
  const startedAt = useRef<number | null>(null);

  useEffect(() => {
    if (isSearching) { setVisible(true); setCollapsed(false); if (!startedAt.current) startedAt.current = Date.now(); }
    if (completedAt) { setVisible(true); startedAt.current = null; }
  }, [isSearching, completedAt]);

  useEffect(() => {
    if (!isSearching || progress.jobsFound === 0) { setEta(null); return; }
    const remaining = progress.jobsFound - progress.jobsProcessed;
    if (remaining <= 0) { setEta("finishing up…"); return; }
    const elapsed = startedAt.current ? (Date.now() - startedAt.current) / 1000 : 0;
    const rate = progress.jobsProcessed > 0 ? elapsed / progress.jobsProcessed : AVG_SECONDS_PER_JOB;
    const secs = Math.round(remaining * rate);
    setEta(secs < 60 ? `~${secs}s remaining` : `~${Math.ceil(secs / 60)}m remaining`);
  }, [isSearching, progress]);

  if (!visible) return null;

  const isDone = !!completedAt && !isSearching;
  const pct = isDone ? 100
    : progress.jobsProcessed > 0
      ? Math.min(95, Math.round((progress.jobsProcessed / Math.max(progress.jobsFound, 1)) * 100))
      : (isSearching ? 4 : 4);

  return (
    <div
      className="rounded-2xl overflow-hidden transition-all duration-500"
      style={{ background: "#111111", border: "1px solid #1e1e1e" }}
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="relative shrink-0">
          {isDone
            ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            : <>
                <Search className="w-4 h-4 text-orange-400" />
                <span className="pulse-ring absolute inset-0 rounded-full border border-orange-400/40" style={{ animationDelay: "0.2s" }} />
              </>
          }
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className={`text-xs font-bold ${isDone ? "text-emerald-400" : "text-orange-400"}`}>
              {isDone ? "Search complete" : "Searching jobs…"}
            </p>
            {isSearching && eta && <span className="text-[10px] font-medium" style={{ color: "#444" }}>{eta}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={() => setCollapsed(c => !c)}
            className="text-[10px] font-medium px-2 py-0.5 rounded-lg transition"
            style={{ color: "#555" }}
            onMouseEnter={e => (e.currentTarget.style.color = "#888")}
            onMouseLeave={e => (e.currentTarget.style.color = "#555")}
          >
            {collapsed ? "expand" : "collapse"}
          </button>
          {isDone && (
            <button onClick={() => setVisible(false)}
              className="transition"
              style={{ color: "#444" }}
              onMouseEnter={e => (e.currentTarget.style.color = "#888")}
              onMouseLeave={e => (e.currentTarget.style.color = "#444")}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {!collapsed && (
        <>
          {/* ── Inverted Yamanote rail: orange track → dark fill → white line ── */}
          <div className="px-4 pb-1">
            {/* Pill container — no outer glow */}
            <div
              className="h-7 rounded-full relative overflow-hidden"
              style={{
                /* Orange-tinted track = "remaining" */
                background: isDone
                  ? "rgba(52,211,153,0.18)"
                  : "rgba(249,115,22,0.18)",
                border: "1.5px solid rgba(255,255,255,0.06)",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04), inset 0 -1px 0 rgba(0,0,0,0.30)",
              }}
            >
              {/* Dark fill on the LEFT — the "done" portion covers the orange track */}
              <div
                className="absolute inset-y-0 left-0"
                style={{
                  width: `${Math.max(pct, 4)}%`,
                  background: isDone
                    ? "rgba(10,10,10,0.92)"
                    : isSearching && pct <= 4
                      ? "rgba(10,10,10,0.92)"
                      : "rgba(10,10,10,0.92)",
                  transition: "width 0.7s cubic-bezier(0.4,0,0.2,1)",
                  borderRadius: "inherit",
                }}
              />

              {/* White vertical line marker at the progress boundary */}
              {pct < 99 && (
                <div
                  className="absolute top-0 bottom-0 z-10 pointer-events-none"
                  style={{
                    left: `${Math.max(pct, 4)}%`,
                    transform: "translateX(-50%)",
                    width: 2,
                    background: "#ffffff",
                    boxShadow: "0 0 8px rgba(255,255,255,0.9), 0 0 16px rgba(255,255,255,0.5)",
                    transition: "left 0.7s cubic-bezier(0.4,0,0.2,1)",
                  }}
                />
              )}

              {/* Percentage label */}
              <span
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-bold tabular-nums select-none z-20"
                style={{
                  color: pct > 85
                    ? "rgba(0,0,0,0.7)"
                    : isDone
                      ? "rgba(52,211,153,0.9)"
                      : "rgba(249,115,22,0.9)",
                }}
              >
                {pct < 5 ? "" : `${pct}%`}
              </span>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-px px-4 pb-4 pt-3">
            {[
              { label: "Found",   value: progress.jobsFound,     color: "#e0e0e0"    },
              { label: "Scored",  value: progress.jobsProcessed,  color: "#f97316"  },
              { label: "Matched", value: progress.jobsMatched,   color: "#4ade80" },
            ].map(({ label, value, color }) => (
              <div key={label} className="text-center">
                <p className="text-lg font-bold tabular-nums" style={{ color }}>{value}</p>
                <p className="text-[10px] font-medium" style={{ color: "#444" }}>{label}</p>
              </div>
            ))}
          </div>

          {isDone && (
            <div className="px-4 pb-4 pt-0 flex items-center justify-between">
              <p className="text-[11px]" style={{ color: "#555" }}>
                Completed at {new Date(completedAt!).toLocaleTimeString()}
              </p>
              <button onClick={() => startSearch()} className="text-[11px] text-orange-500 hover:text-orange-400 font-semibold transition">
                Run again →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
