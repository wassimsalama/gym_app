import { useEffect, useState } from 'react';

import { subscribe, type SyncState } from '@/lib/sync';

const IDLE: SyncState = { pending: 0, struggling: 0, flushing: false };

/** Live view of the write queue, for the "N unsynced" indicator (§8.2). */
export function useSyncState(): SyncState {
  const [state, setState] = useState<SyncState>(IDLE);

  useEffect(() => subscribe(setState), []);

  return state;
}
