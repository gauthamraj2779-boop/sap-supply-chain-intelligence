import { useState, useEffect, useRef, useMemo } from 'react';

// Easing functions
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
const easeOutQuad = (t) => 1 - (1 - t) * (1 - t);

/**
 * Hook to detect if user has prefers-reduced-motion enabled
 */
export function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handler = (event) => setPrefersReducedMotion(event.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  return prefersReducedMotion;
}

/**
 * useDoubleRaf
 * Two requestAnimationFrame calls pattern for triggering CSS transitions reliably from React.
 * State changes in the same tick don't transition because the browser doesn't calculate the initial layout.
 * The double rAF ensures the browser paints the initial un-transitioned frame before applying the active class.
 */
export function useDoubleRaf(initialState = false) {
  const [ready, setReady] = useState(initialState);

  useEffect(() => {
    let frame1;
    let frame2;

    frame1 = requestAnimationFrame(() => {
      frame2 = requestAnimationFrame(() => {
        setReady(true);
      });
    });

    return () => {
      cancelAnimationFrame(frame1);
      if (frame2) cancelAnimationFrame(frame2);
    };
  }, []);

  return ready;
}

/**
 * useCountUp
 * Always animates from 0 to targetValue on mount or when targetValue changes.
 * Used for FinancialDashboard, OverviewSection, ConfidenceBadge.
 *
 * @param {number} targetValue - Target number to count up to
 * @param {object} options - Options: duration (ms), formatFn, delay (ms), easing
 */
export function useCountUp(targetValue, { duration = 1000, delay = 0, formatFn, easing = easeOutCubic } = {}) {
  const prefersReduced = usePrefersReducedMotion();
  const target = typeof targetValue === 'number' ? targetValue : 0;
  const [current, setCurrent] = useState(prefersReduced ? target : 0);

  useEffect(() => {
    if (prefersReduced) {
      setCurrent(target);
      return;
    }

    let animationFrameId;
    let timeoutId;
    let startTime = null;

    const startAnimation = () => {
      const step = (timestamp) => {
        if (!startTime) startTime = timestamp;
        const elapsed = timestamp - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easedProgress = easing(progress);
        const nextValue = Math.round(0 + (target - 0) * easedProgress);

        setCurrent(nextValue);

        if (progress < 1) {
          animationFrameId = requestAnimationFrame(step);
        } else {
          setCurrent(target);
        }
      };

      animationFrameId = requestAnimationFrame(step);
    };

    if (delay > 0) {
      timeoutId = setTimeout(startAnimation, delay);
    } else {
      startAnimation();
    }

    return () => {
      if (timeoutId) clearTimeout(timeoutId);
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
    };
  }, [target, duration, delay, prefersReduced, easing]);

  const formatted = useMemo(() => {
    if (formatFn) return formatFn(current);
    return current.toLocaleString();
  }, [current, formatFn]);

  return { value: current, formatted };
}

/**
 * useAnimatedNumber
 * Animates between two arbitrary values (starts from wherever the number currently sits).
 * Crucial for AvoidancePanel where each click moves totals up/down from their current state.
 *
 * @param {number} targetValue - Target number
 * @param {object} options - Options: duration (ms), formatFn, easing
 */
export function useAnimatedNumber(targetValue, { duration = 500, formatFn, easing = easeOutQuad } = {}) {
  const prefersReduced = usePrefersReducedMotion();
  const target = typeof targetValue === 'number' ? targetValue : 0;
  const [current, setCurrent] = useState(target);

  const startValueRef = useRef(target);
  const currentValRef = useRef(target);

  useEffect(() => {
    if (prefersReduced) {
      currentValRef.current = target;
      setCurrent(target);
      return;
    }

    const startVal = currentValRef.current;
    startValueRef.current = startVal;

    let animationFrameId;
    let startTime = null;

    const step = (timestamp) => {
      if (!startTime) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = easing(progress);

      const nextValue = Math.round(startVal + (target - startVal) * eased);
      currentValRef.current = nextValue;
      setCurrent(nextValue);

      if (progress < 1) {
        animationFrameId = requestAnimationFrame(step);
      } else {
        currentValRef.current = target;
        setCurrent(target);
      }
    };

    animationFrameId = requestAnimationFrame(step);

    return () => {
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
    };
  }, [target, duration, prefersReduced, easing]);

  const formatted = useMemo(() => {
    if (formatFn) return formatFn(current);
    return current.toLocaleString();
  }, [current, formatFn]);

  return { value: current, formatted };
}
