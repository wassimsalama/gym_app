import { Redirect } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';

import { getActiveGoal } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Destination = '/(tabs)' | '/onboarding' | null;

/**
 * Entry point. Signed out -> sign in. Signed in with no goal -> onboarding,
 * so the app is never empty on day one (spec §2.6).
 */
export default function Index() {
  const { session, loading } = useAuth();
  const [destination, setDestination] = useState<Destination>(null);

  useEffect(() => {
    if (!session) return;

    let active = true;
    getActiveGoal()
      .then((goal) => {
        if (active) setDestination(goal ? '/(tabs)' : '/onboarding');
      })
      .catch(() => {
        // Offline or the API is down: send them to the tabs, which render
        // cached data and surface their own error, rather than trapping them
        // in onboarding they cannot complete.
        if (active) setDestination('/(tabs)');
      });

    return () => {
      active = false;
    };
  }, [session]);

  if (loading) return null;
  if (!session) return <Redirect href="/(auth)/sign-in" />;

  if (destination === null) {
    return (
      <View className="flex-1 items-center justify-center bg-ink">
        <ActivityIndicator color="#4ADE80" />
      </View>
    );
  }

  return <Redirect href={destination} />;
}
