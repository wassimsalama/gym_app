/**
 * Read cache (spec §8.4).
 *
 * The last successful response per key is kept in SQLite so screens render
 * instantly from disk and refresh in the background. The app must be fully
 * readable with zero connectivity — a user in a basement gym should still see
 * last session's numbers.
 */

import * as SQLite from 'expo-sqlite';

const DB_NAME = 'gym-cache.db';

let db: SQLite.SQLiteDatabase | null = null;

async function database(): Promise<SQLite.SQLiteDatabase> {
  if (db) return db;
  db = await SQLite.openDatabaseAsync(DB_NAME);
  await db.execAsync(`
    pragma journal_mode = WAL;
    create table if not exists cached_reads (
      key text primary key,
      value_json text not null,
      cached_at text not null
    );
  `);
  return db;
}

export async function readCache<T>(key: string): Promise<T | null> {
  try {
    const handle = await database();
    const row = await handle.getFirstAsync<{ value_json: string }>(
      'select value_json from cached_reads where key = ?',
      [key],
    );
    return row ? (JSON.parse(row.value_json) as T) : null;
  } catch {
    // A cache miss and a broken cache are the same thing to the caller.
    return null;
  }
}

export async function writeCache(key: string, value: unknown): Promise<void> {
  try {
    const handle = await database();
    await handle.runAsync(
      `insert into cached_reads (key, value_json, cached_at) values (?, ?, ?)
       on conflict(key) do update set value_json = excluded.value_json,
                                      cached_at = excluded.cached_at`,
      [key, JSON.stringify(value), new Date().toISOString()],
    );
  } catch {
    // Caching is an optimisation; never fail a screen over it.
  }
}

/** Wipe on sign-out — the next user must not see the previous one's data. */
export async function clearCache(): Promise<void> {
  try {
    const handle = await database();
    await handle.runAsync('delete from cached_reads');
  } catch {
    // Nothing useful to do; the store is per-device and will be overwritten.
  }
}
