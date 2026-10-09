import { useRef, useCallback } from "react";

interface TiltOptions {
  max?: number;       // max rotation degrees (default 8)
  scale?: number;     // scale on hover (default 1.02)
  glare?: boolean;    // show glare overlay (default false)
}

export function useTilt(options: TiltOptions = {}) {
  const { max = 8, scale = 1.02 } = options;
  const ref = useRef<HTMLDivElement>(null);

  const onMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width  - 0.5; // -0.5 to 0.5
    const y = (e.clientY - rect.top)  / rect.height - 0.5;
    const rotY =  x * max * 2;
    const rotX = -y * max * 2;
    el.style.transform = `perspective(800px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale(${scale})`;
  }, [max, scale]);

  const onMouseLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.transform = "perspective(800px) rotateX(0deg) rotateY(0deg) scale(1)";
  }, []);

  return { ref, onMouseMove, onMouseLeave };
}
