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

/** First day of the month containing `iso`. */
export function startOfMonth(iso: IsoDate = today()): IsoDate {
  const date = fromIsoDate(iso);
  return toIsoDate(new Date(date.getFullYear(), date.getMonth(), 1));
}

/** Shift by whole months, clamping the day (31 Jan + 1 month -> 28/29 Feb). */
export function addMonths(iso: IsoDate, months: number): IsoDate {
  const date = fromIsoDate(iso);
  const targetMonth = date.getMonth() + months;
  const shifted = new Date(date.getFullYear(), targetMonth, 1);
  const lastDay = new Date(shifted.getFullYear(), shifted.getMonth() + 1, 0).getDate();
  shifted.setDate(Math.min(date.getDate(), lastDay));
  return toIsoDate(shifted);
}

export function daysInMonth(iso: IsoDate): number {
  const date = fromIsoDate(iso);
  return new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
}

/** Weekday index of the 1st, Monday = 0 — matches the Monday-anchored week (§7.6). */
export function firstWeekdayOfMonth(iso: IsoDate): number {
  const date = fromIsoDate(startOfMonth(iso));
  return (date.getDay() + 6) % 7;
}

export function isFuture(iso: IsoDate, reference: IsoDate = today()): boolean {
  return iso > reference;
}

export function isSameMonth(a: IsoDate, b: IsoDate): boolean {
  return a.slice(0, 7) === b.slice(0, 7);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Sept 1" style label for charts and cards. */
export function formatShort(iso: IsoDate): string {
  const date = fromIsoDate(iso);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

const MONTHS_LONG = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

/** "September 2026" — the calendar header. */
export function formatMonth(iso: IsoDate): string {
  const date = fromIsoDate(iso);
  return `${MONTHS_LONG[date.getMonth()]} ${date.getFullYear()}`;
}

/** "Today" / "Yesterday" / "Sep 3" — for a date the user picked. */
export function formatRelativeDay(iso: IsoDate, reference: IsoDate = today()): string {
  if (iso === reference) return 'Today';
  if (iso === addDays(reference, -1)) return 'Yesterday';
  return formatShort(iso);
}

export function formatLong(iso: IsoDate): string {
  const date = fromIsoDate(iso);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
}
