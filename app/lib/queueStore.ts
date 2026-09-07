/**
 * Durable storage for the write queue — native implementation (spec §8).
 *
 * `expo-sqlite` has no working web build in this SDK (it imports a wasm file it
 * does not ship), so the queue lives behind this interface with an IndexedDB
 * sibling in `queueStore.web.ts`. Metro picks the right one per platform, and
 * `lib/sync.ts` never learns which it got.
 */

import * as SQLite from 'expo-sqlite';

export type StoredOp = {
  id: number;
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path: string;
  body_json: string | null;
  created_at: string;
  attempts: number;
  next_attempt_at: string | null;
};

export type NewOp = Omit<StoredOp, 'id' | 'attempts' | 'next_attempt_at'>;

export type QueueCounts = { pending: number; struggling: number };

const DB_NAME = 'gym-sync.db';

let db: SQLite.SQLiteDatabase | null = null;

async function database(): Promise<SQLite.SQLiteDatabase> {
  if (db) return db;

  db = await SQLite.openDatabaseAsync(DB_NAME);
  await db.execAsync(`
    pragma journal_mode = WAL;
    create table if not exists pending_ops (
      id integer primary key autoincrement,
      method text not null,
      path text not null,
      body_json text,
      created_at text not null,
      attempts integer not null default 0,
      next_attempt_at text
    );
  `);
  return db;
}

export async function insert(op: NewOp): Promise<number> {
  const handle = await database();
  const result = await handle.runAsync(
    `insert into pending_ops (method, path, body_json, created_at, attempts)
     values (?, ?, ?, ?, 0)`,
    [op.method, op.path, op.body_json, op.created_at],
  );
  return result.lastInsertRowId;
}

export async function get(id: number): Promise<StoredOp | null> {
  const handle = await database();
  return (
    (await handle.getFirstAsync<StoredOp>('select * from pending_ops where id = ?', [id])) ?? null
  );
}

/** Ids of ops whose backoff has elapsed, oldest first. */
export async function due(now: string): Promise<number[]> {
  const handle = await database();
  const rows = await handle.getAllAsync<{ id: number }>(
    `select id from pending_ops
     where next_attempt_at is null or next_attempt_at <= ?
     order by id asc`,
    [now],
  );
  return rows.map((row) => row.id);
}

export async function counts(strugglingAfter: number): Promise<QueueCounts> {
  const handle = await database();
  const row = await handle.getFirstAsync<QueueCounts>(
    `select count(*) as pending,
            coalesce(sum(case when attempts > ? then 1 else 0 end), 0) as struggling
     from pending_ops`,
    [strugglingAfter],
  );
  return { pending: row?.pending ?? 0, struggling: row?.struggling ?? 0 };
}

export async function bumpAttempt(id: number, nextAttemptAt: string): Promise<void> {
  const handle = await database();
  await handle.runAsync(
    'update pending_ops set attempts = attempts + 1, next_attempt_at = ? where id = ?',
    [nextAttemptAt, id],
  );
}

export async function clearBackoff(): Promise<void> {
  const handle = await database();
  await handle.runAsync('update pending_ops set next_attempt_at = null');
}

export async function remove(id: number): Promise<void> {
  const handle = await database();
  await handle.runAsync('delete from pending_ops where id = ?', [id]);
}

export async function clear(): Promise<void> {
  const handle = await database();
  await handle.runAsync('delete from pending_ops');
}
