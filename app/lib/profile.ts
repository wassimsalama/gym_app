/**
 * The user's display unit.
 *
 * The API owns this (`profiles.unit`), but every screen needs it to render, so
 * it is read once and shared. Weights are kg on the wire regardless — this only
 * decides what the user sees (spec §5).
 *
 * Shared rather than per-hook. Each `useUnit()` used to fetch on its own, which
 * was fine while the value never changed: every screen arrived at the same
 * answer independently. Now that it is switchable, independent copies would
 * mean the Weight tab still reading pounds after Settings moved to kilos, until
 * each screen happened to remount. One value, one fetch, every subscriber
 * notified.
 */

import { useEffect, useState } from 'react';

import { healthAuth, updateUnit as pushUnit } from '@/lib/api';
import type { Unit } from '@/lib/units';

const DEFAULT_UNIT: Unit = 'lb';

let current: Unit = DEFAULT_UNIT;
let loaded = false;
let inFlight: Promise<void> | null = null;

const listeners = new Set<(unit: Unit) => void>();

function publish(next: Unit): void {
  current = next;
  for (const listener of listeners) listener(next);
}

/** Fetch once, no matter how many screens mount at the same moment. */
function ensureLoaded(): Promise<void> {
  if (loaded) return Promise.resolve();
  inFlight ??= healthAuth()
    .then((me) => {
      loaded = true;
      publish(me.unit);
    })
    .catch(() => {
      // Non-fatal: fall back to the default rather than blocking a screen.
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

export function useUnit(): Unit {
  const [unit, setUnit] = useState<Unit>(current);

  useEffect(() => {
    listeners.add(setUnit);
    void ensureLoaded();
    return () => {
      listeners.delete(setUnit);
    };
  }, []);

  return unit;
}

/**
 * Switch the display unit.
 *
 * Applied locally first so the change is instant, then persisted. On failure it
 * rolls back — showing kilos while the server still says pounds would survive
 * until the next reload and quietly misreport every number on screen.
 */
export async function setUnit(next: Unit): Promise<void> {
  const previous = current;
  if (next === previous) return;

  publish(next);
  try {
    const me = await pushUnit(next);
    loaded = true;
    publish(me.unit);
  } catch (error) {
    publish(previous);
    throw error;
  }
}
