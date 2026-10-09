"use client";

interface ScoreBadgeProps {
  score: number | null | undefined;
  className?: string;
}

export default function ScoreBadge({ score, className = "" }: ScoreBadgeProps) {
  if (score === null || score === undefined) {
    return (
      <span
        className={`inline-flex items-center justify-center text-[11px] font-bold px-2.5 py-1 rounded-lg tabular-nums ${className}`}
        style={{ background: "#1a1a1a", color: "#444", border: "1px solid #2a2a2a" }}
      >—</span>
    );
  }

  const pct = Math.round(score * 100);

  /* ≥75% — orange top-tier */
  if (pct >= 75) {
    return (
      <span
        className={`inline-flex items-center justify-center text-[11px] font-bold px-2.5 py-1 rounded-lg tabular-nums ${className}`}
        style={{
          background: "rgba(249,115,22,0.12)",
          border: "1px solid rgba(249,115,22,0.28)",
          color: "#fb923c",
        }}
      >{pct}%</span>
    );
  }

  /* 60–74% — grey, readable */
  if (pct >= 60) {
    return (
      <span
        className={`inline-flex items-center justify-center text-[11px] font-bold px-2.5 py-1 rounded-lg tabular-nums ${className}`}
        style={{ background: "#1e1e1e", border: "1px solid #2a2a2a", color: "#cccccc" }}
      >{pct}%</span>
    );
  }

  /* 45–59% — dim */
  if (pct >= 45) {
    return (
      <span
        className={`inline-flex items-center justify-center text-[11px] font-bold px-2.5 py-1 rounded-lg tabular-nums ${className}`}
        style={{ background: "#1a1a1a", border: "1px solid #222", color: "#555" }}
      >{pct}%</span>
    );
  }

  /* <45% — red dim */
  return (
    <span
      className={`inline-flex items-center justify-center text-[11px] font-bold px-2.5 py-1 rounded-lg tabular-nums ${className}`}
      style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.18)", color: "#f87171" }}
    >{pct}%</span>
  );
}
