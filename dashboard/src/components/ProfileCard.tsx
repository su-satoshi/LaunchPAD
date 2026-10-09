"use client";
import { Mail, Phone, MapPin, FileText } from "lucide-react";

interface ProfileCardProps {
  profile: Record<string, unknown>;
}

export default function ProfileCard({ profile }: ProfileCardProps) {
  const getInitials = (name: string | undefined) => {
    if (!name) return "?";
    return name.split(" ").map((n) => n[0]).join("").toUpperCase();
  };

  return (
    <div className="rounded-xl p-6" style={{ background: "#111", border: "1px solid #1e1e1e" }}>
      {/* Profile Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-full flex items-center justify-center text-2xl font-bold text-white flex-shrink-0"
            style={{ background: "#f97316" }}>
            {getInitials(String(profile.name || ""))}
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">{String(profile.name || "Not set")}</h2>
            <p className="text-sm mt-1" style={{ color: "#666" }}>
              {String(profile.years_experience || 0)} years experience
            </p>
          </div>
        </div>
      </div>

      {/* Contact Info */}
      <div className="space-y-3 mb-6 pb-6" style={{ borderBottom: "1px solid #1e1e1e" }}>
        {Boolean(profile.email) && (
          <div className="flex items-center gap-3">
            <Mail className="w-4 h-4" style={{ color: "#555" }} />
            <span className="text-sm" style={{ color: "#ccc" }}>{String(profile.email)}</span>
          </div>
        )}
        {Boolean(profile.phone) && (
          <div className="flex items-center gap-3">
            <Phone className="w-4 h-4" style={{ color: "#555" }} />
            <span className="text-sm" style={{ color: "#ccc" }}>{String(profile.phone)}</span>
          </div>
        )}
        {Boolean(profile.location) && (
          <div className="flex items-center gap-3">
            <MapPin className="w-4 h-4" style={{ color: "#555" }} />
            <span className="text-sm" style={{ color: "#ccc" }}>{String(profile.location)}</span>
          </div>
        )}
      </div>

      {/* Skills */}
      {Array.isArray(profile.skills) && (profile.skills as string[]).length > 0 && (
        <div className="mb-6 pb-6" style={{ borderBottom: "1px solid #1e1e1e" }}>
          <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "#555" }}>Skills</h3>
          <div className="flex flex-wrap gap-2">
            {(profile.skills as string[]).map((skill: string) => (
              <span key={skill} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full"
                style={{ background: "rgba(249,115,22,0.10)", color: "#fb923c", border: "1px solid rgba(249,115,22,0.22)" }}>
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Resume */}
      {Boolean(profile.has_resume) && (
        <div className="flex items-center gap-3 p-3 rounded-lg" style={{ background: "#1a1a1a" }}>
          <FileText className="w-4 h-4" style={{ color: "#f97316" }} />
          <div className="flex-1">
            <p className="text-xs font-medium text-white">Resume uploaded</p>
            <p className="text-xs" style={{ color: "#555" }}>{String(profile.resume_filename || "resume.pdf")}</p>
          </div>
        </div>
      )}
    </div>
  );
}
