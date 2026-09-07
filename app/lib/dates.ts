/**
 * The single date util (spec §11).
 *
 * The API takes ISO `YYYY-MM-DD` in the user's *local* sense — the server never
 * derives "today" from UTC (spec §6). So local dates are formatted from the
 * device clock's calendar fields, never from `toISOString()`, which would roll
 * the date over for anyone west of UTC in the evening.
 */

export type IsoDate = string; // YYYY-MM-DD

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

/** Format a Date's *local* calendar day as YYYY-MM-DD. */
export function toIsoDate(date: Date): IsoDate {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Today, per the device's own clock. */
export function today(): IsoDate {
  return toIsoDate(new Date());
}

/** Parse YYYY-MM-DD into a local-midnight Date (not UTC midnight). */
export function fromIsoDate(iso: IsoDate): Date {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day);
}

export function addDays(iso: IsoDate, days: number): IsoDate {
  const date = fromIsoDate(iso);
  date.setDate(date.getDate() + days);
  return toIsoDate(date);
}

export function yesterday(): IsoDate {
  return addDays(today(), -1);
}

/** Whole days from `a` to `b`; negative when `b` is earlier. */
export function daysBetween(a: IsoDate, b: IsoDate): number {
  const ms = fromIsoDate(b).getTime() - fromIsoDate(a).getTime();
  return Math.round(ms / 86_400_000);
}

/** Monday-anchored week start, matching the volume rings (spec §7.6). */
export function startOfWeek(iso: IsoDate = today()): IsoDate {
  const date = fromIsoDate(iso);
  const dayOfWeek = (date.getDay() + 6) % 7; // Monday = 0
  return addDays(iso, -dayOfWeek);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Sept 1" style label for charts and cards. */
export function formatShort(iso: IsoDate): string {
  const date = fromIsoDate(iso);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

export function formatLong(iso: IsoDate): string {
  const date = fromIsoDate(iso);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
}
