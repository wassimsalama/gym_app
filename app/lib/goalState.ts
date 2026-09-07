/**
 * Reading a goal's health from its numbers.
 *
 * A goal whose baseline sits between the user and their target is broken in a
 * quiet way: the progress bar reads 0% and stays there until they claw all the
 * way back past the old starting weight. Detecting that is what lets the UI
 * offer a fix instead of showing a dead bar.
 */

export type GoalNumbers = {
  start_weight_kg: number;
  goal_weight_kg: number;
};

/**
 * How far past the starting weight, in the wrong direction, the user now is —
 * or null when they are between start and goal as expected.
 */
export function driftFromBaselineKg(
  goal: GoalNumbers,
  currentKg: number | null | undefined,
): number | null {
  if (currentKg === null || currentKg === undefined) return null;

  const losing = goal.goal_weight_kg < goal.start_weight_kg;
  const drift = currentKg - goal.start_weight_kg;
  const wrongWay = losing ? drift > 0 : drift < 0;

  return wrongWay ? Math.abs(drift) : null;
}

/** True when the baseline is stale enough that the bar cannot move for a while. */
export function baselineIsStale(goal: GoalNumbers, currentKg: number | null | undefined): boolean {
  return driftFromBaselineKg(goal, currentKg) !== null;
}
