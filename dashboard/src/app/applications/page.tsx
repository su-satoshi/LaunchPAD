"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getApplications, updateApplication } from "@/lib/api";
import { statusBadgeStyle, sourceIcon } from "@/lib/utils";
import ScoreBadge from "@/components/ScoreBadge";
import { formatDistanceToNow, format } from "date-fns";
import { ExternalLink, Bell, LayoutGrid, List } from "lucide-react";
import toast from "react-hot-toast";

const STAGES = ["email_sent","applied","interview","offer","rejected"];
const STAGE_META: Record<string, { label: string; dot: string; card: string }> = {
  email_sent: { label: "Emailed",   dot: "bg-orange-400",    card: "border-t-orange-600"    },
  applied:    { label: "Applied",   dot: "bg-emerald-400", card: "border-t-emerald-600" },
  interview:  { label: "Interview", dot: "bg-amber-400",   card: "border-t-amber-600"   },
  offer:      { label: "Offer",     dot: "bg-orange-300",    card: "border-t-orange-500"    },
  rejected:   { label: "Rejected",  dot: "bg-red-500",     card: "border-t-red-700"     },
};

export default function ApplicationsPage() {
  const qc = useQueryClient();
  const [view, setView] = useState<"kanban" | "list">("kanban");

  const { data: appsData, isLoading } = useQuery({
    queryKey: ["applications"],
    queryFn: () => getApplications({ limit: 200 }),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      updateApplication(id, data),
    onSuccess: () => {
      toast.success("Updated");
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["pipeline"] });
    },
  });

  const apps = appsData?.applications || [];
  const byStage = (stage: string) =>
    apps.filter((a: Record<string, unknown>) => a.status === stage);

  return (
    <div className="p-7 max-w-[1400px] mx-auto space-y-5" style={{ background: "#080808", minHeight: "100vh" }}>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Applications</h1>
          <p className="text-sm mt-0.5" style={{ color: "#666" }}>{apps.length} tracked applications</p>
        </div>
        <div className="flex gap-1 p-1 rounded-xl" style={{ background: "#111", border: "1px solid #1e1e1e" }}>
          <button
            type="button"
            onClick={() => setView("kanban")}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-medium transition"
            style={view === "kanban"
              ? { background: "#1e1e1e", color: "#fff" }
              : { color: "#555" }}
          >
            <LayoutGrid className="w-3.5 h-3.5" /> Kanban
          </button>
          <button
            type="button"
            onClick={() => setView("list")}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-medium transition"
            style={view === "list"
              ? { background: "#1e1e1e", color: "#fff" }
              : { color: "#555" }}
          >
            <List className="w-3.5 h-3.5" /> List
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center text-sm py-20" style={{ color: "#555" }}>Loading…</div>
      ) : view === "kanban" ? (

        /* ── Kanban ── */
        <div className="flex gap-4 overflow-x-auto pb-2">
          {STAGES.map((stage) => {
            const meta = STAGE_META[stage];
            const stageApps = byStage(stage);
            const dotColors: Record<string, string> = {
              email_sent: "#f97316", applied: "#22c55e", interview: "#eab308",
              offer: "#86efac", rejected: "#ef4444",
            };
            const accentColor = dotColors[stage] || "#555";
            return (
              <div key={stage} className="w-64 flex-shrink-0">
                <div className="flex items-center gap-2 mb-2 px-1">
                  <span className="w-2 h-2 rounded-full" style={{ background: accentColor }} />
                  <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "#666" }}>
                    {meta.label}
                  </p>
                  <span className="ml-auto text-xs" style={{ color: "#444" }}>{stageApps.length}</span>
                </div>
                <div className="space-y-2 min-h-32">
                  {stageApps.map((app: Record<string, unknown>) => {
                    const job = app.job as Record<string, unknown>;
                    return (
                      <div
                        key={String(app.id)}
                        className="rounded-2xl p-3.5 transition"
                        style={{ background: "#111", border: "1px solid #1e1e1e" }}
                        onMouseEnter={e => (e.currentTarget.style.background = "#161616")}
                        onMouseLeave={e => (e.currentTarget.style.background = "#111")}
                      >
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-white truncate">
                              {String(job?.title || "—")}
                            </p>
                            <p className="text-xs truncate" style={{ color: "#666" }}>{String(job?.company || "")}</p>
                          </div>
                          {Boolean(job?.url) && (
                            <a
                              href={String(job.url)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="shrink-0 transition"
                              style={{ color: "#444" }}
                              onMouseEnter={e => (e.currentTarget.style.color = "#f97316")}
                              onMouseLeave={e => (e.currentTarget.style.color = "#444")}
                            >
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>
                        {job?.match_score != null && (
                          <ScoreBadge score={Number(job.match_score)} />
                        )}
                        {Boolean(app.applied_at) && (
                          <p className="text-xs mt-2" style={{ color: "#555" }}>
                            Applied {formatDistanceToNow(new Date(String(app.applied_at)), { addSuffix: true })}
                          </p>
                        )}
                        {Boolean(app.follow_up_at) && new Date(String(app.follow_up_at)) <= new Date() && (
                          <div className="flex items-center gap-1 text-xs mt-1.5" style={{ color: "#f59e0b" }}>
                            <Bell className="w-3 h-3" /> Follow up due
                          </div>
                        )}
                        <select
                          className="mt-3 w-full text-xs rounded-lg px-2 py-1.5 outline-none cursor-pointer transition"
                          style={{ background: "#1a1a1a", border: "1px solid #2a2a2a", color: "#ccc" }}
                          value={String(app.status)}
                          onChange={(e) => updateMut.mutate({ id: Number(app.id), data: { status: e.target.value } })}
                        >
                          {STAGES.map((s) => (
                            <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                          ))}
                        </select>
                      </div>
                    );
                  })}
                  {stageApps.length === 0 && (
                    <div className="rounded-xl h-16 flex items-center justify-center" style={{ border: "1px dashed #2a2a2a" }}>
                      <p className="text-xs" style={{ color: "#333" }}>Empty</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

      ) : (

        /* ── List ── */
        <div className="rounded-2xl overflow-hidden" style={{ background: "#111", border: "1px solid #1e1e1e" }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: "1px solid #1e1e1e" }}>
                {["Job", "Source", "Match", "Applied", "Follow Up", "Status"].map(h => (
                  <th key={h} className="text-left px-5 py-3 text-[10px] font-bold uppercase tracking-widest" style={{ color: "#666" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {apps.map((app: Record<string, unknown>) => {
                const job = app.job as Record<string, unknown>;
                return (
                  <tr
                    key={String(app.id)}
                    className="transition-colors"
                    style={{ borderBottom: "1px solid #1a1a1a" }}
                    onMouseEnter={e => (e.currentTarget.style.background = "#161616")}
                    onMouseLeave={e => (e.currentTarget.style.background = "")}
                  >
                    <td className="px-5 py-3.5">
                      <p className="font-semibold text-white">{String(job?.title || "—")}</p>
                      <p className="text-xs mt-0.5" style={{ color: "#666" }}>{String(job?.company || "")}</p>
                    </td>
                    <td className="px-4 py-3.5 text-xs" style={{ color: "#555" }}>
                      {sourceIcon(String(job?.source || ""))} {String(job?.source || "")}
                    </td>
                    <td className="px-4 py-3.5">
                      <ScoreBadge score={job?.match_score != null ? Number(job.match_score) : null} />
                    </td>
                    <td className="px-4 py-3.5 text-xs" style={{ color: "#555" }}>
                      {Boolean(app.applied_at)
                        ? format(new Date(String(app.applied_at)), "dd MMM yyyy")
                        : "—"}
                    </td>
                    <td className="px-4 py-3.5">
                      {Boolean(app.follow_up_at) ? (
                        <span className="text-xs" style={{
                          color: new Date(String(app.follow_up_at)) <= new Date() ? "#f59e0b" : "#555",
                          fontWeight: new Date(String(app.follow_up_at)) <= new Date() ? 600 : 400,
                        }}>
                          {format(new Date(String(app.follow_up_at)), "dd MMM")}
                        </span>
                      ) : <span style={{ color: "#333" }}>—</span>}
                    </td>
                    <td className="px-4 py-3.5">
                      <select
                        className="text-xs font-medium px-2.5 py-1 rounded-full border-0 cursor-pointer outline-none"
                        style={statusBadgeStyle(String(app.status))}
                        value={String(app.status)}
                        onChange={(e) => updateMut.mutate({ id: Number(app.id), data: { status: e.target.value } })}
                      >
                        {STAGES.map((s) => (
                          <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
              {apps.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-16 text-center text-sm" style={{ color: "#444" }}>
                    No applications yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
