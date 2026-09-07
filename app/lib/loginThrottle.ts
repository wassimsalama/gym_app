/**
 * Slowing down repeated failed sign-ins.
 *
 * Be clear about what this is and is not. An attacker guessing passwords does
 * not use this form — they call Supabase's auth endpoint directly, where none
 * of this code runs. The real defences are Supabase's own per-IP auth rate
 * limits, leaked-password protection and a CAPTCHA, all configured in its
 * dashboard.
 *
 * What this does buy:
 *   - someone poking at a friend's account on a shared laptop gives up;
 *   - a stuck client cannot hammer the auth endpoint in a loop;
 *   - the person locked out is told what is happening and when to try again,
 *     instead of watching a form fail silently.
 *
 * State is per device and per email, so one person's mistyping never affects
 * anyone else.
 */

const STORAGE_KEY = 'gym-login-attempts';

/** Failures tolerated before any delay is imposed. */
export const FREE_ATTEMPTS = 4;

/** Lockout after each subsequent failure, in seconds. The last repeats. */
const BACKOFF_SECONDS = [30, 60, 300, 900];

type Record = { failures: number; lockedUntil: number };

function readAll(): { [email: string]: Record } {
  try {
    return JSON.parse(globalThis.localStorage?.getItem(STORAGE_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function writeAll(state: { [email: string]: Record }): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Storage unavailable — throttling degrades to nothing, which is the same
    // position as before this existed. Never block sign-in over it.
  }
}

function key(email: string): string {
  return email.trim().toLowerCase();
}

/** Seconds still to wait for this address, or 0 if it may try now. */
export function secondsRemaining(email: string): number {
  const record = readAll()[key(email)];
  if (!record) return 0;
  return Math.max(0, Math.ceil((record.lockedUntil - Date.now()) / 1000));
}

/** Record a failure and return how long the address must now wait. */
export function recordFailure(email: string): number {
  const state = readAll();
  const id = key(email);
  const failures = (state[id]?.failures ?? 0) + 1;

  const over = failures - FREE_ATTEMPTS;
  const wait = over <= 0 ? 0 : BACKOFF_SECONDS[Math.min(over - 1, BACKOFF_SECONDS.length - 1)];

  state[id] = { failures, lockedUntil: Date.now() + wait * 1000 };
  writeAll(state);

  return wait;
}

/** Clear the record for an address after a successful sign-in. */
export function recordSuccess(email: string): void {
  const state = readAll();
  delete state[key(email)];
  writeAll(state);
}

/** "30 seconds" / "2 minutes" — for telling the user what to expect. */
export function describeWait(seconds: number): string {
  if (seconds < 60) return `${seconds} second${seconds === 1 ? '' : 's'}`;
  const minutes = Math.ceil(seconds / 60);
  return `${minutes} minute${minutes === 1 ? '' : 's'}`;
}
