import { useEffect, useState, type RefObject } from "react";

type Target = { from: number; to: number };

/**
 * Animates each target value from→to with an easeOutCubic curve, returning the
 * current integer values. With a `triggerRef` the animation (re)runs whenever
 * that element scrolls into view; without one it runs once on mount. Honors
 * `prefers-reduced-motion` (jumps straight to the final values).
 */
export function useCountUp(
  targets: Target[],
  triggerRef?: RefObject<HTMLElement | null>,
  dur = 1100
): number[] {
  const [values, setValues] = useState<number[]>(() => targets.map((t) => t.from));

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    const run = () => {
      cancelAnimationFrame(raf); // never let a re-trigger leave a loop running
      if (reduced) {
        setValues(targets.map((t) => t.to));
        return;
      }
      const start = performance.now();
      const tick = (now: number) => {
        const p = Math.min(1, (now - start) / dur);
        const e = 1 - Math.pow(1 - p, 3);
        setValues(targets.map((t) => Math.round(t.from + (t.to - t.from) * e)));
        if (p < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    };

    if (!triggerRef) {
      run();
      return () => cancelAnimationFrame(raf);
    }
    const el = triggerRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => entries.forEach((en) => en.isIntersecting && run()),
      { threshold: 0.4 }
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [targets, triggerRef, dur]);

  return values;
}
