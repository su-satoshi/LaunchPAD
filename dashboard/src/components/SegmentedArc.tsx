"use client";

interface SegmentedArcProps {
  value: number;
  max: number;
  label: string;
  size?: number;
}

function lerp(a: number, b: number, t: number) {
  return Math.round(a + (b - a) * t);
}

function segmentColor(t: number): string {
  // Dark muted orange → rich orange → bright orange
  // #7c2d12 (42,13,6) → #c2410c (194,65,12) → #f97316 (249,115,22)
  if (t < 0.5) {
    const u = t / 0.5;
    return `rgb(${lerp(42,194,u)},${lerp(13,65,u)},${lerp(6,12,u)})`;
  } else {
    const u = (t - 0.5) / 0.5;
    return `rgb(${lerp(194,249,u)},${lerp(65,115,u)},${lerp(12,22,u)})`;
  }
}

export default function SegmentedArc({ value, max, label, size = 220 }: SegmentedArcProps) {
  const SEGMENTS = 36;
  const START_DEG = 135;   // 7-o'clock position
  const TOTAL_DEG = 270;   // spans 3/4 of the circle
  const R_MID = 75;        // radius to segment centres
  const SEG_W = 7;         // segment width (tangential)
  const SEG_H = 20;        // segment height (radial)
  const RX = 3;            // corner radius
  const CX = 100;
  const CY = 105;          // slightly below centre so text sits nicely

  const pct = max > 0 ? Math.min(value / max, 1) : 0;
  const activeCount = Math.round(pct * SEGMENTS);
  const displayPct = Math.round(pct * 100);

  return (
    <div className="flex flex-col items-center gap-2" style={{ width: size, height: size }}>
      <svg
        viewBox="0 0 200 210"
        width={size}
        height={size}
        style={{ overflow: "visible" }}
      >
        {/* Subtle glow ring behind arc */}
        <circle
          cx={CX} cy={CY} r={R_MID}
          fill="none"
          stroke="rgba(249,115,22,0.06)"
          strokeWidth={SEG_H + 4}
        />

        {/* Segments */}
        {Array.from({ length: SEGMENTS }, (_, i) => {
          const angleDeg = START_DEG + (TOTAL_DEG / (SEGMENTS - 1)) * i;
          const angleRad = (angleDeg * Math.PI) / 180;
          const x = CX + R_MID * Math.cos(angleRad);
          const y = CY + R_MID * Math.sin(angleRad);
          const isActive = i < activeCount;
          const t = i / (SEGMENTS - 1);
          const fill = isActive ? segmentColor(t) : "rgba(255,255,255,0.06)";
          const opacity = isActive ? 1 : 0.7;

          return (
            <rect
              key={i}
              x={x - SEG_W / 2}
              y={y - SEG_H / 2}
              width={SEG_W}
              height={SEG_H}
              rx={RX}
              fill={fill}
              opacity={opacity}
              transform={`rotate(${angleDeg + 90},${x},${y})`}
              style={isActive ? { filter: `drop-shadow(0 0 4px ${segmentColor(t)}88)` } : undefined}
            />
          );
        })}

        {/* Centre text */}
        <text
          x={CX}
          y={CY - 6}
          textAnchor="middle"
          fill="white"
          fontSize="30"
          fontWeight="700"
          fontFamily="var(--font-montserrat), sans-serif"
          letterSpacing="-1"
        >
          {max > 0 ? `${displayPct}%` : "—"}
        </text>
        <text
          x={CX}
          y={CY + 14}
          textAnchor="middle"
          fill="rgba(160,160,160,0.55)"
          fontSize="11"
          fontFamily="var(--font-montserrat), sans-serif"
          fontWeight="500"
        >
          {label}
        </text>

        {/* Bottom min/max labels */}
        <text x={28} y={CY + 55} fill="rgba(100,116,139,0.6)" fontSize="9" fontFamily="var(--font-montserrat), sans-serif">0</text>
        <text x={172} y={CY + 55} fill="rgba(100,116,139,0.6)" fontSize="9" fontFamily="var(--font-montserrat), sans-serif" textAnchor="end">{max}</text>
      </svg>
    </div>
  );
}
