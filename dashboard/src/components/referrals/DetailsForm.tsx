"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  User, Briefcase, MessageSquareText, ShieldCheck, Radio, RotateCcw, Save, AlertTriangle, FileText,
} from "lucide-react";
import { getReferralProfile, updateReferralProfile, resetReferralProfileToResume } from "@/lib/api";
import {
  CARD, Field, TextInput, TextArea, TagInput, Toggle, SectionTitle, type FieldSource,
} from "./fields";

type Values = Record<string, unknown>;

const PLATFORM_OPTIONS = [
  { id: "reddit", label: "Reddit", emoji: "👽" },
  { id: "linkedin", label: "LinkedIn", emoji: "💼" },
  { id: "glassdoor", label: "Glassdoor Community", emoji: "🚪" },
];

const FIELD_LABELS: Record<string, string> = {
  full_name: "Full name", target_roles: "Target roles", location: "Location", skills: "Skills",
};

export default function DetailsForm() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["referral-profile"], queryFn: getReferralProfile });
  const [edits, setEdits] = useState<Values>({});

  const server = (data ?? {}) as {
    values?: Values; sources?: Record<string, FieldSource>; settings?: Values;
    missing_required?: string[]; has_resume?: boolean;
  };
  const merged: Values = { ...(server.values ?? {}), ...(server.settings ?? {}), ...edits };
  const src = (k: string): FieldSource | undefined => (k in edits ? "saved" : server.sources?.[k]);

  const str = (k: string) => (merged[k] == null ? "" : String(merged[k]));
  const list = (k: string) => (Array.isArray(merged[k]) ? (merged[k] as string[]) : []);
  const bool = (k: string) => Boolean(merged[k]);
  const set = (k: string, v: unknown) => setEdits((e) => ({ ...e, [k]: v }));

  const save = useMutation({
    mutationFn: () => {
      const payload: Values = { ...edits };
      if ("years_experience" in payload) {
        const n = parseInt(String(payload.years_experience), 10);
        payload.years_experience = Number.isFinite(n) ? n : null;
      }
      if ("max_posts_per_day" in payload) payload.max_posts_per_day = parseInt(String(payload.max_posts_per_day), 10) || 5;
      return updateReferralProfile(payload);
    },
    onSuccess: (res) => {
      qc.setQueryData(["referral-profile"], res);
      setEdits({});
      toast.success("Referral details saved");
    },
    onError: () => toast.error("Couldn't save your details"),
  });

  const reset = useMutation({
    mutationFn: resetReferralProfileToResume,
    onSuccess: (res) => {
      qc.setQueryData(["referral-profile"], res);
      setEdits({});
      toast.success("Using your resume and preferences again");
    },
  });

  if (isLoading) return <div className="text-center py-20 text-sm" style={{ color: "#555" }}>Loading…</div>;

  const dirty = Object.keys(edits).length > 0;
  const missing = server.missing_required ?? [];

  return (
    <div className="max-w-4xl space-y-4 pb-24">
      {/* Where values come from */}
      <div className="flex items-start gap-4 px-5 py-4 rounded-2xl"
        style={{ background: "rgba(59,130,246,0.05)", border: "1px solid rgba(59,130,246,0.18)" }}>
        <FileText className="w-5 h-5 shrink-0 mt-0.5" style={{ color: "#60a5fa" }} />
        <div className="text-xs leading-relaxed" style={{ color: "#888" }}>
          <p className="text-sm font-semibold mb-0.5" style={{ color: "#93c5fd" }}>These details go into your forum posts</p>
          {server.has_resume
            ? <>Empty fields are filled from your resume and job preferences (marked <span style={{ color: "#60a5fa" }}>From resume</span> /{" "}
              <span style={{ color: "#a78bfa" }}>From preferences</span>). Type in any field to override it.</>
            : <>No resume uploaded yet. Fill these in, or upload a resume in Settings and they&apos;ll fill themselves.</>}
        </div>
      </div>

      {missing.length > 0 && (
        <div className="flex items-start gap-3 px-5 py-3.5 rounded-2xl"
          style={{ background: "rgba(234,179,8,0.06)", border: "1px solid rgba(234,179,8,0.20)" }}>
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "#f59e0b" }} />
          <p className="text-xs" style={{ color: "#fbbf24" }}>
            Needed before the agent can write posts: {missing.map((m) => FIELD_LABELS[m] ?? m).join(", ")}
          </p>
        </div>
      )}

      {/* Personal */}
      <section className="rounded-3xl p-6" style={CARD}>
        <SectionTitle icon={<User className="w-4 h-4" />} title="Personal details" subtitle="How you introduce yourself" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Full name" source={src("full_name")} required>
            <TextInput value={str("full_name")} onChange={(v) => set("full_name", v)} placeholder="Jane Citizen" />
          </Field>
          <Field label="Headline" source={src("headline")} hint="One line, e.g. 'Cybersecurity grad, SOC / blue team'">
            <TextInput value={str("headline")} onChange={(v) => set("headline", v)} placeholder="What you do, in a few words" />
          </Field>
          <Field label="Location" source={src("location")} required>
            <TextInput value={str("location")} onChange={(v) => set("location", v)} placeholder="Melbourne, VIC" />
          </Field>
          <Field label="Email" source={src("email")}>
            <TextInput type="email" value={str("email")} onChange={(v) => set("email", v)} placeholder="you@example.com" />
          </Field>
          <Field label="Phone" source={src("phone")}>
            <TextInput value={str("phone")} onChange={(v) => set("phone", v)} placeholder="+61 …" />
          </Field>
          <Field label="LinkedIn" source={src("linkedin_url")}>
            <TextInput value={str("linkedin_url")} onChange={(v) => set("linkedin_url", v)} placeholder="https://linkedin.com/in/…" />
          </Field>
          <Field label="GitHub" source={src("github_url")}>
            <TextInput value={str("github_url")} onChange={(v) => set("github_url", v)} placeholder="https://github.com/…" />
          </Field>
          <Field label="Portfolio" source={src("portfolio_url")}>
            <TextInput value={str("portfolio_url")} onChange={(v) => set("portfolio_url", v)} placeholder="https://…" />
          </Field>
        </div>
      </section>

      {/* Career */}
      <section className="rounded-3xl p-6" style={CARD}>
        <SectionTitle icon={<Briefcase className="w-4 h-4" />} title="What you're looking for" subtitle="Used to find threads and tailor replies" />
        <div className="grid grid-cols-1 gap-4">
          <Field label="Target roles" source={src("target_roles")} required>
            <TagInput values={list("target_roles")} onChange={(v) => set("target_roles", v)} placeholder="SOC Analyst, Security Analyst…" />
          </Field>
          <Field label="Target companies" source={src("target_companies")} hint="Optional. The agent prioritises referral offers from these.">
            <TagInput values={list("target_companies")} onChange={(v) => set("target_companies", v)} placeholder="Atlassian, Telstra, ANZ…" />
          </Field>
          <Field label="Skills" source={src("skills")} required>
            <TagInput values={list("skills")} onChange={(v) => set("skills", v)} placeholder="SIEM, Splunk, Incident response…" />
          </Field>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Field label="Years of experience" source={src("years_experience")}>
              <TextInput type="number" value={str("years_experience")} onChange={(v) => set("years_experience", v)} placeholder="1" />
            </Field>
            <Field label="Work rights" source={src("work_rights")}>
              <TextInput value={str("work_rights")} onChange={(v) => set("work_rights", v)} placeholder="Full working rights" />
            </Field>
            <Field label="Availability" source={src("availability")}>
              <TextInput value={str("availability")} onChange={(v) => set("availability", v)} placeholder="Immediately" />
            </Field>
          </div>
        </div>
      </section>

      {/* Pitch */}
      <section className="rounded-3xl p-6" style={CARD}>
        <SectionTitle icon={<MessageSquareText className="w-4 h-4" />} title="Your pitch"
          subtitle="2-3 sentences in your own words. The agent keeps your voice and never invents experience." />
        <TextArea rows={4} value={str("pitch")} onChange={(v) => set("pitch", v)}
          placeholder="I'm finishing a Master of Cybersecurity and have hands-on SOC lab experience…" />
      </section>

      {/* Privacy */}
      <section className="rounded-3xl p-6" style={CARD}>
        <SectionTitle icon={<ShieldCheck className="w-4 h-4" />} title="What can appear in public posts"
          subtitle="Forum posts are public. Anything switched off is never written into a post." />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Toggle label="LinkedIn link" checked={bool("share_linkedin")} onChange={(v) => set("share_linkedin", v)} />
          <Toggle label="Email address" checked={bool("share_email")} onChange={(v) => set("share_email", v)} />
          <Toggle label="Phone number" checked={bool("share_phone")} onChange={(v) => set("share_phone", v)}
            description="Not recommended" />
        </div>
      </section>

      {/* Where */}
      <section className="rounded-3xl p-6" style={CARD}>
        <SectionTitle icon={<Radio className="w-4 h-4" />} title="Where the agent looks and posts" />
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {PLATFORM_OPTIONS.map((p) => {
              const on = list("platforms").includes(p.id);
              return (
                <button key={p.id} type="button"
                  onClick={() => set("platforms", on ? list("platforms").filter((x) => x !== p.id) : [...list("platforms"), p.id])}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition"
                  style={on
                    ? { background: "rgba(249,115,22,0.12)", color: "#fb923c", border: "1px solid rgba(249,115,22,0.35)" }
                    : { background: "#151515", color: "#666", border: "1px solid #222" }}
                  aria-pressed={on}>
                  <span>{p.emoji}</span>{p.label}
                </button>
              );
            })}
          </div>
          {list("platforms").includes("reddit") && (
            <Field label="Subreddits for your post" hint="Check each subreddit's rules first. r/forhire wants '[For Hire]' titles.">
              <TagInput values={list("subreddits")} onChange={(v) => set("subreddits", v)} placeholder="forhire, cscareerquestionsOCE…" />
            </Field>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Toggle label="Find threads on every search run" checked={bool("auto_discover")}
              onChange={(v) => set("auto_discover", v)} description="Drafts replies only. Nothing posts until you approve it." />
            <div className="px-4 py-3 rounded-2xl flex items-center justify-between gap-3" style={{ background: "#151515", border: "1px solid #222" }}>
              <div>
                <p className="text-sm font-semibold" style={{ color: "#ddd" }}>Max posts per day</p>
                <p className="text-[11px] mt-0.5" style={{ color: "#555" }}>Per platform. Keep it low to avoid spam flags.</p>
              </div>
              <input type="number" min={1} max={20} value={str("max_posts_per_day")}
                onChange={(e) => set("max_posts_per_day", e.target.value)}
                className="w-16 text-sm text-center rounded-lg px-2 py-1.5 outline-none"
                style={{ background: "#1a1a1a", border: "1px solid #2a2a2a", color: "#e0e0e0" }}
                aria-label="Max posts per day" />
            </div>
          </div>
        </div>
      </section>

      {/* Sticky save bar */}
      <div className="fixed bottom-6 right-6 left-[260px] flex justify-end pointer-events-none">
        <div className="flex items-center gap-2 p-2 rounded-2xl pointer-events-auto"
          style={{ background: "rgba(17,17,17,0.92)", border: "1px solid #262626", backdropFilter: "blur(8px)" }}>
          <button type="button" onClick={() => reset.mutate()} disabled={reset.isPending}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition"
            style={{ color: "#888" }}>
            <RotateCcw className="w-4 h-4" /> Use resume values
          </button>
          <button type="button" onClick={() => save.mutate()} disabled={!dirty || save.isPending}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold text-white transition disabled:opacity-40"
            style={{ background: "#f97316" }}>
            <Save className="w-4 h-4" /> {save.isPending ? "Saving…" : dirty ? "Save details" : "Saved"}
          </button>
        </div>
      </div>
    </div>
  );
}
