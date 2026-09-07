import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { ProgressBar } from '@/components/ProgressBar';
import { WeightChart } from '@/components/WeightChart';
import { ApiError, getDashboard, type Dashboard } from '@/lib/api';
import { signOut, useAuth } from '@/lib/auth';
import { formatLong } from '@/lib/dates';
import { useUnit } from '@/lib/profile';
import { formatDelta, formatWeight } from '@/lib/units';

export default function DashboardScreen() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const { session } = useAuth();
  const unit = useUnit();

  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await getDashboard());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not load your dashboard');
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    getDashboard()
      .then((next) => {
        if (active) setData(next);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof ApiError ? err.detail : 'Could not load your dashboard');
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const weight = data?.weight;
  const goal = data?.goal ?? null;

  return (
    <View className="flex-1 bg-ink" style={{ paddingTop: insets.top }}>
      <View className="px-5 pb-3 pt-2">
        <Text className="text-2xl font-bold text-white">Dashboard</Text>
        <Text className="mt-1 text-sm text-muted">{session?.user.email ?? ''}</Text>
      </View>

      <ScrollView
        className="flex-1 px-5"
        contentContainerClassName="gap-4 pb-10"
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={load} tintColor="#8A97A6" />
        }
      >
        {loading ? (
          <View className="h-40 items-center justify-center">
            <ActivityIndicator color="#4ADE80" />
          </View>
        ) : error ? (
          <Card title="Offline">
            <Text className="text-base text-danger">{error}</Text>
            <View className="mt-4">
              <Button title="Retry" onPress={load} />
            </View>
          </Card>
        ) : (
          <>
            <Card title="Weight trend">
              <View className="mb-3 flex-row items-baseline gap-3">
                <Text className="text-3xl font-bold text-white">
                  {formatWeight(weight?.current_smoothed_kg, unit)}
                </Text>
                {weight?.delta_since_start_kg != null ? (
                  <Text
                    className={`text-base font-semibold ${
                      weight.delta_since_start_kg <= 0 ? 'text-accent' : 'text-muted'
                    }`}
                  >
                    {formatDelta(weight.delta_since_start_kg, unit)} since start
                  </Text>
                ) : null}
              </View>
              <WeightChart series={weight?.series ?? []} unit={unit} width={width - 72} />
            </Card>

            {goal ? (
              <Card title="Goal">
                <ProgressBar
                  pct={goal.progress_pct}
                  label="Progress"
                  caption={
                    goal.projected_date
                      ? `On this trend you reach it around ${formatLong(goal.projected_date)}.`
                      : 'Not enough of a trend yet to project a date.'
                  }
                />
                {goal.on_track !== null ? (
                  <Text
                    className={`mt-3 text-sm font-semibold ${
                      goal.on_track ? 'text-accent' : 'text-danger'
                    }`}
                  >
                    {goal.on_track
                      ? 'Ahead of your target date.'
                      : 'Behind your target date at this rate.'}
                  </Text>
                ) : null}
              </Card>
            ) : null}

            <Card title="What lands next" footnote="Roadmap §12.">
              <View className="gap-2">
                <Text className="text-sm text-muted">
                  Phase 2 — workout logging with last-set prefill, PRs, offline queue.
                </Text>
                <Text className="text-sm text-muted">
                  Phase 3 — nutrition, streaks, volume rings, TDEE.
                </Text>
                <Text className="text-sm text-muted">
                  Phase 4 — photos, the suggestions engine, TestFlight.
                </Text>
              </View>
            </Card>
          </>
        )}

        <Button title="Sign out" variant="ghost" onPress={() => void signOut()} />
      </ScrollView>
    </View>
  );
}
