import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Screen } from '@/components/Screen';
import { ApiError, API_URL, healthAuth, type AuthHealth } from '@/lib/api';
import { signOut, useAuth } from '@/lib/auth';

type Check =
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'ok'; result: AuthHealth }
  | { state: 'failed'; detail: string };

export default function Dashboard() {
  const { session } = useAuth();
  const [check, setCheck] = useState<Check>({ state: 'idle' });

  const runCheck = useCallback(async () => {
    setCheck({ state: 'checking' });
    try {
      setCheck({ state: 'ok', result: await healthAuth() });
    } catch (error) {
      const detail =
        error instanceof ApiError ? error.detail : 'Unexpected error contacting the API';
      setCheck({ state: 'failed', detail });
    }
  }, []);

  return (
    <Screen title="Dashboard" subtitle={session?.user.email ?? undefined}>
      <Card
        title="Backend connection"
        footnote={`Phase 0 acceptance: this device holds a Supabase session, the API verifies its JWT, and a profiles row exists. Talking to ${API_URL}.`}
      >
        {check.state === 'ok' ? (
          <View className="gap-1">
            <Text className="text-lg font-semibold text-accent">Authenticated</Text>
            <Text className="text-sm text-muted">user_id {check.result.user_id}</Text>
            <Text className="text-sm text-muted">display unit {check.result.unit}</Text>
          </View>
        ) : check.state === 'failed' ? (
          <Text className="text-base text-danger">{check.detail}</Text>
        ) : (
          <Text className="text-base text-muted">Not checked yet on this launch.</Text>
        )}

        <View className="mt-4">
          <Button
            title="Check connection"
            onPress={runCheck}
            loading={check.state === 'checking'}
          />
        </View>
      </Card>

      <Card title="What lands next" footnote="Roadmap §12.">
        <View className="gap-2">
          <Text className="text-sm text-muted">
            Phase 1 — weight entry, smoothed trend, goal progress.
          </Text>
          <Text className="text-sm text-muted">
            Phase 2 — workout logging with last-session prefill, PRs, offline queue.
          </Text>
          <Text className="text-sm text-muted">
            Phase 3 — nutrition, streaks, volume rings, TDEE.
          </Text>
          <Text className="text-sm text-muted">
            Phase 4 — photos, the suggestions engine, TestFlight.
          </Text>
        </View>
      </Card>

      <Button title="Sign out" variant="ghost" onPress={() => void signOut()} />
    </Screen>
  );
}
