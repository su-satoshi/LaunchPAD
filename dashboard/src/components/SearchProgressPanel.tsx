"use client";
import { useSearch } from "@/lib/SearchContext";
import { getQcStatus } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Search, ShieldCheck, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type QcState = {
  running?: boolean;
  ran_at?: string | null;
  result?: { removed_total?: number; dead_link?: number; closed?: number; old?: number;
             duplicate?: number; criteria?: number; threads_expired?: number } | null;
};

const AVG_SECONDS_PER_JOB = 0.5;

// Grass green progress fill with a matching glow on the leading edge
const GRASS = "#4cbb17";
const GRASS_LIGHT = "#6fdc3a";
const GRASS_GLOW = "0 0 8px rgba(76,187,23,0.95), 0 0 18px rgba(76,187,23,0.6), 0 0 32px rgba(76,187,23,0.35)";

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

  // Quality control starts by itself when a search finishes; follow it until it's done
  const { data: qcData } = useQuery({
    queryKey: ["qc-status"],
    queryFn: getQcStatus,
    enabled: visible && !!completedAt,
    refetchInterval: (q) => ((q.state.data as QcState | undefined)?.running ? 3000 : 15000),
  });
  const qc = qcData as QcState | undefined;

  if (!visible) return null;

  const isDone = !!completedAt && !isSearching;
  const pct = isDone ? 100
    : progress.jobsProcessed > 0
      ? Math.min(95, Math.round((progress.jobsProcessed / Math.max(progress.jobsFound, 1)) * 100))
      : 4;

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
                <Search className="w-4 h-4" style={{ color: GRASS_LIGHT }} />
                <span className="pulse-ring absolute inset-0 rounded-full border" style={{ animationDelay: "0.2s", borderColor: "rgba(76,187,23,0.45)" }} />
              </>
          }
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-xs font-bold" style={{ color: GRASS_LIGHT }}>
              {isDone ? "Search complete" : "Searching jobs…"}
            </p>
            {isSearching && eta && <span className="text-[10px] font-medium" style={{ color: "#444" }}>{eta}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button type="button" onClick={() => setCollapsed(c => !c)}
            className="text-[10px] font-medium px-2 py-0.5 rounded-lg transition"
            style={{ color: "#555" }}
            onMouseEnter={e => (e.currentTarget.style.color = "#888")}
            onMouseLeave={e => (e.currentTarget.style.color = "#555")}
          >
            {collapsed ? "expand" : "collapse"}
          </button>
          {isDone && (
            <button type="button" aria-label="Dismiss" onClick={() => setVisible(false)}
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
          {/* ── Progress rail: grass-green fill with a green-glowing leading edge ── */}
          <div className="px-4 pb-1">
            <div
              className="h-7 rounded-full relative overflow-hidden"
              role="progressbar"
              aria-valuenow={pct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Search progress"
              style={{
                background: "rgba(76,187,23,0.08)",
                border: "1.5px solid rgba(76,187,23,0.22)",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03), inset 0 -1px 0 rgba(0,0,0,0.30)",
              }}
            >
              {/* Filled (done) portion */}
              <div
                className="absolute inset-y-0 left-0"
                style={{
                  width: `${Math.max(pct, 4)}%`,
                  background: `linear-gradient(90deg, ${GRASS} 0%, ${GRASS_LIGHT} 100%)`,
                  boxShadow: isDone ? "0 0 14px rgba(76,187,23,0.45)" : undefined,
                  transition: "width 0.7s cubic-bezier(0.4,0,0.2,1)",
                  borderRadius: "inherit",
                }}
              />

              {/* Glowing leading edge */}
              {pct < 99 && (
                <div
                  className="absolute top-0 bottom-0 z-10 pointer-events-none search-edge-glow"
                  style={{
                    left: `${Math.max(pct, 4)}%`,
                    transform: "translateX(-50%)",
                    width: 3,
                    background: GRASS_LIGHT,
                    boxShadow: GRASS_GLOW,
                    transition: "left 0.7s cubic-bezier(0.4,0,0.2,1)",
                  }}
                />
              )}

              {/* Percentage label: dark on the green fill, green on the empty track */}
              <span
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-bold tabular-nums select-none z-20"
                style={{ color: pct > 85 ? "rgba(6,30,0,0.85)" : GRASS_LIGHT }}
              >
                {pct < 5 ? "" : `${pct}%`}
              </span>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-px px-4 pb-4 pt-3">
            {[
              { label: "Found",   value: progress.jobsFound,     color: "#e0e0e0"    },
              { label: "Scored",  value: progress.jobsProcessed,  color: "#e0e0e0"  },
              { label: "Matched", value: progress.jobsMatched,   color: GRASS_LIGHT },
            ].map(({ label, value, color }) => (
              <div key={label} className="text-center">
                <p className="text-lg font-bold tabular-nums" style={{ color }}>{value}</p>
                <p className="text-[10px] font-medium" style={{ color: "#444" }}>{label}</p>
              </div>
            ))}
          </div>

          {isDone && qc && (qc.running || qc.result) && (
            <div className="mx-4 mb-3 px-3 py-2 rounded-xl flex items-start gap-2"
              style={{ background: "rgba(76,187,23,0.06)", border: "1px solid rgba(76,187,23,0.18)" }}>
              <ShieldCheck className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: GRASS_LIGHT }} />
              <p className="text-[11px] leading-relaxed" style={{ color: "#8a8a8a" }}>
                {qc.running ? "Quality check running: verifying links and removing stale listings…" : (() => {
                  const r = qc.result || {};
                  const parts = [
                    r.dead_link ? `${r.dead_link} dead links` : "",
                    r.closed ? `${r.closed} closed ads` : "",
                    r.old ? `${r.old} old posts` : "",
                    r.duplicate ? `${r.duplicate} duplicates` : "",
                    r.criteria ? `${r.criteria} outside your criteria` : "",
                    r.threads_expired ? `${r.threads_expired} stale referral threads` : "",
                  ].filter(Boolean);
                  return r.removed_total
                    ? `Quality check removed ${r.removed_total}: ${parts.join(", ")}.`
                    : "Quality check passed: every listing is live and matches your criteria.";
                })()}
              </p>
            </div>
          )}

          {isDone && (
            <div className="px-4 pb-4 pt-0 flex items-center justify-between">
              <p className="text-[11px]" style={{ color: "#555" }}>
                Completed at {new Date(completedAt!).toLocaleTimeString()}
              </p>
              <button type="button" onClick={() => startSearch()} className="text-[11px] font-semibold transition hover:opacity-80" style={{ color: GRASS_LIGHT }}>
                Run again →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
