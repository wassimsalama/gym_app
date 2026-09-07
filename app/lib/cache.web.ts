/**
 * Read cache — browser implementation (spec §8.4).
 *
 * localStorage rather than IndexedDB here, unlike the write queue. The
 * distinction is what is at stake: losing a cached read costs a spinner, while
 * losing a queued write costs the user's workout. A cache does not need
 * transactions.
 */

const PREFIX = 'gym-cache:';

export async function readCache<T>(key: string): Promise<T | null> {
  try {
    const raw = globalThis.localStorage?.getItem(PREFIX + key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    // A cache miss and a broken cache are the same thing to the caller.
    return null;
  }
}

export async function writeCache(key: string, value: unknown): Promise<void> {
  try {
    globalThis.localStorage?.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Quota exceeded or storage blocked; caching is only ever an optimisation.
  }
}

/** Wipe on sign-out — the next user must not see the previous one's data. */
export async function clearCache(): Promise<void> {
  try {
    const storage = globalThis.localStorage;
    if (!storage) return;
    Object.keys(storage)
      .filter((key) => key.startsWith(PREFIX))
      .forEach((key) => storage.removeItem(key));
  } catch {
    // Nothing to clean up if storage was never available.
  }
}
