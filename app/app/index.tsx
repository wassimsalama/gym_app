import { Redirect } from 'expo-router';

import { useAuth } from '@/lib/auth';

/** Entry point: hand off to the tabs or the sign-in screen. */
export default function Index() {
  const { session, loading } = useAuth();
  if (loading) return null;
  return <Redirect href={session ? '/(tabs)' : '/(auth)/sign-in'} />;
}
