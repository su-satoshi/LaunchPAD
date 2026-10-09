"use client";
import { useState } from "react";
import { X } from "lucide-react";

export const CARD = { background: "#111111", border: "1px solid #1e1e1e" };
export const INPUT_STYLE = { background: "#1a1a1a", border: "1px solid #2a2a2a", color: "#e0e0e0" };

const focus = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) =>
  (e.currentTarget.style.borderColor = "#f97316");
const blur = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) =>
  (e.currentTarget.style.borderColor = "#2a2a2a");

export type FieldSource = "saved" | "resume" | "preferences" | "missing";

export function SourceBadge({ source }: { source?: FieldSource }) {
  if (!source || source === "saved") return null;
  const meta: Record<string, { label: string; color: string; bg: string; border: string }> = {
    resume:      { label: "From resume",      color: "#60a5fa", bg: "rgba(59,130,246,0.08)", border: "rgba(59,130,246,0.22)" },
    preferences: { label: "From preferences", color: "#a78bfa", bg: "rgba(139,92,246,0.08)", border: "rgba(139,92,246,0.22)" },
    missing:     { label: "Missing",          color: "#fbbf24", bg: "rgba(234,179,8,0.08)",  border: "rgba(234,179,8,0.22)" },
  };
  const m = meta[source];
  return (
    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
      style={{ color: m.color, background: m.bg, border: `1px solid ${m.border}` }}>
      {m.label}
    </span>
  );
}

export function Field({ label, source, hint, children, required }: {
  label: string; source?: FieldSource; hint?: string; children: React.ReactNode; required?: boolean;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <label className="text-[11px] font-bold uppercase tracking-wider" style={{ color: "#555" }}>
          {label}{required && <span style={{ color: "#f87171" }}> *</span>}
        </label>
        <SourceBadge source={source} />
      </div>
      {children}
      {hint && <p className="text-[11px] mt-1" style={{ color: "#444" }}>{hint}</p>}
    </div>
  );
}

export function TextInput({ value, onChange, placeholder, type = "text" }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string;
}) {
  return (
    <input type={type} className="w-full text-sm rounded-xl px-4 py-2.5 outline-none transition font-medium"
      style={INPUT_STYLE} value={value} placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)} onFocus={focus} onBlur={blur} />
  );
}

export function TextArea({ value, onChange, placeholder, rows = 4, mono }: {
  value: string; onChange: (v: string) => void; placeholder?: string; rows?: number; mono?: boolean;
}) {
  return (
    <textarea rows={rows}
      className={`w-full text-sm rounded-xl px-4 py-3 outline-none transition resize-y leading-relaxed ${mono ? "font-mono" : ""}`}
      style={INPUT_STYLE} value={value} placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)} onFocus={focus} onBlur={blur} />
  );
}

export function TagInput({ values, onChange, placeholder }: {
  values: string[]; onChange: (v: string[]) => void; placeholder?: string;
}) {
  const [input, setInput] = useState("");
  const add = () => {
    const v = input.trim().replace(/,$/, "");
    if (v && !values.includes(v)) onChange([...values, v]);
    setInput("");
  };
  return (
    <div className="flex flex-wrap gap-1.5 rounded-xl p-2.5 min-h-11 transition"
      style={{ background: "#1a1a1a", border: "1px solid #2a2a2a" }}>
      {values.map((v) => (
        <span key={v} className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg font-medium"
          style={{ background: "rgba(249,115,22,0.10)", color: "#fb923c", border: "1px solid rgba(249,115,22,0.22)" }}>
          {v}
          <button type="button" aria-label={`Remove ${v}`}
            onClick={() => onChange(values.filter((x) => x !== v))} className="ml-0.5 opacity-60 hover:opacity-100 transition">
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      <input className="text-sm outline-none flex-1 min-w-28 bg-transparent font-medium" style={{ color: "#e0e0e0" }}
        placeholder={values.length === 0 ? placeholder : ""} value={input}
        onChange={(e) => setInput(e.target.value)} onBlur={add}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }} />
    </div>
  );
}

export function Toggle({ checked, onChange, label, description }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; description?: string;
}) {
  return (
    <button type="button" onClick={() => onChange(!checked)}
      className="w-full flex items-center justify-between gap-4 px-4 py-3 rounded-2xl text-left transition"
      style={{ background: "#151515", border: "1px solid #222" }} role="switch" aria-checked={checked}>
      <div>
        <p className="text-sm font-semibold" style={{ color: "#ddd" }}>{label}</p>
        {description && <p className="text-[11px] mt-0.5" style={{ color: "#555" }}>{description}</p>}
      </div>
      <span className="relative w-10 h-6 rounded-full shrink-0 transition"
        style={{ background: checked ? "#f97316" : "#2a2a2a" }}>
        <span className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all"
          style={{ left: checked ? "20px" : "4px" }} />
      </span>
    </button>
  );
}

export function SectionTitle({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle?: string }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: "rgba(249,115,22,0.10)", border: "1px solid rgba(249,115,22,0.22)", color: "#f97316" }}>
        {icon}
      </div>
      <div>
        <p className="text-sm font-bold text-white">{title}</p>
        {subtitle && <p className="text-xs" style={{ color: "#666" }}>{subtitle}</p>}
      </div>
    </div>
  );
}
