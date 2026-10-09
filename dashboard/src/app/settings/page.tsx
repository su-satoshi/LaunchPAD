"use client";
import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getProfile, updateProfile, getPreferences, updatePreferences, uploadResume, getApiStatus,
} from "@/lib/api";
import {
  Upload, Check, X, FileText, Zap, Briefcase,
  User, AtSign, Phone, MapPin, Link2, Code2, Globe,
  Activity, Mail, Database, AlertTriangle, CheckCircle2, XCircle,
  ExternalLink,
} from "lucide-react";
import toast from "react-hot-toast";

const CARD = { background: "#111111", border: "1px solid #1e1e1e" };
const INPUT_STYLE = { background: "#1a1a1a", border: "1px solid #2a2a2a", color: "#e0e0e0" };

/* ── Tag Input ── */
function TagInput({ values, onChange, placeholder }: {
  values: string[]; onChange: (v: string[]) => void; placeholder?: string;
}) {
  const [input, setInput] = useState("");
  const add = () => {
    const v = input.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setInput("");
  };
  return (
    <div
      className="flex flex-wrap gap-1.5 rounded-xl p-2.5 min-h-11 transition"
      style={{ background: "#1a1a1a", border: "1px solid #2a2a2a" }}
    >
      {values.map((v) => (
        <span key={v} className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg font-medium"
          style={{ background: "rgba(249,115,22,0.10)", color: "#fb923c", border: "1px solid rgba(249,115,22,0.22)" }}>
          {v}
          <button type="button" onClick={() => onChange(values.filter((x) => x !== v))} className="ml-0.5 opacity-60 hover:opacity-100 transition">
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      <input
        className="text-sm outline-none flex-1 min-w-28 bg-transparent font-medium"
        style={{ color: "#e0e0e0" }}
        placeholder={values.length === 0 ? placeholder : ""}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }}
      />
    </div>
  );
}

/* ── Text Input ── */
function TextInput({ value, onChange, placeholder, type = "text" }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string;
}) {
  return (
    <input
      type={type}
      className="w-full text-sm rounded-xl px-4 py-2.5 outline-none transition font-medium"
      style={INPUT_STYLE}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
      onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
    />
  );
}

/* ── Number Input ── */
function NumberInput({ value, onChange, step, min, max, placeholder }: {
  value: string; onChange: (v: string) => void;
  step?: string; min?: string; max?: string; placeholder?: string;
}) {
  return (
    <input
      type="number"
      step={step} min={min} max={max}
      className="w-full text-sm rounded-xl px-4 py-2.5 outline-none transition font-medium"
      style={INPUT_STYLE}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
      onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
    />
  );
}

/* ── Field ── */
function Field({ label, icon: Icon, children }: {
  label: string; icon: React.ElementType; children: React.ReactNode;
}) {
  return (
    <div>
      <label className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider mb-1.5" style={{ color: "#555" }}>
        <Icon className="w-3 h-3" /> {label}
      </label>
      {children}
    </div>
  );
}

/* ── Save button ── */
function SaveBtn({ onClick, pending, dirty, label }: {
  onClick: () => void; pending: boolean; dirty: boolean; label: string;
}) {
  const [justSaved, setJustSaved] = useState(false);
  const prevPending = useRef(pending);
  useEffect(() => {
    if (prevPending.current && !pending && !dirty) {
      setJustSaved(true);
      const t = setTimeout(() => setJustSaved(false), 2500);
      return () => clearTimeout(t);
    }
    prevPending.current = pending;
  }, [pending, dirty]);

  if (justSaved) {
    return (
      <div className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold"
        style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.20)", color: "#4ade80" }}>
        <CheckCircle2 className="w-4 h-4" /> Saved
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={pending || !dirty}
      className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold text-white transition disabled:opacity-40"
      style={{ background: "#f97316" }}
      onMouseEnter={e => { if (!pending && dirty) e.currentTarget.style.background = "#ea6a0a"; }}
      onMouseLeave={e => (e.currentTarget.style.background = "#f97316")}
    >
      <Check className="w-4 h-4" />
      {pending ? "Saving…" : label}
    </button>
  );
}

function CostBreakdown({ cb }: { cb: Record<string, { count: number; tokens_each: number; cost_usd: number }> }) {
  return (
    <div className="mt-4 pt-4 space-y-2" style={{ borderTop: "1px solid #1e1e1e" }}>
      <p className="text-[11px] font-bold uppercase tracking-wider" style={{ color: "#555" }}>Cost Breakdown</p>
      {Object.entries(cb).map(([key, val]) => (
        <div key={key} className="flex items-center justify-between py-1.5 px-3 rounded-xl" style={{ background: "#1a1a1a", border: "1px solid #222" }}>
          <div>
            <p className="text-xs font-semibold text-white capitalize">{key.replace(/_/g, " ")}</p>
            <p className="text-[11px]" style={{ color: "#555" }}>{val.count} × {val.tokens_each.toLocaleString()} tokens</p>
          </div>
          <p className="text-sm font-bold" style={{ color: "#c084fc" }}>${val.cost_usd.toFixed(4)}</p>
        </div>
      ))}
    </div>
  );
}

function GmailConnectButton() {
  const [loading, setLoading] = useState(false);
  const handleConnect = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/settings/gmail/authorize-url");
      const data = await res.json();
      if (data.auth_url) {
        window.open(data.auth_url, "_blank", "width=600,height=700,noopener");
      } else {
        alert(data.detail || "Could not get auth URL — check credentials.json");
      }
    } catch {
      alert("Failed to contact backend — is the server running?");
    } finally {
      setLoading(false);
    }
  };
  return (
    <button
      type="button"
      onClick={handleConnect}
      disabled={loading}
      className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold text-white disabled:opacity-50 transition"
      style={{ background: "#dc2626" }}
      onMouseEnter={e => (e.currentTarget.style.background = "#b91c1c")}
      onMouseLeave={e => (e.currentTarget.style.background = "#dc2626")}
    >
      <Mail className="w-4 h-4" />
      {loading ? "Opening…" : "Connect Gmail"}
      <ExternalLink className="w-3.5 h-3.5 opacity-60" />
    </button>
  );
}

function getInitials(name: string): string {
  if (!name) return "?";
  return name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2);
}

const ALL_SOURCES = [
  { id: "linkedin",      label: "LinkedIn",          emoji: "💼" },
  { id: "indeed",        label: "Indeed",             emoji: "🔍" },
  { id: "glassdoor",     label: "Glassdoor",          emoji: "🚪" },
  { id: "seek",          label: "Seek",               emoji: "🦘" },
  { id: "web3careers",   label: "Web3.Careers",       emoji: "⛓️" },
  { id: "prosple",       label: "Prosple",            emoji: "🎓" },
  { id: "ambitionbox",   label: "AmbitionBox",        emoji: "📦" },
  { id: "top_companies", label: "Top 100 Companies",  emoji: "🏆" },
  { id: "ziprecruiter",  label: "ZipRecruiter",       emoji: "📋" },
  { id: "google",        label: "Google Jobs",        emoji: "🔷" },
  { id: "firecrawl",     label: "Firecrawl (web)",    emoji: "🔥" },
  { id: "agent_browser", label: "Agent Browser",      emoji: "🧭" },
];

type Tab = "profile" | "search" | "automation" | "api";

export default function SettingsPage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [activeTab, setActiveTab] = useState<Tab>("profile");

  const { data: profileData = {} } = useQuery({ queryKey: ["profile"], queryFn: getProfile });
  const { data: prefsData = {} }   = useQuery({ queryKey: ["preferences"], queryFn: getPreferences });

  const [pfEdits, setPfEdits] = useState<Record<string, unknown>>({});
  const [prEdits, setPrEdits] = useState<Record<string, unknown>>({});

  const pf = { ...(profileData as Record<string, unknown>), ...pfEdits };
  const pr = { ...(prefsData  as Record<string, unknown>), ...prEdits };

  const setPf = (k: string, v: unknown) => setPfEdits((e) => ({ ...e, [k]: v }));
  const setPr = (k: string, v: unknown) => setPrEdits((e) => ({ ...e, [k]: v }));

  const toggleSource = (id: string) => {
    const cur: string[] = Array.isArray(pr.sources) ? pr.sources as string[] : [];
    setPr("sources", cur.includes(id) ? cur.filter((s) => s !== id) : [...cur, id]);
  };

  const saveProfile = useMutation({
    mutationFn: () => updateProfile(pfEdits),
    onSuccess: () => { toast.success("Profile saved!"); qc.invalidateQueries({ queryKey: ["profile"] }); setPfEdits({}); },
    onError: () => toast.error("Failed to save profile"),
  });

  const savePrefs = useMutation({
    mutationFn: () => updatePreferences(prEdits),
    onSuccess: () => { toast.success("Preferences saved!"); qc.invalidateQueries({ queryKey: ["preferences"] }); setPrEdits({}); },
    onError: () => toast.error("Failed to save preferences"),
  });

  const uploadMut = useMutation({
    mutationFn: uploadResume,
    onSuccess: (res) => {
      toast.success(`Resume parsed: ${(res as Record<string, Record<string, string>>).parsed?.name || "done"}`);
      qc.invalidateQueries({ queryKey: ["profile"] });
      if (fileRef.current) fileRef.current.value = "";
    },
    onError: () => { toast.error("Upload failed — use a valid PDF or TXT file"); if (fileRef.current) fileRef.current.value = ""; },
  });

  const { data: apiStatus } = useQuery({
    queryKey: ["api-status"],
    queryFn: getApiStatus,
    refetchInterval: 60_000,
  });
  const api = apiStatus as Record<string, Record<string, unknown>> | undefined;

  const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
    { id: "profile",    label: "Profile",    icon: User },
    { id: "search",     label: "Job Search", icon: Briefcase },
    { id: "automation", label: "Automation", icon: Zap },
    { id: "api",        label: "API Usage",  icon: Activity },
  ];

  const sectionLabel = (text: string) => (
    <p className="text-[11px] font-bold uppercase tracking-wider mb-4" style={{ color: "#555" }}>{text}</p>
  );

  const fieldLabel = (text: string) => (
    <p className="text-[11px] font-bold uppercase tracking-wider block mb-1.5" style={{ color: "#555" }}>{text}</p>
  );

  const selectStyle = { ...INPUT_STYLE, width: "100%", borderRadius: "10px", padding: "10px 16px", fontSize: "14px", outline: "none", fontFamily: "inherit" };

  return (
    <div className="min-h-screen p-6 space-y-6" style={{ background: "#080808" }}>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Settings</h1>
        <p className="text-xs mt-0.5 font-medium" style={{ color: "#555" }}>Manage profile, preferences &amp; automation</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-0.5" style={{ borderBottom: "1px solid #1e1e1e" }}>
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
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

      {/* ══ PROFILE TAB ══ */}
      {activeTab === "profile" && (
        <div className="max-w-3xl space-y-4">
          <div className="rounded-3xl p-6" style={CARD}>

            {/* Avatar + name */}
            <div className="flex items-center gap-5 mb-6">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-xl font-bold text-white shrink-0"
                style={{ background: "#f97316" }}>
                {getInitials(String(pf.name || ""))}
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">{String(pf.name || "Your Name")}</h2>
                <p className="text-sm font-medium" style={{ color: "#666" }}>{String(pf.location || "No location set")}</p>
                {Boolean(pf.has_resume) && (
                  <span className="inline-flex items-center gap-1 mt-1.5 text-[11px] px-2.5 py-0.5 rounded-full font-semibold"
                    style={{ background: "rgba(34,197,94,0.08)", color: "#4ade80", border: "1px solid rgba(34,197,94,0.20)" }}>
                    <Check className="w-3 h-3" /> Resume uploaded
                  </span>
                )}
              </div>
            </div>

            {/* Resume upload */}
            <input ref={fileRef} type="file" accept=".pdf,.txt,.doc,.docx" className="hidden"
              onChange={(e) => e.target.files?.[0] && uploadMut.mutate(e.target.files[0])} />
            <div
              role="button" tabIndex={0}
              onClick={() => fileRef.current?.click()}
              onKeyDown={(e) => e.key === "Enter" && fileRef.current?.click()}
              className="mb-6 rounded-2xl p-5 text-center cursor-pointer transition"
              style={{ border: "1px dashed #2a2a2a" }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(249,115,22,0.4)"; e.currentTarget.style.background = "rgba(249,115,22,0.04)"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "#2a2a2a"; e.currentTarget.style.background = ""; }}
            >
              {uploadMut.isPending ? (
                <p className="text-sm font-semibold" style={{ color: "#f97316" }}>Uploading &amp; parsing with AI…</p>
              ) : Boolean(pf.has_resume) ? (
                <div className="flex items-center justify-center gap-3">
                  <FileText className="w-5 h-5" style={{ color: "#4ade80" }} />
                  <div className="text-left">
                    <p className="text-sm font-semibold text-white">{String(pf.resume_filename || "Resume uploaded")}</p>
                    <p className="text-xs" style={{ color: "#555" }}>Click to replace</p>
                  </div>
                </div>
              ) : (
                <>
                  <Upload className="w-6 h-6 mx-auto mb-2" style={{ color: "#444" }} />
                  <p className="text-sm font-medium" style={{ color: "#666" }}>Click to upload resume</p>
                  <p className="text-xs mt-1" style={{ color: "#444" }}>PDF or TXT · Claude AI auto-fills your profile</p>
                </>
              )}
            </div>

            {/* Fields grid */}
            <div className="grid grid-cols-2 gap-4 mb-4">
              <Field label="Full Name" icon={User}>
                <TextInput value={String(pf.name || "")} onChange={(v) => setPf("name", v)} placeholder="Jane Smith" />
              </Field>
              <Field label="Email" icon={AtSign}>
                <TextInput value={String(pf.email || "")} onChange={(v) => setPf("email", v)} placeholder="you@email.com" type="email" />
              </Field>
              <Field label="Phone" icon={Phone}>
                <TextInput value={String(pf.phone || "")} onChange={(v) => setPf("phone", v)} placeholder="+61 400 000 000" />
              </Field>
              <Field label="Location" icon={MapPin}>
                <TextInput value={String(pf.location || "")} onChange={(v) => setPf("location", v)} placeholder="Sydney, NSW" />
              </Field>
              <Field label="LinkedIn" icon={Link2}>
                <TextInput value={String(pf.linkedin_url || "")} onChange={(v) => setPf("linkedin_url", v)} placeholder="linkedin.com/in/you" />
              </Field>
              <Field label="GitHub" icon={Code2}>
                <TextInput value={String(pf.github_url || "")} onChange={(v) => setPf("github_url", v)} placeholder="github.com/you" />
              </Field>
              <div className="col-span-2">
                <Field label="Portfolio / Website" icon={Globe}>
                  <TextInput value={String(pf.portfolio_url || "")} onChange={(v) => setPf("portfolio_url", v)} placeholder="yoursite.com" />
                </Field>
              </div>

              {/* Visa & Work Rights */}
              <Field label="Visa Status" icon={User}>
                <div className="space-y-1.5">
                  <select style={selectStyle}
                    value={String(pf.visa_status || "")}
                    onChange={(e) => setPf("visa_status", e.target.value)}
                    onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
                    onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
                  >
                    <option value="">Select visa status</option>
                    <option value="Australian Citizen">Australian Citizen</option>
                    <option value="Australian PR">Australian Permanent Resident</option>
                    <option value="Student Visa">Student Visa (subclass 500)</option>
                    <option value="Graduate Visa">Graduate Visa (subclass 485)</option>
                    <option value="Temporary Skilled">Temporary Skilled (subclass 482)</option>
                    <option value="Working Holiday">Working Holiday</option>
                    <option value="NZ Citizen">NZ Citizen (subclass 444)</option>
                    <option value="Other">Other</option>
                  </select>
                  {Boolean((profileData as Record<string,unknown>).visa_status) && !pfEdits.visa_status && (
                    <div className="flex items-center gap-1.5 text-[10px] font-semibold px-2" style={{ color: "#4ade80" }}>
                      <CheckCircle2 className="w-3 h-3" />
                      Saved: {String((profileData as Record<string,unknown>).visa_status)}
                    </div>
                  )}
                </div>
              </Field>
              <Field label="Work Rights" icon={Briefcase}>
                <div className="space-y-1.5">
                  <select style={selectStyle}
                    value={String(pf.work_rights || "")}
                    onChange={(e) => setPf("work_rights", e.target.value)}
                    onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
                    onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
                  >
                    <option value="">Select work rights</option>
                    <option value="Full working rights">Full working rights</option>
                    <option value="Limited hours (20h/week)">Limited hours (20h/week — student visa)</option>
                    <option value="Requires sponsorship">Requires employer sponsorship</option>
                    <option value="No restrictions">No restrictions</option>
                  </select>
                  {Boolean((profileData as Record<string,unknown>).work_rights) && !pfEdits.work_rights && (
                    <div className="flex items-center gap-1.5 text-[10px] font-semibold px-2" style={{ color: "#4ade80" }}>
                      <CheckCircle2 className="w-3 h-3" />
                      Saved: {String((profileData as Record<string,unknown>).work_rights)}
                    </div>
                  )}
                </div>
              </Field>
            </div>

            <div className="mb-4">
              <label className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider mb-1.5" style={{ color: "#555" }}>
                <Code2 className="w-3 h-3" /> Skills
              </label>
              <TagInput
                values={Array.isArray(pf.skills) ? pf.skills as string[] : []}
                onChange={(v) => setPf("skills", v)}
                placeholder="Python, React, AWS — press Enter"
              />
            </div>

            <div className="flex items-center gap-3">
              <SaveBtn onClick={() => saveProfile.mutate()} pending={saveProfile.isPending} dirty={Object.keys(pfEdits).length > 0} label="Save Profile" />
              {Object.keys(pfEdits).length > 0 && (
                <span className="text-xs font-medium" style={{ color: "#555" }}>{Object.keys(pfEdits).length} unsaved change{Object.keys(pfEdits).length > 1 ? "s" : ""}</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ══ JOB SEARCH TAB ══ */}
      {activeTab === "search" && (
        <div className="max-w-3xl space-y-4">
          <div className="rounded-3xl p-6 space-y-5" style={CARD}>
            {sectionLabel("Search Criteria")}
            {[
              { key: "job_titles",       label: "Job Titles",         placeholder: "Software Engineer, Backend Developer…" },
              { key: "keywords",         label: "Keywords to match",  placeholder: "Python, TypeScript, FastAPI…" },
              { key: "exclude_keywords", label: "Exclude keywords",   placeholder: "10+ years, C++, Embedded…" },
              { key: "locations",        label: "Locations",          placeholder: "Sydney, Melbourne, Remote…" },
            ].map(({ key, label, placeholder }) => (
              <div key={key}>
                {fieldLabel(label)}
                <TagInput
                  values={Array.isArray(pr[key]) ? pr[key] as string[] : []}
                  onChange={(v) => setPr(key, v)}
                  placeholder={placeholder}
                />
              </div>
            ))}
            <div className="grid grid-cols-2 gap-4">
              <div>
                {fieldLabel("Min Salary (AUD)")}
                <NumberInput value={String(pr.min_salary || "")} onChange={(v) => setPr("min_salary", Number(v) || null)} placeholder="80000" />
              </div>
              <div>
                {fieldLabel("Max Salary (AUD)")}
                <NumberInput value={String(pr.max_salary || "")} onChange={(v) => setPr("max_salary", Number(v) || null)} placeholder="150000" />
              </div>
            </div>
            <label className="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" className="w-4 h-4 accent-orange-600 rounded"
                checked={Boolean(pr.remote_only)} onChange={(e) => setPr("remote_only", e.target.checked)} />
              <span className="text-sm font-semibold text-white">Remote only</span>
            </label>
          </div>

          {/* Experience Levels */}
          <div className="rounded-3xl p-6" style={CARD}>
            {sectionLabel("Experience Level")}
            <div className="grid grid-cols-3 gap-2">
              {[
                { id: "intern", label: "Intern", emoji: "🎓" },
                { id: "entry",  label: "Entry Level", emoji: "🌱" },
                { id: "mid",    label: "Mid Level", emoji: "⚡" },
                { id: "senior", label: "Senior", emoji: "🚀" },
                { id: "lead",   label: "Lead / Staff", emoji: "🎯" },
                { id: "manager",label: "Manager", emoji: "👔" },
              ].map(({ id, label, emoji }) => {
                const levels: string[] = Array.isArray(pr.experience_levels) ? pr.experience_levels as string[] : [];
                const selected = levels.includes(id);
                return (
                  <button
                    key={id} type="button"
                    onClick={() => setPr("experience_levels", selected ? levels.filter((l) => l !== id) : [...levels, id])}
                    className="flex items-center gap-2 p-3 rounded-xl text-sm text-left font-semibold transition"
                    style={selected
                      ? { background: "rgba(249,115,22,0.10)", border: "1px solid rgba(249,115,22,0.25)", color: "#fb923c" }
                      : { background: "#1a1a1a", border: "1px solid #222", color: "#555" }}
                  >
                    <span>{emoji}</span>
                    <span className="flex-1 text-xs">{label}</span>
                    {selected && <Check className="w-3 h-3 shrink-0" style={{ color: "#f97316" }} />}
                  </button>
                );
              })}
            </div>
            <p className="text-[11px] mt-3" style={{ color: "#444" }}>Select the seniority levels you&apos;re targeting. Claude will score jobs accordingly.</p>
          </div>

          {/* Sources */}
          <div className="rounded-3xl p-6" style={CARD}>
            {sectionLabel("Job Sources")}
            <div className="grid grid-cols-2 gap-2">
              {ALL_SOURCES.map(({ id, label, emoji }) => {
                const selected = (Array.isArray(pr.sources) ? pr.sources as string[] : []).includes(id);
                return (
                  <button
                    key={id} type="button"
                    onClick={() => toggleSource(id)}
                    className="flex items-center gap-2.5 p-3 rounded-xl text-sm text-left font-semibold transition"
                    style={selected
                      ? { background: "rgba(249,115,22,0.10)", border: "1px solid rgba(249,115,22,0.25)", color: "#fb923c" }
                      : { background: "#1a1a1a", border: "1px solid #222", color: "#666" }}
                  >
                    <span className="text-base">{emoji}</span>
                    <span className="flex-1">{label}</span>
                    {selected && <Check className="w-3.5 h-3.5" style={{ color: "#f97316" }} />}
                  </button>
                );
              })}
            </div>
          </div>

          <SaveBtn onClick={() => savePrefs.mutate()} pending={savePrefs.isPending} dirty={Object.keys(prEdits).length > 0} label="Save Preferences" />
        </div>
      )}

      {/* ══ AUTOMATION TAB ══ */}
      {activeTab === "automation" && (
        <div className="max-w-3xl space-y-4">
          <div className="rounded-3xl p-6 space-y-6" style={CARD}>
            {sectionLabel("Automation Rules")}
            <div className="grid grid-cols-2 gap-5">
              <div>
                {fieldLabel("Min match score (0–1)")}
                <NumberInput step="0.05" min="0" max="1"
                  value={String(pr.min_match_score ?? 0.6)}
                  onChange={(v) => setPr("min_match_score", Number(v))} />
                <p className="text-[11px] mt-1.5" style={{ color: "#444" }}>Jobs below this score are skipped</p>
              </div>
              <div>
                {fieldLabel("Auto-send if score ≥")}
                <NumberInput step="0.05" min="0" max="1"
                  value={String(pr.auto_send_above_score ?? 0.85)}
                  onChange={(v) => setPr("auto_send_above_score", Number(v))} />
                <p className="text-[11px] mt-1.5" style={{ color: "#444" }}>Set to 1.0 to always review manually</p>
              </div>
              <div>
                {fieldLabel("Max applications / day")}
                <NumberInput min="1" max="50"
                  value={String(pr.max_applications_per_day ?? 10)}
                  onChange={(v) => setPr("max_applications_per_day", Number(v))} />
              </div>
              <div>
                {fieldLabel("Search frequency")}
                <select
                  style={selectStyle}
                  value={String(pr.search_frequency_hours ?? 6)}
                  onChange={(e) => setPr("search_frequency_hours", Number(e.target.value))}
                  onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
                  onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
                >
                  {[1, 2, 4, 6, 12, 24].map((h) => (
                    <option key={h} value={h}>Every {h} hour{h > 1 ? "s" : ""}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="pt-4" style={{ borderTop: "1px solid #1e1e1e" }}>
              <label className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" className="w-4 h-4 accent-orange-600 rounded"
                  checked={Boolean(pr.active ?? true)} onChange={(e) => setPr("active", e.target.checked)} />
                <div>
                  <p className="text-sm font-bold text-white">Agent active</p>
                  <p className="text-xs" style={{ color: "#555" }}>Run searches and process jobs automatically</p>
                </div>
              </label>
            </div>
          </div>

          <SaveBtn onClick={() => savePrefs.mutate()} pending={savePrefs.isPending} dirty={Object.keys(prEdits).length > 0} label="Save Automation" />
        </div>
      )}

      {/* ══ API USAGE TAB ══ */}
      {activeTab === "api" && (
        <div className="max-w-3xl space-y-4">

          {/* Claude AI */}
          <div className="rounded-3xl p-6" style={CARD}>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                style={{ background: "rgba(168,85,247,0.10)", border: "1px solid rgba(168,85,247,0.22)" }}>
                <Activity className="w-4 h-4" style={{ color: "#c084fc" }} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-bold text-white">Claude AI (Anthropic)</p>
                <p className="text-xs" style={{ color: "#666" }}>{String(api?.claude?.model ?? "claude-sonnet-4-6")}</p>
              </div>
              {api?.claude?.status === "connected" ? (
                <span className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full"
                  style={{ background: "rgba(34,197,94,0.08)", color: "#4ade80", border: "1px solid rgba(34,197,94,0.20)" }}>
                  <CheckCircle2 className="w-3.5 h-3.5" /> Connected
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full"
                  style={{ background: "rgba(239,68,68,0.08)", color: "#f87171", border: "1px solid rgba(239,68,68,0.18)" }}>
                  <XCircle className="w-3.5 h-3.5" /> Not configured
                </span>
              )}
            </div>

            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                { label: "Est. Tokens Used", value: api ? Number(api.claude?.est_tokens ?? 0).toLocaleString() : "—", color: "#e0e0e0" },
                { label: "Est. Cost (USD)",  value: api ? `$${Number(api.claude?.est_cost_usd ?? 0).toFixed(4)}` : "—", color: "#c084fc" },
                { label: "Jobs Processed",   value: api ? Number(api.database?.total_jobs ?? 0) : "—", color: "#e0e0e0" },
              ].map(({ label, value, color }) => (
                <div key={label} className="rounded-2xl p-4 text-center" style={{ background: "#1a1a1a", border: "1px solid #222" }}>
                  <p className="text-2xl font-bold" style={{ color }}>{value}</p>
                  <p className="text-[11px] font-medium mt-0.5" style={{ color: "#555" }}>{label}</p>
                </div>
              ))}
            </div>

            {api?.claude?.status !== "connected" && (
              <div className="flex items-start gap-3 px-4 py-3 rounded-2xl"
                style={{ background: "rgba(234,179,8,0.06)", border: "1px solid rgba(234,179,8,0.18)" }}>
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "#f59e0b" }} />
                <div>
                  <p className="text-xs font-bold" style={{ color: "#fbbf24" }}>ANTHROPIC_API_KEY not set</p>
                  <p className="text-xs mt-0.5" style={{ color: "#92400e" }}>Add your API key to the <code className="font-mono">.env</code> file. Get one at <span style={{ color: "#f59e0b" }}>console.anthropic.com</span></p>
                </div>
              </div>
            )}

            {Boolean(api?.claude?.cost_breakdown) && (
              <CostBreakdown cb={(api?.claude?.cost_breakdown ?? {}) as Record<string, { count: number; tokens_each: number; cost_usd: number }>} />
            )}
            <p className="text-[10px] mt-3 font-medium" style={{ color: "#444" }}>
              Estimates: 1,200 tokens/job score · 900 tokens/email · Sonnet pricing ($3/$15/M tokens).
              Check exact usage at <span style={{ color: "#666" }}>console.anthropic.com</span>
            </p>
          </div>

          {/* Gmail */}
          <div className="rounded-3xl p-6" style={CARD}>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.18)" }}>
                <Mail className="w-4 h-4" style={{ color: "#f87171" }} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-bold text-white">Gmail</p>
                <p className="text-xs" style={{ color: "#666" }}>{String(api?.gmail?.from_address || "Not configured")}</p>
              </div>
              {api?.gmail?.status === "connected" ? (
                <span className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full"
                  style={{ background: "rgba(34,197,94,0.08)", color: "#4ade80", border: "1px solid rgba(34,197,94,0.20)" }}>
                  <CheckCircle2 className="w-3.5 h-3.5" /> Connected
                </span>
              ) : api?.gmail?.status === "needs_auth" ? (
                <span className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full"
                  style={{ background: "rgba(234,179,8,0.08)", color: "#fbbf24", border: "1px solid rgba(234,179,8,0.20)" }}>
                  <AlertTriangle className="w-3.5 h-3.5" /> Needs Auth
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full"
                  style={{ background: "rgba(239,68,68,0.08)", color: "#f87171", border: "1px solid rgba(239,68,68,0.18)" }}>
                  <XCircle className="w-3.5 h-3.5" /> Not configured
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 mb-4">
              {[
                { label: "Emails Sent",    value: api ? Number(api.gmail?.emails_sent ?? 0) : "—" },
                { label: "Drafts Created", value: api ? Number(api.gmail?.emails_drafted ?? 0) : "—" },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-2xl p-4 text-center" style={{ background: "#1a1a1a", border: "1px solid #222" }}>
                  <p className="text-2xl font-bold text-white">{value}</p>
                  <p className="text-[11px] font-medium mt-0.5" style={{ color: "#555" }}>{label}</p>
                </div>
              ))}
            </div>

            {api?.gmail?.status !== "connected" && (
              <div className="space-y-3">
                <div className="flex items-start gap-3 px-4 py-3 rounded-2xl"
                  style={{ background: "rgba(234,179,8,0.06)", border: "1px solid rgba(234,179,8,0.18)" }}>
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "#f59e0b" }} />
                  <div className="space-y-1">
                    <p className="text-xs font-bold" style={{ color: "#fbbf24" }}>Gmail not connected</p>
                    <p className="text-xs" style={{ color: "#92400e" }}>To connect Gmail:</p>
                    <ol className="text-xs list-decimal list-inside space-y-0.5" style={{ color: "#92400e" }}>
                      <li>Go to Google Cloud Console → APIs &amp; Services → Credentials</li>
                      <li>Download your OAuth 2.0 client JSON as <code className="font-mono">gmail_credentials.json</code></li>
                      <li>Place it in the project root directory</li>
                      <li>Add your Gmail address to <code className="font-mono">GMAIL_FROM_ADDRESS</code> in <code className="font-mono">.env</code></li>
                      <li>Click <strong>Connect Gmail</strong> below to authorize</li>
                    </ol>
                  </div>
                </div>
                {api?.gmail?.status === "needs_auth" && <GmailConnectButton />}
              </div>
            )}
          </div>

          {/* Agent stack: self-hosted Firecrawl + Stagehand */}
          <div className="rounded-3xl p-6" style={CARD}>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                style={{ background: "rgba(249,115,22,0.10)", border: "1px solid rgba(249,115,22,0.22)" }}>
                <Globe className="w-4 h-4" style={{ color: "#f97316" }} />
              </div>
              <div>
                <p className="text-sm font-bold text-white">Agent stack</p>
                <p className="text-xs" style={{ color: "#666" }}>Self-hosted Firecrawl + Stagehand browser agent · no extra API keys</p>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                {
                  name: "Firecrawl",
                  detail: String(api?.firecrawl?.url ?? "http://localhost:3002"),
                  ok: api?.firecrawl?.status === "connected",
                  bad: "Not running - run `docker compose up -d`",
                },
                {
                  name: "Stagehand browser agent",
                  detail: `${String(api?.browser_agent?.model ?? "anthropic/claude-sonnet-4-6")} · uses your Chrome`,
                  ok: Boolean(api?.browser_agent?.stagehand_installed),
                  bad: "Not installed - run `pip install -r agent/requirements.txt`",
                },
              ].map(({ name, detail, ok, bad }) => (
                <div key={name} className="rounded-2xl p-4" style={{ background: "#1a1a1a", border: "1px solid #222" }}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-white">{name}</p>
                    {ok
                      ? <span className="flex items-center gap-1 text-[11px] font-bold" style={{ color: "#4ade80" }}><CheckCircle2 className="w-3.5 h-3.5" /> Ready</span>
                      : <span className="flex items-center gap-1 text-[11px] font-bold" style={{ color: "#f87171" }}><XCircle className="w-3.5 h-3.5" /> Off</span>}
                  </div>
                  <p className="text-[11px] mt-1 truncate" style={{ color: "#555" }}>{ok ? detail : bad}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Database */}
          <div className="rounded-3xl p-6" style={CARD}>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                style={{ background: "rgba(249,115,22,0.10)", border: "1px solid rgba(249,115,22,0.22)" }}>
                <Database className="w-4 h-4" style={{ color: "#f97316" }} />
              </div>
              <div>
                <p className="text-sm font-bold text-white">Local Database</p>
                <p className="text-xs" style={{ color: "#666" }}>SQLite · stored in agent/</p>
              </div>
              <span className="ml-auto flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full"
                style={{ background: "rgba(34,197,94,0.08)", color: "#4ade80", border: "1px solid rgba(34,197,94,0.20)" }}>
                <CheckCircle2 className="w-3.5 h-3.5" /> Active
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Total Jobs",   value: api ? Number(api.database?.total_jobs ?? 0) : "—" },
                { label: "Total Emails", value: api ? Number(api.database?.total_emails ?? 0) : "—" },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-2xl p-4 text-center" style={{ background: "#1a1a1a", border: "1px solid #222" }}>
                  <p className="text-2xl font-bold text-white">{value}</p>
                  <p className="text-[11px] font-medium mt-0.5" style={{ color: "#555" }}>{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
