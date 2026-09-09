import { useRef, useState, useEffect } from "react";

// Tracks a container's pixel width for crisp, non-distorted SVG rendering.
export function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((e) => setW(e[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}
