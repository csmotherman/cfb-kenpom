// Per-column conditional-formatting color scale: red (worst) - white/paper
// (middle) - green (best), like a spreadsheet 3-color scale. Each column is
// scaled independently against its own min/max, not a shared/fixed range.
const GREEN: [number, number, number] = [99, 190, 123];
const RED: [number, number, number] = [248, 105, 107];
// Matches the table's paper background so a mid-range value blends in
// instead of showing as a stark white highlight.
const MID: [number, number, number] = [250, 248, 242];

function mix(a: [number, number, number], b: [number, number, number], t: number): [number, number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

export function columnRange(values: Array<number | null | undefined>): { min: number; max: number } {
  const nums = values.filter((v): v is number => v !== null && v !== undefined && !Number.isNaN(v));
  if (!nums.length) return { min: 0, max: 0 };
  return { min: Math.min(...nums), max: Math.max(...nums) };
}

export function heatBackground(
  value: number | null | undefined,
  range: { min: number; max: number },
  lowerBetter = false,
): string | undefined {
  if (value === null || value === undefined || Number.isNaN(value) || range.max <= range.min) return undefined;
  let t = ((value - range.min) / (range.max - range.min)) * 2 - 1; // -1..1
  if (lowerBetter) t = -t;
  t = Math.max(-1, Math.min(1, t));
  const [r, g, b] = t >= 0 ? mix(MID, GREEN, t) : mix(MID, RED, -t);
  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
}
