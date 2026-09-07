/**
 * Durable storage for the write queue — browser implementation (spec §8).
 *
 * IndexedDB rather than localStorage: a queue is written from every tab the
 * user has open, and localStorage's read-modify-write would let two tabs
 * silently clobber each other's pending writes. IndexedDB gives real
 * transactions, so a queued workout cannot vanish because a second tab saved a
 * weight at the same moment.
 *
 * Mirrors the native module's shape exactly; `lib/sync.ts` cannot tell them
 * apart.
 */

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

const DB_NAME = 'gym-sync';
const DB_VERSION = 1;
const STORE = 'pending_ops';

let connection: Promise<IDBDatabase> | null = null;

function open(): Promise<IDBDatabase> {
  if (connection) return connection;

  connection = new Promise((resolve, reject) => {
    const request = globalThis.indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE)) {
        // autoIncrement gives the same monotonic ids the native table has, so
        // "oldest first" means the same thing on both platforms.
        database.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

  return connection;
}

async function transact<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const database = await open();
  return new Promise<T>((resolve, reject) => {
    const transaction = database.transaction(STORE, mode);
    const request = run(transaction.objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function insert(op: NewOp): Promise<number> {
  const key = await transact<IDBValidKey>(
    'readwrite',
    (store) => store.add({ ...op, attempts: 0, next_attempt_at: null }) as IDBRequest<IDBValidKey>,
  );
  return Number(key);
}

export async function get(id: number): Promise<StoredOp | null> {
  return (await transact<StoredOp | undefined>('readonly', (store) => store.get(id))) ?? null;
}

async function all(): Promise<StoredOp[]> {
  const rows = await transact<StoredOp[]>('readonly', (store) => store.getAll());
  return rows.sort((a, b) => a.id - b.id);
}

export async function due(now: string): Promise<number[]> {
  const rows = await all();
  return rows
    .filter((op) => op.next_attempt_at === null || op.next_attempt_at <= now)
    .map((op) => op.id);
}

export async function counts(strugglingAfter: number): Promise<QueueCounts> {
  const rows = await all();
  return {
    pending: rows.length,
    struggling: rows.filter((op) => op.attempts > strugglingAfter).length,
  };
}

export async function bumpAttempt(id: number, nextAttemptAt: string): Promise<void> {
  const existing = await get(id);
  if (!existing) return;
  await transact('readwrite', (store) =>
    store.put({ ...existing, attempts: existing.attempts + 1, next_attempt_at: nextAttemptAt }),
  );
}

export async function clearBackoff(): Promise<void> {
  const rows = await all();
  await Promise.all(
    rows.map((op) => transact('readwrite', (store) => store.put({ ...op, next_attempt_at: null }))),
  );
}

export async function remove(id: number): Promise<void> {
  await transact('readwrite', (store) => store.delete(id));
}

export async function clear(): Promise<void> {
  await transact('readwrite', (store) => store.clear());
}
