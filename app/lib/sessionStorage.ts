/**
 * Where the Supabase session is kept, per platform.
 *
 * Native gets the keychain via SecureStore. The browser has no equivalent —
 * localStorage is the standard place, readable by any script on the origin,
 * which is the accepted trade-off for a web app and the reason the site must
 * stay free of third-party scripts.
 */

import type { SupportedStorage } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

/**
 * SecureStore refuses values much over 2 KB, and a Supabase session (access
 * token + refresh token + user object) regularly exceeds that. Split across
 * numbered chunks with a count under the base key.
 */
const CHUNK_SIZE = 1536;

const chunkedSecureStore: SupportedStorage = {
  async getItem(key) {
    const count = await SecureStore.getItemAsync(`${key}.count`);
    if (count === null) return null;
    const parts = await Promise.all(
      Array.from({ length: Number(count) }, (_, i) => SecureStore.getItemAsync(`${key}.${i}`)),
    );
    return parts.some((p) => p === null) ? null : parts.join('');
  },

  async setItem(key, value) {
    await chunkedSecureStore.removeItem(key);
    const chunks = value.match(new RegExp(`.{1,${CHUNK_SIZE}}`, 'gs')) ?? [''];
    await Promise.all(chunks.map((chunk, i) => SecureStore.setItemAsync(`${key}.${i}`, chunk)));
    await SecureStore.setItemAsync(`${key}.count`, String(chunks.length));
  },

  async removeItem(key) {
    const count = await SecureStore.getItemAsync(`${key}.count`);
    if (count === null) return;
    await Promise.all(
      Array.from({ length: Number(count) }, (_, i) => SecureStore.deleteItemAsync(`${key}.${i}`)),
    );
    await SecureStore.deleteItemAsync(`${key}.count`);
  },
};

/**
 * localStorage, guarded. Private browsing and storage-blocking settings make
 * every call throw; a session that cannot persist should degrade to signing in
 * again, not crash the page on load.
 */
const browserStorage: SupportedStorage = {
  getItem(key) {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  },
  setItem(key, value) {
    try {
      globalThis.localStorage?.setItem(key, value);
    } catch {
      // Storage unavailable — the session lives for this tab only.
    }
  },
  removeItem(key) {
    try {
      globalThis.localStorage?.removeItem(key);
    } catch {
      // Nothing to clean up if it was never written.
    }
  },
};

export const sessionStorage: SupportedStorage =
  Platform.OS === 'web' ? browserStorage : chunkedSecureStore;
