// Diverging red-white-green background for a value scaled by the largest
// magnitude in its current context. Reuses the same green/red already used
// for stat-cell tone elsewhere on the site, varying the opacity continuously
// by magnitude instead of a flat on/off tint.
export function heatBackground(value: number | null | undefined, maxAbs: number): string | undefined {
  if (value === null || value === undefined || Number.isNaN(value) || maxAbs <= 0) return undefined;
  const t = Math.max(-1, Math.min(1, value / maxAbs));
  const alpha = Math.abs(t) * 0.32;
  const [r, g, b] = t >= 0 ? [75, 123, 87] : [163, 80, 66];
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`;
}
