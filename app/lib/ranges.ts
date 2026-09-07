/**
 * Time spans for the weight history graph.
 *
 * The series arrives already smoothed by the API, computed over the full
 * history. Narrowing the *view* here is therefore safe: each point's 7-day
 * trailing average was calculated using the days before it, including days
 * that fall outside the chosen span. Re-smoothing a filtered slice would give
 * a different — and wrong — line at its left edge.
 */

import type { WeightSeriesPoint } from '@/lib/api';
import { addDays, type IsoDate } from '@/lib/dates';

export type RangeKey = '2W' | '1M' | '3M' | 'ALL';

export const RANGES: readonly { value: RangeKey; label: string; days: number | null }[] = [
  { value: '2W', label: '2 weeks', days: 14 },
  { value: '1M', label: '1 month', days: 30 },
  { value: '3M', label: '3 months', days: 90 },
  { value: 'ALL', label: 'All', days: null },
];

export const RANGE_OPTIONS = RANGES.map(({ value, label }) => ({
  value,
  label: value === 'ALL' ? 'All' : value,
}));

export function rangeDays(key: RangeKey): number | null {
  return RANGES.find((r) => r.value === key)?.days ?? null;
}

export function rangeLabel(key: RangeKey): string {
  return RANGES.find((r) => r.value === key)?.label ?? '';
}

/** The slice of the series covered by `key`, anchored to its most recent point. */
export function sliceSeries(series: WeightSeriesPoint[], key: RangeKey): WeightSeriesPoint[] {
  const days = rangeDays(key);
  if (days === null || series.length === 0) return series;

  const latest = series[series.length - 1].date;
  const cutoff: IsoDate = addDays(latest, -(days - 1));
  return series.filter((point) => point.date >= cutoff);
}

/**
 * Change in the smoothed line across a slice — what the user actually moved
 * over that span, with daily noise already taken out.
 * Null when there is nothing to compare against.
 */
export function deltaOver(slice: WeightSeriesPoint[]): number | null {
  if (slice.length < 2) return null;
  return slice[slice.length - 1].smoothed_kg - slice[0].smoothed_kg;
}

/**
 * Ranges with too little history to be worth offering. A span is available
 * once the series reaches back far enough to say something about it.
 */
export function unavailableRanges(series: WeightSeriesPoint[]): RangeKey[] {
  if (series.length < 2) return RANGES.filter((r) => r.value !== 'ALL').map((r) => r.value);

  const span =
    (new Date(series[series.length - 1].date).getTime() - new Date(series[0].date).getTime()) /
      86_400_000 +
    1;

  // Offer a span once there is at least half of it on record; below that the
  // graph is mostly empty axis.
  return RANGES.filter((r) => r.days !== null && span < r.days / 2).map((r) => r.value);
}
