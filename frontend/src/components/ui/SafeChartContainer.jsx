/**
 * SafeChartContainer — Prevents Recharts ResponsiveContainer -1 dimension errors.
 *
 * PROBLEM: Recharts' ResponsiveContainer throws console warnings ("width(-1) and
 * height(-1) of chart should be greater than 0") when it mounts before its parent
 * has a layout size. This happens due to React concurrent rendering, Suspense
 * boundaries, or tab components that are hidden (display:none) when first rendered.
 *
 * SOLUTION: Wraps children in a div observed by ResizeObserver. Children are only
 * rendered after the container has positive, stable dimensions. Uses a two-stage
 * verification:
 *   1. ResizeObserver checks for positive dimensions + 100ms stabilization delay
 *   2. Before rendering children, re-verifies dimensions in useLayoutEffect
 *   3. If dimensions become invalid after rendering, immediately unmounts children
 *
 * USAGE:
 *   <SafeChartContainer className="h-[280px] w-full">
 *     <ResponsiveContainer width="100%" height="100%">
 *       <BarChart data={data}>...</BarChart>
 *     </ResponsiveContainer>
 *   </SafeChartContainer>
 *
 * NOTE: The className MUST include explicit dimensions (e.g. h-[280px]) otherwise
 * the container may never get a positive height and the chart will never render.
 */
import { useRef, useState, useEffect, useLayoutEffect } from "react";

const STABILIZE_MS = 100;

const SafeChartContainer = ({ children, className = "" }) => {
  const containerRef = useRef(null);
  const [ready, setReady] = useState(false);
  const stableTimerRef = useRef(null);

  // Main ResizeObserver loop — watches for dimension changes
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let rafId;

    const check = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const hasSize = rect.width > 2 && rect.height > 2;

        if (hasSize) {
          // Stabilization delay: wait to ensure layout is fully settled
          if (stableTimerRef.current) clearTimeout(stableTimerRef.current);
          stableTimerRef.current = setTimeout(() => {
            // Re-check dimensions after stabilization delay
            const r2 = el.getBoundingClientRect();
            if (r2.width > 2 && r2.height > 2) {
              setReady(true);
            }
          }, STABILIZE_MS);
        } else {
          if (stableTimerRef.current) clearTimeout(stableTimerRef.current);
          setReady(false);
        }
      });
    };

    check();

    const observer = new ResizeObserver(check);
    observer.observe(el);

    return () => {
      observer.disconnect();
      if (rafId) cancelAnimationFrame(rafId);
      if (stableTimerRef.current) clearTimeout(stableTimerRef.current);
    };
  }, []);

  // Final guard: verify dimensions one last time right before paint.
  // If a reflow happened between setReady(true) and React committing,
  // this will catch it and unmount the chart before Recharts measures.
  useLayoutEffect(() => {
    if (!ready) return;
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 2 || rect.height <= 2) {
      setReady(false);
    }
  }, [ready]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ minWidth: 0, minHeight: 0, overflow: "hidden" }}
    >
      {ready ? children : null}
    </div>
  );
};

export default SafeChartContainer;
