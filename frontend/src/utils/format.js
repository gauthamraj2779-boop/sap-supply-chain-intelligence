/** Shared formatters. Presentation only — no value is derived here. */

export function formatMoney(val) {
  if (val === null || val === undefined) return '—';
  if (val === 0) return '$0';
  const abs = Math.abs(val);
  if (abs >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${(val / 1_000).toFixed(1)}K`;
  return `$${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function formatMoneyExact(val) {
  if (val === null || val === undefined) return '—';
  return `$${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function formatQty(val) {
  if (val === null || val === undefined) return '—';
  return val.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/** ROI comes from the backend; null means the action had no cost. */
export function formatRoi(roi) {
  if (roi === null || roi === undefined) return 'no cost';
  return `${Math.round(roi).toLocaleString()}×`;
}
