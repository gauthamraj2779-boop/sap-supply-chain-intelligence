import { useState, useEffect, useRef } from 'react';

// Easing functions
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

function formatNumber(value, decimals = 0) {
  const fixed = Number(value).toFixed(decimals);
  const [int, dec] = fixed.split('.');
  const withCommas = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return dec ? `${withCommas}.${dec}` : withCommas;
}

function formatDisplay(value, target = {}) {
  const prefix = target.prefix || '';
  const suffix = target.suffix || '';
  const decimals = target.decimals || 0;
  return `${prefix}${formatNumber(value, decimals)}${suffix}`;
}

export function fmtUSD(val) {
  if (!val && val !== 0) return '—';
  if (val === 0) return '$0';
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}K`;
  return `$${val}`;
}

/**
 * usePrefersReducedMotion
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
 * Animates from 0 up to target value. Re-runs whenever target or active changes.
 * Supports target as { value, prefix, suffix, decimals } or a raw number.
 */
export function useCountUp(target, options = {}) {
  const active = options.active !== undefined ? options.active : true;
  const duration = options.duration || 700;
  const formatFn = options.formatFn;
  const prefersReduced = usePrefersReducedMotion();

  // Normalize target
  const targetObj = typeof target === 'number'
    ? { value: target, prefix: '', suffix: '', decimals: 0 }
    : (target || { value: 0 });

  const format = (v) => {
    if (formatFn) return formatFn(v);
    return formatDisplay(v, targetObj);
  };

  const [display, setDisplay] = useState(() => format(prefersReduced ? targetObj.value : 0));
  const frameRef = useRef();

  useEffect(() => {
    if (!active) return;

    if (prefersReduced) {
      setDisplay(format(targetObj.value));
      return;
    }

    const start = performance.now();
    const from = 0;
    const to = targetObj.value;

    function tick(now) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = easeOutCubic(progress);
      const current = from + (to - from) * eased;
      setDisplay(format(current));
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        setDisplay(format(to));
      }
    }

    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [active, targetObj.value, duration, prefersReduced]);

  return display;
}

/**
 * useAnimatedNumber
 * Animates between two arbitrary values (from previous value to new target).
 * Supports (targetValue, formatFn, duration) and (targetValue, { formatFn, duration }).
 */
export function useAnimatedNumber(targetValue, formatFnOrOptions, durationOption = 650) {
  let formatFn = fmtUSD;
  let duration = durationOption;

  if (typeof formatFnOrOptions === 'function') {
    formatFn = formatFnOrOptions;
  } else if (typeof formatFnOrOptions === 'object' && formatFnOrOptions !== null) {
    if (formatFnOrOptions.formatFn) formatFn = formatFnOrOptions.formatFn;
    if (formatFnOrOptions.duration) duration = formatFnOrOptions.duration;
  }

  const prefersReduced = usePrefersReducedMotion();
  const [display, setDisplay] = useState(() => formatFn(targetValue));
  const prevValue = useRef(targetValue);
  const frameRef = useRef();

  useEffect(() => {
    if (prefersReduced) {
      setDisplay(formatFn(targetValue));
      prevValue.current = targetValue;
      return;
    }

    const from = prevValue.current;
    const to = targetValue;
    const start = performance.now();

    function tick(now) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = easeOutCubic(progress);
      const current = from + (to - from) * eased;
      setDisplay(formatFn(current));
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        prevValue.current = to;
        setDisplay(formatFn(to));
      }
    }

    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [targetValue, duration, prefersReduced]);

  return display;
}
