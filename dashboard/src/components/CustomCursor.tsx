"use client";
import { useEffect, useRef } from "react";

export default function CustomCursor() {
  const dotRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const el = dotRef.current;
      if (!el) return;
      el.style.transform = `translate(${e.clientX - 8}px, ${e.clientY - 8}px)`;
      el.style.opacity = "1";
    };
    const onLeave = () => { if (dotRef.current) dotRef.current.style.opacity = "0"; };
    const onEnter = () => { if (dotRef.current) dotRef.current.style.opacity = "1"; };

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseleave", onLeave);
    document.addEventListener("mouseenter", onEnter);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseleave", onLeave);
      document.removeEventListener("mouseenter", onEnter);
    };
  }, []);

  return (
    <div
      ref={dotRef}
      style={{
        position: "fixed",
        top: 0, left: 0,
        width: 16, height: 16,
        borderRadius: "50%",
        background: "rgba(255,255,255,0.85)",
        pointerEvents: "none",
        zIndex: 99999,
        opacity: 0,
        willChange: "transform",
        mixBlendMode: "difference",
      }}
    />
  );
}
