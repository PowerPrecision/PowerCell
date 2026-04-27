/**
 * SafeChartContainer — Prevents Recharts ResponsiveContainer -1 dimension errors.
 *
 * PROBLEM: Recharts' ResponsiveContainer throws console warnings ("width(-1) and
 * height(-1) of chart should be greater than 0") when it mounts before its parent
 * has a layout size. This happens due to React concurrent rendering, Suspense
 * boundaries, or tab components that are hidden (display:none) when first rendered.
 *
 * SOLUTION: Wraps children in a div observed by ResizeObserver. Children are only
 * rendered after the container has positive, stable dimensions for at least one
 * animation frame. A 50ms stabilization delay ensures the layout is fully settled
 * before Recharts measures the container.
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
import { useRef, useState, useEffect } from "react";

const SafeChartContainer = ({ children, className = "" }) => {
  const containerRef = useRef(null);
  const [ready, setReady] = useState(false);
  const stableTimerRef = useRef(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let rafId;

    const check = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const hasSize = rect.width > 1 && rect.height > 1;

        if (hasSize) {
          // Stabilization delay: wait 50ms to ensure layout is fully settled
          // before rendering charts. This prevents race conditions where the
          // container has size momentarily but reflows before Recharts measures.
          if (stableTimerRef.current) clearTimeout(stableTimerRef.current);
          stableTimerRef.current = setTimeout(() => {
            setReady(true);
          }, 50);
        } else {
          // If size is not valid, cancel any pending stabilization
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

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ minWidth: 1, minHeight: 1 }}
    >
      {ready ? children : null}
    </div>
  );
};

export default SafeChartContainer;
