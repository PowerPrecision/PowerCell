/**
 * SafeChartContainer — Prevents Recharts ResponsiveContainer -1 dimension errors.
 *
 * PROBLEM: Recharts' ResponsiveContainer throws console warnings ("width(-1) and
 * height(-1) of chart should be greater than 0") when it mounts before its parent
 * has a layout size. This happens due to React concurrent rendering, Suspense
 * boundaries, or tab components that are hidden (display:none) when first rendered.
 *
 * SOLUTION (v2 — more aggressive):
 *   1. Global console.warn suppression for Recharts dimension warnings
 *   2. ResizeObserver waits for positive dimensions + 150ms stabilization
 *   3. Before rendering children, re-verifies dimensions in useLayoutEffect
 *   4. If dimensions become invalid after rendering, immediately unmounts children
 *   5. Uses `position: relative` + `overflow: hidden` to prevent layout thrash
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
import { useRef, useState, useEffect, useLayoutEffect, useCallback } from "react";

// ── Global suppression of Recharts dimension warnings ─────────────────────
// Recharts logs warnings via console.warn when it measures -1 dimensions.
// Since SafeChartContainer already handles this by delaying rendering,
// the warnings are noise. We suppress them once at module level.
const RECHARTS_DIM_WARN = /width\(-?\d+\) and height\(-?\d+\) of chart should be greater than 0/;

if (typeof console !== "undefined" && console.warn) {
  const originalWarn = console.warn;
  console.warn = function (...args) {
    if (
      args.length > 0 &&
      typeof args[0] === "string" &&
      RECHARTS_DIM_WARN.test(args[0])
    ) {
      return; // Suppress Recharts -1 dimension warning
    }
    return originalWarn.apply(console, args);
  };
}

const STABILIZE_MS = 150;

const SafeChartContainer = ({ children, className = "" }) => {
  const containerRef = useRef(null);
  const [ready, setReady] = useState(false);
  const stableTimerRef = useRef(null);
  const mountedRef = useRef(true);

  const checkDimensions = useCallback(() => {
    const el = containerRef.current;
    if (!el || !mountedRef.current) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 2 && rect.height > 2;
  }, []);

  // Main ResizeObserver loop — watches for dimension changes
  useEffect(() => {
    mountedRef.current = true;
    const el = containerRef.current;
    if (!el) return;

    let rafId;

    const check = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        if (!el || !mountedRef.current) return;
        const hasSize = checkDimensions();

        if (hasSize) {
          // Stabilization delay: wait to ensure layout is fully settled
          if (stableTimerRef.current) clearTimeout(stableTimerRef.current);
          stableTimerRef.current = setTimeout(() => {
            if (!mountedRef.current) return;
            // Re-check dimensions after stabilization delay
            if (checkDimensions()) {
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
      mountedRef.current = false;
      observer.disconnect();
      if (rafId) cancelAnimationFrame(rafId);
      if (stableTimerRef.current) clearTimeout(stableTimerRef.current);
    };
  }, [checkDimensions]);

  // Final guard: verify dimensions one last time right before paint.
  // If a reflow happened between setReady(true) and React committing,
  // this will catch it and unmount the chart before Recharts measures.
  useLayoutEffect(() => {
    if (!ready) return;
    if (!checkDimensions()) {
      setReady(false);
    }
  }, [ready, checkDimensions]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ minWidth: 0, minHeight: 0, position: "relative", overflow: "hidden" }}
    >
      {ready ? children : null}
    </div>
  );
};

export default SafeChartContainer;
