"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getEmails, sendEmail, deleteEmail, updateEmail } from "@/lib/api";
import { Mail, Send, Trash2, Edit2, Check, X } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import toast from "react-hot-toast";

type Email = {
  id: number;
  job_id: number | null;
  email_type: string;
  to_address: string;
  to_name: string;
  subject: string;
  body: string;
  status: string;
  sent_at: string | null;
  created_at: string;
  error_message: string | null;
};

const STATUS_STYLE: Record<string, { background: string; color: string }> = {
  sent:   { background: "rgba(34,197,94,0.08)",   color: "#4ade80" },
  failed: { background: "rgba(239,68,68,0.08)",   color: "#f87171" },
  draft:  { background: "rgba(249,115,22,0.10)",  color: "#fb923c" },
};

const FILTER_LABELS: Record<string, string> = { "": "All", draft: "Drafts", sent: "Sent", failed: "Failed" };

export default function EmailsPage() {
  const qc = useQueryClient();
  const [filterStatus, setFilterStatus] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [editData, setEditData] = useState<Partial<Email>>({});
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["emails", filterStatus],
    queryFn: () => getEmails({ status: filterStatus || undefined, limit: 200 }),
  });

  const sendMut = useMutation({
    mutationFn: (id: number) => sendEmail(id),
    onSuccess: () => {
      toast.success("Email sent!");
      qc.invalidateQueries({ queryKey: ["emails"] });
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(`Send failed: ${msg || "unknown error"}`);
    },
  });

  const deleteMut = useMutation({
    mutationFn: deleteEmail,
    onSuccess: () => {
      toast.success("Deleted");
      qc.invalidateQueries({ queryKey: ["emails"] });
      setSelectedEmail(null);
    },
  });

  const saveMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Email> }) =>
      updateEmail(id, data as Record<string, unknown>),
    onSuccess: (updated) => {
      toast.success("Saved");
      setEditing(null);
      qc.invalidateQueries({ queryKey: ["emails"] });
      setSelectedEmail(updated);
    },
  });

  const emails: Email[] = data?.emails || [];
  const drafts = emails.filter((e) => e.status === "draft").length;
  const sent   = emails.filter((e) => e.status === "sent").length;

  const startEdit = (e: Email) => {
    setEditing(e.id);
    setEditData({ to_address: e.to_address, to_name: e.to_name, subject: e.subject, body: e.body });
  };

  const inputStyle = {
    background: "#1a1a1a", border: "1px solid #2a2a2a", color: "#e0e0e0",
  };

  return (
    <div className="p-7 max-w-[1400px] mx-auto space-y-5" style={{ background: "#080808", minHeight: "100vh" }}>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Emails</h1>
          <p className="text-sm mt-0.5" style={{ color: "#666" }}>{drafts} drafts · {sent} sent</p>
        </div>
        <div className="flex gap-1 p-1 rounded-xl" style={{ background: "#111", border: "1px solid #1e1e1e" }}>
          {["", "draft", "sent", "failed"].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setFilterStatus(s)}
              className="text-xs px-3 py-1.5 rounded-lg font-medium transition"
              style={filterStatus === s
                ? { background: "#1e1e1e", color: "#fff" }
                : { color: "#555" }}
            >
              {FILTER_LABELS[s]}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-5 h-[calc(100vh-180px)]">

        {/* Email list */}
        <div className="w-80 flex-shrink-0 space-y-1.5 overflow-y-auto pr-1">
          {isLoading ? (
            <div className="text-center text-sm py-12" style={{ color: "#555" }}>Loading…</div>
          ) : emails.length === 0 ? (
            <div className="text-center py-16">
              <Mail className="w-8 h-8 mx-auto mb-3" style={{ color: "#333" }} />
              <p className="text-sm" style={{ color: "#555" }}>No emails yet</p>
            </div>
          ) : (
            emails.map((email) => {
              const isActive = selectedEmail?.id === email.id;
              return (
                <button
                  key={email.id}
                  type="button"
                  onClick={() => setSelectedEmail(email)}
                  className="w-full text-left rounded-2xl p-4 transition"
                  style={isActive
                    ? { background: "rgba(249,115,22,0.08)", border: "1px solid rgba(249,115,22,0.25)" }
                    : { background: "#111", border: "1px solid #1e1e1e" }}
                  onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = "#161616"; }}
                  onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "#111"; }}
                >
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <p className="text-sm font-medium text-white truncate">{email.subject}</p>
                    <span
                      className="text-[10px] px-2 py-0.5 rounded-full shrink-0 font-medium"
                      style={STATUS_STYLE[email.status] || { background: "#1a1a1a", color: "#555" }}
                    >
                      {email.status}
                    </span>
                  </div>
                  <p className="text-xs truncate" style={{ color: "#666" }}>{email.to_name || email.to_address}</p>
                  <p className="text-xs mt-1.5" style={{ color: "#444" }}>
                    {email.created_at && formatDistanceToNow(new Date(email.created_at), { addSuffix: true })}
                  </p>
                </button>
              );
            })
          )}
        </div>

        {/* Email detail */}
        {selectedEmail ? (
          <div className="flex-1 rounded-3xl flex flex-col overflow-hidden" style={{ background: "#111", border: "1px solid #1e1e1e" }}>

            {/* Detail header */}
            <div className="px-6 py-4" style={{ borderBottom: "1px solid #1e1e1e" }}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {editing === selectedEmail.id ? (
                    <input
                      className="w-full text-base font-semibold rounded-xl px-3 py-2 outline-none transition"
                      style={inputStyle}
                      value={editData.subject || ""}
                      onChange={(e) => setEditData((d) => ({ ...d, subject: e.target.value }))}
                      onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
                      onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
                    />
                  ) : (
                    <h2 className="text-base font-semibold text-white">{selectedEmail.subject}</h2>
                  )}
                  <div className="mt-2 flex items-center gap-4 text-xs flex-wrap">
                    <span style={{ color: "#666" }}>
                      <span style={{ color: "#444" }}>To:</span>{" "}
                      {editing === selectedEmail.id ? (
                        <input
                          className="rounded-lg px-3 py-1.5 text-xs outline-none transition"
                          style={inputStyle}
                          value={editData.to_address || ""}
                          onChange={(e) => setEditData((d) => ({ ...d, to_address: e.target.value }))}
                          placeholder="email@company.com"
                          onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
                          onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
                        />
                      ) : (
                        <span style={{ color: "#ccc" }}>
                          {selectedEmail.to_name
                            ? `${selectedEmail.to_name} <${selectedEmail.to_address}>`
                            : selectedEmail.to_address || (
                              <span style={{ color: "#f59e0b" }}>⚠ No email address</span>
                            )}
                        </span>
                      )}
                    </span>
                    <span className="capitalize" style={{ color: "#555" }}>
                      <span style={{ color: "#444" }}>Type:</span> {selectedEmail.email_type?.replace(/_/g, " ")}
                    </span>
                    {selectedEmail.sent_at && (
                      <span style={{ color: "#4ade80" }}>
                        Sent {formatDistanceToNow(new Date(selectedEmail.sent_at), { addSuffix: true })}
                      </span>
                    )}
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex items-center gap-2 shrink-0">
                  {selectedEmail.status === "draft" && (
                    <>
                      {editing === selectedEmail.id ? (
                        <>
                          <button
                            onClick={() => saveMut.mutate({ id: selectedEmail.id, data: editData })}
                            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl text-white transition"
                            style={{ background: "#16a34a" }}
                            onMouseEnter={e => (e.currentTarget.style.background = "#15803d")}
                            onMouseLeave={e => (e.currentTarget.style.background = "#16a34a")}
                          >
                            <Check className="w-3 h-3" /> Save
                          </button>
                          <button
                            onClick={() => setEditing(null)}
                            className="text-xs px-2.5 py-1.5 rounded-xl transition"
                            style={{ border: "1px solid #2a2a2a", color: "#888" }}
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => startEdit(selectedEmail)}
                          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl transition"
                          style={{ border: "1px solid #2a2a2a", color: "#888" }}
                          onMouseEnter={e => (e.currentTarget.style.color = "#fff")}
                          onMouseLeave={e => (e.currentTarget.style.color = "#888")}
                        >
                          <Edit2 className="w-3 h-3" /> Edit
                        </button>
                      )}
                      <button
                        onClick={() => sendMut.mutate(selectedEmail.id)}
                        disabled={sendMut.isPending}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl text-white disabled:opacity-50 transition"
                        style={{ background: "#f97316" }}
                        onMouseEnter={e => (e.currentTarget.style.background = "#ea6a0a")}
                        onMouseLeave={e => (e.currentTarget.style.background = "#f97316")}
                      >
                        <Send className="w-3 h-3" />
                        {sendMut.isPending ? "Sending…" : "Send Now"}
                      </button>
                    </>
                  )}
                  {selectedEmail.status !== "sent" && (
                    <button
                      onClick={() => deleteMut.mutate(selectedEmail.id)}
                      className="px-2 py-1.5 rounded-xl transition"
                      style={{ color: "#555" }}
                      onMouseEnter={e => (e.currentTarget.style.color = "#f87171")}
                      onMouseLeave={e => (e.currentTarget.style.color = "#555")}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 p-6 overflow-auto">
              {editing === selectedEmail.id ? (
                <textarea
                  className="w-full h-full min-h-80 rounded-2xl p-4 text-sm outline-none font-mono resize-none transition"
                  style={{ background: "#161616", border: "1px solid #2a2a2a", color: "#e0e0e0" }}
                  value={editData.body || ""}
                  onChange={(e) => setEditData((d) => ({ ...d, body: e.target.value }))}
                  onFocus={e => (e.currentTarget.style.borderColor = "#f97316")}
                  onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")}
                />
              ) : (
                <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed" style={{ color: "#ccc" }}>
                  {selectedEmail.body}
                </pre>
              )}
            </div>

            {selectedEmail.error_message && (
              <div className="px-6 py-3" style={{ borderTop: "1px solid #1e1e1e", background: "rgba(239,68,68,0.06)" }}>
                <p className="text-xs" style={{ color: "#f87171" }}>Error: {selectedEmail.error_message}</p>
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 rounded-3xl flex items-center justify-center" style={{ background: "#111", border: "1px solid #1e1e1e" }}>
            <div className="text-center">
              <Mail className="w-10 h-10 mx-auto mb-3" style={{ color: "#333" }} />
              <p className="text-sm" style={{ color: "#555" }}>Select an email to view</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
