"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { getJob, updateJobStatus, createDraftEmail, autoApplyJob } from "@/lib/api";
import { statusBadgeStyle, sourceIcon, formatSalary, safeUrl } from "@/lib/utils";
import ScoreBadge from "@/components/ScoreBadge";
import {
  ArrowLeft, ExternalLink, Mail, MapPin, Building2,
  CheckCircle, Star, DollarSign, Zap, X, AlertTriangle,
} from "lucide-react";
import toast from "react-hot-toast";

const STATUSES = ["found","matched","draft_ready","email_sent","applied","interview","offer","rejected","skipped"];

const CARD = { background: "#111111", border: "1px solid #1e1e1e" };

interface AutoApplyResult {
  success: boolean;
  portal: string;
  status: string;
  message: string;
  screenshot_b64: string;
  fields_filled: string[];
  requires_confirmation: boolean;
}

export default function JobDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const qc = useQueryClient();
  const [autoResult, setAutoResult] = useState<AutoApplyResult | null>(null);

  const { data: job, isLoading } = useQuery({
    queryKey: ["job", id],
    queryFn: () => getJob(Number(id)),
  });

  const statusMut = useMutation({
    mutationFn: (s: string) => updateJobStatus(Number(id), s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["job", id] }),
  });

  const draftEmail = useMutation({
    mutationFn: () => createDraftEmail({ job_id: Number(id), email_type: "application" }),
    onSuccess: (email: Record<string, unknown>) => {
      toast.success("Email drafted!");
      router.push(`/emails?highlight=${email.id}`);
    },
    onError: () => toast.error("Draft failed — ensure resume is uploaded"),
  });

  const autoApply = useMutation({
    mutationFn: () => autoApplyJob(Number(id)),
    onSuccess: (data: AutoApplyResult) => {
      setAutoResult(data);
      if (data.success) {
        toast.success(`Auto-apply launched on ${data.portal}!`);
        qc.invalidateQueries({ queryKey: ["job", id] });
      } else if (data.status === "login_required") {
        toast.error("Login credentials needed");
      }
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Auto-apply failed");
    },
  });

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center h-64" style={{ background: "#080808" }}>
        <div className="text-sm" style={{ color: "#555" }}>Loading…</div>
      </div>
    );
  }
  if (!job) {
    return <div className="p-8 text-sm" style={{ background: "#080808", color: "#555" }}>Job not found</div>;
  }

  return (
    <div className="p-7 max-w-4xl mx-auto space-y-5" style={{ background: "#080808", minHeight: "100vh" }}>

      {/* Back */}
      <button
        type="button"
        onClick={() => router.back()}
        className="flex items-center gap-2 text-sm transition"
        style={{ color: "#555" }}
        onMouseEnter={e => (e.currentTarget.style.color = "#e0e0e0")}
        onMouseLeave={e => (e.currentTarget.style.color = "#555")}
      >
        <ArrowLeft className="w-4 h-4" /> Back to Jobs
      </button>

      {/* Hero card */}
      <div className="rounded-3xl p-6" style={CARD}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-lg">{sourceIcon(job.source)}</span>
              <span className="text-xs uppercase tracking-widest" style={{ color: "#444" }}>{job.source}</span>
            </div>
            <h1 className="text-2xl font-bold text-white">{job.title}</h1>
            <div className="flex flex-wrap items-center gap-4 mt-2 text-sm" style={{ color: "#666" }}>
              <span className="flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5" style={{ color: "#444" }} /> {job.company}
              </span>
              {job.location && (
                <span className="flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5" style={{ color: "#444" }} /> {job.location}
                </span>
              )}
              {(job.salary_min || job.salary_max) && (
                <span className="flex items-center gap-1.5" style={{ color: "#4ade80" }}>
                  <DollarSign className="w-3.5 h-3.5" />
                  {formatSalary(job.salary_min, job.salary_max, job.salary_currency)}
                </span>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            {job.match_score != null && (
              <ScoreBadge score={job.match_score} />
            )}
            <select
              className="text-xs font-medium px-3 py-1.5 rounded-full border-0 cursor-pointer outline-none"
              style={statusBadgeStyle(job.status)}
              value={job.status}
              onChange={(e) => statusMut.mutate(e.target.value)}
            >
              {STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
            </select>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-3 mt-5 pt-5" style={{ borderTop: "1px solid #1e1e1e" }}>
          {job.url && (
            <a
              href={safeUrl(job.url)}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm transition"
              style={{ background: "#1a1a1a", border: "1px solid #2a2a2a", color: "#888" }}
              onMouseEnter={e => { e.currentTarget.style.color = "#fff"; e.currentTarget.style.background = "#222"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "#888"; e.currentTarget.style.background = "#1a1a1a"; }}
            >
              <ExternalLink className="w-4 h-4" /> View on {job.source}
            </a>
          )}
          <button
            type="button"
            onClick={() => draftEmail.mutate()}
            disabled={draftEmail.isPending}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition disabled:opacity-50"
            style={{ background: "#1a1a1a", border: "1px solid #2a2a2a", color: "#888" }}
            onMouseEnter={e => { e.currentTarget.style.color = "#fff"; e.currentTarget.style.background = "#222"; }}
            onMouseLeave={e => { e.currentTarget.style.color = "#888"; e.currentTarget.style.background = "#1a1a1a"; }}
          >
            <Mail className="w-4 h-4" />
            {draftEmail.isPending ? "Drafting…" : "Draft Email"}
          </button>
          <button
            type="button"
            onClick={() => autoApply.mutate()}
            disabled={autoApply.isPending}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold disabled:opacity-50 transition text-white"
            style={{ background: autoApply.isPending ? "rgba(249,115,22,0.30)" : "#f97316" }}
            onMouseEnter={e => { if (!autoApply.isPending) e.currentTarget.style.background = "#ea6a0a"; }}
            onMouseLeave={e => (e.currentTarget.style.background = autoApply.isPending ? "rgba(249,115,22,0.30)" : "#f97316")}
          >
            <Zap className="w-4 h-4" />
            {autoApply.isPending ? "Launching browser…" : "Auto Apply"}
          </button>
        </div>
      </div>

      {/* Auto-apply result panel */}
      {autoResult && (
        <div
          className="rounded-3xl p-5 relative"
          style={{
            background: autoResult.success
              ? "rgba(16,185,129,0.06)"
              : "rgba(239,68,68,0.06)",
            border: autoResult.success
              ? "1px solid rgba(16,185,129,0.20)"
              : "1px solid rgba(239,68,68,0.20)",
          }}
        >
          <button
            className="absolute top-4 right-4 transition"
            style={{ color: "#555" }}
            onClick={() => setAutoResult(null)}
            onMouseEnter={e => (e.currentTarget.style.color = "#e0e0e0")}
            onMouseLeave={e => (e.currentTarget.style.color = "#555")}
          >
            <X className="w-4 h-4" />
          </button>

          <div className="flex items-start gap-3 mb-3">
            {autoResult.status === "login_required" ? (
              <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" style={{ color: "#f97316" }} />
            ) : autoResult.success ? (
              <CheckCircle className="w-5 h-5 shrink-0 mt-0.5" style={{ color: "#4ade80" }} />
            ) : (
              <X className="w-5 h-5 shrink-0 mt-0.5" style={{ color: "#f87171" }} />
            )}
            <div>
              <p className="font-semibold text-white text-sm capitalize">
                {autoResult.portal} · {autoResult.status.replace(/_/g, " ")}
              </p>
              <p className="text-sm mt-1" style={{ color: "#888" }}>{autoResult.message}</p>
            </div>
          </div>

          {autoResult.fields_filled.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              <span className="text-xs mr-1" style={{ color: "#555" }}>Fields pre-filled:</span>
              {autoResult.fields_filled.map((f) => (
                <span key={f} className="text-xs px-2 py-0.5 rounded-full"
                  style={{ background: "rgba(249,115,22,0.10)", color: "#fb923c", border: "1px solid rgba(249,115,22,0.22)" }}>
                  {f}
                </span>
              ))}
            </div>
          )}

          {autoResult.status === "login_required" && (
            <div className="mt-3 p-3 rounded-xl text-xs font-mono" style={{ background: "#0d0d0d", color: "#888" }}>
              Add to your <span style={{ color: "#f97316" }}>.env</span> file:<br />
              <span style={{ color: "#e0e0e0" }}>
                {autoResult.portal.toUpperCase()}_EMAIL=your@email.com<br />
                {autoResult.portal.toUpperCase()}_PASSWORD=yourpassword
              </span>
            </div>
          )}

          {autoResult.requires_confirmation && autoResult.success && (
            <p className="mt-2 text-xs flex items-center gap-1.5" style={{ color: "#888" }}>
              <AlertTriangle className="w-3.5 h-3.5" style={{ color: "#f59e0b" }} />
              The browser is open — review the form, then click Submit to complete the application.
            </p>
          )}

          {autoResult.screenshot_b64 && (
            <div className="mt-4">
              <p className="text-xs mb-2" style={{ color: "#555" }}>Screenshot at time of form fill:</p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`data:image/png;base64,${autoResult.screenshot_b64}`}
                alt="Auto-apply screenshot"
                className="rounded-xl w-full object-cover"
                style={{ maxHeight: 400, objectPosition: "top", border: "1px solid #1e1e1e" }}
              />
            </div>
          )}
        </div>
      )}

      {/* AI Match Analysis */}
      {(job.match_reasons?.length > 0 || job.skills_matched?.length > 0 || job.skills_missing?.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          {job.match_reasons?.length > 0 && (
            <div className="rounded-3xl p-5" style={CARD}>
              <h3 className="font-semibold text-white mb-3 flex items-center gap-2 text-sm">
                <Star className="w-4 h-4" style={{ color: "#f59e0b" }} /> Why it matched
              </h3>
              <ul className="space-y-2">
                {job.match_reasons.map((r: string, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-sm" style={{ color: "#888" }}>
                    <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: "#4ade80" }} />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="rounded-3xl p-5 space-y-4" style={CARD}>
            {job.skills_matched?.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "#555" }}>Skills Matched</h3>
                <div className="flex flex-wrap gap-1.5">
                  {job.skills_matched.map((s: string) => (
                    <span key={s} className="text-xs px-2.5 py-1 rounded-full"
                      style={{ background: "rgba(34,197,94,0.08)", color: "#4ade80", border: "1px solid rgba(34,197,94,0.20)" }}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {job.skills_missing?.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "#555" }}>Skills Missing</h3>
                <div className="flex flex-wrap gap-1.5">
                  {job.skills_missing.map((s: string) => (
                    <span key={s} className="text-xs px-2.5 py-1 rounded-full"
                      style={{ background: "rgba(239,68,68,0.08)", color: "#f87171", border: "1px solid rgba(239,68,68,0.18)" }}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Description */}
      {job.description && (
        <div className="rounded-3xl p-6" style={CARD}>
          <h3 className="text-sm font-semibold text-white mb-4">Job Description</h3>
          <div className="text-sm whitespace-pre-wrap leading-relaxed" style={{ color: "#888" }}>
            {job.description}
          </div>
        </div>
      )}
    </div>
  );
}
