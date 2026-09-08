import { createClient, type Session } from '@supabase/supabase-js';
import { useEffect, useState } from 'react';
import { AppState, Platform } from 'react-native';

import { sessionStorage } from '@/lib/sessionStorage';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'Missing EXPO_PUBLIC_SUPABASE_URL / EXPO_PUBLIC_SUPABASE_ANON_KEY. ' +
      'Copy app/.env.example to app/.env and fill them in.',
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    storage: sessionStorage,
    autoRefreshToken: true,
    persistSession: true,
    // On the web the confirmation and recovery links come back through the
    // URL and must be consumed; in a native app there is no URL to read.
    detectSessionInUrl: Platform.OS === 'web',
  },
});

// Refresh tokens only while the app is actually in front of the user.
// AppState reports "active" permanently on web, so the listener would be a
// no-op there; supabase-js handles browser visibility itself.
if (Platform.OS !== 'web') {
  AppState.addEventListener('change', (state) => {
    if (state === 'active') {
      void supabase.auth.startAutoRefresh();
    } else {
      void supabase.auth.stopAutoRefresh();
    }
  });
}

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
  return supabase.auth.signUp({
    email: email.trim(),
    password,
    // Without this the confirmation link goes to whatever Supabase's Site URL
    // happens to be. That is a single global value, so it is wrong for anyone
    // signing up from a different origin, and it was pointing at
    // http://localhost:3000 for the first weeks this was live — every account
    // created then got a confirmation link that led nowhere, and those users
    // cannot sign in at all, because an unconfirmed email is rejected.
    options: { emailRedirectTo: appUrl('/') },
  });
}

/**
 * Send the confirmation email again.
 *
 * Needed because an unconfirmed account is invisible from the outside: sign-in
 * fails with "Email not confirmed" and, with only a "Forgotten your password?"
 * link on screen, resetting the password looks like the fix. It is not — a
 * reset does not confirm the address, so the next sign-in fails the same way.
 */
export async function resendConfirmation(email: string) {
  return supabase.auth.resend({
    type: 'signup',
    email: email.trim(),
    options: { emailRedirectTo: appUrl('/') },
  });
}

export async function signOut() {
  return supabase.auth.signOut();
}

/**
 * Where an emailed link should land. Must be listed in Supabase's redirect
 * allow-list, and built from the origin actually being used rather than a
 * hardcoded host — the site answers on more than one.
 */
function appUrl(path: string): string | undefined {
  if (Platform.OS !== 'web') return process.env.EXPO_PUBLIC_RESET_URL;
  const origin = globalThis.location?.origin;
  return origin ? `${origin}${path}` : undefined;
}

/**
 * Send a reset link. Resolves the same way whether or not the address has an
 * account — telling a stranger which emails are registered is an account
 * enumeration hole, and Supabase deliberately does not distinguish.
 */
export async function requestPasswordReset(email: string) {
  return supabase.auth.resetPasswordForEmail(email.trim(), {
    redirectTo: appUrl('/reset-password'),
  });
}

/** Set a new password. Requires a live session — either signed in, or arrived
 * via a recovery link, which Supabase exchanges for a temporary one. */
export async function updatePassword(password: string) {
  return supabase.auth.updateUser({ password });
}
