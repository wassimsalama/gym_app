/**
 * Macro arithmetic (spec §2.2).
 *
 * The cross-check exists because a mistyped macro is the most common logging
 * error and the one that quietly poisons the TDEE estimate. It is a note, never
 * a blocker: §2.2 says show it gently and always allow the save.
 */

export const KCAL_PER_G = { protein: 4, carbs: 4, fat: 9 } as const;

/** Tolerated gap between entered and computed calories before saying anything. */
export const MISMATCH_THRESHOLD = 0.1;

export function computedCalories(protein: number, carbs: number, fat: number): number {
  return protein * KCAL_PER_G.protein + carbs * KCAL_PER_G.carbs + fat * KCAL_PER_G.fat;
}

export type MacroCheck = {
  computed: number;
  entered: number;
  /** Signed fraction: positive when the entered figure is the higher one. */
  drift: number;
  mismatched: boolean;
};

/**
 * Compare entered calories against 4P + 4C + 9F.
 * Returns null when there is not enough filled in to say anything useful.
 */
export function checkMacros(
  calories: number | null,
  protein: number | null,
  carbs: number | null,
  fat: number | null,
): MacroCheck | null {
  if (calories === null || calories <= 0) return null;
  if (protein === null && carbs === null && fat === null) return null;

  const computed = computedCalories(protein ?? 0, carbs ?? 0, fat ?? 0);
  if (computed <= 0) return null;

  const drift = (calories - computed) / computed;

  return {
    computed,
    entered: calories,
    drift,
    mismatched: Math.abs(drift) > MISMATCH_THRESHOLD,
  };
}

/** Parse a whole-number field; null for anything unusable. */
export function parseWholeNumber(raw: string, max: number): number | null {
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < 0 || value > max) return null;
  return Math.round(value);
}

/** Mean of the values present, ignoring days with nothing logged. */
export function meanOf(values: (number | null | undefined)[]): number | null {
  const present = values.filter((v): v is number => typeof v === 'number');
  if (present.length === 0) return null;
  return present.reduce((sum, v) => sum + v, 0) / present.length;
}
