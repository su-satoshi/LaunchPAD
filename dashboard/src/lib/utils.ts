import type React from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function scoreColor(score: number | null): string {
  if (!score) return "text-slate-500";
  if (score >= 0.85) return "text-emerald-400";
  if (score >= 0.7) return "text-orange-400";
  if (score >= 0.5) return "text-amber-400";
  return "text-red-400";
}

export function scoreBg(score: number | null): string {
  if (!score) return "bg-slate-800 text-slate-400";
  if (score >= 0.85) return "bg-emerald-950 text-emerald-400 ring-1 ring-emerald-700/50";
  if (score >= 0.7)  return "bg-orange-950 text-orange-400 ring-1 ring-orange-700/50";
  if (score >= 0.5)  return "bg-amber-950 text-amber-400 ring-1 ring-amber-700/50";
  return "bg-red-950 text-red-400 ring-1 ring-red-700/50";
}

export function statusBadgeStyle(status: string): React.CSSProperties {
  const map: Record<string, React.CSSProperties> = {
    found:       { background: "#1a1a1a",                    color: "#666",    border: "1px solid #2a2a2a" },
    matched:     { background: "rgba(249,115,22,0.10)",      color: "#fb923c", border: "1px solid rgba(249,115,22,0.22)" },
    draft_ready: { background: "rgba(168,85,247,0.10)",      color: "#c084fc", border: "1px solid rgba(168,85,247,0.22)" },
    email_sent:  { background: "rgba(34,197,94,0.08)",       color: "#4ade80", border: "1px solid rgba(34,197,94,0.20)" },
    applied:     { background: "rgba(34,197,94,0.08)",       color: "#4ade80", border: "1px solid rgba(34,197,94,0.20)" },
    rejected:    { background: "rgba(239,68,68,0.08)",       color: "#f87171", border: "1px solid rgba(239,68,68,0.18)" },
    interview:   { background: "rgba(234,179,8,0.08)",       color: "#facc15", border: "1px solid rgba(234,179,8,0.20)" },
    offer:       { background: "rgba(34,197,94,0.12)",       color: "#86efac", border: "1px solid rgba(34,197,94,0.28)" },
    skipped:     { background: "#141414",                    color: "#444",    border: "1px solid #1e1e1e" },
  };
  return map[status] || { background: "#1a1a1a", color: "#555", border: "1px solid #2a2a2a" };
}

// Keep old function name as shim
export function statusBadge(status: string): string {
  return ""; // use statusBadgeStyle instead
}

export function sourceIcon(source: string): string {
  const map: Record<string, string> = {
    linkedin:     "💼",
    indeed:       "🔍",
    glassdoor:    "🚪",
    seek:         "🦘",
    web3careers:  "⛓️",
    prosple:      "🎓",
    ambitionbox:  "📦",
    top_companies:"🏆",
    ziprecruiter: "📋",
    google:       "🔷",
    bulk_import:  "📥",
    firecrawl:    "🔥",
    agent_browser:"🧭",
    reddit:       "👽",
  };
  return map[source] || "💼";
}

export function formatSalary(min?: number, max?: number, currency = "AUD"): string {
  if (!min && !max) return "";
  const fmt = (n: number) =>
    n >= 1000 ? `${(n / 1000).toFixed(0)}k` : String(n);
  if (min && max) return `${currency} ${fmt(min)}–${fmt(max)}`;
  if (min) return `${currency} ${fmt(min)}+`;
  return `Up to ${currency} ${fmt(max!)}`;
}
