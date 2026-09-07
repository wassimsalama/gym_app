import { createClient, type Session, type SupportedStorage } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';
import { useEffect, useState } from 'react';
import { AppState } from 'react-native';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'Missing EXPO_PUBLIC_SUPABASE_URL / EXPO_PUBLIC_SUPABASE_ANON_KEY. ' +
      'Copy app/.env.example to app/.env and fill them in.',
  );
}

/**
 * SecureStore refuses values much over 2 KB, and a Supabase session (access
 * token + refresh token + user object) regularly exceeds that. Split the value
 * across numbered chunks and keep a count under the base key.
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

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    storage: chunkedSecureStore,
    autoRefreshToken: true,
    persistSession: true,
    // There is no URL to read a session back from in a native app.
    detectSessionInUrl: false,
  },
});

// Refresh tokens only while the app is actually in front of the user.
AppState.addEventListener('change', (state) => {
  if (state === 'active') {
    void supabase.auth.startAutoRefresh();
  } else {
    void supabase.auth.stopAutoRefresh();
  }
});

export type AuthState = {
  session: Session | null;
  /** True until the persisted session has been read back from SecureStore. */
  loading: boolean;
};

/**
 * Reading the persisted session touches the keychain and may attempt a token
 * refresh. If that stalls, the app must still render — an unbounded wait here
 * is a white screen with no way out. Falling back to "signed out" is safe: the
 * onAuthStateChange listener below still promotes a real session if one
 * arrives late.
 */
const SESSION_READ_TIMEOUT_MS = 8_000;

/** Subscribe to the session. Drives the auth gate in app/_layout.tsx. */
export function useAuth(): AuthState {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const settle = (next: Session | null) => {
      if (!active) return;
      setSession(next);
      setLoading(false);
    };

    const timer = setTimeout(() => {
      if (!active) return;
      console.warn(
        `[auth] getSession() did not resolve within ${SESSION_READ_TIMEOUT_MS}ms — ` +
          'rendering as signed out.',
      );
      settle(null);
    }, SESSION_READ_TIMEOUT_MS);

    supabase.auth
      .getSession()
      .then(({ data }) => settle(data.session))
      .catch((error) => {
        console.warn('[auth] getSession() failed:', error);
        settle(null);
      })
      .finally(() => clearTimeout(timer));

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setLoading(false);
    });

    return () => {
      active = false;
      clearTimeout(timer);
      subscription.subscription.unsubscribe();
    };
  }, []);

  return { session, loading };
}

export async function signIn(email: string, password: string) {
  return supabase.auth.signInWithPassword({ email: email.trim(), password });
}

export async function signUp(email: string, password: string) {
  return supabase.auth.signUp({ email: email.trim(), password });
}

export async function signOut() {
  return supabase.auth.signOut();
}
