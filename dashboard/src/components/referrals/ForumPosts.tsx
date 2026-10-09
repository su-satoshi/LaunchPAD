"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  Radar, PenSquare, Send, X, ExternalLink, RefreshCw, CheckCircle2, XCircle,
  LogIn, Flame, Compass, AlertTriangle, ChevronDown, ChevronUp, Clock,
} from "lucide-react";
import {
  getReferralPlatforms, openPlatformLogin, finishPlatformLogin, discoverReferralThreads,
  composeOpenToWork, getForumPosts, updateForumPost, approveForumPost,
} from "@/lib/api";
import { CARD, INPUT_STYLE } from "./fields";

type Post = {
  id: number; platform: string; kind: string; target?: string | null;
  thread_url?: string | null; thread_title?: string | null; thread_author?: string | null;
  thread_snippet?: string | null; relevance?: number | null; title?: string | null; body: string;
  status: string; error_message?: string | null; posted_url?: string | null; found_via?: string | null;
  created_at?: string | null;
};

const PLATFORM_META: Record<string, { label: string; emoji: string }> = {
  reddit: { label: "Reddit", emoji: "👽" },
  linkedin: { label: "LinkedIn", emoji: "💼" },
  glassdoor: { label: "Glassdoor", emoji: "🚪" },
};

const KIND_LABEL: Record<string, string> = {
  open_to_work: "Your open-to-work post",
  reply_hiring: "Reply to a hiring post",
  reply_referral: "Reply to a referral offer",
};

const FILTERS = [
  { id: "draft,failed", label: "To review" },
  { id: "approved,posting", label: "Posting" },
  { id: "posted", label: "Posted" },
  { id: "", label: "All" },
];

function StatusChip({ status }: { status: string }) {
  const m: Record<string, { c: string; bg: string; label: string }> = {
    draft:     { c: "#a3a3a3", bg: "rgba(255,255,255,0.05)", label: "Draft" },
    approved:  { c: "#fbbf24", bg: "rgba(234,179,8,0.08)",  label: "Queued" },
    posting:   { c: "#fbbf24", bg: "rgba(234,179,8,0.08)",  label: "Posting…" },
    posted:    { c: "#4ade80", bg: "rgba(34,197,94,0.08)",  label: "Posted" },
    failed:    { c: "#f87171", bg: "rgba(239,68,68,0.08)",  label: "Failed" },
    dismissed: { c: "#666",    bg: "rgba(255,255,255,0.03)", label: "Dismissed" },
  };
  const s = m[status] ?? m.draft;
  return <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full"
    style={{ color: s.c, background: s.bg }}>{s.label}</span>;
}

function PostCard({ post }: { post: Post }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState(post.title ?? "");
  const [body, setBody] = useState(post.body);
  const [showThread, setShowThread] = useState(false);
  const editable = ["draft", "failed"].includes(post.status);
  const dirty = title !== (post.title ?? "") || body !== post.body;
  const meta = PLATFORM_META[post.platform] ?? { label: post.platform, emoji: "🌐" };
  const needsTitle = post.kind === "open_to_work" && post.platform !== "linkedin";

  const refresh = () => qc.invalidateQueries({ queryKey: ["forum-posts"] });

  const save = useMutation({
    mutationFn: () => updateForumPost(post.id, { title, body }),
    onSuccess: () => { toast.success("Draft saved"); refresh(); },
    onError: () => toast.error("Couldn't save the draft"),
  });
  const dismiss = useMutation({
    mutationFn: () => updateForumPost(post.id, { status: "dismissed" }),
    onSuccess: refresh,
  });
  const approve = useMutation({
    mutationFn: async () => {
      if (dirty) await updateForumPost(post.id, { title, body });
      return approveForumPost(post.id);
    },
    onSuccess: () => { toast.success(`Posting to ${meta.label}… watch the Chrome window`); refresh(); },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(d ?? "Couldn't start posting");
    },
  });

  return (
    <div className="rounded-3xl p-5 flex flex-col gap-3" style={CARD}>
      {/* header */}
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0"
          style={{ background: "#1a1a1a", border: "1px solid #222" }}>{meta.emoji}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-bold text-white">{KIND_LABEL[post.kind] ?? post.kind}</p>
            <StatusChip status={post.status} />
            {post.relevance != null && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                style={{ color: "#fb923c", border: "1px solid rgba(249,115,22,0.3)" }}>
                {Math.round(post.relevance * 100)}% fit
              </span>
            )}
          </div>
          <p className="text-xs mt-0.5" style={{ color: "#666" }}>
            {meta.label}
            {post.target ? ` · r/${post.target}` : ""}
            {post.found_via ? ` · found via ${post.found_via === "agent_browser" ? "browser agent" : "Firecrawl"}` : ""}
          </p>
        </div>
      </div>

      {/* thread context */}
      {post.thread_url && (
        <div className="rounded-2xl px-4 py-3" style={{ background: "#151515", border: "1px solid #202020" }}>
          <div className="flex items-start justify-between gap-3">
            <a href={post.thread_url} target="_blank" rel="noopener noreferrer"
              className="text-sm font-semibold hover:underline flex items-center gap-1.5 min-w-0" style={{ color: "#ddd" }}>
              <span className="truncate">{post.thread_title || post.thread_url}</span>
              <ExternalLink className="w-3.5 h-3.5 shrink-0" style={{ color: "#666" }} />
            </a>
            {post.thread_snippet && (
              <button type="button" onClick={() => setShowThread((s) => !s)} className="text-[11px] flex items-center gap-1 shrink-0"
                style={{ color: "#666" }} aria-expanded={showThread}>
                {showThread ? <>Hide <ChevronUp className="w-3 h-3" /></> : <>Original post <ChevronDown className="w-3 h-3" /></>}
              </button>
            )}
          </div>
          {post.thread_author && <p className="text-[11px] mt-0.5" style={{ color: "#555" }}>by {post.thread_author}</p>}
          {showThread && post.thread_snippet && (
            <p className="text-xs mt-2 whitespace-pre-wrap leading-relaxed max-h-48 overflow-auto" style={{ color: "#888" }}>
              {post.thread_snippet}
            </p>
          )}
        </div>
      )}

      {/* draft */}
      {needsTitle && (
        <input className="w-full text-sm font-semibold rounded-xl px-4 py-2.5 outline-none" style={INPUT_STYLE}
          value={title} onChange={(e) => setTitle(e.target.value)} disabled={!editable} placeholder="Post title"
          aria-label="Post title" />
      )}
      <textarea rows={Math.min(12, Math.max(5, body.split("\n").length + 1))}
        className="w-full text-sm rounded-xl px-4 py-3 outline-none resize-y leading-relaxed"
        style={INPUT_STYLE} value={body} onChange={(e) => setBody(e.target.value)} disabled={!editable}
        aria-label="Post text" />

      {post.error_message && (
        <div className="flex items-start gap-2 text-xs px-3 py-2 rounded-xl"
          style={{ background: "rgba(239,68,68,0.06)", color: "#f87171", border: "1px solid rgba(239,68,68,0.18)" }}>
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> <span className="break-words">{post.error_message}</span>
        </div>
      )}

      {/* actions */}
      <div className="flex items-center gap-2 pt-1">
        {editable ? (
          <>
            <button type="button" onClick={() => approve.mutate()} disabled={approve.isPending || !body.trim()}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold text-white disabled:opacity-50"
              style={{ background: "#f97316" }}>
              {approve.isPending ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              {post.status === "failed" ? "Retry post" : "Approve & post"}
            </button>
            {dirty && (
              <button type="button" onClick={() => save.mutate()} className="px-4 py-2.5 rounded-xl text-xs font-semibold"
                style={{ color: "#ccc", border: "1px solid #2a2a2a" }}>Save edits</button>
            )}
            <button type="button" onClick={() => dismiss.mutate()} className="ml-auto flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-semibold"
              style={{ color: "#666" }}>
              <X className="w-3.5 h-3.5" /> Dismiss
            </button>
          </>
        ) : post.status === "posted" ? (
          <a href={post.posted_url || post.thread_url || "#"} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: "#4ade80" }}>
            <CheckCircle2 className="w-3.5 h-3.5" /> View on {meta.label}
          </a>
        ) : (
          <p className="flex items-center gap-1.5 text-xs" style={{ color: "#fbbf24" }}>
            <Clock className="w-3.5 h-3.5" /> The browser agent is posting this now
          </p>
        )}
      </div>
    </div>
  );
}

export default function ForumPosts() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState(FILTERS[0].id);

  const { data: plat } = useQuery({
    queryKey: ["referral-platforms"],
    queryFn: getReferralPlatforms,
    refetchInterval: (q) => {
      const d = q.state.data as { discover?: { running?: boolean }; login?: { status?: string } } | undefined;
      return d?.discover?.running || d?.login?.status === "waiting_for_user" || d?.login?.status === "opening" ? 4000 : 30000;
    },
  });
  const p = (plat ?? {}) as {
    firecrawl?: { available?: boolean; url?: string };
    browser?: { stagehand_installed?: boolean; busy?: boolean };
    login?: { platform?: string | null; status?: string };
    discover?: { running?: boolean; last_run?: string | null; last_result?: { drafted?: number; candidates?: number } | null };
  };
  const discovering = Boolean(p.discover?.running);

  const { data: postsData, isLoading } = useQuery({
    queryKey: ["forum-posts", filter],
    queryFn: () => getForumPosts(filter || undefined),
    refetchInterval: discovering ? 4000 : 10000,
  });
  const posts = ((postsData as { posts?: Post[] })?.posts) ?? [];
  const counts = ((postsData as { counts?: Record<string, number> })?.counts) ?? {};

  const discover = useMutation({
    mutationFn: () => discoverReferralThreads(),
    onSuccess: (r) => {
      toast.success((r as { started?: boolean }).started ? "Agent is searching forums for hiring and referral posts" : "Already searching");
      qc.invalidateQueries({ queryKey: ["referral-platforms"] });
    },
    onError: () => toast.error("Couldn't start the search"),
  });
  const compose = useMutation({
    mutationFn: () => composeOpenToWork(),
    onSuccess: (r) => {
      const n = ((r as { created?: unknown[] }).created ?? []).length;
      toast.success(`Drafted ${n} post${n === 1 ? "" : "s"} for you to review`);
      setFilter("draft,failed");
      qc.invalidateQueries({ queryKey: ["forum-posts"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(d ?? "Couldn't draft posts");
    },
  });
  const login = useMutation({
    mutationFn: (platform: string) => openPlatformLogin(platform),
    onSuccess: (r) => {
      const res = r as { ok?: boolean; detail?: string };
      (res.ok ? toast.success : toast.error)(res.detail ?? "");
      qc.invalidateQueries({ queryKey: ["referral-platforms"] });
    },
  });
  const loginDone = useMutation({
    mutationFn: finishPlatformLogin,
    onSuccess: () => { toast.success("Saved your sign-in"); qc.invalidateQueries({ queryKey: ["referral-platforms"] }); },
  });

  const waitingLogin = p.login?.status === "waiting_for_user" || p.login?.status === "opening";

  return (
    <div className="space-y-4">
      {/* engines + accounts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="rounded-2xl px-4 py-3.5 flex items-center gap-3" style={CARD}>
          <Flame className="w-4 h-4 shrink-0" style={{ color: "#f97316" }} />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white">Firecrawl</p>
            <p className="text-[11px] truncate" style={{ color: "#555" }}>Self-hosted · {p.firecrawl?.url ?? "localhost:3002"}</p>
          </div>
          {p.firecrawl?.available
            ? <span className="flex items-center gap-1 text-[11px] font-bold" style={{ color: "#4ade80" }}><CheckCircle2 className="w-3.5 h-3.5" />Running</span>
            : <span className="flex items-center gap-1 text-[11px] font-bold" style={{ color: "#f87171" }} title="Run: docker compose up -d"><XCircle className="w-3.5 h-3.5" />Not running</span>}
        </div>
        <div className="rounded-2xl px-4 py-3.5 flex items-center gap-3" style={CARD}>
          <Compass className="w-4 h-4 shrink-0" style={{ color: "#f97316" }} />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white">Browser agent</p>
            <p className="text-[11px]" style={{ color: "#555" }}>Stagehand · your Chrome profile</p>
          </div>
          {p.browser?.stagehand_installed
            ? <span className="flex items-center gap-1 text-[11px] font-bold" style={{ color: p.browser?.busy ? "#fbbf24" : "#4ade80" }}>
                <CheckCircle2 className="w-3.5 h-3.5" />{p.browser?.busy ? "Busy" : "Ready"}</span>
            : <span className="flex items-center gap-1 text-[11px] font-bold" style={{ color: "#f87171" }}><XCircle className="w-3.5 h-3.5" />Not installed</span>}
        </div>
        <div className="rounded-2xl px-4 py-3 flex items-center gap-2 flex-wrap" style={CARD}>
          <LogIn className="w-4 h-4 shrink-0" style={{ color: "#f97316" }} />
          <p className="text-sm font-semibold text-white mr-1">Accounts</p>
          {waitingLogin ? (
            <button type="button" onClick={() => loginDone.mutate()}
              className="ml-auto text-xs font-bold px-3 py-1.5 rounded-lg text-white" style={{ background: "#16a34a" }}>
              I&apos;ve signed in to {PLATFORM_META[p.login?.platform ?? ""]?.label ?? "it"} - done
            </button>
          ) : (
            Object.entries(PLATFORM_META).map(([id, m]) => (
              <button key={id} type="button" onClick={() => login.mutate(id)}
                className="text-[11px] font-semibold px-2.5 py-1.5 rounded-lg transition"
                style={{ color: "#bbb", border: "1px solid #2a2a2a" }} title={`Open a Chrome window to sign in to ${m.label}`}>
                {m.emoji} {m.label}
              </button>
            ))
          )}
        </div>
      </div>

      {/* actions */}
      <div className="flex flex-col md:flex-row gap-3">
        <button type="button" onClick={() => discover.mutate()} disabled={discovering || discover.isPending}
          className="flex-1 flex items-center gap-3 px-5 py-4 rounded-2xl text-left transition disabled:opacity-70"
          style={{ background: "rgba(249,115,22,0.08)", border: "1px solid rgba(249,115,22,0.25)" }}>
          {discovering ? <RefreshCw className="w-5 h-5 animate-spin shrink-0" style={{ color: "#f97316" }} />
            : <Radar className="w-5 h-5 shrink-0" style={{ color: "#f97316" }} />}
          <div>
            <p className="text-sm font-bold" style={{ color: "#fb923c" }}>{discovering ? "Searching forums…" : "Find hiring & referral posts"}</p>
            <p className="text-[11px] mt-0.5" style={{ color: "#777" }}>
              {p.discover?.last_result
                ? `Last run: ${p.discover.last_result.candidates ?? 0} posts checked, ${p.discover.last_result.drafted ?? 0} replies drafted`
                : "Agent searches Reddit, LinkedIn and Glassdoor, then drafts replies"}
            </p>
          </div>
        </button>
        <button type="button" onClick={() => compose.mutate()} disabled={compose.isPending}
          className="flex-1 flex items-center gap-3 px-5 py-4 rounded-2xl text-left transition disabled:opacity-70" style={CARD}>
          {compose.isPending ? <RefreshCw className="w-5 h-5 animate-spin shrink-0" style={{ color: "#f97316" }} />
            : <PenSquare className="w-5 h-5 shrink-0" style={{ color: "#f97316" }} />}
          <div>
            <p className="text-sm font-bold text-white">{compose.isPending ? "Drafting…" : "Draft my open-to-work posts"}</p>
            <p className="text-[11px] mt-0.5" style={{ color: "#777" }}>&quot;Looking for a referral&quot; post for each platform, from My details</p>
          </div>
        </button>
      </div>

      {/* filters */}
      <div className="flex items-center gap-1.5">
        {FILTERS.map((f) => {
          const n = f.id ? f.id.split(",").reduce((a, s) => a + (counts[s] ?? 0), 0) : undefined;
          const on = filter === f.id;
          return (
            <button key={f.label} type="button" onClick={() => setFilter(f.id)}
              className="text-xs font-semibold px-3.5 py-2 rounded-xl transition"
              style={on ? { background: "#1f1f1f", color: "#fff", border: "1px solid #333" } : { color: "#666", border: "1px solid transparent" }}>
              {f.label}{n != null && n > 0 ? <span className="ml-1.5" style={{ color: "#f97316" }}>{n}</span> : null}
            </button>
          );
        })}
        <p className="ml-auto text-[11px]" style={{ color: "#444" }}>Nothing is posted until you press Approve.</p>
      </div>

      {/* list */}
      {isLoading ? (
        <div className="text-center py-16 text-sm" style={{ color: "#555" }}>Loading…</div>
      ) : posts.length === 0 ? (
        <div className="text-center py-16 rounded-3xl" style={CARD}>
          <Radar className="w-9 h-9 mx-auto mb-3" style={{ color: "#333" }} />
          <p className="text-sm font-semibold" style={{ color: "#666" }}>No posts here yet</p>
          <p className="text-xs mt-1" style={{ color: "#444" }}>Find hiring posts or draft your own open-to-work post above.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {posts.map((post) => <PostCard key={`${post.id}-${post.status}`} post={post} />)}
        </div>
      )}
    </div>
  );
}
