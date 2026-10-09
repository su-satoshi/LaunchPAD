"use client";
import { useQuery } from "@tanstack/react-query";
import { getProfile } from "@/lib/api";
import { X, Edit2, Mail, Phone, MapPin, Link2, Code2, Download, Check } from "lucide-react";
import Link from "next/link";

interface ProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
}

function getInitials(name: string | undefined): string {
  if (!name) return "?";
  return name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2);
}

export default function ProfileModal({ isOpen, onClose }: ProfileModalProps) {
  const { data: profile = {} } = useQuery({ queryKey: ["profile"], queryFn: getProfile });
  const p = profile as Record<string, unknown>;

  if (!isOpen) return null;

  const skills = Array.isArray(p.skills) ? p.skills as string[] : [];

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.70)" }} onClick={onClose} />

      <div className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-sm z-50 px-4">
        <div className="rounded-2xl overflow-hidden" style={{ background: "#111", border: "1px solid #2a2a2a" }}>

          {/* Header */}
          <div className="px-6 pt-6 pb-5 relative" style={{ background: "rgba(249,115,22,0.04)" }}>
            <button
              onClick={onClose}
              className="absolute top-4 right-4 transition"
              style={{ color: "#555" }}
              onMouseEnter={e => (e.currentTarget.style.color = "#fff")}
              onMouseLeave={e => (e.currentTarget.style.color = "#555")}
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-xl font-bold text-white shrink-0"
                style={{ background: "#f97316" }}>
                {getInitials(String(p.name || ""))}
              </div>
              <div>
                <h2 className="text-base font-bold text-white">{String(p.name || "No name set")}</h2>
                {Boolean(p.location) && (
                  <p className="text-xs flex items-center gap-1 mt-0.5" style={{ color: "#666" }}>
                    <MapPin className="w-3 h-3" /> {String(p.location)}
                  </p>
                )}
                {Boolean(p.years_experience) && (
                  <p className="text-xs mt-0.5" style={{ color: "#555" }}>{String(p.years_experience)} yrs experience</p>
                )}
              </div>
            </div>

            {Boolean(p.has_resume) && (
              <div className="mt-4 flex items-center gap-2 p-2.5 rounded-xl"
                style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.20)" }}>
                <Check className="w-3.5 h-3.5 shrink-0" style={{ color: "#4ade80" }} />
                <p className="text-xs flex-1 truncate" style={{ color: "#4ade80" }}>
                  {String(p.resume_filename || "Resume uploaded")}
                </p>
              </div>
            )}
          </div>

          {/* Contact info */}
          <div className="px-6 pb-4 space-y-2">
            {[
              { icon: Mail,  val: p.email },
              { icon: Phone, val: p.phone },
              { icon: Link2, val: p.linkedin_url },
              { icon: Code2, val: p.github_url },
            ].filter(({ val }) => Boolean(val)).map(({ icon: Icon, val }) => (
              <div key={String(val)} className="flex items-center gap-2.5 text-xs" style={{ color: "#888" }}>
                <Icon className="w-3.5 h-3.5 shrink-0" style={{ color: "#555" }} />
                <span className="truncate">{String(val)}</span>
              </div>
            ))}
          </div>

          {/* Skills */}
          {skills.length > 0 && (
            <div className="px-6 pb-4">
              <p className="text-xs font-medium uppercase tracking-wider mb-2" style={{ color: "#444" }}>Skills</p>
              <div className="flex flex-wrap gap-1.5">
                {skills.slice(0, 12).map((s) => (
                  <span key={s} className="text-xs px-2 py-0.5 rounded-full"
                    style={{ background: "rgba(249,115,22,0.10)", color: "#fb923c", border: "1px solid rgba(249,115,22,0.22)" }}>
                    {s}
                  </span>
                ))}
                {skills.length > 12 && (
                  <span className="text-xs" style={{ color: "#555" }}>+{skills.length - 12} more</span>
                )}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="px-6 pb-6 pt-2 flex gap-2" style={{ borderTop: "1px solid #1e1e1e" }}>
            <Link
              href="/settings"
              onClick={onClose}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white transition"
              style={{ background: "#f97316" }}
              onMouseEnter={e => (e.currentTarget.style.background = "#ea6a0a")}
              onMouseLeave={e => (e.currentTarget.style.background = "#f97316")}
            >
              <Edit2 className="w-3.5 h-3.5" /> Edit Profile
            </Link>
            {Boolean(p.has_resume) && (
              <button
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm transition"
                style={{ background: "#1a1a1a", border: "1px solid #2a2a2a", color: "#888" }}
                onMouseEnter={e => { e.currentTarget.style.color = "#fff"; e.currentTarget.style.background = "#222"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "#888"; e.currentTarget.style.background = "#1a1a1a"; }}
              >
                <Download className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
