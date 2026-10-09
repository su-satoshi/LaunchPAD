"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getJobs, updateJobStatus, triggerSearch, createDraftEmail } from "@/lib/api";
import { statusBadgeStyle, sourceIcon, formatSalary, safeUrl } from "@/lib/utils";
import ScoreBadge from "@/components/ScoreBadge";
import {
  Search, ExternalLink, RefreshCw, Play,
  MapPin, ChevronRight, Filter, SlidersHorizontal,
  Mail, Snowflake, Briefcase, ShieldCheck,
} from "lucide-react";
import { verifyLinks } from "@/lib/api";
import toast from "react-hot-toast";
import Link from "next/link";

const SOURCE_OPTIONS = [
  { id: "linkedin",      label: "LinkedIn",         emoji: "💼" },
  { id: "indeed",        label: "Indeed",            emoji: "🔍" },
  { id: "glassdoor",     label: "Glassdoor",         emoji: "🚪" },
  { id: "seek",          label: "Seek",              emoji: "🦘" },
  { id: "web3careers",   label: "Web3.Careers",      emoji: "⛓️" },
  { id: "prosple",       label: "Prosple",           emoji: "🎓" },
  { id: "ambitionbox",   label: "AmbitionBox",       emoji: "📦" },
  { id: "top_companies", label: "Top Companies",     emoji: "🏆" },
  { id: "ziprecruiter",  label: "ZipRecruiter",      emoji: "📋" },
  { id: "google",        label: "Google Jobs",       emoji: "🔷" },
];
const SOURCES = SOURCE_OPTIONS.map((s) => s.id);
const STATUSES = ["found","matched","draft_ready","email_sent","applied","interview","offer","rejected","skipped","expired"];

// Days after which a job is considered "old/expired"
const COLD_EMAIL_DAYS = 14;

function Select({ value, onChange, children, className = "" }: {
  value: string; onChange: (v: string) => void; children: React.ReactNode; className?: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`text-sm rounded-xl px-4 py-2.5 outline-none cursor-pointer transition ${className}`}
      style={{ background: "#111", border: "1px solid #2a2a2a", color: "#e0e0e0" }}
      onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
      onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
    >
      {children}
    </select>
  );
}

type JobRecord = Record<string, unknown>;

function ColdEmailTargetsTab() {
  const qc = useQueryClient();
  const [draftingId, setDraftingId] = useState<number | null>(null);

  // Fetch old matched jobs (>14 days old, never contacted, >60% match)
  const { data, isLoading } = useQuery({
    queryKey: ["jobs-cold-email"],
    queryFn: () => getJobs({
      min_score: 0.6,
      status: "matched",
      limit: 100,
      page: 1,
    }),
    refetchInterval: 60_000,
  });

  const jobs: JobRecord[] = (data?.jobs || []).filter((job: JobRecord) => {
    const foundAt = job.found_at ? new Date(String(job.found_at)) : null;
    if (!foundAt) return false;
    const ageDays = (Date.now() - foundAt.getTime()) / (1000 * 60 * 60 * 24);
    return ageDays >= COLD_EMAIL_DAYS;
  });

  const draftColdEmail = async (jobId: number) => {
    setDraftingId(jobId);
    try {
      await createDraftEmail({ job_id: jobId, email_type: "cold_email" });
      toast.success("Cold email draft created! Check Emails →");
      qc.invalidateQueries({ queryKey: ["emails"] });
    } catch {
      toast.error("Failed to draft email — make sure your resume is uploaded");
    } finally {
      setDraftingId(null);
    }
  };

  if (isLoading) {
    return <div className="py-20 text-center text-sm" style={{ color: "#555" }}>Loading cold email targets…</div>;
  }

  if (jobs.length === 0) {
    return (
      <div className="py-20 text-center">
        <Snowflake className="w-8 h-8 mx-auto mb-3" style={{ color: "#333" }} />
        <p className="text-sm font-medium" style={{ color: "#555" }}>No cold email targets yet</p>
        <p className="text-xs mt-1.5 max-w-xs mx-auto" style={{ color: "#444" }}>
          Jobs matched at 60%+ that are older than {COLD_EMAIL_DAYS} days will appear here for cold outreach.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 px-1">
        <Snowflake className="w-4 h-4" style={{ color: "#f97316" }} />
        <p className="text-sm font-medium" style={{ color: "#888" }}>
          {jobs.length} job{jobs.length !== 1 ? "s" : ""} matched ≥60% · older than {COLD_EMAIL_DAYS} days · ready for cold outreach
        </p>
      </div>
      <div className="rounded-2xl overflow-hidden" style={{ background: "#111", border: "1px solid #1e1e1e" }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: "1px solid #1e1e1e" }}>
                {["Job", "Source", "Match", "Found", "Actions"].map(h => (
                  <th key={h} className="text-left px-5 py-3 text-[10px] font-bold uppercase tracking-widest" style={{ color: "#666" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const foundAt = job.found_at ? new Date(String(job.found_at)) : null;
                const ageDays = foundAt
                  ? Math.floor((Date.now() - foundAt.getTime()) / (1000 * 60 * 60 * 24))
                  : null;
                return (
                  <tr
                    key={String(job.id)}
                    className="group transition-colors"
                    style={{ borderBottom: "1px solid #1a1a1a" }}
                    onMouseEnter={e => (e.currentTarget.style.background = "#161616")}
                    onMouseLeave={e => (e.currentTarget.style.background = "")}
                  >
                    <td className="px-5 py-3.5">
                      <p className="font-semibold text-white truncate max-w-[260px]">{String(job.title)}</p>
                      <p className="text-xs mt-0.5" style={{ color: "#666" }}>{String(job.company)}</p>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="flex items-center gap-1.5 text-xs" style={{ color: "#555" }}>
                        {sourceIcon(String(job.source))}
                        <span className="capitalize">{String(job.source)}</span>
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <ScoreBadge score={job.match_score != null ? Number(job.match_score) : null} />
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="text-xs" style={{ color: "#555" }}>
                        {ageDays !== null ? `${ageDays}d ago` : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => draftColdEmail(Number(job.id))}
                          disabled={draftingId === Number(job.id)}
                          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg disabled:opacity-50 transition font-semibold"
                          style={{ background: "rgba(249,115,22,0.10)", color: "#f97316", border: "1px solid rgba(249,115,22,0.22)" }}
                        >
                          {draftingId === Number(job.id)
                            ? <RefreshCw className="w-3 h-3 animate-spin" />
                            : <Mail className="w-3 h-3" />}
                          {draftingId === Number(job.id) ? "Drafting…" : "Draft Cold Email"}
                        </button>
                        {Boolean(job.url) && (
                          <a
                            href={safeUrl(job.url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: "#444" }}
                            onMouseEnter={e => (e.currentTarget.style.color = "#f97316")}
                            onMouseLeave={e => (e.currentTarget.style.color = "#444")}
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                        <Link
                          href={`/jobs/${job.id}`}
                          style={{ color: "#444" }}
                          onMouseEnter={e => (e.currentTarget.style.color = "#f97316")}
                          onMouseLeave={e => (e.currentTarget.style.color = "#444")}
                        >
                          <ChevronRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function JobsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [minScore, setMinScore] = useState("");
  const [page, setPage] = useState(1);
  const [activeTab, setActiveTab] = useState<"all" | "cold">("all");
  const [validOnly, setValidOnly] = useState(false);
  const [verifying, setVerifying] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["jobs", search, source, status, minScore, page],
    queryFn: () => getJobs({
      search: search || undefined,
      source: source || undefined,
      status: status || undefined,
      min_score: minScore ? Number(minScore) : undefined,
      page,
      limit: 50,
    }),
    enabled: activeTab === "all",
  });

  const trigger = useMutation({
    mutationFn: triggerSearch,
    onSuccess: () => {
      toast.success("Search triggered!");
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: () => toast.error("Search failed"),
  });

  const statusUpdate = useMutation({
    mutationFn: ({ id, s }: { id: number; s: string }) => updateJobStatus(id, s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });

  const handleVerify = async () => {
    setVerifying(true);
    try {
      const r = await verifyLinks();
      toast.success(`Verified ${r.checked} links — ${r.valid} valid, ${r.broken} broken`);
      qc.invalidateQueries({ queryKey: ["jobs"] });
    } catch { toast.error("Verification failed"); }
    finally { setVerifying(false); }
  };

  const jobs = (data?.jobs || []).filter((j: Record<string, unknown>) =>
    validOnly ? j.url_valid === true : true
  );
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / 50);

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-5 min-h-screen" style={{ background: "#080808" }}>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Jobs</h1>
          <p className="text-xs mt-0.5" style={{ color: "#666" }}>{total.toLocaleString()} jobs in database</p>
        </div>
        <button
          onClick={() => trigger.mutate()}
          disabled={trigger.isPending}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold disabled:opacity-50 transition"
          style={{ background: "#f97316", color: "#fff" }}
        >
          {trigger.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          {trigger.isPending ? "Searching…" : "Search Now"}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5" style={{ borderBottom: "1px solid #1e1e1e" }}>
        {[
          { id: "all",  label: "All Jobs",          icon: Briefcase },
          { id: "cold", label: "Cold Email Targets", icon: Snowflake },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id as "all" | "cold")}
            className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold transition-all select-none relative"
            style={{ color: activeTab === id ? "#fff" : "#555" }}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
            {activeTab === id && (
              <span className="absolute inset-x-0 bottom-0 h-0.5 rounded-full" style={{ background: "#f97316" }} />
            )}
          </button>
        ))}
      </div>

      {/* ── All Jobs Tab ── */}
      {activeTab === "all" && (
        <>
          {/* Filters */}
          <div className="flex flex-wrap gap-2.5 items-center">
            <div className="relative flex-1 min-w-52">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none" style={{ color: "#555" }} />
              <input
                className="search-input w-full pl-10 pr-4 py-2.5 text-sm rounded-xl"
                placeholder="Search title or company…"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              />
            </div>

            <Select value={source} onChange={(v) => { setSource(v); setPage(1); }}>
              <option value="">All portals</option>
              {SOURCE_OPTIONS.map((s) => (
                <option key={s.id} value={s.id}>{s.emoji} {s.label}</option>
              ))}
            </Select>

            <Select value={status} onChange={(v) => { setStatus(v); setPage(1); }}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </Select>
            <Select value={minScore} onChange={(v) => { setMinScore(v); setPage(1); }}>
              <option value="">Any score</option>
              <option value="0.85">85%+ (excellent)</option>
              <option value="0.70">70%+ (good)</option>
              <option value="0.50">50%+ (moderate)</option>
            </Select>
            <button
              onClick={() => { setValidOnly(v => !v); setPage(1); }}
              className="flex items-center gap-1.5 text-xs px-3 py-2.5 rounded-xl font-semibold transition-all"
              style={validOnly
                ? { background: "rgba(34,197,94,0.12)", color: "#4ade80", border: "1px solid rgba(34,197,94,0.25)" }
                : { background: "#111", border: "1px solid #2a2a2a", color: "#555" }}
            >
              <span className={`w-2 h-2 rounded-full ${validOnly ? "link-dot-valid" : "link-dot-unchecked"}`} />
              {validOnly ? "Working links only" : "All links"}
            </button>

            <button
              onClick={handleVerify}
              disabled={verifying}
              className="flex items-center gap-1.5 text-xs px-3 py-2.5 rounded-xl font-semibold transition-all disabled:opacity-50"
              style={{ background: "#111", border: "1px solid #2a2a2a", color: "#666" }}
              onMouseEnter={e => { e.currentTarget.style.color = "#f97316"; e.currentTarget.style.borderColor = "rgba(249,115,22,0.3)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "#666"; e.currentTarget.style.borderColor = "#2a2a2a"; }}
            >
              {verifying ? <RefreshCw className="w-3 h-3 animate-spin" /> : <ShieldCheck className="w-3 h-3" />}
              {verifying ? "Verifying…" : "Verify Links"}
            </button>

            <div className="flex items-center gap-1.5 text-xs ml-1">
              <SlidersHorizontal className="w-3.5 h-3.5" style={{ color: "#444" }} />
              <span className="font-bold" style={{ color: "#f97316" }}>{validOnly ? jobs.length : total}</span>
              <span style={{ color: "#555" }}>results</span>
            </div>
          </div>

          {/* Table */}
          <div className="rounded-2xl overflow-hidden" style={{ background: "#111", border: "1px solid #1e1e1e" }}>
            {isLoading ? (
              <div className="py-20 text-center text-sm" style={{ color: "#555" }}>Loading…</div>
            ) : jobs.length === 0 ? (
              <div className="py-20 text-center">
                <Filter className="w-8 h-8 mx-auto mb-3" style={{ color: "#333" }} />
                <p className="text-sm" style={{ color: "#555" }}>No jobs match your filters</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: "1px solid #1e1e1e" }}>
                      {["Job", "Portal", "Location", "Salary", "Match", "Status", ""].map(h => (
                        <th key={h} className="text-left px-5 py-3 text-[10px] font-bold uppercase tracking-widest" style={{ color: "#666" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((job: Record<string, unknown>) => (
                      <tr
                        key={String(job.id)}
                        className="group transition-colors"
                        style={{ borderBottom: "1px solid #1a1a1a" }}
                        onMouseEnter={e => (e.currentTarget.style.background = "#161616")}
                        onMouseLeave={e => (e.currentTarget.style.background = "")}
                      >
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-2">
                            <p className="font-semibold text-white truncate max-w-[240px]">{String(job.title)}</p>
                            {job.url_valid === true && <span className="w-1.5 h-1.5 rounded-full shrink-0 link-dot-valid" title="Link verified working" />}
                            {job.url_valid === false && <span className="w-1.5 h-1.5 rounded-full shrink-0 link-dot-broken" title="Link is broken" />}
                          </div>
                          <p className="text-xs mt-0.5" style={{ color: "#666" }}>{String(job.company)}</p>
                          {Boolean(job.is_referral_post) && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded mt-1 inline-block"
                              style={{ background: "rgba(234,179,8,0.08)", color: "#facc15", border: "1px solid rgba(234,179,8,0.18)" }}>Referral</span>
                          )}
                        </td>
                        <td className="px-4 py-3.5">
                          <span className="flex items-center gap-1.5 text-xs" style={{ color: "#555" }}>
                            {sourceIcon(String(job.source))}
                            {(() => { const src = SOURCE_OPTIONS.find((s) => s.id === String(job.source)); return <span>{src ? src.label : String(job.source)}</span>; })()}
                          </span>
                        </td>
                        <td className="px-4 py-3.5">
                          <span className="flex items-center gap-1 text-xs" style={{ color: "#555" }}>
                            <MapPin className="w-3 h-3" style={{ color: "#333" }} />
                            {String(job.location || "—")}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 text-xs" style={{ color: "#555" }}>
                          {formatSalary(Number(job.salary_min), Number(job.salary_max), String(job.salary_currency || "AUD")) || "—"}
                        </td>
                        <td className="px-4 py-3.5">
                          <ScoreBadge score={job.match_score != null ? Number(job.match_score) : null} />
                        </td>
                        <td className="px-4 py-3.5">
                          <select
                            className="text-xs font-medium px-2.5 py-1 rounded-lg border-0 cursor-pointer outline-none"
                            style={statusBadgeStyle(String(job.status))}
                            title={job.qc_reason ? `Quality check: ${String(job.qc_reason)}` : undefined}
                            aria-label="Job status"
                            value={String(job.status)}
                            onChange={(e) => statusUpdate.mutate({ id: Number(job.id), s: e.target.value })}
                          >
                            {STATUSES.map((s) => (
                              <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                            ))}
                          </select>
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition">
                            {Boolean(job.url) && (
                              <a href={safeUrl(job.url)} target="_blank" rel="noopener noreferrer"
                                style={{ color: "#444" }}
                                onMouseEnter={e => (e.currentTarget.style.color = "#f97316")}
                                onMouseLeave={e => (e.currentTarget.style.color = "#444")}>
                                <ExternalLink className="w-3.5 h-3.5" />
                              </a>
                            )}
                            <Link href={`/jobs/${job.id}`}
                              style={{ color: "#444" }}
                              onMouseEnter={e => (e.currentTarget.style.color = "#f97316")}
                              onMouseLeave={e => (e.currentTarget.style.color = "#444")}>
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

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-4 py-2 text-sm rounded-xl transition disabled:opacity-30"
                style={{ background: "#161616", border: "1px solid #2a2a2a", color: "#888" }}
                onMouseEnter={e => { if (page !== 1) e.currentTarget.style.background = "#1e1e1e"; }}
                onMouseLeave={e => (e.currentTarget.style.background = "#161616")}
              >
                Previous
              </button>
              <span className="text-sm" style={{ color: "#555" }}>
                Page <span className="font-semibold" style={{ color: "#e0e0e0" }}>{page}</span> of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-4 py-2 text-sm rounded-xl transition disabled:opacity-30"
                style={{ background: "#161616", border: "1px solid #2a2a2a", color: "#888" }}
                onMouseEnter={e => { if (page !== totalPages) e.currentTarget.style.background = "#1e1e1e"; }}
                onMouseLeave={e => (e.currentTarget.style.background = "#161616")}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {/* ── Cold Email Targets Tab ── */}
      {activeTab === "cold" && <ColdEmailTargetsTab />}

    </div>
  );
}
