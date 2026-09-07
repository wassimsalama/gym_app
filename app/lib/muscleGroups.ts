/** Mirrors the §5 vocabulary the API validates against. */
export const MUSCLE_GROUPS = [
  'chest',
  'back',
  'shoulders',
  'biceps',
  'triceps',
  'quads',
  'hamstrings',
  'glutes',
  'calves',
  'core',
  'other',
] as const;

export type MuscleGroup = (typeof MUSCLE_GROUPS)[number];
