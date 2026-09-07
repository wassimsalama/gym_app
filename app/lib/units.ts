/**
 * The only place in the app where weight leaves or enters kilograms.
 *
 * The database and the API speak kg exclusively (spec §5). Every display
 * string and every user-typed number passes through this module, so a unit bug
 * can only ever live here.
 */

export type Unit = 'kg' | 'lb';

const LB_PER_KG = 2.2046226218487757;

/** Smallest plate change worth a tap, per unit (spec §2.3). */
export const WEIGHT_STEP: Record<Unit, number> = { kg: 1.25, lb: 2.5 };

export function kgToLb(kg: number): number {
  return kg * LB_PER_KG;
}

export function lbToKg(lb: number): number {
  return lb / LB_PER_KG;
}

/** Convert a canonical kg value into the user's unit. */
export function fromKg(kg: number, unit: Unit): number {
  return unit === 'kg' ? kg : kgToLb(kg);
}

/** Convert a number the user typed (in their unit) back to canonical kg. */
export function toKg(value: number, unit: Unit): number {
  return unit === 'kg' ? value : lbToKg(value);
}

function round(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

/**
 * Format a canonical kg value for display, e.g. `formatWeight(84.1, 'lb')`
 * -> `"185.4 lb"`. Body weights read best at one decimal; whole numbers drop it.
 */
export function formatWeight(
  kg: number | null | undefined,
  unit: Unit,
  options: { decimals?: number; withUnit?: boolean } = {},
): string {
  if (kg === null || kg === undefined || Number.isNaN(kg)) return '—';
  const { decimals = 1, withUnit = true } = options;
  const value = round(fromKg(kg, unit), decimals);
  const text = Number.isInteger(value) ? String(value) : value.toFixed(decimals);
  return withUnit ? `${text} ${unit}` : text;
}

/** Format a difference, always signed: `"−4.2 lb"` / `"+0.8 lb"`. */
export function formatDelta(deltaKg: number | null | undefined, unit: Unit): string {
  if (deltaKg === null || deltaKg === undefined || Number.isNaN(deltaKg)) return '—';
  const value = round(fromKg(deltaKg, unit), 1);
  if (value === 0) return `0 ${unit}`;
  // U+2212 minus, not a hyphen — it aligns with digits.
  const sign = value > 0 ? '+' : '−';
  return `${sign}${Math.abs(value).toFixed(1)} ${unit}`;
}

/**
 * Parse free text from a numeric keyboard into canonical kg.
 * Returns null for anything that is not a usable positive number.
 */
export function parseWeightInput(raw: string, unit: Unit): number | null {
  const cleaned = raw.replace(',', '.').trim();
  if (cleaned === '') return null;
  const value = Number(cleaned);
  if (!Number.isFinite(value) || value <= 0) return null;
  return round(toKg(value, unit), 3);
}

/** Step a displayed weight up or down by one plate increment, in kg. */
export function stepKg(kg: number, direction: 1 | -1, unit: Unit): number {
  const stepInUnit = WEIGHT_STEP[unit];
  const next = fromKg(kg, unit) + direction * stepInUnit;
  return round(toKg(Math.max(next, 0), unit), 3);
}
