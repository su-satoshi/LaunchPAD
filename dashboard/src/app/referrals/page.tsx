"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getJobs, createDraftEmail, sendEmail } from "@/lib/api";
import { sourceIcon } from "@/lib/utils";
import ScoreBadge from "@/components/ScoreBadge";
import {
  Users, Send, X, Building2, MapPin,
  ExternalLink, ChevronRight, Search, RefreshCw, Briefcase,
  Mail, CheckCircle2,
} from "lucide-react";
import toast from "react-hot-toast";
import Link from "next/link";

const REFERRAL_SOURCES = ["linkedin", "glassdoor", "ambitionbox", "indeed"];
const CARD = { background: "#111111", border: "1px solid #1e1e1e" };
const INPUT_STYLE = { background: "#1a1a1a", border: "1px solid #2a2a2a", color: "#e0e0e0" };

interface DraftState {
  jobId: number;
  company: string;
  title: string;
  contactName: string;
  contactRole: string;
  subject: string;
  body: string;
  emailId?: number;
}

function ContactModal({
  draft, onClose, onSend,
}: {
  draft: DraftState;
  onClose: () => void;
  onSend: (emailId: number, overrides: { subject: string; body: string; to_address: string; to_name: string }) => void;
}) {
  const [subject, setSubject]     = useState(draft.subject);
  const [body, setBody]           = useState(draft.body);
  const [toAddress, setToAddress] = useState("");
  const [toName, setToName]       = useState(draft.contactName);
  const [sending, setSending]     = useState(false);

  const canSend = toAddress.trim().includes("@");

  const handleSend = async () => {
    if (!draft.emailId || !canSend) return;
    setSending(true);
    try {
      await onSend(draft.emailId, { subject, body, to_address: toAddress.trim(), to_name: toName });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4" aria-modal="true" role="dialog">
      <div className="absolute inset-0" style={{ background: "rgba(0,0,0,0.80)" }} onClick={onClose} />
      <div
        className="relative z-50 w-full max-w-2xl rounded-3xl p-6 flex flex-col gap-4"
        style={{ background: "#111", border: "1px solid #2a2a2a" }}
      >
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold text-white">Review Referral Request</h2>
            <p className="text-sm mt-0.5">
              <span style={{ color: "#f97316" }}>{draft.company}</span>
              {" · "}<span style={{ color: "#ccc" }}>{draft.title}</span>
            </p>
          </div>
          <button type="button" onClick={onClose}
            className="w-8 h-8 rounded-xl flex items-center justify-center transition"
            style={{ color: "#555" }}
            onMouseEnter={e => (e.currentTarget.style.color = "#fff")}
            onMouseLeave={e => (e.currentTarget.style.color = "#555")}
            aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Recipient fields */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[11px] font-bold uppercase tracking-wider block mb-1.5" style={{ color: "#555" }}>Recipient Name</label>
            <input
              className="w-full text-sm rounded-xl px-4 py-2.5 outline-none transition"
              style={INPUT_STYLE}
              value={toName}
              onChange={(e) => setToName(e.target.value)}
              placeholder="Hiring Manager"
              onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
              onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
            />
          </div>
          <div>
            <label className="text-[11px] font-bold uppercase tracking-wider block mb-1.5" style={{ color: "#555" }}>
              Recipient Email <span style={{ color: "#f87171" }}>*</span>
            </label>
            <input
              type="email"
              className="w-full text-sm rounded-xl px-4 py-2.5 outline-none transition"
              style={{
                ...INPUT_STYLE,
                borderColor: toAddress && !canSend ? "#ef4444" : "#2a2a2a",
              }}
              value={toAddress}
              onChange={(e) => setToAddress(e.target.value)}
              placeholder="recruiter@company.com"
              onFocus={e => (e.currentTarget.style.borderColor = toAddress && !canSend ? "#ef4444" : "#f97316")}
              onBlur={e => (e.currentTarget.style.borderColor = toAddress && !canSend ? "#ef4444" : "#2a2a2a")}
              required
            />
            {!toAddress && (
              <p className="text-[11px] mt-1" style={{ color: "#f59e0b" }}>Find the contact&apos;s email on LinkedIn or the company website</p>
            )}
          </div>
        </div>

        {/* Subject */}
        <div>
          <label className="text-[11px] font-bold uppercase tracking-wider block mb-1.5" style={{ color: "#555" }}>Subject</label>
          <input
            className="w-full text-sm rounded-xl px-4 py-2.5 outline-none transition"
            style={INPUT_STYLE}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
            onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
          />
        </div>

        {/* Body */}
        <div>
          <label className="text-[11px] font-bold uppercase tracking-wider block mb-1.5" style={{ color: "#555" }}>
            Message <span className="font-normal normal-case" style={{ color: "#444" }}>(edit before sending)</span>
          </label>
          <textarea
            rows={10}
            className="w-full text-sm rounded-xl px-4 py-3 outline-none transition resize-none font-mono"
            style={INPUT_STYLE}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
            onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
          />
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between pt-2">
          <Link href={`/jobs/${draft.jobId}`}
            className="text-xs flex items-center gap-1.5 transition"
            style={{ color: "#555" }}
            onMouseEnter={e => (e.currentTarget.style.color = "#f97316")}
            onMouseLeave={e => (e.currentTarget.style.color = "#555")}
          >
            <ExternalLink className="w-3.5 h-3.5" /> View job
          </Link>
          <div className="flex items-center gap-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2.5 rounded-xl text-sm font-semibold transition"
              style={{ color: "#666" }}
              onMouseEnter={e => (e.currentTarget.style.color = "#fff")}
              onMouseLeave={e => (e.currentTarget.style.color = "#666")}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSend}
              disabled={sending || !draft.emailId || !canSend}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold text-white disabled:opacity-50 transition"
              style={{ background: "#f97316" }}
              title={!canSend ? "Enter a valid recipient email address" : undefined}
              onMouseEnter={e => { if (!sending && canSend) e.currentTarget.style.background = "#ea6a0a"; }}
              onMouseLeave={e => (e.currentTarget.style.background = "#f97316")}
            >
              {sending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              {sending ? "Sending…" : "Send Email"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ReferralsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [drafting, setDrafting] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["referral-jobs", search],
    queryFn: () => getJobs({ search: search || undefined, limit: 60, page: 1 }),
  });

  const jobs = ((data?.jobs as Record<string, unknown>[]) || []).filter(
    (j) => REFERRAL_SOURCES.includes(String(j.source || "")) || Boolean(j.is_referral_post)
  );

  const draftMut = useMutation({
    mutationFn: (payload: { job_id: number; company: string; title: string; contact_name: string; contact_role?: string }) =>
      createDraftEmail({ job_id: payload.job_id, email_type: "referral_request", recipient_name: payload.contact_name }),
    onSuccess: (res, vars) => {
      const r = res as Record<string, unknown>;
      setDraft({
        jobId: vars.job_id, company: vars.company, title: vars.title,
        contactName: "Hiring Manager", contactRole: vars.contact_role ?? "",
        subject: String(r.subject ?? `Referral Request — ${vars.title} at ${vars.company}`),
        body: String(r.body ?? ""),
        emailId: Number(r.id),
      });
      setDrafting(null);
    },
    onError: () => { toast.error("Failed to draft email — check Claude API key"); setDrafting(null); },
  });

  const handleDraft = (job: Record<string, unknown>) => {
    const jobId = Number(job.id);
    setDrafting(jobId);
    draftMut.mutate({ job_id: jobId, company: String(job.company), title: String(job.title), contact_name: "the hiring team" });
  };

  const handleSend = async (emailId: number, overrides: { subject: string; body: string; to_address: string; to_name: string }) => {
    try {
      await sendEmail(emailId, overrides);
      toast.success("Referral request sent!");
      setDraft(null);
      qc.invalidateQueries({ queryKey: ["emails"] });
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail ? `Send failed: ${detail}` : "Send failed — check Gmail setup in Settings → API Usage");
    }
  };

  return (
    <div className="min-h-screen p-6 space-y-5" style={{ background: "#080808" }}>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Referrals</h1>
          <p className="text-xs mt-0.5 font-medium" style={{ color: "#666" }}>
            Find people at target companies and request a referral via email
          </p>
        </div>
        <Link
          href="/jobs"
          className="flex items-center gap-2 text-sm px-4 py-2 rounded-2xl transition"
          style={{ color: "#888", border: "1px solid #2a2a2a" }}
          onMouseEnter={e => { e.currentTarget.style.color = "#fff"; e.currentTarget.style.background = "#1a1a1a"; }}
          onMouseLeave={e => { e.currentTarget.style.color = "#888"; e.currentTarget.style.background = ""; }}
        >
          <Briefcase className="w-4 h-4" /> All Jobs
        </Link>
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-4 px-5 py-4 rounded-2xl"
        style={{ background: "rgba(249,115,22,0.06)", border: "1px solid rgba(249,115,22,0.18)" }}>
        <Users className="w-5 h-5 shrink-0 mt-0.5" style={{ color: "#f97316" }} />
        <div>
          <p className="text-sm font-semibold" style={{ color: "#fb923c" }}>How referrals work</p>
          <p className="text-xs mt-0.5 leading-relaxed" style={{ color: "#888" }}>
            Jobs below are sourced from LinkedIn, Glassdoor, AmbitionBox and similar platforms where employees are visible.
            Click <strong style={{ color: "#ccc" }}>Request Referral</strong> — Orion AI drafts a short, professional
            email which you review and send with one click.
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none" style={{ color: "#444" }} />
        <input
          className="w-full pl-10 pr-4 py-2.5 text-sm rounded-xl outline-none transition"
          style={{ ...INPUT_STYLE, paddingLeft: "40px" }}
          placeholder="Search company or title…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
          onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
        />
      </div>

      {/* Jobs grid */}
      {isLoading ? (
        <div className="text-center py-20 text-sm" style={{ color: "#555" }}>Loading…</div>
      ) : jobs.length === 0 ? (
        <div className="text-center py-20">
          <Users className="w-10 h-10 mx-auto mb-4" style={{ color: "#333" }} />
          <p className="text-sm font-semibold" style={{ color: "#555" }}>No referral-eligible jobs found</p>
          <p className="text-xs mt-1" style={{ color: "#444" }}>
            Run a search first — jobs from LinkedIn, Glassdoor and AmbitionBox will appear here.
          </p>
          <Link
            href="/"
            className="inline-flex items-center gap-2 mt-4 px-5 py-2.5 rounded-xl text-sm font-bold text-white transition"
            style={{ background: "#f97316" }}
          >
            <RefreshCw className="w-4 h-4" /> Run Search
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {jobs.map((job) => {
            const isDrafting = drafting === Number(job.id);
            return (
              <div
                key={String(job.id)}
                className="rounded-3xl p-5 flex flex-col gap-4 transition"
                style={CARD}
                onMouseEnter={e => (e.currentTarget.style.background = "#161616")}
                onMouseLeave={e => (e.currentTarget.style.background = "#111")}
              >
                {/* Job info */}
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl shrink-0"
                    style={{ background: "#1a1a1a", border: "1px solid #222" }}>
                    {sourceIcon(String(job.source || ""))}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-white truncate">{String(job.title)}</p>
                    <p className="text-xs font-semibold mt-0.5 flex items-center gap-1.5" style={{ color: "#888" }}>
                      <Building2 className="w-3 h-3 shrink-0" />
                      {String(job.company)}
                    </p>
                    {Boolean(job.location) && (
                      <p className="text-xs flex items-center gap-1 mt-0.5" style={{ color: "#555" }}>
                        <MapPin className="w-3 h-3 shrink-0" />
                        {String(job.location)}
                      </p>
                    )}
                  </div>
                  {job.match_score != null && <ScoreBadge score={Number(job.match_score)} />}
                </div>

                {/* Platform badge */}
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full capitalize"
                    style={{ color: "#555", border: "1px solid #2a2a2a" }}>
                    {String(job.source || "unknown")}
                  </span>
                  {Boolean(job.is_referral_post) && (
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full"
                      style={{ background: "rgba(234,179,8,0.08)", color: "#fbbf24", border: "1px solid rgba(234,179,8,0.20)" }}>
                      Referral post
                    </span>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 mt-auto pt-1">
                  <button
                    type="button"
                    onClick={() => handleDraft(job)}
                    disabled={isDrafting}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold text-white transition disabled:opacity-50"
                    style={{ background: "#f97316" }}
                    onMouseEnter={e => { if (!isDrafting) e.currentTarget.style.background = "#ea6a0a"; }}
                    onMouseLeave={e => (e.currentTarget.style.background = "#f97316")}
                  >
                    {isDrafting
                      ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Drafting…</>
                      : <><Mail className="w-3.5 h-3.5" /> Request Referral</>}
                  </button>
                  <Link href={`/jobs/${job.id}`}
                    className="w-10 h-10 flex items-center justify-center rounded-xl transition"
                    style={{ border: "1px solid #2a2a2a", color: "#555" }}
                    onMouseEnter={e => { e.currentTarget.style.color = "#f97316"; e.currentTarget.style.borderColor = "rgba(249,115,22,0.40)"; }}
                    onMouseLeave={e => { e.currentTarget.style.color = "#555"; e.currentTarget.style.borderColor = "#2a2a2a"; }}
                    aria-label="View job details">
                    <ChevronRight className="w-4 h-4" />
                  </Link>
                  {Boolean(job.url) && (
                    <a href={String(job.url)} target="_blank" rel="noopener noreferrer"
                      className="w-10 h-10 flex items-center justify-center rounded-xl transition"
                      style={{ border: "1px solid #2a2a2a", color: "#555" }}
                      onMouseEnter={e => { e.currentTarget.style.color = "#f97316"; e.currentTarget.style.borderColor = "rgba(249,115,22,0.40)"; }}
                      onMouseLeave={e => { e.currentTarget.style.color = "#555"; e.currentTarget.style.borderColor = "#2a2a2a"; }}
                      aria-label="Open job listing">
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Sent confirmations strip */}
      {jobs.length > 0 && (
        <div className="flex items-center gap-2 pt-2">
          <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "#4ade80" }} />
          <p className="text-xs font-medium" style={{ color: "#555" }}>
            Sent referral emails are saved in{" "}
            <Link href="/emails" className="transition underline underline-offset-2"
              style={{ color: "#f97316" }}
              onMouseEnter={e => (e.currentTarget.style.color = "#fb923c")}
              onMouseLeave={e => (e.currentTarget.style.color = "#f97316")}
            >Emails</Link>{" "}for follow-up.
          </p>
        </div>
      )}

      {/* Review modal */}
      {draft && (
        <ContactModal draft={draft} onClose={() => setDraft(null)} onSend={handleSend} />
      )}
    </div>
  );
}
