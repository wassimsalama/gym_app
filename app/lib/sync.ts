/**
 * Offline-first write queue (spec §8).
 *
 * Every write goes through here: it is durably enqueued in SQLite, the caller
 * gets an optimistic result immediately, and a flush is attempted in the
 * background. Nothing the user logs can be lost to a dead connection, and
 * nothing blocks on one.
 *
 * Safety rests on the server's idempotency guarantees (§8.3), not on this
 * queue being clever:
 *   - daily logs upsert by (user, date)
 *   - sessions dedupe on client_uuid
 * So replaying an operation whose response was lost is always safe. The queue
 * therefore retries freely and never has to reason about partial success.
 */

import NetInfo from '@react-native-community/netinfo';
import * as SQLite from 'expo-sqlite';
import { AppState, type AppStateStatus } from 'react-native';

import { ApiError, request } from '@/lib/http';

export type PendingOp = {
  id: number;
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path: string;
  body: unknown;
  created_at: string;
  attempts: number;
};

/** Surfaced in tab headers once anything has struggled (§8.2). */
export type SyncState = {
  pending: number;
  /** Ops that have failed more than `ATTEMPTS_BEFORE_VISIBLE` times. */
  struggling: number;
  flushing: boolean;
};

const DB_NAME = 'gym-sync.db';
const ATTEMPTS_BEFORE_VISIBLE = 3;
const BASE_BACKOFF_MS = 2_000;
const MAX_BACKOFF_MS = 5 * 60_000;

let db: SQLite.SQLiteDatabase | null = null;
let flushing = false;
let listenersBound = false;

const subscribers = new Set<(state: SyncState) => void>();

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

function backoffMs(attempts: number): number {
  return Math.min(BASE_BACKOFF_MS * 2 ** attempts, MAX_BACKOFF_MS);
}

async function currentState(): Promise<SyncState> {
  const handle = await database();
  const row = await handle.getFirstAsync<{ pending: number; struggling: number }>(
    `select count(*) as pending,
            coalesce(sum(case when attempts > ? then 1 else 0 end), 0) as struggling
     from pending_ops`,
    [ATTEMPTS_BEFORE_VISIBLE],
  );
  return {
    pending: row?.pending ?? 0,
    struggling: row?.struggling ?? 0,
    flushing,
  };
}

async function notify(): Promise<void> {
  if (subscribers.size === 0) return;
  const state = await currentState();
  subscribers.forEach((listener) => listener(state));
}

export function subscribe(listener: (state: SyncState) => void): () => void {
  subscribers.add(listener);
  void notify();
  return () => subscribers.delete(listener);
}

/**
 * Queue a write and try to send it now.
 *
 * Returns the server's response when the network cooperates, or null when the
 * op was queued for later. Callers apply their optimistic update either way —
 * a null is "saved, not yet synced", never "failed".
 */
export async function enqueue<T>(
  method: PendingOp['method'],
  path: string,
  body?: unknown,
): Promise<T | null> {
  const handle = await database();
  const result = await handle.runAsync(
    `insert into pending_ops (method, path, body_json, created_at, attempts)
     values (?, ?, ?, ?, 0)`,
    [method, path, body === undefined ? null : JSON.stringify(body), new Date().toISOString()],
  );

  void notify();
  return flushOne<T>(result.lastInsertRowId);
}

/** Send a single queued op, deleting it on success or terminal failure. */
async function flushOne<T>(id: number): Promise<T | null> {
  const handle = await database();
  const op = await handle.getFirstAsync<{
    id: number;
    method: PendingOp['method'];
    path: string;
    body_json: string | null;
    attempts: number;
  }>('select id, method, path, body_json, attempts from pending_ops where id = ?', [id]);

  if (!op) return null;

  try {
    const response = await request<T>(op.path, {
      method: op.method,
      body: op.body_json === null ? undefined : JSON.parse(op.body_json),
    });
    await handle.runAsync('delete from pending_ops where id = ?', [op.id]);
    void notify();
    return response;
  } catch (error) {
    await recordFailure(op.id, op.attempts, error);
    void notify();
    return null;
  }
}

/**
 * A failed op either waits for a retry or is dropped.
 *
 * Retrying a request the server *rejected* is pointless — a 422 will be a 422
 * forever, and leaving it queued would block everything behind it and show a
 * permanent "unsynced" badge the user cannot clear. Only failures that might
 * resolve on their own are kept.
 */
async function recordFailure(id: number, attempts: number, error: unknown): Promise<void> {
  const handle = await database();
  const retryable = !(error instanceof ApiError) || error.isRetryable;

  if (!retryable) {
    await handle.runAsync('delete from pending_ops where id = ?', [id]);
    return;
  }

  const next = new Date(Date.now() + backoffMs(attempts)).toISOString();
  await handle.runAsync(
    'update pending_ops set attempts = attempts + 1, next_attempt_at = ? where id = ?',
    [next, id],
  );
}

/**
 * Send everything that is due, oldest first.
 *
 * Order matters: a session's custom exercise must exist before the session
 * referencing it, so the queue stops at the first failure rather than skipping
 * ahead and landing writes out of order.
 */
export async function flush(): Promise<void> {
  if (flushing) return;
  flushing = true;
  void notify();

  try {
    const handle = await database();
    const now = new Date().toISOString();
    const due = await handle.getAllAsync<{ id: number }>(
      `select id from pending_ops
       where next_attempt_at is null or next_attempt_at <= ?
       order by id asc`,
      [now],
    );

    for (const { id } of due) {
      const before = await handle.getFirstAsync<{ attempts: number }>(
        'select attempts from pending_ops where id = ?',
        [id],
      );
      await flushOne(id);
      const after = await handle.getFirstAsync<{ attempts: number }>(
        'select attempts from pending_ops where id = ?',
        [id],
      );
      // Still present with a bumped attempt count means it failed; stop so
      // later ops cannot overtake it.
      if (after && before && after.attempts > before.attempts) break;
    }
  } finally {
    flushing = false;
    void notify();
  }
}

/** Flush triggers from §8.2: reconnect and app foreground. */
export function startSync(): () => void {
  if (listenersBound) return () => {};
  listenersBound = true;

  const unsubscribeNet = NetInfo.addEventListener((state) => {
    if (state.isConnected && state.isInternetReachable !== false) void flush();
  });

  const appStateSub = AppState.addEventListener('change', (status: AppStateStatus) => {
    if (status === 'active') void flush();
  });

  void flush();

  return () => {
    listenersBound = false;
    unsubscribeNet();
    appStateSub.remove();
  };
}

/** Called after a successful token refresh — queued 401s may now succeed. */
export async function flushAfterAuthRefresh(): Promise<void> {
  const handle = await database();
  await handle.runAsync('update pending_ops set next_attempt_at = null');
  await flush();
}

/** Test/debug helper: drop everything queued. */
export async function clearQueue(): Promise<void> {
  const handle = await database();
  await handle.runAsync('delete from pending_ops');
  void notify();
}
