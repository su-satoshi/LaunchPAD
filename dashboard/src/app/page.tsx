"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDashboard, getJobs, getPipelineStats, bulkApplyFromUrl } from "@/lib/api";
import { sourceIcon, statusBadgeStyle, formatSalary, safeUrl } from "@/lib/utils";
import ScoreBadge from "@/components/ScoreBadge";
import {
  Briefcase, Mail,
  Play, RefreshCw, ExternalLink, ChevronRight,
  Target, Award, Clock, ArrowUpRight, Link2, Layers,
} from "lucide-react";
import toast from "react-hot-toast";
import Link from "next/link";
import { useSearch } from "@/lib/SearchContext";
import SegmentedArc from "@/components/SegmentedArc";
import SearchProgressPanel from "@/components/SearchProgressPanel";

const C = {
  bg:       "#080808",
  card:     "#111111",
  card2:    "#161616",
  border:   "#1e1e1e",
  border2:  "#2a2a2a",
  text:     "#e0e0e0",
  muted:    "#666666",
  dim:      "#333333",
  orange:   "#f97316",
  orangeDim:"rgba(249,115,22,0.08)",
  orangeBorder:"rgba(249,115,22,0.20)",
};

const PIPELINE = [
  { key: "email_sent", label: "Emailed",   color: "#f97316" },
  { key: "applied",    label: "Applied",   color: "#22c55e" },
  { key: "interview",  label: "Interview", color: "#eab308" },
  { key: "offer",      label: "Offer",     color: "#fb923c" },
  { key: "rejected",   label: "Rejected",  color: "#ef4444" },
];

function Card({ children, className = "", style = {} }: { children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  return (
    <div className={`rounded-2xl p-5 ${className}`} style={{ background: C.card, border: `1px solid ${C.border}`, ...style }}>
      {children}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: C.muted }}>{children}</p>;
}

/* ─── Bulk Apply ─── */
function BulkApplyPanel() {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const bulkMut = useMutation({
    mutationFn: (u: string) => bulkApplyFromUrl(u),
    onSuccess: (data) => {
      setResult(data as Record<string, unknown>);
      qc.invalidateQueries({ queryKey: ["jobs-all"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Failed to process URL";
      setResult({ error: msg });
    },
  });

  return (
    <div className="rounded-2xl p-5" style={{ background: C.card, border: `1px solid ${C.border}` }}>
      <div className="flex items-center gap-3 mb-4">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: C.orangeDim, border: `1px solid ${C.orangeBorder}` }}>
          <Layers className="w-4 h-4" style={{ color: C.orange }} />
        </div>
        <div>
          <h2 className="text-sm font-bold text-white">Bulk Apply from URL</h2>
          <p className="text-xs" style={{ color: C.muted }}>Paste a careers page — Claude extracts jobs, scores & drafts emails</p>
        </div>
      </div>
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Link2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none" style={{ color: C.dim }} />
          <input
            className="w-full pl-10 pr-4 py-2.5 text-sm rounded-xl font-medium transition-all"
            style={{ background: "#0d0d0d", border: `1px solid ${C.border2}`, color: C.text }}
            placeholder="https://company.com/careers"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && url && bulkMut.mutate(url)}
            onFocus={e => (e.currentTarget.style.borderColor = C.orange)}
            onBlur={e => (e.currentTarget.style.borderColor = C.border2)}
          />
        </div>
        <button
          onClick={() => url && bulkMut.mutate(url)}
          disabled={bulkMut.isPending || !url}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all whitespace-nowrap disabled:opacity-40"
          style={{ background: C.orange, color: "#fff" }}
        >
          {bulkMut.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          {bulkMut.isPending ? "Processing…" : "Extract & Apply"}
        </button>
      </div>
      {result && (
        <div className="mt-3 px-4 py-3 rounded-xl text-xs font-medium"
          style={{
            background: (result as Record<string, unknown>).error ? "rgba(239,68,68,0.08)" : "rgba(34,197,94,0.08)",
            border: `1px solid ${(result as Record<string, unknown>).error ? "rgba(239,68,68,0.20)" : "rgba(34,197,94,0.20)"}`,
            color: (result as Record<string, unknown>).error ? "#f87171" : "#4ade80",
          }}>
          {(result as Record<string, unknown>).error
            ? String((result as Record<string, unknown>).error)
            : String((result as Record<string, unknown>).message || "Done")}
          {!(result as Record<string, unknown>).error && (
            <span className="ml-3" style={{ color: C.muted }}>
              {Number((result as Record<string, unknown>).imported)} imported ·{" "}
              {Number((result as Record<string, unknown>).matched)} matched ·{" "}
              {Number((result as Record<string, unknown>).emails_drafted)} drafted
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { data, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard, refetchInterval: 15_000 });
  const { data: jobsData }  = useQuery({ queryKey: ["jobs-all"], queryFn: () => getJobs({ limit: 100, page: 1 }), refetchInterval: 30_000 });
  const { data: pipelineData } = useQuery({ queryKey: ["pipeline"], queryFn: getPipelineStats, refetchInterval: 30_000 });
  const { isSearching, progress, startSearch } = useSearch();

  const handleSearch = async () => {
    try { await startSearch(); toast.success("Search started"); }
    catch { toast.error("Search failed — check agent logs"); }
  };

  const stats      = data?.stats || {};
  const lastRun    = data?.last_run;
  const topMatches: Record<string, unknown>[] = data?.top_matches || [];
  const allJobs:    Record<string, unknown>[] = jobsData?.jobs || [];
  const pipeline   = pipelineData?.pipeline || {};

  const totalFound    = Number(stats.total_jobs_found ?? 0);
  const totalMatched  = Number(stats.jobs_matched ?? 0);
  const emailsSent    = Number(stats.applications_sent ?? 0);
  const interviews    = Number(stats.interviews ?? 0);
  const pendingReview = Number(stats.pending_review ?? 0);

  const STATS = [
    { label: "Jobs Found",     value: totalFound,    icon: Briefcase },
    { label: "Matched",        value: totalMatched,  icon: Target    },
    { label: "Emails Sent",    value: emailsSent,    icon: Mail      },
    { label: "Interviews",     value: interviews,    icon: Award     },
    { label: "Pending Review", value: pendingReview, icon: Clock     },
  ];

  return (
    <div className="min-h-screen p-6 space-y-5 page-enter" style={{ background: C.bg }}>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Overview</h1>
          <p className="text-xs mt-0.5" style={{ color: C.muted }}>
            {lastRun ? `Last scan ${new Date(lastRun.started_at).toLocaleString()} · ${lastRun.jobs_found ?? 0} found` : "No scans yet"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isSearching && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl"
              style={{ background: "rgba(76,187,23,0.08)", border: "1px solid rgba(76,187,23,0.30)" }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "#6fdc3a", boxShadow: "0 0 6px rgba(76,187,23,0.9)" }} />
              <span className="text-xs font-semibold" style={{ color: "#6fdc3a" }}>
                {progress.jobsFound} found · {progress.jobsMatched} matched
              </span>
            </div>
          )}
          <button
            type="button"
            onClick={handleSearch}
            disabled={isSearching}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all disabled:opacity-80"
            style={isSearching
              ? { background: "rgba(76,187,23,0.10)", color: "#6fdc3a", border: "1px solid rgba(76,187,23,0.35)" }
              : { background: C.orange, color: "#fff" }}
          >
            {isSearching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {isSearching ? "Searching…" : "Run Search"}
          </button>
        </div>
      </div>

      {/* Progress panel */}
      <SearchProgressPanel />

      {/* Stats strip */}
      <div className="grid grid-cols-5 gap-3">
        {STATS.map(({ label, value, icon: Icon }) => (
          <div key={label} className="rounded-2xl p-4 transition-all duration-150"
            style={{ background: C.card, border: `1px solid ${C.border}` }}
            onMouseEnter={e => (e.currentTarget.style.background = C.card2)}
            onMouseLeave={e => (e.currentTarget.style.background = C.card)}>
            <Icon className="w-4 h-4 mb-3" style={{ color: C.dim }} />
            <p className="text-3xl font-bold tabular-nums" style={{ color: isLoading ? C.muted : value === 0 ? C.dim : C.orange }}>
              {isLoading ? "—" : value}
            </p>
            <p className="text-[11px] font-medium mt-0.5" style={{ color: C.muted }}>{label}</p>
          </div>
        ))}
      </div>

      {/* Bento grid */}
      <div className="grid grid-cols-4 gap-4">

        {/* Match Rate */}
        <Card className="col-span-1 flex flex-col items-center">
          <SectionLabel>Match Rate</SectionLabel>
          <div className="flex-1 flex items-center justify-center py-2">
            <SegmentedArc value={totalMatched} max={Math.max(totalFound, 1)} label="matched" size={180} />
          </div>
        </Card>

        {/* Top Matches */}
        <Card className="col-span-2">
          <div className="flex items-center justify-between mb-3">
            <SectionLabel>Top Matches</SectionLabel>
            <Link href="/jobs" className="flex items-center gap-1 text-xs font-semibold transition-colors"
              style={{ color: C.orange }}>
              View all <ArrowUpRight className="w-3 h-3" />
            </Link>
          </div>
          {topMatches.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48">
              <Briefcase className="w-7 h-7 mb-3" style={{ color: C.dim }} />
              <p className="text-sm" style={{ color: C.muted }}>No matches yet</p>
              <p className="text-xs mt-1" style={{ color: C.dim }}>Run a search to populate</p>
            </div>
          ) : (
            <div className="space-y-0.5">
              {topMatches.slice(0, 7).map((job) => (
                <Link key={String(job.id)} href={`/jobs/${job.id}`}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-100 group"
                  style={{ borderRadius: "10px" }}
                  onMouseEnter={e => (e.currentTarget.style.background = C.card2)}
                  onMouseLeave={e => (e.currentTarget.style.background = "")}>
                  <span className="text-base shrink-0">{sourceIcon(String(job.source || ""))}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-white truncate">{String(job.title)}</p>
                    <p className="text-xs truncate" style={{ color: C.muted }}>{String(job.company)}</p>
                  </div>
                  <ScoreBadge score={job.match_score != null ? Number(job.match_score) : null} />
                </Link>
              ))}
            </div>
          )}
        </Card>

        {/* Pipeline */}
        <Card className="col-span-1 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <SectionLabel>Pipeline</SectionLabel>
            <Link href="/applications"><ArrowUpRight className="w-3.5 h-3.5" style={{ color: C.orange }} /></Link>
          </div>
          <div className="space-y-3 flex-1">
            {PIPELINE.map(({ key, label, color }) => {
              const count = Number(pipeline[key] ?? 0);
              const maxCount = Math.max(...PIPELINE.map(s => Number(pipeline[s.key] ?? 0)), 1);
              const pct = (count / maxCount) * 100;
              return (
                <div key={key}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs" style={{ color: C.muted }}>{label}</span>
                    <span className="text-xs font-bold" style={{ color: count === 0 ? C.dim : color }}>{count}</span>
                  </div>
                  <div className="h-1 rounded-full overflow-hidden" style={{ background: "#1a1a1a" }}>
                    <div className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${pct}%`, background: count === 0 ? "#2a2a2a" : color, opacity: count === 0 ? 1 : 0.8 }} />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-4 pt-3 flex items-center justify-between text-xs" style={{ borderTop: `1px solid ${C.border}` }}>
            <span style={{ color: C.muted }}>Total</span>
            {(() => {
              const total = PIPELINE.reduce((a, s) => a + Number(pipeline[s.key] ?? 0), 0);
              return <span className="font-bold" style={{ color: total === 0 ? C.dim : C.orange }}>{total}</span>;
            })()}
          </div>
        </Card>
      </div>

      {/* Bulk Apply */}
      <BulkApplyPanel />

      {/* Jobs table */}
      <div className="rounded-2xl overflow-hidden" style={{ background: C.card, border: `1px solid ${C.border}` }}>
        <div className="px-5 py-4 flex items-center justify-between" style={{ borderBottom: `1px solid ${C.border}` }}>
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-white">All Jobs</h2>
            <span className="text-[11px] px-2.5 py-0.5 rounded-full font-semibold"
              style={{ background: "#1a1a1a", color: C.muted }}>
              {allJobs.length} loaded
            </span>
          </div>
          <Link href="/jobs" className="flex items-center gap-1 text-xs font-semibold transition-colors"
            style={{ color: C.orange }}>
            Manage <ArrowUpRight className="w-3 h-3" />
          </Link>
        </div>
        {allJobs.length === 0 ? (
          <div className="py-20 text-center">
            <p className="text-sm" style={{ color: C.muted }}>No jobs yet — run a search</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                  {["Job", "Source", "Location", "Salary", "Match", "Status", ""].map((h) => (
                    <th key={h} className="text-left px-5 py-3 text-[10px] font-bold uppercase tracking-widest"
                      style={{ color: C.muted }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allJobs.map((job) => (
                  <tr key={String(job.id)} className="group transition-colors duration-100"
                    style={{ borderBottom: `1px solid ${C.border}` }}
                    onMouseEnter={e => (e.currentTarget.style.background = C.card2)}
                    onMouseLeave={e => (e.currentTarget.style.background = "")}>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <p className="font-semibold text-white">{String(job.title)}</p>
                        {job.url_valid === true && <span className="w-1.5 h-1.5 rounded-full shrink-0 link-dot-valid" title="Link verified" />}
                        {job.url_valid === false && <span className="w-1.5 h-1.5 rounded-full shrink-0 link-dot-broken" title="Link broken" />}
                      </div>
                      <p className="text-xs mt-0.5" style={{ color: C.muted }}>{String(job.company)}</p>
                    </td>
                    <td className="px-4 py-3.5 text-xs" style={{ color: C.muted }}>
                      {sourceIcon(String(job.source))} {String(job.source)}
                    </td>
                    <td className="px-4 py-3.5 text-xs" style={{ color: C.muted }}>{String(job.location || "—")}</td>
                    <td className="px-4 py-3.5 text-xs" style={{ color: C.muted }}>
                      {formatSalary(Number(job.salary_min), Number(job.salary_max), String(job.salary_currency || "AUD")) || "—"}
                    </td>
                    <td className="px-4 py-3.5">
                      <ScoreBadge score={job.match_score != null ? Number(job.match_score) : null} />
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="text-[11px] font-semibold px-2.5 py-1 rounded-lg"
                        style={statusBadgeStyle(String(job.status))}>
                        {String(job.status).replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        {Boolean(job.url) && (
                          <a href={safeUrl(job.url)} target="_blank" rel="noopener noreferrer"
                            className="transition-colors" style={{ color: C.dim }}
                            onMouseEnter={e => (e.currentTarget.style.color = C.orange)}
                            onMouseLeave={e => (e.currentTarget.style.color = C.dim)}>
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                        <Link href={`/jobs/${job.id}`}
                          className="transition-colors" style={{ color: C.dim }}
                          onMouseEnter={e => (e.currentTarget.style.color = C.orange)}
                          onMouseLeave={e => (e.currentTarget.style.color = C.dim)}>
                          <ChevronRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
