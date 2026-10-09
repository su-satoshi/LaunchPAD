"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard, Briefcase, Mail, FileText, Settings,
  ChevronRight, Users, Play, RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getProfile } from "@/lib/api";
import ProfileModal from "@/components/ProfileModal";
import OrionLogo from "@/components/OrionLogo";
import { useSearch } from "@/lib/SearchContext";
import toast from "react-hot-toast";

const NAV = [
  { href: "/",             label: "Overview",     icon: LayoutDashboard },
  { href: "/jobs",         label: "Jobs",         icon: Briefcase },
  { href: "/referrals",    label: "Referrals",    icon: Users },
  { href: "/emails",       label: "Emails",       icon: Mail },
  { href: "/applications", label: "Applications", icon: FileText },
  { href: "/settings",     label: "Settings",     icon: Settings },
];

function getInitials(name: string): string {
  if (!name) return "?";
  return name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2);
}

export default function Sidebar() {
  const pathname = usePathname();
  const [showProfile, setShowProfile] = useState(false);
  const { data: profile = {} } = useQuery({ queryKey: ["profile"], queryFn: getProfile });
  const { isSearching, progress, startSearch } = useSearch();
  const p = profile as Record<string, unknown>;

  const handleSearch = async () => {
    try {
      await startSearch();
      toast.success("Search started — running in background");
    } catch {
      toast.error("Search failed — check agent logs");
    }
  };

  return (
    <>
      <aside
        className="w-56 flex flex-col"
        style={{
          background: "#0d0d0d",
          borderRight: "1px solid #1a1a1a",
        }}
      >
        {/* Brand */}
        <div className="px-5 pt-5 pb-4 flex items-center gap-3" style={{ borderBottom: "1px solid #1a1a1a" }}>
          <OrionLogo size={32} className="rounded-xl shrink-0" />
          <div>
            <p className="font-bold text-white text-sm tracking-tight leading-none">Orion AI</p>
            <p className="text-[10px] uppercase tracking-widest font-semibold mt-0.5" style={{ color: "#444" }}>Job Engine</p>
          </div>
        </div>

        {/* Profile chip */}
        <div className="p-3" style={{ borderBottom: "1px solid #1a1a1a" }}>
          <button
            type="button"
            onClick={() => setShowProfile(true)}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left group transition-all duration-150"
            style={{ background: "#161616", border: "1px solid #242424" }}
            onMouseEnter={e => (e.currentTarget.style.background = "#1e1e1e")}
            onMouseLeave={e => (e.currentTarget.style.background = "#161616")}
          >
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 text-xs font-bold text-white"
              style={{ background: "#f97316" }}
            >
              {getInitials(String(p.name || ""))}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-white truncate leading-none">
                {String(p.name || "Set up profile")}
              </p>
              <p className="text-[10px] truncate font-medium mt-0.5" style={{ color: "#555" }}>
                {String(p.location || "Add location")}
              </p>
            </div>
            <ChevronRight className="w-3 h-3 shrink-0 transition-colors" style={{ color: "#444" }} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-2.5 space-y-0.5">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || (href !== "/" && pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150",
                )}
                style={
                  active
                    ? { background: "#f97316", color: "#fff" }
                    : { color: "#666666" }
                }
                onMouseEnter={e => { if (!active) { e.currentTarget.style.background = "#141414"; e.currentTarget.style.color = "#fff"; } }}
                onMouseLeave={e => { if (!active) { e.currentTarget.style.background = ""; e.currentTarget.style.color = "#666666"; } }}
              >
                <Icon className="w-4 h-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Run Search button */}
        <div className="px-2.5 pb-2.5">
          <button
            onClick={handleSearch}
            disabled={isSearching}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-bold transition-all duration-200 disabled:opacity-60"
            style={{
              background: isSearching ? "#1a1a1a" : "#f97316",
              color: isSearching ? "#f97316" : "#fff",
              border: isSearching ? "1px solid #2a2a2a" : "none",
            }}
          >
            {isSearching
              ? <RefreshCw className="w-3 h-3 animate-spin" />
              : <Play className="w-3 h-3" />}
            {isSearching
              ? `Searching… ${progress.jobsFound > 0 ? `(${progress.jobsFound})` : ""}`
              : "Run Search"}
          </button>
        </div>

        {/* Search mini-progress */}
        {isSearching && (
          <div className="mx-2.5 mb-2.5 p-3 rounded-xl" style={{ background: "#141414", border: "1px solid #222" }}>
            {(() => {
              const miniPct = progress.jobsFound > 0
                ? Math.min(100, Math.round((progress.jobsMatched / progress.jobsFound) * 100))
                : 8;
              return (
                <div className="h-1 rounded-full relative mb-2 overflow-hidden" style={{ background: "rgba(249,115,22,0.18)" }}>
                  <div
                    className="absolute inset-y-0 left-0 rounded-full"
                    style={{ width: `${Math.max(miniPct, 8)}%`, background: "#111", transition: "width 0.7s ease" }}
                  />
                  {miniPct > 8 && miniPct < 100 && (
                    <div
                      className="absolute top-0 bottom-0 pointer-events-none"
                      style={{ left: `${miniPct}%`, transform: "translateX(-50%)", width: 1.5, background: "#fff", transition: "left 0.7s ease" }}
                    />
                  )}
                </div>
              );
            })()}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "#f97316" }} />
                <p className="text-[10px] font-bold" style={{ color: "#f97316" }}>Live</p>
              </div>
              <p className="text-[10px] tabular-nums font-medium" style={{ color: "#555" }}>
                {progress.jobsFound} · {progress.jobsMatched}
              </p>
            </div>
          </div>
        )}

        {/* Agent status */}
        <div className="p-2.5" style={{ borderTop: "1px solid #1a1a1a" }}>
          <div className="px-3 py-2 rounded-xl flex items-center gap-2" style={{ background: "#141414" }}>
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "#22c55e" }} />
            <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: "#444" }}>Agent</p>
            <p className="text-xs font-bold ml-auto" style={{ color: "#22c55e" }}>Active</p>
          </div>
        </div>
      </aside>

      <ProfileModal isOpen={showProfile} onClose={() => setShowProfile(false)} />
    </>
  );
}
