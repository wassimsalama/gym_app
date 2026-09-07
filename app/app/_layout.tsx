import { Stack } from 'expo-router';
import { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { ActivityIndicator, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AppFrame } from '@/components/AppFrame';
import '@/global.css';
import { supabase, useAuth } from '@/lib/auth';
import { flushAfterAuthRefresh, startSync } from '@/lib/sync';

export default function RootLayout() {
  const { session, loading } = useAuth();

  useEffect(() => {
    // Flush triggers from §8.2: reconnect and foreground are handled inside
    // startSync; a token refresh is handled here because lib/auth cannot import
    // lib/sync without creating a cycle through the transport layer.
    const stopSync = startSync();
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (event === 'TOKEN_REFRESHED' || event === 'SIGNED_IN') {
        void flushAfterAuthRefresh();
      }
    });

    return () => {
      stopSync();
      data.subscription.unsubscribe();
    };
  }, []);

  // Hold the shell until the persisted session is read back from SecureStore,
  // otherwise the sign-in screen flashes on every cold start for a signed-in user.
  if (loading) {
    return (
      <View className="flex-1 items-center justify-center bg-ink">
        <ActivityIndicator color="#4ADE80" />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      {/*
        `Stack.Protected` is the gate in both directions: signing in makes the
        tabs reachable, and signing out navigates off them rather than leaving
        an authenticated screen mounted with a dead session.
      */}
      <AppFrame>
        <Stack screenOptions={{ headerShown: false }}>
          {/*
            Outside both guards on purpose. Clicking the emailed recovery link
            creates a session, so a screen gated on *not* having one would
            bounce the user away before they could set a password.
          */}
          <Stack.Screen name="reset-password" />
          <Stack.Screen name="forgot-password" />

          <Stack.Protected guard={!!session}>
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="onboarding" />
            <Stack.Screen name="settings" options={{ presentation: 'modal' }} />
          </Stack.Protected>

          <Stack.Protected guard={!session}>
            <Stack.Screen name="(auth)" />
          </Stack.Protected>
        </Stack>
      </AppFrame>
    </SafeAreaProvider>
  );
}
