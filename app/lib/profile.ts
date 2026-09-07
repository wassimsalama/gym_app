/**
 * The user's display unit.
 *
 * The API owns this (`profiles.unit`), but every screen needs it to render, so
 * it is read once from /health-auth and cached. Weights are kg on the wire
 * regardless — this only decides what the user sees (spec §5).
 */

import { useEffect, useState } from 'react';

import { healthAuth } from '@/lib/api';
import type { Unit } from '@/lib/units';

const DEFAULT_UNIT: Unit = 'lb';

export function useUnit(): Unit {
  const [unit, setUnit] = useState<Unit>(DEFAULT_UNIT);

  useEffect(() => {
    let active = true;
    healthAuth()
      .then((me) => {
        if (active) setUnit(me.unit);
      })
      .catch(() => {
        // Non-fatal: fall back to the default rather than blocking a screen.
      });
    return () => {
      active = false;
    };
  }, []);

  return unit;
}
