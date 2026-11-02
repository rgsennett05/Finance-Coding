/** Cross-sectional percentile rank in [0, 1]; nulls get null. */
export function percentiles(values) {
  const present = values.map((v, i) => [v, i]).filter(([v]) => Number.isFinite(v)).sort((a, b) => a[0] - b[0]);
  const out = values.map(() => null);
  present.forEach(([, i], rank) => (out[i] = present.length === 1 ? 0.5 : rank / (present.length - 1)));
  return out;
}

export const avg = (xs) => {
  const v = xs.filter(Number.isFinite);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
};
